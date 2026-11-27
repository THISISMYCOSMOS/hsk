"""Fee-sensitive size screen for the pinned, single-tick-range 5:3 sell/buy fixture."""

import json
from decimal import Decimal, localcontext
from zipfile import ZipFile
from backend.app.blockchain.rpc import ROOT, words
from backtest.collect import save
from backtest.fork_compare import BLOCK, ANCHOR, UNIT

Q96 = 2**96


def ceil(a, b):
    return -(-a // b)


def analyze():
    root = ROOT / "reports/economics"
    fee = json.loads((root / "fee_model.json").read_text())
    verified = json.loads((root / "reference_quotes.json").read_text())
    with ZipFile(ROOT / "backtests/HSK_Session2_Quotes.zip") as z:
        archive = json.loads(z.read("archive.json"))
        info = json.loads(z.read("quotes.json"))
    if (
        info["block_hash"] != ANCHOR
        or fee["hash"] != ANCHOR
        or not all(v["agrees"] for v in verified.values())
    ):
        raise ValueError("reference state not verified")
    p = words(archive["pool_calls"]["slot0"])[0]
    L = int(info["active_liquidity_raw"])
    tick = info["starting_tick"]
    spacing = int(archive["pool_calls"]["tickSpacing"], 16)

    def step(price, qty, buy):
        a = L * Q96
        if buy:
            end = ceil(a * price, a - qty * price)
            cash = ceil(ceil(L * (end - price), Q96) * 1000000, 997000)
        else:
            net = qty * 997000 // 1000000
            end = ceil(a * price, a + net * price)
            cash = L * (price - end) // Q96
        with localcontext() as ctx:
            ctx.prec = 90
            band = tick // spacing * spacing
            if (
                not Decimal("1.0001") ** band
                < (Decimal(end) / Q96) ** 2
                < Decimal("1.0001") ** (band + spacing)
            ):
                raise ValueError("tick boundary reached")
        return end, cash

    entries = []
    for fixed in (1, 5, 10, 20, 25, 50, 75, 100, 150, 250, 400, 600):
        q = fixed * UNIT
        total = 5 * q // 3
        ps, sell = step(p, total, False)
        _, buy_second = step(ps, q, True)
        pb, buy = step(p, q, True)
        _, sell_second = step(pb, total, False)
        _, residual = step(p, total - q, False)
        # Enforce the synthetic demo's signed rates plus both possible baseline orderings.
        # A transfer inside the strict open interval improves both parties before additional costs.
        low = (
            max(ceil(total * 80000000, 1000 * UNIT), sell + 1, sell_second + 1)
            - residual
        )
        high = min(q * 49000000 // (600 * UNIT), buy - 1, buy_second - 1)
        margin = min(residual + buy_second - sell, residual + buy - sell_second)
        entries.append(
            dict(
                matched_whsk_raw=str(q),
                gross_lower_usdt_raw=str(margin),
                two_user_price_feasible=low <= high,
                payment_min_raw=str(low),
                payment_max_raw=str(high),
            )
        )
    if int(entries[-1]["gross_lower_usdt_raw"]) != 291315:
        raise ValueError("600 WHSK screen diverged from fork")
    screens = []
    for scenario in fee["partial_match"]:
        if scenario["baseline"] != "A_sell_first":
            continue
        extra = int(scenario["operator_cost_upper_raw"])
        if scenario["fresh_approvals"]:
            extra += sum(
                int(c["replenishment_upper_usdt_raw"])
                for c in fee["charges"]
                if c["name"] in ("settlement_approval_0", "settlement_approval_1")
            )
        permitted = [
            e
            for e in entries
            if e["two_user_price_feasible"] and int(e["gross_lower_usdt_raw"]) > extra
        ]
        screens.append(
            dict(
                fresh_approvals=scenario["fresh_approvals"],
                reverts_per_success=scenario["expired_reverts_per_success"],
                no_trade_per_success=scenario["no_trade_per_success"],
                offchain_usdt_raw=scenario["offchain_assumption_usdt_raw"],
                assumed_total_cost_raw=str(extra),
                smallest_tested_whsk_raw=permitted[0]["matched_whsk_raw"]
                if permitted
                else None,
            )
        )
    save(
        root / "fill_sizes.json",
        dict(
            evidence="BACKTEST",
            block=BLOCK,
            block_hash=ANCHOR,
            orders="SYNTHETIC",
            grid=entries,
            scenarios=screens,
            note="One tick interval. Independent constant historical gas budget from 600-WHSK hybrid, no avoided DEX cost credited. Screened size and payment interval require current quotes, fees, per-user allocation and simulation before use.",
        ),
    )


if __name__ == "__main__":
    analyze()
