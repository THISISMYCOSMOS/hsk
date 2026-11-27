"""Re-run role-owned suites in disposable build directories."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from paths import role,backend_python

with tempfile.TemporaryDirectory() as tmp:
    stage=Path(tmp)
    shutil.copytree(role("C")/"contracts",stage/"contracts",ignore=shutil.ignore_patterns("out","cache","broadcast"))
    forge=shutil.which("forge") or str(Path.home()/".foundry/bin/forge")
    if "--fork" in sys.argv:
        subprocess.run([forge,"test","--fork-url",os.getenv("HSK_FORK_RPC","https://mainnet.hsk.xyz"),
                        "--fork-block-number","30592078","--match-test","testFork(RequoteAndConditionalFallback|LiquidityUpdate)"],
                       env={**os.environ,"HSK_FORK_TEST":"true"},cwd=stage/"contracts",check=True)
    else:
        subprocess.run([forge,"test","--offline","--no-match-contract","ForkTest"],cwd=stage/"contracts",check=True)
        shutil.copytree(role("B")/"backend",stage/"backend",ignore=shutil.ignore_patterns("__pycache__",".pytest_cache"))
        subprocess.run([backend_python(),"-m","pytest","-q","backend/tests"],cwd=stage,env={**os.environ,"PYTHONPATH":str(stage)},check=True)
