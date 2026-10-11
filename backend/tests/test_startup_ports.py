import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell")
pytestmark = pytest.mark.skipif(os.name != "nt" or not POWERSHELL, reason="Windows launcher check")


@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0"])
def test_busy_api_port_is_reported_before_build_or_database_operations(address):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts/start_system.ps1"),
                "-SkipBuild",
                "-HostAddress",
                address,
                "-ApiPort",
                str(port),
            ],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env={**os.environ, "UV_CACHE_DIR": str(ROOT / "reports/startup-port-test-cache")},
        )
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "PORT_IN_USE" in output, output
        assert str(os.getpid()) in output
        assert str(port) in output
        assert "--connection-only" not in output and "MySQL schema" not in output
        assert "Started server process" not in output
        # Port preflight never terminates the owner, including unrelated services.
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass


def test_development_checks_frontend_port_before_starting_dependencies():
    with socket.socket() as listener, socket.socket() as reserved:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        reserved.bind(("127.0.0.1", 0))
        api_port, frontend_port = reserved.getsockname()[1], listener.getsockname()[1]
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts/start_system.ps1"),
                "-Mode",
                "Development",
                "-ApiPort",
                str(api_port),
                "-FrontendPort",
                str(frontend_port),
            ],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "PORT_IN_USE" in output and "Frontend port" in output
        assert str(frontend_port) in output and "MySQL" not in output


def test_free_port_passes_the_guard():
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    script = (ROOT / "scripts/startup_ports.ps1").as_posix().replace("'", "''")
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"$ErrorActionPreference='Stop'; . '{script}'; "
            f"Assert-StartupPortAvailable -Address 127.0.0.1 -Port {port} -Service API; 'AVAILABLE'",
        ],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AVAILABLE" in result.stdout
