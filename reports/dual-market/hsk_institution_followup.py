"""One offline replay with an estimated arrival that misses custody cutoff."""

import json

from hsk_institution_scenarios import (
    D,
    TARGET,
    Plan,
    Quote,
    Scenario,
    choose_with_payment_constraints,
    gross_for_net,
    observed_spendable,
    price_candidates,
)


def main() -> None:
    a_fee = D("0.005")
    c_quote = Quote("C", D("30000"), D("0.0008"))
    split_a_quote = Quote(
        "A", gross_for_net(TARGET - c_quote.net_amount, a_fee), a_fee,
        spendable_by=90, observed_spendable_at=96,
    )
    full_a_quote = Quote(
        "A", gross_for_net(TARGET, a_fee), a_fee,
        spendable_by=91, observed_spendable_at=91,
    )
    cheaper = Plan("A+C", (split_a_quote, c_quote))
    single = Plan("A only", (full_a_quote,))
    scenario = Scenario(
        "projected timely combination misses an earlier custody cutoff",
        (cheaper, single), "A+C", "A+C", payment_deadline=100, custody_cutoff=95,
    )

    price_first = min(price_candidates(scenario), key=lambda plan: plan.gross_amount)
    decision, chosen = choose_with_payment_constraints(scenario)
    price_first_funds = observed_spendable(price_first, scenario)
    chosen_funds = observed_spendable(chosen, scenario)
    single_funds = observed_spendable(single, scenario)
    assert price_first.name == scenario.expected_before
    assert decision == scenario.expected_after
    assert scenario.funds_deadline == 95
    assert price_first_funds == chosen_funds == D("29976")
    assert TARGET - chosen_funds == D("10024")
    assert single_funds == D("40000.00495")
    assert single.gross_amount - cheaper.gross_amount == D("126.63")
    print(json.dumps({
        "scenario": scenario.name,
        "expected_results_reproduced": "1/1",
        "deadline_minute": scenario.funds_deadline,
        "estimated_a_for_combination_minute": split_a_quote.spendable_by,
        "observed_a_for_combination_minute": split_a_quote.observed_spendable_at,
        "price_first_plan": price_first.name,
        "payment_constraints_plan": decision,
        "price_first_spendable": str(price_first_funds),
        "payment_constraints_spendable": str(chosen_funds),
        "shortfall": str(TARGET - chosen_funds),
        "timely_single_from_start_spendable": str(single_funds),
        "timely_single_from_start_extra_gross": str(single.gross_amount - cheaper.gross_amount),
        "data": "synthetic; no dynamic cutover or shared-balance simulation",
    }))


if __name__ == "__main__":
    main()
