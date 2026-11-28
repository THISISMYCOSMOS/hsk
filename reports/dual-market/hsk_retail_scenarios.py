"""Offline policy comparisons for HSK Dual-Market, no wallet or network calls."""

from dataclasses import dataclass
from typing import Any, Callable


IMBALANCE_PERCENT = 3


@dataclass(frozen=True)
class Scenario:
    name: str
    preceding_rule: Callable[[], Any]
    proposed_rule: Callable[[], Any]
    expected_preceding: Any
    expected_proposed: Any


def within_imbalance(seller_net: int, buyer_net: int) -> bool:
    return min(seller_net, buyer_net) > 0 and (
        abs(seller_net - buyer_net) * 100 <= IMBALANCE_PERCENT * (seller_net + buyer_net)
    )


def fees_with_shared_cap(
    seller_net: int, buyer_net: int, seller_room: int, buyer_room: int, advertised_fee: int
) -> tuple[int, int]:
    # Equal fees preserve the difference but lower the combined net gain.
    imbalance_room = (
        IMBALANCE_PERCENT * (seller_net + buyer_net) - 100 * abs(seller_net - buyer_net)
    ) // (2 * IMBALANCE_PERCENT)
    fee = max(0, min(
        seller_room, buyer_room, advertised_fee, seller_net - 1, buyer_net - 1,
        imbalance_room,
    ))
    return fee, fee


def fees_and_balance(seller_net: int, buyer_net: int, advertised_fee: int) -> tuple[int, bool]:
    seller_fee, buyer_fee = fees_with_shared_cap(
        seller_net, buyer_net, advertised_fee, advertised_fee, advertised_fee
    )
    assert not within_imbalance(seller_net - seller_fee - 1, buyer_net - buyer_fee - 1)
    return seller_fee, within_imbalance(seller_net - seller_fee, buyer_net - buyer_fee)


def candidate_before_approval(
    seller_gain: int, buyer_gain: int, approval_cost: int, approved_price_increase: int
) -> str:
    seller_after = seller_gain - approval_cost + approved_price_increase
    buyer_after = buyer_gain - approved_price_increase
    if not within_imbalance(seller_after, buyer_after):
        return "show_direct_before_requesting_approval"
    return "show_incremental_approval_cost_then_request_consent"


def resume_approved_order(
    approval_paid: int, quote_is_valid: bool
) -> tuple[str, int, int]:
    if not quote_is_valid:
        return "refresh_quote_and_check_signed_limits", 0, approval_paid
    return "review_current_quote", 0, approval_paid


def choose_purchase(
    *,
    requested: int,
    match_quantity: int,
    atomically_available_remainder: int,
    partial_allowed: bool,
    direct_can_fill: bool,
) -> tuple[str, int]:
    if match_quantity == requested:
        return "match", requested
    if match_quantity + atomically_available_remainder == requested:
        action = "evaluate_atomic_and_direct_costs" if direct_can_fill else "offer_atomic"
        return action, requested
    if partial_allowed and match_quantity > 0:
        if direct_can_fill:
            return "evaluate_partial_and_direct_costs", match_quantity
        return "partial", match_quantity
    if direct_can_fill:
        return "offer_direct", requested
    return "wait", 0


def remaining_order_budget(
    maximum_total: int, already_spent: int, pending_reserved: int, proposed_cost: int
) -> bool:
    return already_spent + pending_reserved + proposed_cost <= maximum_total


def can_send_again(
    previous_status: str,
    already_filled: int,
    order_quantity: int,
    next_quantity: int,
) -> bool:
    known_final = previous_status in ("cancelled", "failed", "confirmed")
    return known_final and 0 < next_quantity <= order_quantity - already_filled


def main() -> None:
    checks = [
        Scenario(
            "after approval, stale quote", lambda: ("stop_as_expired", 0, 0),
            lambda: resume_approved_order(12_000, False),
            ("stop_as_expired", 0, 0), ("refresh_quote_and_check_signed_limits", 0, 12_000),
        ),
        Scenario(
            "approval cost turns seller negative", lambda: "request_approval_at_old_price",
            lambda: candidate_before_approval(112_443, 112_443, 120_000, 0),
            "request_approval_at_old_price", "show_direct_before_requesting_approval",
        ),
        Scenario(
            "repricing shares the approval cost", lambda: "reject_because_fixed_price_is_negative",
            lambda: candidate_before_approval(112_443, 112_443, 120_000, 60_000),
            "reject_because_fixed_price_is_negative",
            "show_incremental_approval_cost_then_request_consent",
        ),
        Scenario(
            "imbalance below 3 percent", lambda: 10_299 > 0 and 9_701 > 0,
            lambda: within_imbalance(10_299, 9_701), True, True,
        ),
        Scenario(
            "imbalance equals 3 percent", lambda: 10_300 > 0 and 9_700 > 0,
            lambda: within_imbalance(10_300, 9_700), True, True,
        ),
        Scenario(
            "imbalance above 3 percent", lambda: 10_301 > 0 and 9_699 > 0,
            lambda: within_imbalance(10_301, 9_699), True, False,
        ),
        Scenario(
            "fee ceilings and 3 percent conflict", lambda: within_imbalance(
                111_814 - 24_775, 111_814 - 30_000
            ),
            lambda: within_imbalance(*tuple(
                111_814 - fee for fee in fees_with_shared_cap(111_814, 111_814, 24_775, 30_000, 30_000)
            )),
            False, True,
        ),
        Scenario(
            "equal positive fees break a quote already at 3 percent",
            lambda: (1_000, within_imbalance(103_000 - 1_000, 97_000 - 1_000)),
            lambda: fees_and_balance(103_000, 97_000, 1_000),
            (1_000, False), (0, True),
        ),
        Scenario(
            "equal fee is reduced to the last token unit permitted by 3 percent",
            lambda: (10_000, within_imbalance(102_900 - 10_000, 97_100 - 10_000)),
            lambda: fees_and_balance(102_900, 97_100, 10_000),
            (10_000, False), (3_333, True),
        ),
        Scenario(
            "partial fill would miss a full-order requirement", lambda: ("partial", 400),
            lambda: choose_purchase(requested=600, match_quantity=400, atomically_available_remainder=0,
                                    partial_allowed=False, direct_can_fill=True),
            ("partial", 400), ("offer_direct", 600),
        ),
        Scenario(
            "atomic completion still deserves comparison", lambda: ("offer_direct", 600),
            lambda: choose_purchase(requested=600, match_quantity=400, atomically_available_remainder=200,
                                    partial_allowed=False, direct_can_fill=True),
            ("offer_direct", 600), ("evaluate_atomic_and_direct_costs", 600),
        ),
        Scenario(
            "expiry with no full alternative preserves quantity requirement", lambda: ("partial", 400),
            lambda: choose_purchase(requested=600, match_quantity=400, atomically_available_remainder=0,
                                    partial_allowed=False, direct_can_fill=False),
            ("partial", 400), ("wait", 0),
        ),
        Scenario(
            "partial consent does not automatically prefer a small fill", lambda: ("partial", 400),
            lambda: choose_purchase(requested=600, match_quantity=400, atomically_available_remainder=0,
                                    partial_allowed=True, direct_can_fill=True),
            ("partial", 400), ("evaluate_partial_and_direct_costs", 400),
        ),
        Scenario(
            "zero available quantity never becomes a partial fill", lambda: ("partial", 0),
            lambda: choose_purchase(requested=600, match_quantity=0, atomically_available_remainder=0,
                                    partial_allowed=True, direct_can_fill=False),
            ("partial", 0), ("wait", 0),
        ),
        Scenario(
            "400 already bought and remaining 200 would exceed total budget",
            lambda: 17_000 <= 50_000,
            lambda: remaining_order_budget(50_000, 34_000, 0, 17_000), True, False,
        ),
        Scenario(
            "remaining budget inclusive at total limit", lambda: 16_000 <= 50_000,
            lambda: remaining_order_budget(50_000, 34_000, 0, 16_000), True, True,
        ),
        Scenario(
            "pending reservations exhaust gas budget", lambda: 40 <= 120,
            lambda: remaining_order_budget(120, 30, 60, 40), True, False,
        ),
        Scenario(
            "cancel requested while same quantity is pending", lambda: True,
            lambda: can_send_again("cancel_requested", 0, 600, 600), True, False,
        ),
        Scenario(
            "confirmed 400 leaves only 200 eligible", lambda: True,
            lambda: can_send_again("confirmed", 400, 600, 600), True, False,
        ),
        Scenario(
            "confirmed 400 permits only remaining 200", lambda: True,
            lambda: can_send_again("confirmed", 400, 600, 200), True, True,
        ),
    ]

    differing = 0
    for check in checks:
        before = check.preceding_rule()
        after = check.proposed_rule()
        assert before == check.expected_preceding, (check.name, before)
        assert after == check.expected_proposed, (check.name, after)
        differing += before != after
        print(f"{check.name} | {before!r} -> {after!r}")

    print(f"Retail comparisons: {len(checks)}/{len(checks)} matched expectations; {differing} changed outcomes.")


if __name__ == "__main__":
    main()
