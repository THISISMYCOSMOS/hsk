"""Exercise the public provider API against a known finalized swap and fixed quote."""

import argparse
import json
from backend.app.blockchain.rpc import ROOT, A
from backend.app.market_data.provider import MarketData
from backtest.collect import save, unpack


def run(end):
    provider = MarketData()
    row = next(
        v
        for v in unpack(ROOT / f"data/processed/swaps-{end}.json.gz")
        if v["pool_address"] == A["pool"]
    )
    n = row["block_number"]
    owner = row["transaction_sender"]
    cases = dict(
        chain=provider.get_chain_state(),
        pool=provider.get_pool_state(A["pool"], end),
        token=provider.get_token_metadata(A["USDT"], end),
        wrapped=provider.get_token_metadata(A["WHSK"], end),
        balance=provider.get_wallet_balance(owner, A["WHSK"], n),
        allowance=provider.get_allowance(owner, A["USDT"], A["router"], n),
        exact_in=provider.get_dex_quote_exact_in(
            A["WHSK"], A["USDT"], 1000 * 10**18, 30592078
        ),
        exact_out=provider.get_dex_quote_exact_out(
            A["USDT"], A["WHSK"], 600 * 10**18, 30592078
        ),
        gas=provider.get_execution_fee_estimate(
            {"to": A["WHSK"], "data": "0x313ce567"}
        ),
        receipt=provider.get_transaction_receipt(row["transaction_hash"]),
        events=provider.backfill_market_events(n, n),
    )
    stream = provider.subscribe_market_events(n)
    cases["subscription"] = next(stream)
    stream.close()
    for k, v in cases.items():
        if v["error"] or v["data"] is None:
            raise ValueError((k, v["error"]))
    if row["transaction_hash"] not in {
        r["transactionHash"] for r in cases["events"]["data"]
    }:
        raise ValueError("recorded event absent")
    if (
        cases["token"]["data"]["decimals"] != 6
        or cases["wrapped"]["data"]["decimals"] != 18
    ):
        raise ValueError("token unit mismatch")
    if (
        cases["exact_in"]["data"]["amount_out"] != "80558131"
        or cases["exact_out"]["data"]["amount_in"] != "48641160"
    ):
        raise ValueError("historical Quoter amount mismatch")
    if (
        cases["receipt"]["block_hash"] != row["block_hash"]
        or cases["pool"]["block_hash"]
        != json.loads((ROOT / f"data/raw/{end}/coverage.json").read_text())["end_hash"]
    ):
        raise ValueError("observations disagree")
    save(ROOT / "data/fixtures/market/MarketSnapshot.json", cases["pool"])
    save(ROOT / "data/fixtures/market/DexQuote.json", cases["exact_in"])
    save(
        ROOT / "reports/economics/provider_smoke.json",
        {
            name: {k: v for k, v in case.items() if k != "data"}
            for name, case in cases.items()
        },
    )
    print("passed", list(cases))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--block", type=int, required=True)
    run(p.parse_args().block)
