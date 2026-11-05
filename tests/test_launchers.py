"""Exercise existing launchers with mock APIs only, never the installed model."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


def quote(path):
    return "'" + str(path).replace("'", "''") + "'"


@contextmanager
def mock_api(service="strata", context=131072):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(dict(status="ok", service=service, loaded=True,
                                   max_context=context)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@unittest.skipUnless(os.name == "nt", "Windows PowerShell launchers")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.parent = (ROOT / ".launcher-tests").resolve()
        self.parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="repo-launcher-", dir=self.parent)
        self.fixture = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup)
        self.root = self.fixture / "Strata"
        self.root.mkdir()
        self.data = self.fixture / "Strata-data"
        self.data.mkdir()
        python = self.root / ".venv/Scripts/python.exe"
        python.parent.mkdir(parents=True)
        # The tests must reject/reuse before this invalid executable can run.
        python.touch()
        (self.root / "run-iq3_xxs.bat").write_text("@exit /b 97\n")
        self.config = self.root / "strata-iq3_xxs.json"

    def cleanup(self):
        # Validate the resolved target before TemporaryDirectory recursively removes it.
        if self.fixture.parent != self.parent or not self.fixture.name.startswith("repo-launcher-"):
            raise RuntimeError("Unexpected launcher fixture path")
        self.temp.cleanup()

    def configure(self, port):
        self.config.write_text(json.dumps(dict(port=port, args=["--max-context", "131072"])))
        self.before = self.config.read_bytes()

    def invoke(self, *options, main=False, sibling_layout=False):
        name = "start_model_qwen.ps1" if main else "start_web_strata.ps1"
        script_root = self.data if sibling_layout else ROOT
        if sibling_layout:
            shutil.copyfile(ROOT / name, self.data / name)
        command = "& " + quote(script_root / name)
        if not sibling_layout:
            command += " -StrataRoot " + quote(self.root)
        command += " " + " ".join(options)
        command = "try { " + command + " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
        return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                               "-ExecutionPolicy", "Bypass", "-Command", command],
                              capture_output=True, text=True, timeout=20,
                              creationflags=subprocess.CREATE_NO_WINDOW)

    def unchanged(self):
        self.assertEqual(self.config.read_bytes(), self.before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         [".venv", "run-iq3_xxs.bat", "strata-iq3_xxs.json"])

    def reused(self, result, port):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn(f"Strata ya esta activo: http://127.0.0.1:{port}", result.stdout)
        self.unchanged()

    def rejected(self, result, message):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr.strip(), message)
        self.assertEqual(result.stdout, "")
        self.unchanged()

    def test_configured_high_port_reuses_existing_mock_server(self):
        with mock_api() as port:
            self.assertGreater(port, 8099)
            self.configure(port)
            self.reused(self.invoke("-NoBrowser"), port)

    def test_relocated_web_finds_sibling_strata_without_absolute_root(self):
        with mock_api() as port:
            self.configure(port)
            self.reused(self.invoke("-NoBrowser", sibling_layout=True), port)

    def test_relocated_main_finds_sibling_strata_without_absolute_root(self):
        with mock_api() as port:
            self.configure(port)
            self.rejected(self.invoke(main=True, sibling_layout=True),
                          "El puerto configurado ya esta ocupado. Este script no detiene servidores ajenos. "
                          "Para abrir Strata existente, usa start_web_strata.ps1.")

    def test_configured_port_respects_explicit_maximum(self):
        with mock_api() as port:
            self.configure(port)
            self.rejected(self.invoke("-NoBrowser", "-MaxPort 1024"),
                          "MaxPort debe ser igual o mayor que PreferredPort.")

    def test_explicit_high_range_is_preserved(self):
        with mock_api() as port:
            self.configure(port)
            self.reused(self.invoke("-NoBrowser", f"-PreferredPort {port}", f"-MaxPort {port}"), port)

    def test_invalid_explicit_range_is_rejected(self):
        self.configure(38181)
        self.rejected(self.invoke("-NoBrowser", "-PreferredPort 12000", "-MaxPort 11999"),
                      "MaxPort debe ser igual o mayor que PreferredPort.")

    def test_foreign_service_is_not_reused_or_stopped(self):
        with mock_api(service="not-strata") as port:
            self.configure(port)
            self.rejected(self.invoke("-NoBrowser"), f"No hay un puerto libre entre {port} y {port}.")
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

    def test_main_rejects_an_occupied_configured_port(self):
        with mock_api() as port:
            self.configure(port)
            self.rejected(self.invoke(main=True),
                          "El puerto configurado ya esta ocupado. Este script no detiene servidores ajenos. "
                          "Para abrir Strata existente, usa start_web_strata.ps1.")

    def test_wrong_context_is_not_reused_or_reconfigured(self):
        with mock_api(context=32768) as port:
            self.configure(port)
            self.rejected(self.invoke("-NoBrowser"),
                          "Strata ya esta activo con otro contexto. Cierra la consola que lo inicio y vuelve "
                          "a ejecutar este script para iniciar con 131072 tokens.")


if __name__ == "__main__":
    unittest.main()
