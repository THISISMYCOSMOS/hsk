"""Bundle the committed integration tree and the Agent A inputs consumed by its entry points."""
import hashlib
import io
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from paths import ROOT,role

PREFIX="HSK-Smart-Execution/"
def main():
    a=role("A")
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(["git","archive","--format=zip","--prefix="+PREFIX,head],cwd=ROOT)
    release=ROOT/"release/HSK-Smart-Execution.zip"
    release.parent.mkdir(exist_ok=True)
    market=json.loads((a/"reports/economics/market.json").read_text())
    processed=Path(market["coverage"]["processed"])
    if processed.parent!=Path("data/processed") or processed.suffix!=".gz":
        raise ValueError("unexpected processed-log path")
    additions=["backend/app/blockchain/rpc.py","backend/app/market_data/provider.py",
               "config/network/mainnet.json","config/verified_contracts.json","backtest/collect.py",
               "backtest/fork_compare.py","backtest/settlement.py",str(processed),
               *["reports/economics/"+name+".json" for name in ("market","preorders","operations","fee_model","observed_fees")]]
    with ZipFile(io.BytesIO(archive)) as src,ZipFile(release,"w",compression=ZIP_DEFLATED) as out:
        for name in src.namelist():
            out.writestr(name,src.read(name))
        present=set(src.namelist())
        manifest={}
        for name in additions:
            key=PREFIX+name
            data=(a/name).read_bytes()
            if key in present:
                if src.read(key)!=data:raise ValueError(f"source collision: {name}")
            else:
                out.writestr(key,data)
            manifest[name]=hashlib.sha256(data).hexdigest()
        out.writestr(PREFIX+"INTEGRATION-SOURCES.json",json.dumps({"integrationGitCommit":head,"agentAInputSHA256":manifest},indent=2))
    with ZipFile(release) as bundle:
        if bundle.testzip():raise ValueError("archive integrity failure")
    print(release,hashlib.sha256(release.read_bytes()).hexdigest())
if __name__=="__main__":
    main()
