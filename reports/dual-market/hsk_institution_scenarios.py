"""Offline replay of illustrative HSK Dual-Market institutional payment decisions.

Only the amounts and fee rates come from the proposal. All time, quote,
permission, and payment observations are synthetic. No network or wallet calls.
"""
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_CEILING
import json


D = Decimal
CENT = D("0.01")
TARGET = D("40000")
PAYMENT_ASSET = "USD"
PAYMENT_ACCOUNT = "approved payment account"


@dataclass(frozen=True)
class Quote:
    asset: str
    gross_amount: Decimal
    fee_rate: Decimal
    expires_at: int = 30
    spendable_by: int | None = 60
    observed_spendable_at: int | None = 60
    proceeds_asset: str = PAYMENT_ASSET
    proceeds_account: str = PAYMENT_ACCOUNT
    approved: bool = True

    @property
    def net_amount(self) -> Decimal:
        return self.gross_amount * (1 - self.fee_rate)


@dataclass(frozen=True)
class Plan:
    name: str
    quotes: tuple[Quote, ...]
    can_accept_together: bool = True

    @property
    def gross_amount(self) -> Decimal:
        return sum(quote.gross_amount for quote in self.quotes)

    @property
    def net_amount(self) -> Decimal:
        return sum(quote.net_amount for quote in self.quotes)


@dataclass(frozen=True)
class Scenario:
    name: str
    plans: tuple[Plan, Plan]
    expected_before: str
    expected_after: str
    payment_deadline: int = 100
    custody_cutoff: int = 100
    now: int = 10
    accept_buffer: int = 3
    prior_submission_unknown: bool = False

    @property
    def funds_deadline(self) -> int:
        return min(self.payment_deadline, self.custody_cutoff)


def gross_for_net(net: Decimal, fee_rate: Decimal) -> Decimal:
    return (net / (1 - fee_rate)).quantize(CENT, rounding=ROUND_CEILING)


def price_candidates(scenario: Scenario) -> list[Plan]:
    # Give the illustrative comparator visible expiry and permission checks.
    return [
        plan
        for plan in scenario.plans
        if plan.net_amount >= TARGET
        and all(quote.approved and quote.expires_at > scenario.now for quote in plan.quotes)
    ]


def choose_with_payment_constraints(scenario: Scenario) -> tuple[str, Plan | None]:
    if scenario.prior_submission_unknown:
        return "WAIT_PENDING", None

    candidates = [
        plan
        for plan in price_candidates(scenario)
        if plan.can_accept_together
        and all(
            quote.expires_at > scenario.now + scenario.accept_buffer
            and quote.spendable_by is not None
            and quote.spendable_by <= scenario.funds_deadline
            and quote.proceeds_asset == PAYMENT_ASSET
            and quote.proceeds_account == PAYMENT_ACCOUNT
            for quote in plan.quotes
        )
    ]
    best = min(candidates, key=lambda plan: plan.gross_amount, default=None)
    return (best.name, best) if best is not None else ("NO_SAFE_PLAN", None)


def observed_spendable(plan: Plan | None, scenario: Scenario) -> Decimal | None:
    if scenario.prior_submission_unknown:
        return None
    if plan is None:
        return D("0")
    # An incompatible combination needs an observed leg-level result to count.
    if not plan.can_accept_together or any(
        quote.observed_spendable_at is None for quote in plan.quotes
    ):
        return None
    return sum(
        (
            quote.net_amount
            for quote in plan.quotes
            if quote.observed_spendable_at <= scenario.funds_deadline
            and quote.proceeds_asset == PAYMENT_ASSET
            and quote.proceeds_account == PAYMENT_ACCOUNT
        ),
        start=D("0"),
    )


def main() -> None:
    a_fee = D("0.005")
    c = Quote("C", D("30000"), D("0.0008"))
    a_split = Quote("A", gross_for_net(TARGET - c.net_amount, a_fee), a_fee)
    a_all = Quote("A", gross_for_net(TARGET, a_fee), a_fee)
    combo = Plan("A+C", (a_split, c))
    single = Plan("A only", (a_all,))
    late_c = replace(c, spendable_by=105, observed_spendable_at=105)
    late_combo = replace(combo, quotes=(a_split, late_c))
    no_arrival = replace(c, spendable_by=None, observed_spendable_at=None)
    late_custody_c = replace(c, spendable_by=85, observed_spendable_at=85)

    assert c.net_amount == D("29976")
    assert TARGET - c.net_amount == D("10024")
    assert combo.gross_amount == D("40074.38")
    assert single.gross_amount == D("40201.01")
    assert single.gross_amount - combo.gross_amount == D("126.63")

    cases = (
        Scenario("normal cheaper combination", (combo, single), "A+C", "A+C"),
        Scenario(
            "verification unavailable; cheaper route would have settled in time",
            (
                replace(combo, quotes=(a_split, replace(c, spendable_by=None))),
                replace(single, quotes=(replace(a_all, spendable_by=None),)),
            ),
            "A+C", "NO_SAFE_PLAN",
        ),
        Scenario("cheaper leg late; single A timely", (late_combo, single), "A+C", "A only"),
        Scenario(
            "no verified arrival on either route",
            (
                replace(combo, quotes=(a_split, no_arrival)),
                replace(single, quotes=(replace(a_all, spendable_by=None),)),
            ),
            "A+C", "NO_SAFE_PLAN",
        ),
        Scenario(
            "earlier submission unresolved",
            (combo, single), "A+C", "WAIT_PENDING", prior_submission_unknown=True,
        ),
        Scenario(
            "fallback not approved",
            (late_combo, replace(single, quotes=(replace(a_all, approved=False),))),
            "A+C", "NO_SAFE_PLAN",
        ),
        Scenario(
            "fallback expires by the end of acceptance buffer",
            (late_combo, replace(single, quotes=(replace(a_all, expires_at=13),))),
            "A+C", "NO_SAFE_PLAN",
        ),
        Scenario(
            "custody cutoff precedes payment deadline",
            (replace(combo, quotes=(a_split, late_custody_c)), single),
            "A+C", "A only", custody_cutoff=75,
        ),
        Scenario(
            "combination quotes cannot both be accepted",
            (replace(combo, can_accept_together=False), single), "A+C", "A only",
        ),
        Scenario(
            "cheaper leg arrives in incompatible account",
            (replace(combo, quotes=(a_split, replace(c, proceeds_account="trading account"))), single),
            "A+C", "A only",
        ),
    )

    before_meets_deadline = 0
    after_meets_deadline = 0
    duplicate_submissions_prevented = 0
    for scenario in cases:
        before = min(price_candidates(scenario), key=lambda plan: plan.gross_amount)
        decision, after = choose_with_payment_constraints(scenario)
        assert before.name == scenario.expected_before, scenario.name
        assert decision == scenario.expected_after, scenario.name

        before_funds = observed_spendable(before, scenario)
        after_funds = observed_spendable(after, scenario)
        before_met = before_funds is not None and before_funds >= TARGET
        after_met = after_funds is not None and after_funds >= TARGET
        before_meets_deadline += before_met
        after_meets_deadline += after_met
        duplicate_submissions_prevented += scenario.prior_submission_unknown and after is None
        print(json.dumps({
            "case": scenario.name,
            "effective_cutoff_minute": scenario.funds_deadline,
            "illustrative_price_first": before.name,
            "with_payment_constraints": decision,
            "price_first_spendable": str(before_funds) if before_funds is not None else None,
            "with_constraints_spendable": str(after_funds) if after_funds is not None else None,
        }))

    assert observed_spendable(combo, cases[1]) > TARGET
    assert choose_with_payment_constraints(cases[1])[0] == "NO_SAFE_PLAN"
    assert before_meets_deadline == 2
    assert after_meets_deadline == 5
    assert duplicate_submissions_prevented == 1
    assert observed_spendable(late_combo, cases[2]) == a_split.net_amount
    assert observed_spendable(single, cases[2]) == D("40000.00495")
    print(json.dumps({
        "passed": len(cases),
        "tested": len(cases),
        "price_first_meets_deadline": before_meets_deadline,
        "with_constraints_meets_deadline": after_meets_deadline,
        "duplicate_submissions_prevented": duplicate_submissions_prevented,
        "target": str(TARGET),
        "c_net": str(c.net_amount),
        "remaining_after_c": str(TARGET - c.net_amount),
        "extra_gross_for_timely_a_only": str(single.gross_amount - combo.gross_amount),
        "data": "synthetic timing, quote, and observed outcomes; no live transactions",
    }))


if __name__ == "__main__":
    main()
