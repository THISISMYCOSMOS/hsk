import os
import shutil
import subprocess
from pathlib import Path
from paths import ROOT,role,backend_python

backend=role("B",required=False)
if backend:
    python=Path(backend_python())
    if os.environ.get("AGENT_B_PYTHON"):
        subprocess.run([str(python),"-c","import uvicorn,fastapi,eth_account,sqlalchemy"],check=True)
    else:
        if not python.exists():
            interpreter=os.getenv("BACKEND_BOOTSTRAP_PYTHON") or shutil.which("python3.12") or "python3"
            subprocess.run([interpreter,"-m","venv",str(ROOT/".runtime/venv")],check=True)
        subprocess.run([str(python),"-m","pip","install","-r",str(backend/"backend/requirements.txt")],check=True)
