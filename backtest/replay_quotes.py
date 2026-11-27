"""Capture the historical RPC replies needed by B's actual read_market adapter."""

import argparse
from backend.app.blockchain.rpc import A, RPC, ROOT, call
from backtest.collect import packed, unpack, batches


def capture(block):
    r = RPC()
    rows = [
        x
        for x in unpack(ROOT / f"data/processed/swaps-{block}.json.gz")
        if x["pool_address"] == A["pool"]
    ]
    start = rows[0]["timestamp"]
    anchors = {
        x["block_number"]: x["block_hash"]
        for x in rows
        if x["timestamp"] < start + 86400
    }
    calls = []
    for number in sorted(anchors):
        n = hex(number)
        calls.append(("eth_getBlockByNumber", [n, False]))
        calls.append(call(A["pool"], "ddca3f43", block=n))
        for a, b, sel in [
            (A["WHSK"], A["USDT"], "c6a5026a"),
            (A["USDT"], A["WHSK"], "bd21704a"),
        ]:
            calls.extend(
                [
                    call(A["factory"], "1698ee82", a, b, 3000, block=n),
                    call(A["quoter"], sel, a, b, 10**18, 3000, 0, block=n),
                ]
            )
    responses = []
    for (m, p), result in zip(calls, batches(r, calls)):
        if m == "eth_getBlockByNumber":
            if anchors[int(p[0], 16)] != result["hash"]:
                raise ValueError("historical block mismatch")
            result = {
                k: result[k] for k in ("number", "hash", "parentHash", "timestamp")
            }
        responses.append([m, p, result])
    packed(ROOT / f"data/raw/{block}/worker-quote-replay.json.gz", responses)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--block", type=int, required=True)
    capture(p.parse_args().block)
