"""Both-direction exact-in quote probes by token units at a fixed snapshot."""

import argparse
import json
import time
from fractions import Fraction
from backend.app.blockchain.rpc import A, ROOT, RPC, call, words
from backtest.collect import save


def grid(block):
    rpc = RPC()
    b = hex(block)
    p = ROOT / f"data/raw/{block}"
    header = rpc.block(block)
    meta = json.loads((p / "pools.json").read_text())
    out = {}
    for pool, m in meta["pools"].items():
        samples = []
        out[pool] = samples
        for a, z in [(m["token0"], m["token1"]), (m["token1"], m["token0"])]:
            spot = Fraction(int(m["sqrt_price_x96"]) ** 2, 2**192)
            if spot and a == m["token1"]:
                spot = 1 / spot
            for num, den in ((1, 100), (1, 1), (100, 1)):
                amt = max(1, 10 ** meta["decimals"][a] * num // den)
                row = dict(token_in=a, token_out=z, amount_in_requested=str(amt))
                samples.append(row)
                try:
                    quote = rpc.one(
                        *call(A["quoter"], "c6a5026a", a, z, amt, m["fee"], 0, block=b)
                    )
                    amount, after, ticks, gas = words(quote)
                    # A price-limit hit may leave input unspent. Do not calculate impact for that quote.
                    exhausted = after in (
                        4295128740,
                        1461446703485210103287273052203988822378723970341,
                    )
                    net_spot = spot * (1000000 - m["fee"]) / 1000000
                    impact = (
                        10000 * (1 - Fraction(amount, amt) / net_spot)
                        if net_spot and not exhausted
                        else None
                    )
                    row.update(
                        amount_out=str(amount),
                        sqrt_after_x96=str(after),
                        initialized_ticks=ticks,
                        price_limit_hit=exhausted,
                        fee_exclusive_impact_bps=None
                        if impact is None
                        else round(float(impact), 5),
                    )
                except (ValueError, OSError) as e:
                    row["error"] = str(e)
                time.sleep(0.1)
    if rpc.block(block)["hash"] != header["hash"]:
        raise ValueError("snapshot changed")
    save(
        ROOT / "reports/economics/quote_grid.json",
        dict(
            evidence="OBSERVED_MAINNET",
            block_number=block,
            block_hash=header["hash"],
            source=rpc.url,
            pools=out,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", type=int, required=True)
    grid(parser.parse_args().block)
