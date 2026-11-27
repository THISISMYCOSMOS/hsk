"""Monthly sensitivity for operator-paid settlement using a frozen per-fill cost assumption."""

import json
from backend.app.blockchain.rpc import ROOT
from backtest.collect import save


def main():
    folder = ROOT / "reports/economics"
    fee = json.loads((folder / "fee_model.json").read_text())
    sample = next(r for r in fee["charges"] if r["name"] == "partial")
    cost = int(sample["replenishment_upper_usdt_raw"])
    orders = json.loads((folder / "preorders.json").read_text())["scenarios"]
    rows = []
    for scenario in orders[:5]:
        amount = int(scenario["direct_usdt_once_raw"])
        successes = scenario["pair_fills"]
        for overhead in (0, 10_000_000):
            total = successes * cost + overhead
            rows.append(
                dict(
                    hours=scenario["hours"],
                    order_origin="SYNTHETIC",
                    matched_cash_raw=str(amount),
                    fills=successes,
                    fixed_assumed_monthly_usdt_raw=str(overhead),
                    successful_settlement_cost_raw=str(cost),
                    break_even_fee_bps=None
                    if not amount
                    else -(-(total * 10000) // amount),
                    modeled_operator_profit_raw={
                        str(bps): str(amount * bps // 10000 - total)
                        for bps in (5, 10, 30)
                    },
                )
            )
    save(
        folder / "monthly_break_even.json",
        dict(
            evidence="BACKTEST",
            realized_profit=None,
            scenarios=rows,
            note="One reference hybrid transaction per pair fill; no batching, cancellations or failed submission in this sensitivity. Fixed monthly spending is hypothetical.",
        ),
    )


if __name__ == "__main__":
    main()
