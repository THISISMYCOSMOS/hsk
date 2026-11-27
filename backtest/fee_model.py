"""Price the fork's gas at one historical HSK fee state with explicit payer and retry assumptions."""

import json
from backend.app.blockchain.rpc import A, ROOT, RPC, call, words
from backtest.collect import save
from backtest.fork_compare import BLOCK, ANCHOR


def model():
    r = RPC()
    header = r.block(BLOCK)
    if header["hash"] != ANCHOR:
        raise ValueError("unexpected fee anchor")
    n = hex(BLOCK)
    base = int(header["baseFeePerGas"], 16)
    tip = 10**9
    evidence = json.loads((ROOT / "reports/economics/settlement_fork.json").read_text())
    contract = evidence["settlement"]
    ledger = []

    def oracle(sel, x):
        return words(r.one(*call(A["oracle"], sel, x, block=n)))[0]

    def quote(size, exact_out):
        a, b, sel = (
            (A["USDT"], A["WHSK"], "bd21704a")
            if exact_out
            else (A["WHSK"], A["USDT"], "c6a5026a")
        )
        return words(r.one(*call(A["quoter"], sel, a, b, size, 3000, 0, block=n)))[0]

    def price(name, row):
        gas = int(row["gas_used"])
        # Upper bound on empty-access-list unsigned type-2 RLP overhead. Sized for
        # chain 177, a 20-byte recipient and six independent <=32-byte scalars.
        size = 256 + row["calldata_bytes"]
        l1 = oracle("f1c7a58b", size)
        chain_operator = oracle("275aedd2", gas)
        lower = gas * (base + tip) + chain_operator
        upper = lower + l1
        entry = dict(
            name=name,
            payer=row["payer"],
            gas_used=str(gas),
            l2_wei=str(gas * (base + tip)),
            unsigned_tx_length_upper=size,
            l1_fee_upper_wei=str(l1),
            chain_operator_fee_wei=str(chain_operator),
            avoided_cost_lower_usdt_raw=str(quote(lower, False)),
            replenishment_upper_usdt_raw=str(quote(upper, True)),
        )
        ledger.append(entry)
        return entry

    # Quote each alternative at the same initial block; these are accounting valuations.
    for scenario in ("A_sell_first", "B_buy_first"):
        for i, row in enumerate(evidence["scenarios"][scenario]["receipts"]):
            price(f"{scenario}_{i}", row)
    for i, row in enumerate(evidence["approvals"]):
        price(f"dex_approval_{i}", row)
    for i, row in enumerate(contract["approvals"]):
        price(f"settlement_approval_{i}", row)
    for k, row in contract["results"].items():
        if "receipts" in row:
            for i, v in enumerate(row["receipts"]):
                price(f"{k}_{i}", v)
        else:
            price(k, row)

    def bound(name, k):
        return int(next(row for row in ledger if row["name"] == name)[k])

    def upper(k):
        return bound(k, "replenishment_upper_usdt_raw")

    def lower(k):
        return bound(k, "avoided_cost_lower_usdt_raw")

    results = []
    row = contract["results"]["partial"]
    users = list(row["wallet_deltas"])
    for baseline in ("A_sell_first", "B_buy_first"):
        base_s = evidence["scenarios"][baseline]
        for new in (False, True):
            user_gain = []
            for i, actor in enumerate(users[:2]):
                cash = int(row["wallet_deltas"][actor]["USDT"])
                direct = cash - (
                    int(base_s["seller_receives_usdt_raw"])
                    if i == 0
                    else -int(base_s["buyer_pays_usdt_raw"])
                )
                fee_i = next(
                    j
                    for j, x in enumerate(base_s["receipts"])
                    if x["payer"].lower() == actor.lower()
                )
                # Identical prior allowances assumed either available on both alternatives or absent on both.
                user_gain.append(
                    direct
                    + lower(f"{baseline}_{fee_i}")
                    + (
                        lower(f"dex_approval_{i}") - upper(f"settlement_approval_{i}")
                        if new
                        else 0
                    )
                )
            for no_trade, reverts, offchain in ((0, 0, 0), (1, 1, 10000)):
                cost = (
                    upper("partial")
                    + no_trade * upper("no_trade")
                    + reverts * upper("expired")
                    + offchain
                )
                results.append(
                    dict(
                        baseline=baseline,
                        fresh_approvals=new,
                        no_trade_per_success=no_trade,
                        expired_reverts_per_success=reverts,
                        offchain_assumption_usdt_raw=str(offchain),
                        seller_gain_before_service_fee_raw=str(user_gain[0]),
                        buyer_gain_before_service_fee_raw=str(user_gain[1]),
                        operator_cost_upper_raw=str(cost),
                        combined_modeled_lower_raw=str(sum(user_gain) - cost),
                        operator_break_even_bps_on_direct_cash=(
                            cost * 10000 + 48480000 - 1
                        )
                        // 48480000,
                        operator_profit_by_fee_bps={
                            str(bps): str(48480000 * bps // 10000 - cost)
                            for bps in (0, 5, 10, 30)
                        },
                    )
                )
    if r.block(BLOCK)["hash"] != ANCHOR:
        raise ValueError("fee anchor changed")
    save(
        ROOT / "reports/economics/fee_model.json",
        dict(
            evidence="BACKTEST",
            fork_evidence="FORK_SIMULATION",
            block=BLOCK,
            hash=ANCHOR,
            source=r.url,
            base_fee_per_gas_wei=str(base),
            assumed_tip_wei=str(tip),
            conversion="1 HSK = 1 WHSK. QuoterV2 fixed-block exact-in for avoided fees, exact-out for replenishment.",
            charges=ledger,
            partial_match=results,
            realized_net_usdt=None,
        ),
    )


if __name__ == "__main__":
    model()
