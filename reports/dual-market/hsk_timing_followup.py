"""Offline comparison using four synthetic timelines and the same signed limit."""

from dataclasses import dataclass
from decimal import Decimal
import json


D = Decimal
MIN_RECEIVE = D("100.00")
COMPARISON_LIMIT_MS = 1500


@dataclass(frozen=True)
class Offer:
    opens_ms: int
    closes_ms: int
    seller_net: Decimal

    def open_at(self, time_ms: int) -> bool:
        return self.opens_ms <= time_ms < self.closes_ms


@dataclass(frozen=True)
class Timeline:
    name: str
    dex: tuple[Offer, ...]
    match_bids: tuple[Offer, ...]
    match_snapshot_return_ms: int
    expected_compared_route: str


def executable_dex(timeline: Timeline, time_ms: int) -> Offer | None:
    offers = (
        offer for offer in timeline.dex
        if offer.open_at(time_ms) and offer.seller_net >= MIN_RECEIVE
    )
    return next(offers, None)


def compare(timeline: Timeline) -> tuple[str, Offer | None, int]:
    decision_ms = min(timeline.match_snapshot_return_ms, COMPARISON_LIMIT_MS)
    dex = executable_dex(timeline, decision_ms)
    if timeline.match_snapshot_return_ms <= COMPARISON_LIMIT_MS:
        eligible_bids = (
            offer for offer in timeline.match_bids
            if offer.open_at(0) and offer.open_at(decision_ms)
            and offer.seller_net >= MIN_RECEIVE
        )
        match = max(eligible_bids, key=lambda offer: offer.seller_net, default=None)
        if match and (dex is None or match.seller_net > dex.seller_net):
            return "match", match, decision_ms
    return ("DEX" if dex else "none"), dex, decision_ms


def main() -> None:
    steady_dex = Offer(0, 2000, D("100.10"))
    timelines = (
        Timeline(
            "DEX moves below signed limit while comparison waits",
            (Offer(0, 700, D("100.10")), Offer(700, 2000, D("99.80"))),
            (Offer(-100, 2000, D("100.25")),), 1600, "none",
        ),
        Timeline(
            "already-open bid offers more and returns in time",
            (steady_dex,), (Offer(-100, 2000, D("100.25")),), 800, "match",
        ),
        Timeline(
            "DEX remains the best executable choice",
            (steady_dex,), (Offer(-100, 2000, D("100.05")),), 400, "DEX",
        ),
        Timeline(
            "better bid opens after the initial snapshot, within the comparison window",
            (steady_dex,), (Offer(500, 2000, D("100.25")),), 1200, "DEX",
        ),
    )
    results = []
    for timeline in timelines:
        direct = executable_dex(timeline, 0)
        route, chosen, decision_ms = compare(timeline)
        assert direct is not None
        assert route == timeline.expected_compared_route, timeline.name
        assert decision_ms <= COMPARISON_LIMIT_MS
        results.append({
            "case": timeline.name,
            "bid_open_times_ms": [offer.opens_ms for offer in timeline.match_bids],
            "bids_open_at_zero": sum(offer.open_at(0) for offer in timeline.match_bids),
            "comparison_decision_ms": decision_ms,
            "snapshot_return_ms": timeline.match_snapshot_return_ms,
            "direct_dex_seller_net": str(direct.seller_net),
            "compared_route": route,
            "compared_seller_net": str(chosen.seller_net) if chosen else None,
        })

    assert results[0]["comparison_decision_ms"] == COMPARISON_LIMIT_MS
    assert results[1]["compared_seller_net"] == "100.25"
    assert results[3]["bids_open_at_zero"] == 0
    assert all(result["compared_seller_net"] == result["direct_dex_seller_net"]
               for result in results if result["compared_route"] == "DEX")
    routes = [result["compared_route"] for result in results]
    print(json.dumps({
        "scenarios_reproduced": len(results),
        "immediate_dex_executable": len(results),
        "comparison_executable": routes.count("DEX") + routes.count("match"),
        "lost_executable_order": routes.count("none"),
        "added_executable_order": 0,
        "improved_existing_match": routes.count("match"),
        "same_route_and_seller_net": routes.count("DEX"),
        "data": "synthetic; route decisions only, no execution or fill observation",
        "cases": results,
    }))


if __name__ == "__main__":
    main()
