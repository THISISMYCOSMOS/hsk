"""Replay synthetic orders on a new isolated Anvil fork, using deployed ERC20s and router."""

from pathlib import Path
import shutil
import socket
import subprocess
import time
from backend.app.blockchain.rpc import A, CONFIG, ROOT, fetch, word
from backtest.collect import save

SELLER = "0x000000000000000000000000000000000000a101"
BUYER = "0x000000000000000000000000000000000000b202"
# Fund the synthetic buyer from an unrelated pool on the ephemeral fork only.
FIXTURE_DONOR = "0xb92b79ed6b370d5cfee2e14b1d0983c258304c16"
W, U, R = A["WHSK"], A["USDT"], A["router"]
UNIT = 10**18
BLOCK = 30592078
ANCHOR = "0x8e9ec7357cca666d04911b91bb3f5cf0292a7b4e5150a4e6febe30daa1280bda"


def run(artifact=None):
    global SELLER, BUYER
    exe = shutil.which("anvil") or str(Path.home() / ".foundry/bin/anvil")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # No private keys, no upstream write endpoint, distinct simulation chain ID.
    proc = subprocess.Popen(
        [
            exe,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--silent",
            "--accounts",
            "4" if artifact else "0",
            "--chain-id",
            "31337",
            "--fork-url",
            CONFIG["rpc"],
            "--fork-block-number",
            str(BLOCK),
            "--no-storage-caching",
            "--fork-header",
            "User-Agent: HSK-Smart-Execution/1",
        ],
        stdout=subprocess.DEVNULL,
    )

    def local(m, p):
        res = fetch(
            f"http://127.0.0.1:{port}", dict(jsonrpc="2.0", id=1, method=m, params=p)
        )
        if "error" in res:
            raise ValueError(f"{m}: {res['error']}")
        return res["result"]

    try:
        for _ in range(60):
            if proc.poll() is not None:
                raise RuntimeError("Anvil terminated during startup")
            try:
                with socket.create_connection(("127.0.0.1", port), 0.5):
                    break
            except OSError:
                time.sleep(0.5)
        if (
            local("web3_clientVersion", []).lower().find("anvil") < 0
            or local("eth_chainId", []) != "0x7a69"
        ):
            raise ValueError("unexpected local node")
        if local("eth_getBlockByNumber", [hex(BLOCK), False])["hash"] != ANCHOR:
            raise ValueError("unexpected fork state")
        if artifact:
            SELLER, BUYER, second, operator = local("eth_accounts", [])[:4]

        def tx(actor, target, selector, *args, value=0):
            data = "0x" + selector + "".join(map(word, args))
            txid = local(
                "eth_sendTransaction",
                [
                    dict(
                        to=target,
                        data=data,
                        **{"from": actor},
                        value=hex(value),
                        gas=hex(700000),
                    )
                ],
            )
            receipt = local("eth_getTransactionReceipt", [txid])
            deadline = time.monotonic() + 90
            while receipt is None and time.monotonic() < deadline:
                time.sleep(0.25)
                receipt = local("eth_getTransactionReceipt", [txid])
            if receipt is None:
                raise TimeoutError("local receipt not available")
            if int(receipt["status"], 16) != 1:
                raise ValueError(f"local fixture execution reverted: {selector}")
            return dict(
                payer=actor,
                selector=selector,
                calldata_bytes=(len(data) - 2) // 2,
                gas_used=str(int(receipt["gasUsed"], 16)),
                local_effective_gas_price=str(int(receipt["effectiveGasPrice"], 16)),
                local_tx_hash=txid,
            )

        def balances():
            return {
                actor: {
                    sym: int(
                        local(
                            "eth_call",
                            [{"to": a, "data": "0x70a08231" + word(actor)}, "latest"],
                        ),
                        16,
                    )
                    for sym, a in [("USDT", U), ("WHSK", W)]
                }
                for actor in (SELLER, BUYER)
            }

        for actor in (SELLER, BUYER, FIXTURE_DONOR):
            if not artifact or actor == FIXTURE_DONOR:
                local("anvil_impersonateAccount", [actor])
            local("anvil_setBalance", [actor, hex(2000 * UNIT)])
        tx(SELLER, W, "d0e30db0", value=1000 * UNIT)
        tx(FIXTURE_DONOR, U, "a9059cbb", BUYER, 100 * 10**6)
        approvals = [
            tx(SELLER, W, "095ea7b3", R, 1000 * UNIT),
            tx(BUYER, U, "095ea7b3", R, 49 * 10**6),
        ]

        def sell(size, minimum):
            return tx(
                SELLER, R, "04e45aaf", W, U, 3000, SELLER, size * UNIT, minimum, 0
            )

        def buy():
            return tx(
                BUYER, R, "5023b4df", U, W, 3000, BUYER, 600 * UNIT, 49 * 10**6, 0
            )

        scenarios = {}
        initial = balances()
        for name in ("A_sell_first", "B_buy_first", "C_transfer_legs"):
            snapshot = local("evm_snapshot", [])
            if balances() != initial:
                raise ValueError("scenario initial balances differ")
            if name == "A_sell_first":
                receipts = [sell(1000, 80 * 10**6), buy()]
            elif name == "B_buy_first":
                receipts = [buy(), sell(1000, 80 * 10**6)]
            else:
                payment = 48480000
                receipts = [
                    tx(SELLER, W, "a9059cbb", BUYER, 600 * UNIT),
                    tx(BUYER, U, "a9059cbb", SELLER, payment),
                    sell(400, 80 * 10**6 - payment),
                ]
            final = balances()
            seller_cash = final[SELLER]["USDT"] - initial[SELLER]["USDT"]
            buyer_paid = initial[BUYER]["USDT"] - final[BUYER]["USDT"]
            if (
                initial[SELLER]["WHSK"] - final[SELLER]["WHSK"] != 1000 * UNIT
                or final[BUYER]["WHSK"] - initial[BUYER]["WHSK"] != 600 * UNIT
                or seller_cash < 80000000
                or buyer_paid > 49000000
            ):
                raise ValueError("order constraints failed")
            scenarios[name] = dict(
                seller_receives_usdt_raw=str(seller_cash),
                buyer_pays_usdt_raw=str(buyer_paid),
                joint_cash_usdt_raw=str(seller_cash - buyer_paid),
                receipts=receipts,
            )
            if local("evm_revert", [snapshot]) is not True:
                raise ValueError("failed to restore snapshot")
        result = dict(
            evidence="FORK_SIMULATION",
            orders="SYNTHETIC",
            source_block=BLOCK,
            source_hash=ANCHOR,
            version="1.0",
            anvil=subprocess.check_output([exe, "--version"], text=True).splitlines()[
                0
            ],
            policy=dict(
                seller_min_total_usdt_raw="80000000",
                buyer_max_usdt_raw="49000000",
                seller_whsk_raw=str(1000 * UNIT),
                buyer_whsk_raw=str(600 * UNIT),
                allow_direct_and_residual=True,
                immediate=True,
                approvals="both exact allowances established before each scenario",
            ),
            atomic_settlement_measured=False,
            approvals=approvals,
            scenarios=scenarios,
            l1_fee_wei=None,
            realized_savings_usdt=None,
        )
        if artifact:
            from backtest.settlement import validate

            result["settlement"] = validate(
                local, tx, artifact, SELLER, BUYER, second, operator
            )
            result["atomic_settlement_measured"] = True
        save(
            ROOT
            / (
                "reports/economics/settlement_fork.json"
                if artifact
                else "reports/economics/fork.json"
            ),
            result,
        )
        print({k: v["joint_cash_usdt_raw"] for k, v in scenarios.items()})
    finally:
        proc.terminate()
        proc.wait(timeout=20)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path)
    run(parser.parse_args().artifact)
