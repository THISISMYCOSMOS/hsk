"""Replay two swap orderings inside the single documented V3 tick interval."""
import json
from decimal import Decimal, localcontext
from pathlib import Path
from zipfile import ZipFile


ARCHIVE = Path(__file__).resolve().parents[1] / "backtests" / "HSK_Session2_Quotes.zip"
Q96 = 2**96
FEE_UNIT = 10**6


def _up(n, d):
    return (n + d - 1) // d


def replay(path=ARCHIVE):
    with ZipFile(path) as z:
        source = json.loads(z.read("archive.json"))
        prior = json.loads(z.read("quotes.json"))
    if any(source[k] != prior[k] for k in ("chain_id", "block", "block_hash", "pool")):
        raise ValueError("archive members refer to different market states")
    calls = source["pool_calls"]
    price = int(calls["slot0"][2:66], 16)
    spacing = int(calls["tickSpacing"], 16)
    lower_tick = prior["starting_tick"] // spacing * spacing
    liquidity = int(prior["active_liquidity_raw"])
    fee = int(calls["fee"], 16)
    with localcontext() as ctx:
        ctx.prec = 100
        lower = Decimal(Q96) * Decimal("1.0001") ** (Decimal(lower_tick) / 2)
        upper = Decimal(Q96) * Decimal("1.0001") ** (Decimal(lower_tick + spacing) / 2)

    def inside(p):
        # A one-unit margin excludes the protocol's tick-boundary rounding interval.
        if not int(lower) + 1 < p < int(upper) - 1:
            raise ValueError("trade crosses the documented tick interval")

    def sell(start, whsk):
        inside(start)
        net = whsk * (FEE_UNIT - fee) // FEE_UNIT
        lq = liquidity * Q96
        end = _up(lq * start, lq + net * start)
        inside(end)
        return liquidity * (start - end) // Q96, end

    def buy(start, whsk):
        inside(start)
        lq = liquidity * Q96
        if whsk * start >= lq:
            raise ValueError("size exceeds modeled liquidity")
        end = _up(lq * start, lq - whsk * start)
        inside(end)
        return _up(_up(liquidity * (end - start), Q96) * FEE_UNIT, FEE_UNIT - fee), end

    # Check both an archived forward observation and the reverse one-USDT control.
    control = source["sell_control"]
    if sell(price, int(control["raw_WHSK_in"]))[0] != int(control["raw_USDT_quote_out"]):
        raise ValueError("sell control does not match")
    response = calls["quote_one_USDT_raw"][2:]
    reverse_end = price + (FEE_UNIT - fee) * Q96 // liquidity
    inside(reverse_end)
    reverse_out = liquidity * Q96 * (reverse_end - price) // (price * reverse_end)
    if (reverse_out, reverse_end) != (int(response[:64], 16), int(response[64:128], 16)):
        raise ValueError("buy control does not match")

    archived = {row["id"]: row for row in prior["quotes"]}
    full = int(archived["A_full"]["amount_in_raw"])
    match = int(archived["B_exact_out"]["amount_out_raw"])
    seller_alone, after_sell = sell(price, full)
    buyer_alone, after_buy = buy(price, match)
    residual, _ = sell(price, full - match)
    if (seller_alone, buyer_alone, residual) != (
        int(archived["A_full"]["amount_out_raw"]),
        int(archived["B_exact_out"]["amount_in_raw"]),
        int(archived["A_remaining"]["amount_out_raw"]),
    ):
        raise ValueError("standalone quotes disagree with archived reproduction")
    payment = (seller_alone - residual + buyer_alone) // 2
    buyer_second, _ = buy(after_sell, match)
    seller_second, _ = sell(after_buy, full)

    def compare(sequence, dex_sell, dex_buy):
        seller_saving = payment + residual - dex_sell
        buyer_saving = dex_buy - payment
        return dict(dex_order=sequence, seller_dex_receives=dex_sell, buyer_dex_pays=dex_buy,
                    seller_gross_saving=seller_saving, buyer_gross_saving=buyer_saving,
                    total_gross_saving=seller_saving + buyer_saving, net_saving=None)

    return dict(chain_id=source["chain_id"], block=source["block"], block_hash=source["block_hash"],
                utc=source["utc"], pool=source["pool"], fee_pips=fee,
                evidence="simulation_with_archived_state", order_origin="hypothetical",
                whsk_sold_raw=full, whsk_bought_raw=match, usdt_decimals=6, whsk_decimals=18,
                payment_usdt_raw=payment, residual_usdt_raw=residual,
                comparisons=[compare("sell_then_buy", seller_alone, buyer_second),
                             compare("buy_then_sell", seller_second, buyer_alone)],
                receipt=None)


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2))
