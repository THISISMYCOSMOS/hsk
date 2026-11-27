"""Build C and rerun A's counterfactual/fork suite in an isolated checkout."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from paths import ROOT,role,backend_python
from replay import write


def main():
    a, c = role("A"), role("C")
    forge=shutil.which("forge") or str(Path.home()/".foundry/bin/forge")
    with tempfile.TemporaryDirectory() as tmp:
        stage=Path(tmp)
        for name in ("backtest","config/network","backend/app/blockchain"):
            shutil.copytree(a/name,stage/name,ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(c/"contracts",stage/"contracts",ignore=shutil.ignore_patterns("out","cache","broadcast"))
        subprocess.run([forge,"build","--offline"],cwd=stage/"contracts",check=True)
        artifact=stage/"contracts/out/Settlement.sol/Settlement.json"
        subprocess.run([backend_python(),"-m","backtest.fork_compare","--artifact",str(artifact)],cwd=stage,
                       env={**os.environ,"PYTHONPATH":str(stage)},check=True)
        report=json.loads((stage/"reports/economics/settlement_fork.json").read_text())
    if not report["atomic_settlement_measured"] or report["evidence"]!="FORK_SIMULATION":
        raise ValueError("fork evidence missing")
    settlement=report["settlement"]
    cases={}
    for name,r in settlement["results"].items():
        if not r.get("local_tx_hash"):
            continue
        cases[name]={k:r[k] for k in ("local_tx_hash","gas_used","payer","quoter_subcalls_gas","wallet_deltas")}
        if r["logs"]:
            cases[name]["block"]=str(int(r["logs"][0]["blockNumber"],16))
        else:
            cases[name]["block"]=None
    if not {"direct","partial","multi","no_trade","fallback","cancel","expired"}<=cases.keys():
        raise ValueError("incomplete scenario set")
    for name,fixed in (("direct",600),("partial",1000),("multi",1000),("no_trade",0),("expired",0)):
        delta=sum(-int(v["WHSK"]) for v in cases[name]["wallet_deltas"].values() if int(v["WHSK"])<0)
        if delta!=fixed*10**18:
            raise ValueError(f"wallet amounts disagree: {name}")
    public=dict(source="FORK_SIMULATION",policy=report["policy"],sourceBlock=str(report["source_block"]),
                sourceHash=report["source_hash"],artifactSha256=settlement["artifact_sha256"],
                bytecodeSha256=settlement["creation_bytecode_sha256"],contract=settlement["contract"],
                approvals=settlement["approvals"],cases=cases,l1FeeWei=report["l1_fee_wei"],
                realizedSavings=report["realized_savings_usdt"])
    write(ROOT/"frontend/public/evidence/settlement-fork.json",public)
    print("FORK_SIMULATION · independent Settlement rebuild, signed orders, seven reconciliation cases")

if __name__=="__main__":
    main()
