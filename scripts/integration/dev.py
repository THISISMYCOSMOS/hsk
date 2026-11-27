"""Start local services and terminate child processes together on exit."""
import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.request import urlopen
from paths import ROOT, role, backend_python


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--test",action="store_true")
    options=parser.parse_args()
    backend=role("B",required=False)
    market=role("A",required=False)
    if options.test and not backend:
        raise SystemExit("browser integration tests require Agent B")
    python=backend_python()
    if backend and not Path(python).is_file():
        raise SystemExit("Agent B dependencies missing. Run make setup.")
    web_port,api_port=(5188,8766) if options.test else (5173,8765)
    with ExitStack() as stack:
        work=Path(stack.enter_context(tempfile.TemporaryDirectory())) if options.test else ROOT/".runtime"
        work.mkdir(exist_ok=True)
        env=dict(os.environ,AGENT_B_API=f"http://127.0.0.1:{api_port}")
        if market:
            env.update(AGENT_A_ROOT=str(market),VITE_AGENT_A_PROVIDER="1")
        procs=[]
        def launch(args, cwd, env):
            p=subprocess.Popen(args,cwd=cwd,env=env,start_new_session=True)
            procs.append(p)
            return p
        def cleanup():
            for p in reversed(procs):
                if p.poll() is None:
                    os.killpg(p.pid,signal.SIGTERM)
            for p in procs:
                p.wait(timeout=12)
        stack.callback(cleanup)
        signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
        if backend:
            be=dict(env,HSK_EXECUTION_MODE="MOCK",HSK_ENGINE_DB="sqlite:///"+str(work/"orders.db"),
                    PYTHONPATH=str(backend),PYTHONDONTWRITEBYTECODE="1")
            launch([python,"-m","uvicorn","backend.app.api.main:create_app","--factory","--host","127.0.0.1","--port",str(api_port)],backend,be)
            for _ in range(120):
                if procs[0].poll() is not None:
                    raise SystemExit("Agent B failed to start")
                try:
                    with urlopen(f"http://127.0.0.1:{api_port}/health",timeout=.5) as response:
                        if response.status==200: break
                except OSError:
                    time.sleep(.1)
            else:
                raise SystemExit("Agent B readiness timeout")
        else:
            print("Agent B unavailable. Trade and archive replay only.",flush=True)
        launch(["npm","run","dev","--","--port",str(web_port)],ROOT/"frontend",env)
        while all(p.poll() is None for p in procs):
            time.sleep(.2)
        raise SystemExit(next((p.returncode for p in procs if p.returncode is not None),1))


if __name__=="__main__":
    main()
