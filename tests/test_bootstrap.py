"""Bootstrap simulations only: temporary repos/configs, no network/GPU/model setup."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("data_bootstrap", ROOT / "install/bootstrap.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BootstrapWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="data-bootstrap-test-")
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup)
        self.data, self.fork, self.agent = (self.base / name for name in ("Strata-data", "Strata", "agent"))
        for path in (self.data, self.fork, self.agent):
            path.mkdir()
        ext = self.data / "extensions/strata-compaction/index.ts"
        ext.parent.mkdir(parents=True)
        ext.write_text("synthetic extension")
        self.cfg = self.fork / b.GENERATED[0]
        self.batch = self.fork / b.GENERATED[1]
        self.cfg.write_bytes(b'{"template":"old E:/Strata path"}')
        self.batch.write_bytes(b"old template")
        self.ready = False
        self.calls = []
        self.source = mock.patch.object(b, "source_status", return_value=("synthetic-commit", [], set(b.GENERATED)))
        self.source.start()
        self.addCleanup(self.source.stop)

    def cleanup(self):
        if not self.base.name.startswith("data-bootstrap-test-"):
            raise RuntimeError("Unexpected cleanup path")
        self.temp.cleanup()

    def verifier(self, data, fork):
        if not self.ready:
            raise b.InstallError("synthetic incomplete install")
        return {}

    def runner(self, command, cwd, state, label, capture=False):
        self.calls.append(command)
        if "--bootstrap-check" in command:
            return subprocess.CompletedProcess(command, 0, json.dumps({"protocol": 1, "transactional_config": True, "ok": True, "errors": []}).encode())
        self.recorded_write(self.cfg, b'{"generated":"new local paths"}')
        self.recorded_write(self.batch, b"new local batch")
        self.ready = True
        return subprocess.CompletedProcess(command, 0)

    def recorded_write(self, path, content):
        journal = self.data / ".install-state/pending.json"
        record = b.json_read(journal)
        record["expected"][path.name] = b.hashlib.sha256(content).hexdigest()
        b.atomic_bytes(journal, b.encoded(record))
        b.atomic_bytes(path, content)

    def pending(self):
        state = self.data / ".install-state"
        state.mkdir(exist_ok=True)
        backup = state / ("config-backup-" + "a" * 32)
        backup.mkdir()
        before = {}
        for path in (self.cfg, self.batch):
            content = path.read_bytes()
            (backup / path.name).write_bytes(content)
            before[path.name] = b.digest(path)
        b.atomic_bytes(state / "pending.json", b.encoded(dict(protocol=1,fork_commit="synthetic-commit",
                       fork_dir=str(self.fork.resolve()),data_dir=str(self.data.resolve()),
                       backup=backup.name,before=before,expected={})))
        return state

    def prepare(self, runner=None, verifier=None):
        return b.prepare(self.data, self.fork, runner=runner or self.runner, verifier=verifier or self.verifier)

    def test_clean_data_first_install_uses_fork_modes_and_never_starts(self):
        self.assertEqual(self.prepare()["status"], "installed")
        self.assertEqual(len(self.calls), 2)
        self.assertIn("--bootstrap-install", self.calls[1])
        self.assertEqual(self.calls[1][-1], str(self.data))
        self.assertNotIn("--yes", self.calls[1])
        self.assertTrue((self.data / ".install-state/installed.json").is_file())

    def test_second_run_reuses_without_another_install(self):
        self.prepare()
        self.calls.clear()
        self.assertEqual(self.prepare()["status"], "reused")
        self.assertEqual(len(self.calls), 1)

    def test_bad_hardware_stops_before_install_and_preserves_files(self):
        before = self.cfg.read_bytes()
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 1, b'{"protocol":1,"transactional_config":true,"ok":false,"errors":["RAM"]}'))
        with self.assertRaisesRegex(b.InstallError, "RAM"):
            self.prepare(runner=runner)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(self.cfg.read_bytes(), before)

    def test_setup_failure_restores_original_config_and_does_not_record_success(self):
        before = {p: p.read_bytes() for p in (self.cfg, self.batch)}
        def fail(*args, **kwargs):
            result = self.runner(*args, **kwargs)
            if "--bootstrap-install" in args[0]:
                result.returncode = 7
            return result
        with self.assertRaises(b.InstallError):
            self.prepare(runner=fail)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertFalse((self.data / ".install-state/installed.json").exists())

    def test_success_exit_without_assets_is_not_success(self):
        def invalid(*args, **kwargs):
            result = self.runner(*args, **kwargs)
            self.ready = False
            return result
        with self.assertRaises(b.InstallError):
            self.prepare(runner=invalid)
        self.assertFalse((self.data / ".install-state/installed.json").exists())

    def test_user_config_changes_are_not_overwritten_for_repair(self):
        self.prepare()
        self.ready = False
        self.cfg.write_bytes(b'{"user":"changed after install"}')
        b.source_status.return_value = ("synthetic-commit", [self.cfg.name], set(b.GENERATED))
        self.calls.clear()
        with self.assertRaisesRegex(b.InstallError, "personalizada"):
            self.prepare()
        self.assertEqual(len(self.calls), 1)
        self.assertIn(b"changed after install", self.cfg.read_bytes())

    def test_owned_config_can_be_repaired_after_missing_asset(self):
        self.prepare()
        self.ready = False
        b.source_status.return_value = ("synthetic-commit", [self.cfg.name, self.batch.name], set(b.GENERATED))
        self.assertEqual(self.prepare()["status"], "installed")

    def test_invalid_diagnostic_is_not_success(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, b'not json'))
        with self.assertRaises(b.InstallError):
            self.prepare(runner=runner)
        self.assertEqual(runner.call_count, 1)

    def test_hard_interruption_recovers_journaled_config_and_resumes(self):
        state = self.pending()
        cached = self.data / "cached-download.part"
        cached.write_bytes(b"keep resumable bytes")
        self.recorded_write(self.cfg, b'{"half":"first generated file was replaced"}')
        self.assertEqual(self.prepare()["status"], "installed")
        self.assertFalse((state / "pending.json").exists())
        self.assertEqual(cached.read_bytes(), b"keep resumable bytes")

    def test_user_edit_after_hard_interruption_is_not_discarded(self):
        self.pending()
        self.recorded_write(self.cfg, b'{"generated":"before kill"}')
        self.cfg.write_bytes(b'{"user":"edited after kill"}')
        with self.assertRaisesRegex(b.InstallError, "personales"):
            self.prepare()
        self.assertEqual(self.cfg.read_bytes(), b'{"user":"edited after kill"}')
        self.assertEqual(self.calls, [])

    def test_completed_receipt_is_not_rolled_back_if_journal_cleanup_was_interrupted(self):
        state = self.pending()
        self.recorded_write(self.cfg, b'{"generated":"completed config"}')
        self.recorded_write(self.batch, b"completed batch")
        record = b.json_read(state / "pending.json")
        b.atomic_bytes(state / "installed.json", b.encoded(dict(protocol=1,fork_commit="synthetic-commit",
                       transaction=record["backup"],generated=record["expected"])))
        self.ready = True
        self.assertEqual(self.prepare()["status"], "reused")
        self.assertEqual(self.cfg.read_bytes(), b'{"generated":"completed config"}')
        self.assertFalse((state / "pending.json").exists())

    def test_ignored_generated_user_config_is_protected_by_receipt_not_only_git(self):
        self.prepare()
        self.ready = False
        b.source_status.return_value = ("synthetic-commit", [], set())
        self.cfg.write_bytes(b'{"user":"untracked personalization"}')
        with self.assertRaises(b.InstallError):
            self.prepare()
        self.assertIn(b"untracked personalization", self.cfg.read_bytes())

    def test_unowned_ignored_config_is_not_replaced(self):
        b.source_status.return_value = ("synthetic-commit", [], set())
        with self.assertRaises(b.InstallError):
            self.prepare()
        self.assertEqual(len(self.calls), 1)

    def test_concurrent_gentle_edit_is_not_overwritten(self):
        for name in ("settings.json", "models.json"):
            (self.agent / name).write_bytes(b"{}")
        original = b.atomic_bytes
        def race(path, content):
            original(path, content)
            if path.name == "settings.json" and content != b"{}":
                (self.agent / "models.json").write_bytes(b'{"user":"concurrent edit"}')
        with mock.patch.object(b, "atomic_bytes", side_effect=race), self.assertRaises(b.InstallError):
            b.gentle(self.data, self.agent)
        self.assertEqual((self.agent / "settings.json").read_bytes(), b"{}")
        self.assertEqual((self.agent / "models.json").read_bytes(), b'{"user":"concurrent edit"}')

    def test_old_strata_extension_is_retargeted_not_registered_twice(self):
        old = str(self.base / "old-data/extensions/strata-compaction/index.ts")
        (self.agent / "settings.json").write_text(json.dumps({"extensions": ["other.ts", old, old]}))
        b.gentle(self.data, self.agent)
        entries = json.loads((self.agent / "settings.json").read_text())["extensions"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0], "other.ts")
        self.assertEqual(entries[1], str((self.data / "extensions/strata-compaction/index.ts").resolve()).replace("\\", "/"))

    def test_relative_asset_paths_are_not_accepted(self):
        with self.assertRaises(b.InstallError):
            b.asset("relative.bin", self.data)

    def test_gentle_merge_preserves_other_models_settings_and_auth_files(self):
        settings = {"defaultThinkingLevel": "medium", "extensions": ["unrelated.ts"],
                    "compaction": {"keepRecentTokens": 123, "modelOverrides": {"other/model": {"reserveTokens": 1}}}}
        models = {"providers": {"other": {"models": [{"id": "other"}]}}}
        (self.agent / "settings.json").write_text(json.dumps(settings))
        (self.agent / "models.json").write_text(json.dumps(models))
        (self.agent / "auth.json").write_bytes(b"synthetic auth sentinel")
        first = b.gentle(self.data, self.agent)
        self.assertEqual(first["status"], "configured")
        after = json.loads((self.agent / "settings.json").read_text())
        self.assertEqual(after["defaultThinkingLevel"], "medium")
        self.assertEqual(after["compaction"]["keepRecentTokens"], 123)
        self.assertEqual(after["compaction"]["modelOverrides"]["other/model"], {"reserveTokens": 1})
        self.assertEqual(after["modelThinkingLevels"][b.REF], "high")
        self.assertEqual((self.agent / "auth.json").read_bytes(), b"synthetic auth sentinel")
        self.assertTrue(Path(first["backup"]).is_relative_to(self.agent))
        self.assertEqual(b.gentle(self.data, self.agent)["status"], "unchanged")

    def test_remote_or_authenticated_strata_provider_is_not_replaced(self):
        for provider in ({"baseUrl": "https://remote.invalid/v1"}, {"apiKey": "synthetic-custom-auth"}):
            with self.subTest(provider=provider):
                original = json.dumps({"providers": {"strata": provider}}).encode()
                (self.agent / "models.json").write_bytes(original)
                with self.assertRaises(b.InstallError):
                    b.gentle(self.data, self.agent)
                self.assertEqual((self.agent / "models.json").read_bytes(), original)
                self.assertFalse((self.agent / "settings.json").exists())

    def test_invalid_json_is_preserved(self):
        (self.agent / "settings.json").write_bytes(b"{broken")
        with self.assertRaises(b.InstallError):
            b.gentle(self.data, self.agent)
        self.assertEqual((self.agent / "settings.json").read_bytes(), b"{broken")

    def test_missing_gentle_does_not_create_an_application_profile(self):
        absent = self.base / "not-installed"
        self.assertEqual(b.gentle(self.data, absent)["status"], "absent")
        self.assertFalse(absent.exists())

    def test_failed_second_settings_write_rolls_back_first(self):
        for name in ("settings.json", "models.json"):
            (self.agent / name).write_bytes(b"{}")
        original = b.atomic_bytes
        def write(path, content):
            if path.name == "models.json":
                raise OSError("synthetic write failure")
            return original(path, content)
        with mock.patch.object(b, "atomic_bytes", side_effect=write), self.assertRaises(OSError):
            b.gentle(self.data, self.agent)
        for name in ("settings.json", "models.json"):
            self.assertEqual((self.agent / name).read_bytes(), b"{}")


@unittest.skipUnless(os.name == "nt", "Windows process containment")
class PowerShellBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ps-bootstrap-test-")
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup)
        self.data = self.base / "data with spaces"
        (self.data / "install").mkdir(parents=True)
        self.state = self.data / ".install-state"
        self.state.mkdir()

    def cleanup(self):
        if not self.base.name.startswith("ps-bootstrap-test-"):
            raise RuntimeError("Unexpected cleanup path")
        self.temp.cleanup()

    @staticmethod
    def q(path):
        return "'" + str(path).replace("'", "''") + "'"

    def powershell(self, code, support=False):
        command = "$ErrorActionPreference='Stop'; . " + self.q(ROOT / "install/Instalar-Strata.ps1") + " -FunctionsOnly; "
        if support:
            command += ". " + self.q(ROOT / "start_model_qwen.ps1") + " -FunctionsOnly; "
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command + code],
                                capture_output=True, text=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def test_install_subdirectory_resolves_the_correct_data_root(self):
        output = self.powershell("Get-InstallPaths " + self.q(self.data / "install") + " | ConvertTo-Json -Compress")
        result = json.loads(output)
        self.assertEqual(Path(result["Data"]), self.data)
        self.assertEqual(Path(result["Fork"]), self.base / "Strata")

    def test_cmd_metacharacters_are_refused_before_commands(self):
        output = self.powershell("try { Assert-InstallPath 'C:\\unsafe%path'; throw 'accepted' } catch { if ($_.Exception.Message -eq 'accepted') { throw }; 'refused' }")
        self.assertEqual(output, "refused")

    def test_owned_process_propagates_failure_and_handles_spaces(self):
        code = "Invoke-InstallCommand " + self.q(sys.executable) + " @('-c','import sys;print(123);sys.exit(7)') " + self.q(self.data) + " " + self.q(self.state) + " | ConvertTo-Json -Compress"
        result = json.loads(self.powershell(code, support=True))
        self.assertEqual(result["Code"], 7)
        self.assertEqual(result["Text"], "123")

    def test_double_click_wrapper_resolves_its_ps_in_a_path_with_spaces(self):
        for name in ("Instalar.bat", "Instalar-Strata.ps1"):
            shutil.copyfile(ROOT / "install" / name, self.data / "install" / name)
        code = "Invoke-InstallCommand " + self.q(self.data / "install/Instalar.bat") + " @('-FunctionsOnly') " + self.q(self.data) + " " + self.q(self.state) + " | ConvertTo-Json -Compress"
        result = json.loads(self.powershell(code, support=True))
        self.assertEqual(result["Code"], 0)

    def test_foreign_repo_is_refused_without_mutating_it(self):
        code = "function Invoke-InstallGit { param($Git,$Root,$GitArguments,$State); if ($GitArguments[0] -eq 'rev-parse') { return [pscustomobject]@{Text=$Root} }; return [pscustomobject]@{Text='https://github.com/other/repo.git'} }; try { Assert-InstallRepository 'mock' " + self.q(self.data) + " " + self.q(self.state) + "; throw 'accepted' } catch { if ($_.Exception.Message -eq 'accepted') { throw }; 'refused' }"
        self.assertEqual(self.powershell(code), "refused")

    def test_data_first_clone_uses_confirmed_fork_branch_and_atomic_destination(self):
        fork = self.base / "Strata"
        code = r"""
function Invoke-InstallCommand {
    param($Executable,$Arguments,$Directory,$State)
    if ($Arguments[0] -ne 'clone' -or $Arguments[2] -ne 'strata-local-installation' -or
        $Arguments[4] -ne 'https://github.com/daandradec/Strata.git') { throw 'wrong clone' }
    $target = $Arguments[5]
    New-Item -ItemType Directory -Path (Join-Path $target 'tools') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $target 'tools\bootstrap_setup.py'),'mock protocol')
    return [pscustomobject]@{Code=0; Text=''; ErrorLog='mock'}
}
function Invoke-InstallGit {
    param($Git,$Root,$GitArguments,$State,$AllowFailure)
    $text = switch ($GitArguments[0]) {
        'rev-parse' { $Root }
        'remote' { 'https://github.com/daandradec/Strata.git' }
        'branch' { 'strata-local-installation' }
        default { '' }
    }
    return [pscustomobject]@{Code=0; Text=$text}
}
"""
        code += "Ensure-InstallFork 'mock-git' " + self.q(fork) + " " + self.q(self.state) + "; 'cloned'"
        self.assertEqual(self.powershell(code), "cloned")
        self.assertTrue((fork / "tools/bootstrap_setup.py").is_file())

    def test_complete_entry_in_disposable_repo_installs_once_without_real_setup(self):
        # A real temporary Git checkout and private Python exercise the whole PS ->
        # worker -> CLI protocol. The setup implementation itself is deliberately a
        # tiny fake: all assets are bytes in this fixture, never GPU/model packages.
        fork = self.base / "Strata"
        fork.mkdir()
        (fork / "tools").mkdir()
        (fork / "tools/bootstrap_setup.py").write_text("PROTOCOL = 1\n")
        (fork / "START-HERE.bat").write_text("@exit /b 99\n")
        (fork / ".gitignore").write_text(".venv/\nengine/\n__pycache__/\nstrata-*.json\nrun-*.bat\n")
        source = '''
import json,sys
from pathlib import Path
def whole_shard(path):
    return Path(path).read_bytes().startswith(b'GGUF')
def main():
    root=Path(__file__).resolve().parent
    data=Path(sys.argv[sys.argv.index('--data-dir')+1])
    if '--bootstrap-check' in sys.argv:
        print(json.dumps(dict(protocol=1,transactional_config=True,ok=True,errors=[])));return
    assert '--bootstrap-install' in sys.argv
    count=root/'install-calls.txt'
    count.write_text(str(int(count.read_text())+1) if count.exists() else '1')
    pack=data/'packs/iq3_xxs'; tok=pack/'tokenizer'; tok.mkdir(parents=True,exist_ok=True)
    for name in ('dense.bin','index.txt','native_experts.txt'):(pack/name).write_bytes(b'x')
    for name in ('vocab.json','merges.txt','token_type.json'):(tok/name).write_bytes(b'x')
    mtp=data/'mtp/rt';mtp.mkdir(parents=True,exist_ok=True);(mtp/'experts.bin').write_bytes(b'x')
    models=data/'models/IQ3_XXS';models.mkdir(parents=True,exist_ok=True)
    first=models/'first.gguf';second=models/'second.gguf'
    first.write_bytes(b'GGUFsynthetic');second.write_bytes(b'GGUFsynthetic')
    engine=root/'engine/strata.exe';engine.parent.mkdir(exist_ok=True);engine.write_bytes(b'fake engine')
    cfg=dict(model_name='qwen3.8-flash-next-iq3_xxs',port=38181,host='127.0.0.1',cwd=str(root),
             exe=str(engine),tokenizer=str(tok),args=['--max-context','131072','--pack',str(pack),
             '--native',str(first),'--ple-gguf',str(second),'--mtp',str(mtp)])
    import hashlib,os
    journal=data/'.install-state/pending.json'
    record=json.loads(journal.read_text())
    for path,content in ((root/'strata-iq3_xxs.json',json.dumps(cfg).encode()),
                         (root/'run-iq3_xxs.bat',('fake batch '+str(root)).encode())):
        record['expected'][path.name]=hashlib.sha256(content).hexdigest()
        journal.write_text(json.dumps(record))
        path.write_bytes(content)
if __name__=='__main__':main()
'''
        (fork / "setup.py").write_text(source)
        def git(*args):
            subprocess.run(["git", "-C", str(fork), *args], check=True, capture_output=True)
        git("init", "--quiet", "--initial-branch=strata-local-installation")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture")
        git("remote", "add", "origin", "https://github.com/daandradec/Strata.git")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(fork / ".venv")], check=True, capture_output=True)
        for name in ("Instalar-Strata.ps1", "bootstrap.py"):
            shutil.copyfile(ROOT / "install" / name, self.data / "install" / name)
        shutil.copyfile(ROOT / "start_model_qwen.ps1", self.data / "start_model_qwen.ps1")
        ext = self.data / "extensions/strata-compaction/index.ts"
        ext.parent.mkdir(parents=True)
        ext.write_text("synthetic extension")
        for attempt in range(2):
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                                     str(self.data / "install/Instalar-Strata.ps1"), "-SinGentleShell"],
                                    capture_output=True, text=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            details = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in self.state.glob("*.log")) if result.returncode else ""
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr + details)
            self.assertIn("Listo.", result.stdout)
        self.assertEqual((fork / "install-calls.txt").read_text(), "1")
        self.assertTrue((self.state / "installed.json").is_file())


if __name__ == "__main__":
    unittest.main()
