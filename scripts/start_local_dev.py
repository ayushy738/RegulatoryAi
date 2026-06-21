from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
API_DIR = ROOT / "apps" / "api"
API_PYTHON = API_DIR / ".venv" / "Scripts" / "python.exe"


def start_process(
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    LOG_DIR.mkdir(exist_ok=True)
    stdout = (LOG_DIR / f"{name}.out.log").open("ab")
    stderr = (LOG_DIR / f"{name}.err.log").open("ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
    )


def main() -> None:
    base_env = os.environ.copy()
    web_env = base_env.copy()
    web_env["XDG_CONFIG_HOME"] = str(ROOT / ".wrangler-config")

    api_python = str(API_PYTHON if API_PYTHON.exists() else "python")
    api = start_process(
        "api-8001",
        [
            api_python,
            "-m",
            "uvicorn",
            "backend.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
        ],
        API_DIR,
        base_env,
    )
    web = start_process(
        "web-3000",
        [
            "npm.cmd" if os.name == "nt" else "npm",
            "run",
            "dev",
            "--workspace",
            "@regulatory-ai/web",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            "3000",
        ],
        ROOT,
        web_env,
    )

    print(f"API started on http://127.0.0.1:8001 (pid {api.pid})")
    print(f"Web started on http://127.0.0.1:3000 (pid {web.pid})")
    print(f"Logs: {LOG_DIR}")


if __name__ == "__main__":
    main()
