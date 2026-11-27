"""Bounded subset search at price/time priority and explicitly tested fill sizes."""

from dataclasses import dataclass
from itertools import combinations
from time import monotonic
from ..economics.bounds import Terms, allocate
from ..schemas.orders import Order


@dataclass(frozen=True)
class Entry:
    id: str
    order: Order
    remaining: int
    sequence: int


@dataclass(frozen=True)
class Search:
    max_orders: int = 7
    max_combinations: int = 128
    seconds: float = 2.0
    taker_bps: int = 5000
    sizes: tuple[int, ...] = ()


def terms(entry, size, market, route, legs):
    cost = market.costs(entry.id, route, legs)
    if cost is None:
        return None
    o = entry.order
    return Terms(
        entry.id,
        o.selling,
        market.quote(o.selling, size),
        cost,
        o.limit(size),
        int(o.minSaving),
        int(o.maxCost) * size // int(o.fixedAmount),
    )


def compare(taker, others, market, now, search=Search()):
    o = taker.order
    rows = [
        e
        for e in others
        if e.order.selling != o.selling
        and e.order.maker != o.maker
        and int(e.order.expiry) >= now
        and e.remaining > 0
        and (e.order.price >= o.price if o.selling else e.order.price <= o.price)
    ]
    rows.sort(key=lambda e: ((-e.order.price if o.selling else e.order.price), e.sequence, e.id))
    available = len(rows)
    rows = rows[: search.max_orders]
    candidates = []
    if int(o.expiry) < now or not 0 < taker.remaining <= int(o.fixedAmount):
        raise ValueError("inactive order")

    def candidate(kind, size, residual=0):
        return dict(
            kind=kind,
            fixedFilled=str(size),
            remaining=str(taker.remaining - size),
            dexFixed=str(residual),
            eligible=False,
            reason=None,
            fills=[],
            savings=[],
        )

    def dex(kind, provider):
        c = candidate(kind, taker.remaining, taker.remaining)
        amount = provider(o.selling, taker.remaining)
        t = terms(taker, taker.remaining, market, kind, 1)
        c["gross"] = str(amount)
        if not amount:
            c["reason"] = "ZERO_QUOTE"
        elif not t:
            c["reason"] = "COST_BOUND_UNKNOWN"
        else:
            # Baseline cost lower bound is only credited for a distinct alternative.
            c["savings"] = [t.result(amount)]
            net = int(c["savings"][0]["conservativeSaving"])
            signed_ok = amount - t.cost.upper >= t.limit if o.selling else amount + t.cost.upper <= t.limit
            if not (
                o.allowDex
                and (
                    kind != "DEX_ONLY"
                    or (o.allowFallback and o.timing == "IMMEDIATE" and o.priority == "SPEED")
                )
            ):
                c["reason"] = "DEX_PERMISSION"
            elif not signed_ok or t.cost.upper > t.max_cost:
                c["reason"] = "ORDER_LIMIT"
            elif (
                kind == "DEX_ONLY"
                and (int(o.minSaving) > 0 or net < 0)
                or kind != "DEX_ONLY"
                and net < max(1, int(o.minSaving))
            ):
                c["reason"] = "INSUFFICIENT_SAVING"
            else:
                c["eligible"] = True
        candidates.append(c)

    dex("DEX_ONLY", market.quote)
    for name, provider in market.routes:
        dex("VALID_DEX_ROUTE", provider)
        candidates[-1]["routeId"] = name

    def match(fills, matched, use_dex):
        left = taker.remaining - matched
        residual = left if use_dex else 0
        size = matched + residual
        kind = (
            "HYBRID_MATCH"
            if residual
            else "PARTIAL_AND_KEEP"
            if left
            else "MULTI_ORDER_MATCH"
            if len(fills) > 1
            else "DIRECT_MATCH"
        )
        c = candidate(kind, size, residual)
        candidates.append(c)
        t = terms(taker, size, market, kind, len(fills))
        ms = [terms(e, q, market, kind, 1) for e, q in fills]
        if t is None or None in ms:
            c["reason"] = "COST_BOUND_UNKNOWN"
            return
        rest = market.quote(o.selling, residual)
        if not t.benchmark or any(not m.benchmark for m in ms) or residual and not rest:
            c["reason"] = "ZERO_QUOTE"
            return
        payments = allocate(t, ms, rest, search.taker_bps)
        if payments is None:
            c["reason"] = "INSUFFICIENT_SAVING"
            return
        c["savings"] = [t.result(sum(payments) + rest)]
        for (e, q), cash, m in zip(fills, payments, ms):
            c["fills"].append(dict(orderId=e.id, fixed=str(q), cash=str(cash)))
            c["savings"].append(m.result(cash))
        c["eligible"] = True

    start = monotonic()
    seen = set()
    checked = 0
    truncated = available > len(rows)
    for count in range(1, len(rows) + 1):
        for subset in combinations(rows, count):
            if len({e.order.maker for e in subset}) != count:
                continue
            for target in dict.fromkeys((taker.remaining, *search.sizes)):
                if checked >= search.max_combinations or monotonic() - start >= search.seconds:
                    truncated = True
                    break
                checked += 1
                if not 0 < target <= taker.remaining:
                    continue
                fills = []
                need = target
                for e in subset:
                    q = min(need, e.remaining)
                    if (
                        not q
                        or q < e.remaining
                        and (not e.order.allowPartial or e.order.timing == "IMMEDIATE")
                    ):
                        break
                    fills.append((e, q))
                    need -= q
                if len(fills) != count:
                    continue
                key = tuple((e.id, q) for e, q in fills)
                if key in seen:
                    continue
                seen.add(key)
                matched = target - need
                if matched == taker.remaining:
                    match(fills, matched, False)
                else:
                    if o.allowDex:
                        match(fills, matched, True)
                    if o.allowPartial and o.timing == "LIMIT":
                        match(fills, matched, False)
            if truncated and (checked >= search.max_combinations or monotonic() - start >= search.seconds):
                break
        if checked >= search.max_combinations or monotonic() - start >= search.seconds:
            break
    for c in candidates:
        c["totalConservativeSavingUSDT"] = (
            str(sum(int(s["conservativeSaving"]) for s in c["savings"])) if c["savings"] else None
        )
    best = select_candidate(taker, candidates)
    optimized = [c for c in candidates if c["eligible"] and c["kind"] != "DEX_ONLY"]
    tested = [int(c["fixedFilled"]) - int(c["dexFixed"]) for c in optimized if c["fills"]]
    return dict(
        candidates=candidates,
        selected=best,
        blockHash=market.block_hash,
        blockNumber=str(market.block_number),
        marketEvidence=market.evidence,
        evidence=market.evidence
        if market.evidence in {"SYNTHETIC", "BACKTEST", "FORK_SIMULATION"}
        else "UNVERIFIED",
        combinationsChecked=checked,
        truncated=truncated,
        globalOptimum=False,
        smallestEconomicFillTested=str(min(tested)) if tested else None,
    )


def select_candidate(taker, candidates):
    eligible = [c for c in candidates if c["eligible"]]
    optimized = [c for c in eligible if c["kind"] != "DEX_ONLY"]
    # Prefer completion for SPEED; SAVINGS compares equal completed sizes only.
    groups = {}
    for c in optimized:
        size = int(c["fixedFilled"])
        key = (int(c["savings"][0]["conservativeSaving"]), -len(c["fills"]))
        if size not in groups or key > groups[size][0]:
            groups[size] = key, c
    full = groups.get(taker.remaining)
    fallback = next((c for c in eligible if c["kind"] == "DEX_ONLY"), None)
    return (
        full[1]
        if full
        else (
            fallback
            if taker.order.priority == "SPEED" and fallback
            else groups[max(groups)][1]
            if groups
            else fallback
        )
    )
