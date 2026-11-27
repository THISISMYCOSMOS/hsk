"""Re-run upstream Python suites and archived mock settlement in disposable directories."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile
from backtest.collect import ROOT, save


def audit():
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "backtests").glob("*.zip"))
    }
    results = {}
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)

        def run(label, cmd, cwd):
            result = subprocess.run(
                cmd,
                cwd=cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                timeout=180,
            )
            results[label] = dict(
                exit_code=result.returncode,
                command=[Path(cmd[0]).name, *cmd[1:]],
                output=result.stdout[-4600:],
            )

        def extract(name, dest):
            with ZipFile(ROOT / "backtests" / name) as z:
                z.extractall(dest)

        extract("HSK_B_Session1_Verified.zip", work / "B")
        run("B_replay", [sys.executable, "verify.py"], work / "B")
        extract("HSK_A_Session1.zip", work)
        a = work / "HSK_A_Session1"
        run("A_routes", [sys.executable, "-m", "unittest", "discover", "-v"], a)
        exe = shutil.which("forge") or str(Path.home() / ".foundry/bin/forge")
        run("A_mock_settlement", [exe, "test", "--offline", "-vv"], a)
        extract("HSK_A_Session2_Check(2).zip", work / "A2")
        for src in (work / "A2/fixtures/plans").glob("*.json"):
            shutil.copyfile(src, a / "fixtures/plans" / src.name)
        run(
            "A2_mock_settlement",
            [
                exe,
                "test",
                "--offline",
                "--match-test",
                "test(Direct|NoGain|TooCostly)\\(",
                "-vv",
            ],
            a,
        )
        extract("HSK_Session2_Quotes.zip", work / "Q")
        run("archived_exact_math", [sys.executable, "quotes.py"], work / "Q")
    save(
        ROOT / "reports/economics/archive_audit.json",
        dict(zip_sha256=hashes, runs=results),
    )
    print({k: (v["exit_code"], v["output"][-160:]) for k, v in results.items()})


if __name__ == "__main__":
    audit()
