"""Reconcile Agent A's 30-day WHSK/USDT pool log population with its published totals."""
import gzip
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from paths import ROOT,role
from replay import write

def main():
    a=role("A")
    folder=a/"reports/economics"
    market=json.loads((folder/"market.json").read_text())
    coverage=market["coverage"]
    snapshot=json.loads((a/"config/network/mainnet.json").read_text())
    pool=snapshot["addresses"]["pool"]
    rows=json.loads(gzip.decompress((a/coverage["processed"]).read_bytes()))
    ids={(r["transaction_hash"],r["log_index"]) for r in rows}
    if len(ids)!=len(rows) or len(rows)!=coverage["unique_events"] or coverage["gaps"] or coverage["evidence"]!="OBSERVED_MAINNET":
        raise ValueError("coverage incomplete or duplicate logs")
    token0=snapshot["addresses"]["WHSK"];token1=snapshot["addresses"]["USDT"]
    byday=defaultdict(lambda:Counter(buy=0,sell=0,count=0))
    observed=Counter()
    for r in rows:
        if r["pool_address"]!=pool:continue
        if (r["token0"],r["token1"],r["chain_id"])!=(token0,token1,177) or not coverage["start_block"]<=r["block_number"]<=coverage["end_block"]:
            raise ValueError("wrong pool binding")
        value=int(r["amount1"])
        day=datetime.fromtimestamp(r["timestamp"],timezone.utc).date().isoformat()
        direction="buy" if value>0 else "sell"
        byday[day][direction]+=abs(value)
        byday[day]["count"]+=1
        observed[direction]+=abs(value)
    group=market["pools"][pool]
    for key in ("buy","sell"):
        if observed[key]!=int(group["directions"][key+"_token0"]["token1_volume_raw"]):
            raise ValueError("stablecoin volume does not match processed logs")
    if group["events"]!=sum(d["count"] for d in byday.values()):
        raise ValueError("pool count mismatch")
    scenarios=json.loads((folder/"preorders.json").read_text())
    if scenarios["source_block"]!=coverage["end_block"]:raise ValueError("scenario block mismatch")
    fees=json.loads((folder/"observed_fees.json").read_text())
    if fees["source_block"]!=coverage["end_block"]:raise ValueError("fee block mismatch")
    operations=json.loads((folder/"operations.json").read_text())
    fee_model=json.loads((folder/"fee_model.json").read_text())
    payload=dict(operations=[{k:v[k] for k in ("mode","evidence","observed_events","worker_evaluations","market_requests","live_rpc_calls","ai_calls","operator_cloud_bill")} for v in operations],modeledEconomics=fee_model["partial_match"],source="OBSERVED_MAINNET",start=coverage["utc_start_exclusive"],end=coverage["utc_end_inclusive"],
                 block=str(coverage["end_block"]),hash=coverage["end_hash"],pool=pool,matchedLogs=group["events"],
                 days=[dict(day=day,count=r["count"],buy=str(r["buy"]),sell=str(r["sell"])) for day,r in sorted(byday.items())],
                 fees=fees,scenarios=scenarios["scenarios"],poolMetrics=group)
    write(ROOT/"frontend/public/evidence/market-30d.json",payload)
    print(f"OBSERVED_MAINNET {len(rows)} logs · pair {group['events']} · {observed['buy']+observed['sell']} micro-USDT")

if __name__=="__main__":
    main()
