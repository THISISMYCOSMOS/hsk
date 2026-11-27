"""Observed market summaries and causal hypothetical order replay. No signed user orders."""

import argparse
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from backend.app.blockchain.rpc import A, ROOT
from backtest.collect import save, unpack

Q = 2**192


def quantiles(sizes):
    if not sizes:
        return None
    seq = sorted(sizes)
    return {
        name: str(seq[(len(seq) - 1) * pct // 100])
        for name, pct in (("p50", 50), ("p90", 90), ("max", 100))
    }


def summarize(rows, start, end, meta):
    t0, t1 = meta["token0"], meta["token1"]
    by = Counter(r["transaction_sender"] for r in rows)
    times = [start, *[r["timestamp"] for r in rows], end]
    intervals = [b - a for a, b in zip(times, times[1:])]
    directions = {}
    for direction in ("sell_token0", "buy_token0", "indeterminate"):
        sub = [r for r in rows if r["direction"] == direction]
        directions[direction] = dict(
            events=len(sub),
            token0_volume_raw=str(sum(abs(int(r["amount0"])) for r in sub)),
            token1_volume_raw=str(sum(abs(int(r["amount1"])) for r in sub)),
        )
    values = [int(r["trade_value"]) for r in rows if r["trade_value"] is not None]
    return dict(
        **meta,
        events=len(rows),
        transactions=len({r["transaction_hash"] for r in rows}),
        directions=directions,
        token0_trade_size_raw=quantiles([abs(int(r["amount0"])) for r in rows]),
        usdt_notional_raw=str(sum(values)) if A["USDT"] in (t0, t1) else None,
        usdt_trade_size_raw=quantiles(values),
        unique_tx_senders=len(by),
        largest_tx_sender_event_count=max(by.values(), default=0),
        largest_gap_seconds_including_window_edges=max(intervals),
        internal_gap_seconds=quantiles(intervals[1:-1]),
        gaps_at_least_six_hours=sum(d >= 21600 for d in intervals),
        observed_both_directions=all(
            directions[d]["events"] > 0 for d in ("sell_token0", "buy_token0")
        ),
    )


@dataclass
class Order:
    idx: int
    owner: str
    sell: bool
    remaining: int
    limit: int  # token1 raw per token0 raw, multiplied by Q*10000
    expiry: int


def replay(
    rows,
    end,
    hours,
    participation=100,
    limit_bps=20,
    partial=True,
    min_saving=0,
    delay=0,
    approval_cost=0,
    margin=0,
    max_makers=4,
):
    """Fixed observed flow. Exogenous prices. Cost and limit settings are synthetic."""
    timestamps = [r["timestamp"] for r in rows]
    book = []
    fills = Counter()
    original = {}
    matched_cash = matched_qty = total_orders = 0
    seller_screen = buyer_screen = 0
    pair_fills = 0
    for i, r in enumerate(rows):
        when = r["timestamp"] + delay
        if when > end:
            break
        if i == 0 or r["direction"] == "indeterminate":
            continue
        owner = r["transaction_sender"]
        if (
            int.from_bytes(sha256(owner.encode()).digest()[:8], "big") % 100
            >= participation
        ):
            continue
        qty = abs(int(r["amount0"]))
        if qty == 0:
            continue
        sell = r["direction"] == "sell_token0"
        # The order limit uses the last strictly earlier event's state. Sign and size are
        # known when this log is received. Simulated registration happens just after it.
        prior = int(rows[i - 1]["sqrt_price_x96"]) ** 2
        order = Order(
            i,
            owner,
            sell,
            qty,
            prior * (10000 - limit_bps if sell else 10000 + limit_bps),
            r["timestamp"] + hours * 3600,
        )
        original[i] = qty
        total_orders += 1
        book = [b for b in book if b.expiry >= when and b.remaining]
        if hours and when > order.expiry:
            continue
        j = bisect_right(timestamps, when) - 1 if delay else i
        spot = int(rows[j]["sqrt_price_x96"]) ** 2
        used = 0
        for b in book:
            if b.sell == sell or owner == b.owner:
                continue
            lot = min(order.remaining, b.remaining)
            if not partial and (lot != order.remaining or lot != b.remaining):
                continue
            cash = (lot * spot) // Q
            seller, buyer = (order, b) if sell else (b, order)
            if (
                cash * Q * 10000 < lot * seller.limit
                or cash * Q * 10000 > lot * buyer.limit
            ):
                continue
            # Fee-only infinitesimal DEX comparison, conservative rounding of benefit.
            # No counterfactual AMM state, router fills or gas receipt is inferred here.
            sell_gain = cash - (-(-(lot * spot * 997000) // (Q * 1000000)))
            buy_gain = (lot * spot * 1000000) // (Q * 997000) - cash
            if (
                min(sell_gain, buy_gain) <= approval_cost + margin
                or min(sell_gain, buy_gain) - approval_cost - margin < min_saving
            ):
                continue
            b.remaining -= lot
            order.remaining -= lot
            fills[b.idx] += lot
            fills[i] += lot
            seller_screen += sell_gain - approval_cost - margin
            buyer_screen += buy_gain - approval_cost - margin
            matched_cash += cash
            matched_qty += lot
            pair_fills += 1
            used += 1
            if not order.remaining or used == max_makers:
                break
        if hours and order.remaining:
            book.append(order)
    remaining = sum(original.values()) - sum(fills.values())
    if sum(fills.values()) != 2 * matched_qty or any(
        q > original[i] for i, q in fills.items()
    ):
        raise ValueError("overfill or double counting")
    open_remaining = sum(b.remaining for b in book if b.expiry >= end)
    return dict(
        pair_fills=pair_fills,
        open_at_cutoff_whsk_raw=str(open_remaining),
        expired_or_immediate_unfilled_whsk_raw=str(remaining - open_remaining),
        evidence="BACKTEST",
        order_origin="SYNTHETIC",
        hours=hours,
        participation_pct=participation,
        limit_bps=limit_bps,
        partial=partial,
        min_saving_each_usdt_raw=str(min_saving),
        delay_seconds=delay,
        assumed_approval_cost_each_fill_usdt_raw=str(approval_cost),
        margin_each_fill_usdt_raw=str(margin),
        max_makers=max_makers,
        orders=total_orders,
        orders_with_fill=len(fills),
        orders_fully_filled=sum(fills.get(i) == q for i, q in original.items()),
        submitted_whsk_raw=str(sum(original.values())),
        unmatched_whsk_raw=str(remaining),
        direct_whsk_once_raw=str(matched_qty),
        direct_usdt_once_raw=str(matched_cash),
        seller_fee_screen_usdt_raw=str(seller_screen),
        buyer_fee_screen_usdt_raw=str(buyer_screen),
        realized_user_savings=None,
    )


def study(block):
    raw = ROOT / f"data/raw/{block}"
    coverage = json.loads((raw / "coverage.json").read_text())
    if coverage["evidence"] != "OBSERVED_MAINNET" or coverage["gaps"]:
        raise ValueError("incomplete observation window")
    rows = unpack(ROOT / coverage["processed"])
    if len(rows) != coverage["unique_events"]:
        raise ValueError("coverage mismatch")
    pools = json.loads((raw / "pools.json").read_text())["pools"]
    from datetime import datetime

    start, end = [
        int(datetime.fromisoformat(coverage[k]).timestamp())
        for k in ("utc_start_exclusive", "utc_end_inclusive")
    ]
    by_pool = {
        p: summarize([r for r in rows if r["pool_address"] == p], start, end, m)
        for p, m in pools.items()
    }
    save(
        ROOT / "reports/economics/market.json",
        dict(evidence="OBSERVED_MAINNET", coverage=coverage, pools=by_pool),
    )
    target = [r for r in rows if r["pool_address"] == A["pool"]]
    if (
        pools[A["pool"]]["token0"],
        pools[A["pool"]]["token1"],
        pools[A["pool"]]["fee"],
    ) != (A["WHSK"], A["USDT"], 3000):
        raise ValueError("unexpected WHSK market")
    scenarios = [replay(target, end, h) for h in (0, 1, 6, 12, 24)]
    for k, values in dict(
        participation=[10, 25, 50],
        limit_bps=[0, 100],
        partial=[False],
        min_saving=[10000, 50000],
        delay=[30, 300],
        approval_cost=[25000],
        margin=[10000],
        max_makers=[1, 8],
    ).items():
        scenarios.extend(replay(target, end, 6, **{k: v}) for v in values)
    save(
        ROOT / "reports/economics/preorders.json",
        dict(source_block=block, order_origin="SYNTHETIC", scenarios=scenarios),
    )
    receipts = {r["transaction_hash"]: r for r in target}
    l1 = [int(r["l1_fee"]) for r in receipts.values() if r["l1_fee"] is not None]
    l2 = [int(r["gas_used"]) * int(r["effective_gas_price"]) for r in receipts.values()]
    save(
        ROOT / "reports/economics/observed_fees.json",
        dict(
            evidence="OBSERVED_MAINNET",
            source_block=block,
            unique_transactions=len(receipts),
            l1_fee_available=len(l1),
            l1_fee_wei=quantiles(l1),
            l2_execution_wei=quantiles(l2),
            gas_used=quantiles([int(r["gas_used"]) for r in receipts.values()]),
            note="Whole observed transaction fees. A transaction may contain multiple swaps or other actions.",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", type=int, required=True)
    study(parser.parse_args().block)
