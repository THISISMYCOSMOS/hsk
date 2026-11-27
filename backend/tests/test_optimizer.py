from dataclasses import replace
import time
import pytest
from conftest import UNIT, terms
from backend.app.optimizer.search import Entry, Search, compare
from backend.app.quote_engine.market import synthetic_snapshot
from backend.app.economics.bounds import CostBreakdown


def books(actors, sizes, sell=True, **kw):
    taker = terms(actors[0], sell, **kw)
    return Entry("a", taker, int(taker.fixedAmount), 10), [
        Entry(str(i), terms(actors[i + 1], not sell, x), x * UNIT, i) for i, x in enumerate(sizes)
    ]


@pytest.mark.parametrize("sell", [True, False])
@pytest.mark.parametrize(
    "sizes,flags,expected",
    [
        ([1000], {}, "DIRECT_MATCH"),
        ([600, 400], {}, "MULTI_ORDER_MATCH"),
        ([600], {}, "PARTIAL_AND_KEEP"),
        ([600], {"allowDex": True}, "HYBRID_MATCH"),
    ],
)
def test_matched(actors, sell, sizes, flags, expected):
    a, b = books(actors, sizes, sell, **flags)
    r = compare(a, b, synthetic_snapshot(), int(time.time()))
    c = r["selected"]
    assert c["kind"] == expected
    assert all(int(s["conservativeSaving"]) > 0 for s in c["savings"])
    assert sum(int(f["fixed"]) for f in c["fills"]) + int(c["dexFixed"]) + int(c["remaining"]) == a.remaining
    if expected == "PARTIAL_AND_KEEP":
        assert c["savings"][0]["dexGross"] == str(synthetic_snapshot().quote(sell, int(c["fixedFilled"])))


def test_limits(actors):
    a, b = books(actors, [1000], limitAmount="200000000")
    assert compare(a, b, synthetic_snapshot(), 0)["selected"] is None
    a, b = books(actors, [1000])
    a = replace(a, order=a.order.model_copy(update={"minSaving": str(10**20)}))
    assert compare(a, b, synthetic_snapshot(), 0)["selected"] is None


def test_cost_upper_and_losing_maker(actors):
    a, b = books(actors, [1000])
    m = synthetic_snapshot()
    m.costs = lambda *_: None
    r = compare(a, b, m, 0)
    assert r["selected"] is None
    assert all(c["reason"] == "COST_BOUND_UNKNOWN" for c in r["candidates"])
    m.costs = lambda id_, *_: CostBreakdown(0, 0, 0, 0, 0, 0, 0, 10**9 if id_ != "a" else 0, 0)
    assert compare(a, b, m, 0)["selected"] is None


def test_grid_and_budget(actors):
    a, b = books(actors, [1000])
    grid = (1, UNIT, 10 * UNIT, 100 * UNIT)
    m = synthetic_snapshot()
    r = compare(a, b, m, 0, Search(sizes=grid))
    assert int(r["smallestEconomicFillTested"]) in grid[1:]
    assert int(r["smallestEconomicFillTested"]) > 1
    limited = compare(a, b, m, 0, Search(max_combinations=1, sizes=grid))
    assert limited["truncated"] and limited["selected"] == r["selected"]
    assert not r["globalOptimum"]


def test_permission_and_immediate(actors):
    a, b = books(actors, [600], timing="IMMEDIATE", allowPartial=True)
    assert compare(a, b, synthetic_snapshot(), 0)["selected"] is None
    a, b = books(
        actors, [], allowDex=True, allowFallback=True, minSaving="0", timing="IMMEDIATE", priority="SPEED"
    )
    assert compare(a, b, synthetic_snapshot(), 0)["selected"]["kind"] == "DEX_ONLY"


def test_rounding_and_string_boundary(actors):
    import pydantic

    assert terms(actors[0], fixedAmount="3", limitAmount="5").limit(1) == 2
    assert terms(actors[0], False, fixedAmount="3", limitAmount="5").limit(1) == 1
    for v in [0, 1, 1.5, "01", "-1", str(2**256)]:
        with pytest.raises(pydantic.ValidationError):
            terms(actors[0], fixedAmount=v)
