"""Replay the first 24 hours from the first observed WHSK swap through B's Worker.step."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
from backend.app.blockchain.rpc import A, ROOT
from backtest.collect import save, unpack

MODES = ("poll_60s", "event", "event_cached", "event_selective_ai")


def bench(repo, mode, block):
    # Keep B's dependencies/worktree external and fingerprint the actual implementation.
    import backend

    backend.__path__.append(str(repo / "backend"))
    import backend.app

    backend.app.__path__.append(str(repo / "backend/app"))
    from backend.app.agent.worker import Worker
    from backend.app.agent.intent import parse_user_intent, Intent
    from backend.app.orderbook.store import Store
    from backend.app.orderbook.signatures import typed_data
    from backend.app.schemas.orders import Order, SignedOrder
    from backend.app.quote_engine.provider import read_market
    from backend.app.market_data.provider import MarketData
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from sqlalchemy import event

    rows = [
        r
        for r in unpack(ROOT / f"data/processed/swaps-{block}.json.gz")
        if r["pool_address"] == A["pool"]
    ]
    start = rows[0]["timestamp"]
    window = [r for r in rows if r["timestamp"] < start + 86400]
    current = window[0]
    store = Store("sqlite:///:memory:")
    counts = Counter()
    durations = []

    def sql(conn, cursor, statement, params, context, many):
        cmd = statement.split()[0].upper()
        counts["sql_" + cmd] += 1

    event.listen(store.engine, "before_cursor_execute", sql)
    replies = {
        (m, json.dumps(p, sort_keys=True)): v
        for m, p, v in unpack(ROOT / f"data/raw/{block}/worker-quote-replay.json.gz")
    }

    class ReplayRPC:
        url = "replay://recorded-hsk-mainnet"

        def one(self, m, p):
            counts["rpc_" + m] += 1
            return replies[(m, json.dumps(p, sort_keys=True))]

        def block(self, ref):
            n = current["block_number"] if ref == "latest" else ref
            return self.one("eth_getBlockByNumber", [hex(n), False])

    rpc = ReplayRPC()
    pinned = MarketData(rpc)

    def market():
        counts["market_requests"] += 1
        source = pinned if mode in MODES[2:] else MarketData(rpc)
        return read_market(source)

    worker = Worker(store, market, mode="READ_ONLY")
    eval_ms = []
    evaluate = worker.evaluate

    def timed(*args, **kwargs):
        t = time.perf_counter()
        result = evaluate(*args, **kwargs)
        eval_ms.append((time.perf_counter() - t) * 1000)
        return result

    worker.evaluate = timed
    for selling in (True, False):
        signer = Account.create()
        o = Order(
            maker=signer.address,
            tokenIn=A["WHSK" if selling else "USDT"],
            tokenOut=A["USDT" if selling else "WHSK"],
            kind="EXACT_IN" if selling else "EXACT_OUT",
            fixedAmount=str(10**18),
            limitAmount="50000" if selling else "150000",
            nonce="1",
            expiry=str(int(time.time()) + 86400),
            timing="LIMIT",
            allowPartial=True,
            allowDex=True,
            allowFallback=False,
            priority="SAVINGS",
            maxCost="1000",
            minSaving="1",
        )
        sig = signer.sign_message(
            encode_typed_data(full_message=typed_data(o))
        ).signature
        store.register(
            SignedOrder(order=o, signature="0x" + bytes(sig).hex()), int(time.time())
        )
    worker.step()
    counts.clear()
    eval_ms.clear()
    pinned.cache.clear()
    seen = Counter()
    delays = []

    def deliver(r, t, key=None):
        nonlocal current
        current = r
        id_ = f"{r['transaction_hash']}:{r['log_index']}"
        with store.write() as conn:
            inserted = store.emit(
                conn, "POOL_SWAP", {"block": r["block_number"]}, work=True, key=key
            )
        if inserted is None:
            return
        tick = time.perf_counter()
        if not worker.step():
            raise ValueError("B did not consume outbox")
        durations.append((time.perf_counter() - tick) * 1000)
        seen[id_] += 1
        delays.append(t - r["timestamp"])

    begin = time.perf_counter()
    cpu = time.process_time()
    if mode == MODES[0]:
        idx = 0
        for t in range(start, start + 86400, 60):
            while idx + 1 < len(window) and window[idx + 1]["timestamp"] <= t:
                idx += 1
            deliver(window[idx], t)
    else:
        for i, r in enumerate(window):
            key = (
                f"{r['transaction_hash']}:{r['log_index']}"
                if mode in MODES[2:]
                else None
            )
            deliver(r, r["timestamp"], key)
            if i % 10 == 0:
                deliver(r, r["timestamp"], key)
    parses = 0
    if mode == MODES[3]:
        parsed = parse_user_intent(Intent(text="1 WHSK 매도, 0.05 USDT 이상, 6시간"))
        if parsed["llmCalls"] != 0:
            raise ValueError("unexpected AI invocation")
        parses = 1
    from statistics import median

    files = [
        "agent/worker.py",
        "agent/intent.py",
        "orderbook/store.py",
        "optimizer/search.py",
        "quote_engine/market.py",
        "quote_engine/provider.py",
    ]
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return dict(
        mode=mode,
        evidence="BACKTEST",
        orders="SYNTHETIC",
        interval=[start, start + 86400],
        observed_events=len(window),
        worker_evaluations=len(durations),
        distinct_event_states_evaluated=len(seen),
        missed_event_states=len(window) - len(seen),
        repeat_state_evaluations=sum(x - 1 for x in seen.values()),
        wall_seconds=time.perf_counter() - begin,
        cpu_seconds=time.process_time() - cpu,
        peak_process_rss_bytes=rss if sys.platform == "darwin" else rss * 1024,
        worker_step_p50_ms=median(durations),
        event_to_trigger_p50_seconds=median(delays),
        order_evaluations=len(eval_ms),
        order_evaluation_p50_ms=median(eval_ms),
        step_latency_scope="includes evaluations of two open orders and DB commit",
        db_reads=counts["sql_SELECT"],
        db_writes=sum(counts["sql_" + k] for k in ("INSERT", "UPDATE", "DELETE")),
        market_requests=counts["market_requests"],
        replayed_rpc_calls=sum(v for k, v in counts.items() if k.startswith("rpc_")),
        replayed_rpc_by_method={
            k[4:]: v for k, v in counts.items() if k.startswith("rpc_")
        },
        live_rpc_calls=0,
        ai_calls=0,
        input_tokens=0,
        output_tokens=0,
        literal_intents_parsed=parses,
        user_realized_savings=None,
        operator_cloud_bill=None,
        source_sha256={
            x: hashlib.sha256((repo / "backend/app" / x).read_bytes()).hexdigest()
            for x in files
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--block", type=int, required=True)
    parser.add_argument("--mode", choices=MODES)
    args = parser.parse_args()
    if args.mode:
        print(json.dumps(bench(args.engine, args.mode, args.block)))
    else:
        rows = [
            json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "backtest.operations",
                        "--engine",
                        str(args.engine),
                        "--block",
                        str(args.block),
                        "--mode",
                        mode,
                    ],
                    text=True,
                )
            )
            for mode in MODES
        ]
        save(ROOT / "reports/economics/operations.json", rows)
