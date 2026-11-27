"""Collect a closed 30-day interval. Run from repo root with python -m backtest.collect."""

import argparse
import gzip
import json
import time
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from backend.app.blockchain.rpc import (
    A,
    CONFIG,
    CREATED,
    ROOT,
    RPC,
    SWAP,
    addr_word,
    call,
    fetch,
    logs,
    signed,
    utc,
    words,
)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_bytes(
        path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    )


def replace_bytes(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
    Path(tmp.name).replace(path)


def packed(path, data):
    replace_bytes(
        path, gzip.compress(json.dumps(data, separators=(",", ":")).encode(), mtime=0)
    )


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def integer(v):
    return int(v, 16)


def factory_events(end):
    rows = []
    for page in range(1, 10000):
        params = dict(
            module="logs",
            action="getLogs",
            address=A["factory"],
            topic0=CREATED,
            fromBlock=0,
            toBlock=end,
            page=page,
            offset=1000,
        )
        response = fetch(CONFIG["explorer"] + "/api?" + urlencode(params))
        chunk = response["result"]
        if not isinstance(chunk, list) or response.get("status") != "1" and chunk:
            raise ValueError(f"incomplete factory index: {response.get('message')}")
        if (
            chunk
            and rows
            and chunk[0]["transactionHash"]
            == rows[-min(1000, len(rows))]["transactionHash"]
            and chunk[0]["logIndex"] == rows[-min(1000, len(rows))]["logIndex"]
        ):
            raise ValueError("repeated factory page")
        rows.extend(chunk)
        if len(chunk) < 1000:
            if not rows:
                raise ValueError("no Factory events returned")
            return rows
    raise ValueError("pagination exhausted")


def batches(rpc, calls, size=8):
    for i in range(0, len(calls), size):
        yield from rpc.batch(calls[i : i + size])
        time.sleep(0.8)


def first_after(rpc, end, timestamp):
    lo, hi = 0, end
    while lo < hi:
        mid = (lo + hi) // 2
        if integer(rpc.block(mid)["timestamp"]) <= timestamp:
            lo = mid + 1
        else:
            hi = mid
    return lo


def collect(ref):
    rpc = RPC()
    head = rpc.block(ref)
    end, ts = integer(head["number"]), integer(head["timestamp"])
    base = ROOT / "data/raw" / str(end)
    base.mkdir(parents=True, exist_ok=True)
    start = first_after(rpc, end, ts - 30 * 86400)
    stop = datetime.fromtimestamp(ts, timezone.utc)
    manifest = dict(
        version="1.0",
        evidence="UNVERIFIED",
        rpc=CONFIG["rpc"],
        analysis_started_utc=utc(),
        end_block=end,
        end_hash=head["hash"],
        start_block=start,
        gaps=[],
        utc_start_exclusive=(stop - timedelta(days=30)).isoformat(),
        utc_end_inclusive=stop.isoformat(),
        kst_end_inclusive=stop.astimezone(timezone(timedelta(hours=9))).isoformat(),
    )
    path = base / "coverage.json"
    if path.exists():
        old = json.loads(path.read_text())
        if old["end_hash"] != head["hash"]:
            raise ValueError("anchor reorganized")
        manifest["analysis_started_utc"] = old["analysis_started_utc"]
    manifest["analysis_started_kst"] = (
        datetime.fromisoformat(manifest["analysis_started_utc"])
        .astimezone(timezone(timedelta(hours=9)))
        .isoformat()
    )
    save(path, manifest)
    stage = "factory"
    try:
        factory = factory_events(end)
        pools = {}
        for row in factory:
            p = addr_word(words(row["data"])[1])
            t0, t1, fee = [integer(x) for x in row["topics"][1:4]]
            pools[p] = dict(token0=addr_word(t0), token1=addr_word(t1), fee=fee)
        if A["pool"] not in pools:
            raise ValueError("reference pool absent from Factory index")
        save(base / "factory.json", factory)
        stage = "metadata"
        tokens = sorted({m[k] for m in pools.values() for k in ("token0", "token1")})
        decimals = {
            t: words(v)[0]
            for t, v in zip(
                tokens,
                batches(rpc, [call(t, "313ce567", block=hex(end)) for t in tokens]),
            )
        }
        for pool, meta in pools.items():
            t0, t1, fee, liquidity, slot, resolved = rpc.batch(
                [
                    *[
                        call(pool, s, block=hex(end))
                        for s in (
                            "0dfe1681",
                            "d21220a7",
                            "ddca3f43",
                            "1a686502",
                            "3850c7bd",
                        )
                    ],
                    call(
                        A["factory"],
                        "1698ee82",
                        meta["token0"],
                        meta["token1"],
                        meta["fee"],
                        block=hex(end),
                    ),
                ]
            )
            if (
                addr_word(words(t0)[0]),
                addr_word(words(t1)[0]),
                words(fee)[0],
                addr_word(words(resolved)[0]),
            ) != (meta["token0"], meta["token1"], meta["fee"], pool):
                raise ValueError("pool identity mismatch")
            meta.update(
                active_liquidity=str(words(liquidity)[0]),
                sqrt_price_x96=str(words(slot)[0]),
                tick=signed(words(slot)[1]),
            )
        save(base / "pools.json", dict(pools=pools, decimals=decimals))
        stage = "swap_logs"
        events = []
        ranges = [(lo, min(lo + 4999, end)) for lo in range(start, end + 1, 5000)]
        for i in range(0, len(ranges), 8):
            group = ranges[i : i + 8]
            cache = base / f"logs-{group[0][0]}-{group[-1][1]}.json.gz"
            if cache.exists():
                events.extend(unpack(cache))
                continue
            try:
                rows = [
                    r
                    for batch in rpc.batch(
                        [logs(sorted(pools), SWAP, lo, hi) for lo, hi in group]
                    )
                    for r in batch
                ]
            except Exception as err:
                manifest["gaps"].append(
                    dict(start=group[0][0], end=group[-1][1], error=str(err))
                )
                continue
            packed(cache, rows)
            events.extend(rows)
        if manifest["gaps"]:
            raise ValueError("incomplete log coverage")
        stage = "receipts_and_blocks"
        txs = sorted({r["transactionHash"] for r in events})

        def enrich(keys, method):
            out = {}
            for i in range(0, len(keys), 240):
                subset = keys[i : i + 240]
                chunk = base / f"{method}-{subset[0]}.json.gz"
                if chunk.exists():
                    vals = unpack(chunk)
                else:
                    vals = list(
                        batches(
                            rpc,
                            [
                                (method, [k, False] if method.endswith("Hash") else [k])
                                for k in subset
                            ],
                        )
                    )
                    if any(v is None for v in vals):
                        raise ValueError("missing receipt/header")
                    packed(chunk, vals)
                field = "hash" if method.endswith("Hash") else "transactionHash"
                if [v[field] for v in vals] != subset:
                    raise ValueError("cached RPC identity mismatch")
                out.update(zip(subset, vals))
            return out

        receipts = enrich(txs, "eth_getTransactionReceipt")
        headers = enrich(
            sorted({r["blockHash"] for r in events if not r.get("blockTimestamp")}),
            "eth_getBlockByHash",
        )
        stage = "normalize"
        normalized = {}
        for r in events:
            pool = r["address"].lower()
            meta = pools[pool]
            a, b, sqrt_price, liquidity, tick = words(r["data"])
            a, b = signed(a), signed(b)
            receipt = receipts[r["transactionHash"]]
            header = headers.get(r["blockHash"], r)
            if (
                r.get("removed")
                or r["topics"][0] != SWAP
                or receipt["blockHash"] != r["blockHash"]
                or header.get("number", r["blockNumber"]) != r["blockNumber"]
                or receipt["transactionIndex"] != r["transactionIndex"]
                or not any(
                    x["logIndex"] == r["logIndex"]
                    and x["data"] == r["data"]
                    and x["address"] == r["address"]
                    and x["topics"] == r["topics"]
                    for x in receipt["logs"]
                )
            ):
                raise ValueError("log/receipt/header mismatch")
            token0, token1 = meta["token0"], meta["token1"]
            amounts = {token0: a, token1: b}
            value = amounts.get(A["USDT"])
            row = dict(
                chain_id=177,
                pool_address=pool,
                block_number=integer(r["blockNumber"]),
                block_hash=r["blockHash"],
                transaction_hash=r["transactionHash"],
                transaction_index=integer(r["transactionIndex"]),
                log_index=integer(r["logIndex"]),
                timestamp=integer(
                    header["timestamp"]
                    if "timestamp" in header
                    else r["blockTimestamp"]
                ),
                token0=token0,
                token1=token1,
                amount0=str(a),
                amount1=str(b),
                sqrt_price_x96=str(sqrt_price),
                liquidity=str(liquidity),
                tick=signed(tick),
                transaction_sender=receipt["from"].lower(),
                swap_sender=addr_word(integer(r["topics"][1])),
                swap_recipient=addr_word(integer(r["topics"][2])),
                gas_used=str(integer(receipt["gasUsed"])),
                effective_gas_price=str(integer(receipt["effectiveGasPrice"])),
                l1_fee=str(integer(receipt["l1Fee"]))
                if receipt.get("l1Fee") is not None
                else None,
                direction="sell_token0"
                if a > 0 and b <= 0
                else "buy_token0"
                if b > 0 and a <= 0
                else "indeterminate",
                trade_value=None if value is None else str(abs(value)),
                trade_value_token=A["USDT"] if value is not None else None,
            )
            k = (row["block_number"], row["transaction_index"], row["log_index"])
            if k in normalized and normalized[k] != row:
                raise ValueError("conflicting logs")
            normalized[k] = row
        if rpc.block(end)["hash"] != head["hash"]:
            raise ValueError("anchor reorganized")
        dest = ROOT / f"data/processed/swaps-{end}.json.gz"
        packed(dest, [normalized[k] for k in sorted(normalized)])
        manifest.update(
            evidence="OBSERVED_MAINNET",
            unique_events=len(normalized),
            duplicate_events=len(events) - len(normalized),
            transactions=len(txs),
            pool_count=len(pools),
            processed=str(dest.relative_to(ROOT)),
        )
    except Exception as err:
        manifest.update(failed_stage=stage, error=str(err))
        raise
    finally:
        save(path, manifest)
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=int, help="fixed end block (default finalized)")
    args = parser.parse_args()
    collect(args.end if args.end is not None else "finalized")
