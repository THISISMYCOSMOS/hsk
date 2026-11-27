from dataclasses import dataclass


@dataclass(frozen=True)
class CostBreakdown:
    """USDT raw per user/fill; DEX baseline costs are LOWER bounds."""

    dex_lower: int
    l1: int
    l2: int
    settlement: int
    verification: int
    approval: int
    service: int
    other: int
    margin: int

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in vars(self).values()):
            raise ValueError("cost bounds must be nonnegative integers")

    @property
    def upper(self):
        return sum(vars(self).values()) - self.dex_lower


@dataclass(frozen=True)
class Terms:
    order_id: str
    selling: bool
    benchmark: int
    cost: CostBreakdown
    limit: int
    min_saving: int
    max_cost: int

    @property
    def boundary(self):
        """Lowest acceptable gross receipt or highest acceptable gross spend."""
        shift = self.cost.upper - self.cost.dex_lower + max(1, self.min_saving)
        if self.selling:
            return max(self.limit + self.cost.upper, self.benchmark + shift)
        return min(self.limit - self.cost.upper, self.benchmark - shift)

    def result(self, gross):
        gain = (gross - self.benchmark) * (1 if self.selling else -1)
        net = gain + self.cost.dex_lower - self.cost.upper
        return dict(
            orderId=self.order_id,
            token="USDT",
            gross=str(gross),
            dexGross=str(self.benchmark),
            conservativeSaving=str(net),
            costs={k: str(v) for k, v in vars(self.cost).items()},
        )


def allocate(taker, makers, residual, taker_bps):
    """Meet all signed limits before splitting free micro-USDT; conserve every unit."""
    if not 0 <= taker_bps <= 10000:
        raise ValueError("invalid surplus split")
    if any(t.cost.upper > t.max_cost for t in [taker, *makers]):
        return None
    cash = [m.boundary for m in makers]
    if min(cash) <= 0:
        return None
    sign = 1 if taker.selling else -1
    surplus = sign * (sum(cash) + residual - taker.boundary)
    if surplus < 0:
        return None
    share, extra = divmod(surplus * (10000 - taker_bps) // 10000, len(cash))
    # For buyers the most that can be returned is the payment minus one.
    for i in range(len(cash)):
        delta = share + (i < extra)
        if taker.selling:
            delta = min(cash[i] - 1, delta)
        cash[i] -= sign * delta
    return cash
