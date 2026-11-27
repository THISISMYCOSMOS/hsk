"""Locate a merged checkout or the role's registered worktree without changing it."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLES = {"A": ("agent-a-data", "backend/app/market_data/provider.py"),
         "B": ("agent-b-engine", "backend/app/api/main.py"),
         "C": ("agent-c-contract", "contracts/src/Settlement.sol")}


def role(key, required=True):
    branch, marker = ROLES[key]
    override = os.environ.get(f"AGENT_{key}_ROOT")
    candidates = [Path(override)] if override else [ROOT]
    if not override:
        listing = subprocess.run(["git","worktree","list","--porcelain"],cwd=ROOT,capture_output=True,text=True)
        for record in listing.stdout.strip().split("\n\n"):
            lines = record.splitlines()
            if f"branch refs/heads/{branch}" in lines:
                candidates.append(Path(lines[0].removeprefix("worktree ")))
    for directory in candidates:
        if (directory / marker).is_file():
            return directory.resolve()
    if required:
        raise SystemExit(f"Agent {key} source missing: set AGENT_{key}_ROOT to the checkout containing {marker}")


def backend_python():
    return os.environ.get("AGENT_B_PYTHON",str(ROOT/".runtime/venv/bin/python"))
