import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

root = Path(__file__).resolve().parents[2]
forge = shutil.which("forge") or str(Path.home() / ".foundry/bin/forge")
with tempfile.TemporaryDirectory() as tmp:
    with ZipFile(root / "backtests/HSK_A_Session1.zip") as archive:
        archive.extractall(tmp)
    subprocess.run([forge, "test", "--offline"], cwd=Path(tmp)/"HSK_A_Session1", check=True)
