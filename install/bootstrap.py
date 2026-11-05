"""Private worker for Instalar-Strata.ps1. Standard library only; never starts a model."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

FORK = "daandradec/strata"
BRANCH = "strata-local-installation"
MODEL = "qwen3.8-flash-next-iq3_xxs"
REF = "strata/" + MODEL
GENERATED = ("strata-iq3_xxs.json", "run-iq3_xxs.bat")


class InstallError(Exception):
    pass


def regular_path(path):
    """Reject redirected ancestors before writing, including Windows junctions."""
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise InstallError("No se admiten enlaces/junctions en las rutas de instalacion.")
    return path


def paths(data, fork):
    data, fork = regular_path(data), regular_path(fork)
    if data == fork or data.parent != fork.parent or fork.name.lower() != "strata":
        raise InstallError("Strata y Strata-data deben ser carpetas hermanas diferentes.")
    if not data.is_dir() or not fork.is_dir():
        raise InstallError("Falta el clon de datos o el fork Strata.")
    return data, fork


def json_read(path, default=None):
    if not path.exists():
        return copy.deepcopy(default)
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as error:
        raise InstallError(f"JSON no valido: {path.name}; no se reemplazo.") from error
    if not isinstance(result, dict):
        raise InstallError(f"Se esperaba un objeto JSON en {path.name}.")
    return result


def atomic_bytes(path, value):
    path = regular_path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()  # one explicitly owned temporary file, never recursive


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recover_pending(data, fork, state, head):
    """Recover only files proven original or journaled, even after a hard kill."""
    journal = regular_path(state / "pending.json")
    if not journal.exists():
        return
    record = json_read(journal)
    if record.get("protocol") != 1 or record.get("fork_commit") != head or record.get("fork_dir") != str(fork.resolve()) or record.get("data_dir") != str(data.resolve()):
        raise InstallError("Hay una instalacion interrumpida de otra version/ruta. Sus respaldos se conservaron.")
    backup_name = record.get("backup", "")
    if not isinstance(backup_name, str) or not re.fullmatch(r"config-backup-[a-f0-9]{32}", backup_name):
        raise InstallError("El registro de recuperacion no es valido; no se modificaron archivos.")
    backup = regular_path(state / backup_name)
    originals, expected = record.get("before"), record.get("expected")
    if not isinstance(originals, dict) or set(originals) != set(GENERATED) or not isinstance(expected, dict) or not set(expected) <= set(GENERATED):
        raise InstallError("El registro de recuperacion esta incompleto; no se modificaron archivos.")
    completed = json_read(state / "installed.json", {})
    if completed.get("transaction") == backup_name and completed.get("fork_commit") == head:
        hashes = {name: digest(regular_path(fork / name)) if (fork / name).is_file() else None for name in GENERATED}
        if hashes == completed.get("generated") and hashes == expected:
            journal.unlink()  # success was committed; do not roll a completed install back
            return
    restore = []
    for name in GENERATED:
        target = regular_path(fork / name)
        original_hash = originals[name]
        content = None
        if original_hash is not None:
            original = regular_path(backup / name)
            if not original.is_file() or digest(original) != original_hash:
                raise InstallError("Un respaldo fue modificado; no se restauro automaticamente.")
            content = original.read_bytes()
        current = digest(target) if target.is_file() else None
        if current == original_hash:
            continue
        if name not in expected or current != expected[name]:
            raise InstallError("Hay cambios personales despues de una interrupcion. No se descartaron; revisa .install-state.")
        restore.append((target, content))
    # Validate every file before changing any; unknown concurrent user edits survive.
    for target, content in restore:
        if content is None:
            target.unlink()
        else:
            atomic_bytes(target, content)
    journal.unlink()


def native(command, cwd, state, label, capture=False):
    """Small JSON/Git queries may be captured; lengthy installer output goes to disk."""
    stdout, stderr = state / (label + ".stdout.log"), state / (label + ".stderr.log")
    options = dict(cwd=cwd, stdin=subprocess.DEVNULL,
                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    with stderr.open("wb") as errors:
        if capture:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=errors, **options)
            stdout.write_bytes(result.stdout)
        else:
            with stdout.open("wb") as output:
                result = subprocess.run(command, stdout=output, stderr=errors, **options)
    return result


def git(fork, *args):
    result = subprocess.run(["git", "-C", str(fork), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        raise InstallError("No se pudo comprobar el repositorio Strata; no se descarto ningun cambio.")
    return result.stdout.decode("utf-8").strip()


def origin_name(value):
    value = value.strip().lower().removesuffix("/").removesuffix(".git")
    for prefix in ("https://github.com/", "ssh://git@github.com/", "git@github.com:"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return ""


def source_status(fork):
    if Path(git(fork, "rev-parse", "--show-toplevel")).resolve() != fork.resolve():
        raise InstallError("Strata no es la raiz del repositorio esperado.")
    if origin_name(git(fork, "remote", "get-url", "origin")) != FORK:
        raise InstallError("La carpeta Strata no corresponde al fork daandradec/Strata.")
    if git(fork, "branch", "--show-current") != BRANCH:
        raise InstallError("El fork no esta en strata-local-installation; no se cambio su rama.")
    changed = git(fork, "diff", "--name-only", "HEAD").splitlines()
    if any(name not in GENERATED for name in changed):
        raise InstallError("Hay cambios locales de codigo en Strata. Guardalos antes de instalar.")
    # Never execute an untracked replacement for a trusted entry point.
    git(fork, "ls-files", "--error-unmatch", "setup.py", "START-HERE.bat", "tools/bootstrap_setup.py")
    tracked = set(git(fork, "ls-files", "--", *GENERATED).splitlines())
    return git(fork, "rev-parse", "HEAD"), changed, tracked


def value(args, flag):
    if args.count(flag) != 1:
        raise InstallError("La configuracion no coincide con el perfil automatico.")
    index = args.index(flag) + 1
    if index >= len(args) or args[index].startswith("--"):
        raise InstallError("Configuracion incompleta.")
    return args[index]


def asset(candidate, parent, directory=False):
    if not Path(candidate).is_absolute():
        raise InstallError("La configuracion debe usar rutas absolutas del equipo actual.")
    candidate, parent = regular_path(candidate), regular_path(parent)
    if not candidate.is_absolute() or not candidate.resolve().is_relative_to(parent.resolve()):
        raise InstallError("La configuracion contiene rutas de otra instalacion.")
    if directory:
        if not candidate.is_dir():
            raise InstallError("Faltan directorios del modelo.")
    elif not candidate.is_file() or candidate.stat().st_size == 0:
        raise InstallError("Faltan archivos del modelo/engine.")
    return candidate


def verify(data, fork):
    """Structural verification only: no inference or model process is launched."""
    cfg = json_read(fork / GENERATED[0])
    if not cfg or cfg.get("model_name") != MODEL or cfg.get("port") != 38181 or cfg.get("host") != "127.0.0.1":
        raise InstallError("La configuracion local no coincide con IQ3_XXS/128K/38181.")
    if any(cfg.get(key) for key in ("before_load", "mcp_servers", "api_key")):
        raise InstallError("Hay configuracion privada o hooks personalizados; no se modificaron.")
    if Path(cfg.get("cwd", "")).resolve() != fork.resolve():
        raise InstallError("La configuracion conserva rutas de otro computador.")
    args = cfg.get("args")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise InstallError("Argumentos del engine no validos.")
    if value(args, "--max-context") != "131072":
        raise InstallError("El contexto no es 131072.")
    asset(cfg.get("exe", ""), fork)
    asset(fork / ".venv/Scripts/python.exe", fork)
    batch = asset(fork / GENERATED[1], fork)
    if str(fork).lower() not in batch.read_text(encoding="utf-8-sig").lower():
        raise InstallError("El batch conserva rutas antiguas.")
    pack = asset(value(args, "--pack"), data, directory=True)
    if pack.resolve() != (data / "packs/iq3_xxs").resolve():
        raise InstallError("El pack pertenece a otro perfil.")
    for name in ("dense.bin", "index.txt", "native_experts.txt"):
        asset(pack / name, data)
    tokenizer = asset(cfg.get("tokenizer", ""), data, directory=True)
    if tokenizer.resolve() != (pack / "tokenizer").resolve():
        raise InstallError("El tokenizer pertenece a otro pack.")
    for name in ("vocab.json", "merges.txt", "token_type.json"):
        asset(tokenizer / name, data)
    mtp = asset(value(args, "--mtp"), data, directory=True)
    if mtp.resolve() != (data / "mtp/rt").resolve():
        raise InstallError("La capa MTP pertenece a otra instalacion.")
    asset(mtp / "experts.bin", data)
    # Reuse the installer's header/tensor-directory check, not a multi-GB rehash.
    spec = importlib.util.spec_from_file_location("strata_bootstrap_verifier", fork / "setup.py")
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    if Path(value(args, "--native")).resolve() == Path(value(args, "--ple-gguf")).resolve():
        raise InstallError("Los dos shards del perfil no pueden ser el mismo archivo.")
    for flag in ("--native", "--ple-gguf"):
        shard = asset(value(args, flag), data)
        if not setup.whole_shard(shard):
            raise InstallError("Un shard GGUF esta incompleto; repetir la instalacion para reanudarlo.")
    return cfg


def prepare(data, fork, runner=native, verifier=verify):
    data, fork = paths(data, fork)
    state = regular_path(data / ".install-state")
    state.mkdir(exist_ok=True)
    head, changed, tracked = source_status(fork)
    if (state / "pending.json").exists():
        recover_pending(data, fork, state, head)
        head, changed, tracked = source_status(fork)
    receipt_path = state / "installed.json"
    receipt = json_read(receipt_path, {})
    check = runner([sys.executable, str(fork / "setup.py"), "--bootstrap-check", "--data-dir", str(data)],
                   fork, state, "hardware", capture=True)
    try:
        report = json.loads(check.stdout)
    except (ValueError, TypeError) as error:
        raise InstallError("El fork no entrega un diagnostico bootstrap valido; consulta .install-state.") from error
    if not isinstance(report, dict):
        raise InstallError("El diagnostico bootstrap no es un objeto valido.")
    if type(report.get("protocol")) is not int or report["protocol"] != 1:
        raise InstallError("El protocolo del fork no es compatible con este instalador; no se instalo el modelo.")
    if report.get("transactional_config") is not True:
        raise InstallError("El fork no ofrece configuracion recuperable; no se instalo el modelo.")
    if check.returncode or report.get("ok") is not True:
        errors = report.get("errors", [])
        detail = "; ".join(errors) if isinstance(errors, list) and all(isinstance(e, str) for e in errors) else "Diagnostico incompatible."
        raise InstallError("Este equipo no supera la comprobacion segura: " + detail)
    try:
        verifier(data, fork)
        return {"status": "reused", "message": "La instalacion existente ya es valida. No se reinstalo."}
    except InstallError:
        pass
    existing = [name for name in GENERATED if (fork / name).is_file()]
    if receipt:
        owned = receipt.get("generated", {})
        customized = receipt.get("fork_commit") != head or not isinstance(owned, dict) or any(owned.get(name) != digest(fork / name) for name in existing)
    else:
        customized = any(name in changed or name not in tracked for name in existing)
    if customized:
        raise InstallError("Hay configuracion local personalizada. No se sobrescribio; revisala antes de reinstalar.")
    before = {name: (fork / name).read_bytes() if (fork / name).is_file() else None for name in GENERATED}
    backup = state / ("config-backup-" + uuid.uuid4().hex)
    backup.mkdir()
    for name, content in before.items():
        if content is not None:
            (backup / name).write_bytes(content)
    journal = state / "pending.json"
    atomic_bytes(journal, encoded({"protocol": 1, "fork_commit": head,
                                  "fork_dir": str(fork.resolve()), "data_dir": str(data.resolve()),
                                  "backup": backup.name, "before": {name: hashlib.sha256(content).hexdigest() if content is not None else None for name, content in before.items()},
                                  "expected": {}}))
    try:
        result = runner([sys.executable, str(fork / "setup.py"), "--bootstrap-install", "--data-dir", str(data)],
                        fork, state, "setup")
        if result.returncode:
            raise InstallError("El instalador fallo. Repite el mismo comando para reanudar; consulta .install-state/setup.stderr.log.")
        verifier(data, fork)
        atomic_bytes(receipt_path, encoded({"protocol": 1, "fork_commit": head, "transaction": backup.name,
                                            "generated": {name: digest(fork / name) for name in GENERATED}}))
        journal.unlink()
    except BaseException:
        recover_pending(data, fork, state, head)
        raise
    return {"status": "installed", "message": "Strata instalado y configurado. El modelo NO se inicio."}


def object_at(parent, key):
    result = parent.setdefault(key, {})
    if not isinstance(result, dict):
        raise InstallError("La configuracion de Gentle Shell tiene una estructura inesperada; no se reemplazo.")
    return result


def gentle(data, agent):
    data, agent = regular_path(data), regular_path(agent)
    if not agent.is_dir():
        return {"status": "absent", "message": "Gentle Shell no esta instalado; no se crearon ajustes."}
    settings_path, models_path = (regular_path(agent / name) for name in ("settings.json", "models.json"))
    settings, models = json_read(settings_path, {}), json_read(models_path, {})
    originals = {p: p.read_bytes() if p.exists() else None for p in (settings_path, models_path)}
    extension = str((data / "extensions/strata-compaction/index.ts").resolve()).replace("\\", "/")
    if not Path(extension).is_file():
        raise InstallError("Falta la extension de compactacion; no se cambiaron ajustes.")
    entries = settings.setdefault("extensions", [])
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
        raise InstallError("extensions no es una lista de rutas; no se cambiaron ajustes.")
    # Retarget only this known extension; registering old+new copies would attach
    # two compaction hooks. All unrelated extension entries retain their order.
    suffix = "/extensions/strata-compaction/index.ts"
    updated_entries, inserted = [], False
    for entry in entries:
        known = Path(entry).is_absolute() and entry.replace("\\", "/").lower().endswith(suffix)
        if known:
            if not inserted:
                updated_entries.append(extension)
                inserted = True
        else:
            updated_entries.append(entry)
    if not inserted:
        updated_entries.append(extension)
    settings["extensions"] = updated_entries
    override = object_at(object_at(object_at(settings, "compaction"), "modelOverrides"), REF)
    override["reserveTokens"] = 32768
    object_at(settings, "modelThinkingLevels")[REF] = "high"
    provider = object_at(object_at(models, "providers"), "strata")
    # Do not silently replace an existing private/remote provider or authentication.
    if provider.get("baseUrl") not in (None, "http://127.0.0.1:38181/v1"):
        raise InstallError("Ya existe un proveedor strata con otra URL; no se reemplazo.")
    if provider.get("apiKey") not in (None, "", "strata-local") or provider.get("headers"):
        raise InstallError("El proveedor strata tiene autenticacion personalizada; no se reemplazo.")
    if provider.get("api") not in (None, "openai-completions"):
        raise InstallError("El proveedor strata usa otra API; no se reemplazo.")
    provider.update(baseUrl="http://127.0.0.1:38181/v1", api="openai-completions", apiKey="strata-local")
    model_list = provider.setdefault("models", [])
    if not isinstance(model_list, list) or not all(isinstance(m, dict) for m in model_list):
        raise InstallError("La lista de modelos no es valida; no se cambiaron ajustes.")
    matches = [m for m in model_list if m.get("id") == MODEL]
    if len(matches) > 1:
        raise InstallError("Hay entradas duplicadas del modelo; no se cambiaron ajustes.")
    model = matches[0] if matches else {}
    if model.get("headers") or model.get("apiKey") or model.get("baseUrl") not in (None, "http://127.0.0.1:38181/v1") or model.get("api") not in (None, "openai-completions"):
        raise InstallError("El modelo tiene transporte/autenticacion personalizada; no se reemplazo.")
    model.update(id=MODEL, name="qwen3.8-flash-strata", reasoning=True, input=["text"],
                 contextWindow=131072, maxTokens=8192,
                 cost={"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0})
    if not matches:
        model_list.append(model)
    updated = {settings_path: encoded(settings), models_path: encoded(models)}
    if all(json.loads(originals[p]) == json.loads(updated[p]) for p in updated if originals[p] is not None) and all(originals[p] is not None for p in updated):
        return {"status": "unchanged", "message": "Gentle Shell ya estaba configurado."}
    # Backups inherit the agent directory's privacy, never the public data repository.
    backup = regular_path(agent / ".strata-install-backups")
    backup.mkdir(exist_ok=True)
    backup = backup / uuid.uuid4().hex
    backup.mkdir()
    for path, content in originals.items():
        if content is not None:
            (backup / path.name).write_bytes(content)
    written = []
    try:
        for path, content in updated.items():
            current = path.read_bytes() if path.exists() else None
            if current != originals[path]:
                raise InstallError("Gentle Shell cambio sus ajustes durante la instalacion; no se sobrescribieron.")
            atomic_bytes(path, content)
            written.append(path)
    except BaseException:
        for path in written:
            if path.read_bytes() == updated[path]:
                if originals[path] is None:
                    regular_path(path).unlink()
                else:
                    atomic_bytes(path, originals[path])
        raise
    return {"status": "configured", "message": "Gentle Shell configurado. Usa /reload o una sesion nueva.", "backup": str(backup)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "gentle"))
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--strata-dir")
    parser.add_argument("--agent-dir")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            if not args.strata_dir:
                raise InstallError("Falta --strata-dir.")
            result = prepare(Path(args.data_dir), Path(args.strata_dir))
        else:
            if not args.agent_dir:
                raise InstallError("Falta --agent-dir.")
            result = gentle(Path(args.data_dir), Path(args.agent_dir))
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (InstallError, OSError, ValueError) as error:
        # Never dump JSON documents, environment variables, credentials or tracebacks.
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
