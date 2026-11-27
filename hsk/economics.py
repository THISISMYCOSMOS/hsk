"""Read-only comparison of exact-input WHSK/USDT execution scenarios."""
from functools import lru_cache
from itertools import combinations
from fractions import Fraction


MAX_ORDERS = 5
MAX_GRID_SIZE = 64
SIDES = {"WHSK": ("sell", "USDT"), "USDT": ("buy", "WHSK")}


def _units(value, name, *, positive=False):
    if type(value) is not int or value < int(positive) or value >= 2**256:
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} uint256")
    return value


def _prepare_orders(orders):
    rows = list(orders)
    if len(rows) > MAX_ORDERS:
        raise ValueError(f"at most {MAX_ORDERS} hypothetical counterorders per comparison")
    ids = set()
    for row in rows:
        key = row["id"]
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError("order ids must be distinct nonempty strings")
        ids.add(key)
        for field in ("offer", "want"):
            _units(row[field], field, positive=True)
        minimum = _units(row.get("min_fill", 1), "min_fill", positive=True)
        if minimum > row["offer"]:
            raise ValueError("maker min_fill exceeds offer")
        if "cost" in row:
            _units(row["cost"], "maker cost")
    return sorted(rows, key=lambda o: (-Fraction(o["offer"], o["want"]), o["id"]))


def _market_function(quote_fn):
    if quote_fn is None:
        from .market import quote_exact_input
        return quote_exact_input
    return quote_fn


def quote(snapshot, token_in, amount_in, orders=(), *, costs=None, remainder="dex",
          min_out=0, quote_fn=None, operator=None):
    """Evaluate simulated routes at a single pinned market snapshot. Raw integer units."""
    _units(amount_in, "amount_in", positive=True)
    _units(min_out, "min_out")
    if token_in not in SIDES or remainder not in ("dex", "hold"):
        raise ValueError("invalid token or remainder policy")
    side, token_out = SIDES[token_in]
    reverse = SIDES[token_out][0]
    rows = _prepare_orders(orders)
    if costs is not None:
        for field in ("dex", "direct", "hybrid", "per_order"):
            _units(costs[field], field)
    operator_profit = None
    if operator is not None:
        operator_profit = (_units(operator["revenue_usdt"], "revenue_usdt")
                           - _units(operator["cost_usdt"], "cost_usdt"))
    read_quote = _market_function(quote_fn)

    @lru_cache(maxsize=None)
    def measured(direction, size):
        return _units(read_quote(snapshot, direction, size), "DEX quote")

    def dex(direction, size):
        return measured(direction, size) if size else 0

    baseline = dex(side, amount_in)
    if not baseline:
        raise ValueError("full DEX quote rounded to zero or was unavailable")

    hold = dict(route="hold", out=0, matched_in=0, dex_in=0, held_in=amount_in,
                fills=[], benchmark_out=None, gross_saving=None, net_saving=None,
                eligible=True, exclusion=None)
    dex_only = dict(route="dex", out=baseline, matched_in=0, dex_in=amount_in, held_in=0,
                    fills=[], benchmark_out=baseline, gross_saving=0,
                    net_saving=0 if costs is not None else None,
                    eligible=remainder == "dex" and baseline >= min_out,
                    exclusion="hold_policy" if remainder == "hold" else (
                        "min_out" if baseline < min_out else None))
    candidates = [dex_only]
    seen = set()
    for count in range(1, len(rows) + 1):
        for subset in combinations(rows, count):
            remaining = amount_in
            fills = []
            for order in subset:
                budget = min(remaining, order["want"])
                received = budget * order["offer"] // order["want"]
                if received < order.get("min_fill", 1):
                    continue
                # The smallest debit satisfying the maker's proportional limit.
                paid = (received * order["want"] + order["offer"] - 1) // order["offer"]
                maker_dex = dex(reverse, received)
                maker_gain = paid - maker_dex
                fills.append(dict(id=order["id"], taker_in=paid, taker_out=received,
                                  taker_leg_benchmark_out=dex(side, paid),
                                  maker_benchmark_out=maker_dex, maker_gross_saving=maker_gain,
                                  maker_net_saving=maker_gain - order["cost"] if "cost" in order else None))
                remaining -= paid
                if remaining == 0:
                    break
            signature = tuple((f["id"], f["taker_in"]) for f in fills)
            if not signature or signature in seen:
                continue
            seen.add(signature)
            matched = amount_in - remaining
            dex_in = remaining if remainder == "dex" else 0
            held = remaining - dex_in
            route = "hybrid" if dex_in else "direct"
            out = sum(f["taker_out"] for f in fills) + dex(side, dex_in)
            executed = matched + dex_in
            benchmark = dex(side, executed)
            gross = out - benchmark
            net = None if costs is None else gross + costs["dex"] - costs[route] - len(fills) * costs["per_order"]
            exclusion = None
            if out * amount_in < min_out * executed:
                exclusion = "min_out"
            elif any(f["taker_leg_benchmark_out"] <= 0 or f["maker_benchmark_out"] <= 0 for f in fills):
                exclusion = "zero_leg_benchmark"
            elif any(f["taker_out"] <= f["taker_leg_benchmark_out"] for f in fills):
                exclusion = "taker_leg_no_positive_saving"
            elif any(f["maker_gross_saving"] <= 0 or
                     (f["maker_net_saving"] is not None and f["maker_net_saving"] <= 0) for f in fills):
                exclusion = "maker_no_positive_saving"
            elif (net if net is not None else gross) <= 0:
                exclusion = "taker_no_positive_saving"
            candidates.append(dict(route=route, out=out, matched_in=matched, dex_in=dex_in, held_in=held,
                                   fills=fills, benchmark_out=benchmark, gross_saving=gross, net_saving=net,
                                   eligible=exclusion is None, exclusion=exclusion))
    candidates.append(hold)
    selected = max((c for c in candidates if c["eligible"]),
                   key=lambda c: ((c["net_saving"] if costs is not None else c["gross_saving"]) or 0,
                                  amount_in - c["held_in"], -len(c["fills"])))
    return dict(token_in=token_in, token_out=token_out, amount_in=amount_in, baseline_out=baseline,
                candidate=selected, candidates=candidates, decision={
                    "dex": "dex_benchmark", "hold": "hold",
                    "direct": "hypothetical_match", "hybrid": "hypothetical_match_and_dex"
                }[selected["route"]], market_block=snapshot.get("block_number"),
                evidence="simulation", order_origin="hypothetical", costs_basis="assumed_bounds" if costs else "unmeasured",
                operator_profit_usdt_raw=operator_profit, sequential_baseline_out=None,
                quote_requests=measured.cache_info().misses, realized_saving=None)


def minimum_economic_amount(snapshot, token_in, amounts, orders, *, costs, remainder="dex", quote_fn=None):
    """First strictly profitable modeled match in an explicitly supplied discrete size grid."""
    sizes = list(amounts)
    if not sizes or len(sizes) > MAX_GRID_SIZE:
        raise ValueError(f"provide 1 to {MAX_GRID_SIZE} candidate sizes")
    sizes = sorted({_units(a, "size", positive=True) for a in sizes})
    orders = _prepare_orders(orders)
    if costs is None or any("cost" not in o for o in orders):
        return dict(amount_in=None, status="costs_unmeasured", sizes_checked=[])
    checked = []
    read_quote = _market_function(quote_fn)

    @lru_cache(maxsize=None)
    def read(direction, size):
        return read_quote(snapshot, direction, size)

    for size in sizes:
        result = quote(snapshot, token_in, size, orders, costs=costs, remainder=remainder,
                       quote_fn=lambda s, direction, quantity: read(direction, quantity))
        selected = result["candidate"]
        checked.append(size)
        if selected["matched_in"] and selected["net_saving"] > 0:
            return dict(amount_in=size, matched_in=selected["matched_in"], status="first_positive_tested_size",
                        sizes_checked=checked)
    return dict(amount_in=None, status="no_positive_tested_size", sizes_checked=checked)
