from dataclasses import dataclass
from functools import lru_cache
from typing import Callable
from ..economics.bounds import CostBreakdown


@dataclass
class MarketSnapshot:
    block_hash: str
    block_number: int
    evidence: str
    quote: Callable  # (selling WHSK, amount WHSK raw) -> USDT raw
    costs: Callable  # (order ID, route, number of legs) -> CostBreakdown | None
    routes: tuple = ()  # (verified route identifier, quote callable); supplied only by market adapter

    def __post_init__(self):
        source = self.quote

        @lru_cache(maxsize=256)
        def checked(selling, quantity):
            if quantity == 0:
                return 0
            value = source(selling, quantity)
            if type(value) is not int or not 0 <= value < 2**256:
                raise ValueError("invalid DEX quote")
            return value

        self.quote = checked


def synthetic_snapshot():
    # Independent exact-in and exact-out quotes against the same constant-product reserves.
    base, stable = 10**24, 81_000 * 10**6

    def quote(selling, qty):
        if selling:
            return stable * (997 * qty) // (1000 * base + 997 * qty)
        if qty >= base:
            raise ValueError("insufficient fixture liquidity")
        return -(-(stable * qty * 1000) // ((base - qty) * 997))

    def cost(order_id, route, legs):
        if route == "DEX_ONLY":
            return CostBreakdown(150, 50, 100, 0, 0, 0, 0, 0, 0)
        return CostBreakdown(0, 50, 100, 20 * legs, 40, 0, 0, 0, 10)

    return MarketSnapshot("0x" + "ab" * 32, 1, "SYNTHETIC", quote, cost)
