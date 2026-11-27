"""Agent A adapter. stdout is a single read-only market response."""
import argparse
import json
import sys
from pathlib import Path


def get_quote(root, side, kind, raw):
    sys.path.insert(0, str(root.resolve()))
    from backend.app.market_data.provider import MarketData
    from backend.app.blockchain.rpc import A
    if side not in ("SELL","BUY") or kind not in ("EXACT_IN","EXACT_OUT") or not 0 < raw < 2**256:
        raise ValueError("invalid quote terms")
    provider = MarketData()
    src, dst = (A["WHSK"], A["USDT"]) if side == "SELL" else (A["USDT"], A["WHSK"])
    state = provider.get_chain_state()
    if state["error"]:
        raise ValueError(state["error"])
    block = state["block_number"]
    for address,symbol,decimals in ((A["WHSK"],"WHSK",18),(A["USDT"],"USDT",6)):
        check = provider.get_token_metadata(address,block)
        if check["block_hash"] != state["block_hash"] or check["error"] or check["data"]["decimals"] != decimals or check["data"]["symbol"].lower()!=symbol.lower():
            raise ValueError("token metadata mismatch or unavailable")
    query = provider.get_dex_quote_exact_in if kind=="EXACT_IN" else provider.get_dex_quote_exact_out
    result = query(src,dst,raw,block)
    if result["error"] or result["evidence"]!="OBSERVED_MAINNET" or result["block_hash"]!=state["block_hash"]:
        raise ValueError(result["error"] or "quote evidence mismatch")
    row = result["data"]
    if min(int(row["amount_in"]), int(row["amount_out"])) <= 0:
        raise ValueError("empty quote")
    return dict(source=result["evidence"],side=side,kind=kind,tokenIn=src,tokenOut=dst,
                amountIn=row["amount_in"],amountOut=row["amount_out"],block=str(block),
                hash=result["block_hash"],at=result["queried_at"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root",type=Path)
    parser.add_argument("side",choices=["SELL","BUY"])
    parser.add_argument("kind",choices=["EXACT_IN","EXACT_OUT"])
    parser.add_argument("raw",type=int)
    args=parser.parse_args()
    print(json.dumps(get_quote(args.root,args.side,args.kind,args.raw)))
