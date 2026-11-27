"""Independent integration with the supplied C artifact. All RPC writes go to the parent Anvil."""

import hashlib
import json
import time
from eth_abi import encode
from eth_utils import keccak
from backend.app.blockchain.rpc import A, word
from backtest.fork_compare import UNIT, W, U, FIXTURE_DONOR


def validate(local, tx, path, seller, buyer, second, operator):
    artifact = json.loads(path.read_text())
    mids = artifact["methodIdentifiers"]

    def send(actor, to, data, success=True):
        payload = {"from": actor, "data": data, "gas": hex(7000000)}
        if to:
            payload["to"] = to
        txid = local("eth_sendTransaction", [payload])
        for _ in range(360):
            rec = local("eth_getTransactionReceipt", [txid])
            if rec:
                break
            time.sleep(0.25)
        if rec is None or int(rec["status"], 16) != int(success):
            raise ValueError(f"unexpected local receipt: {txid}")
        return rec

    constructor = encode(
        ["(address,address,address,address,address)", "address", "address", "address"],
        [(W, U, A["pool"], A["router"], A["quoter"]), operator, operator, operator],
    )
    rec = send(operator, None, artifact["bytecode"]["object"] + constructor.hex())
    contract = rec["contractAddress"]
    tx(FIXTURE_DONOR, U, "a9059cbb", second, 100000000)
    approval = [
        tx(actor, t, "095ea7b3", contract, limit)
        for actor, t, limit in [
            (seller, W, 1000 * UNIT),
            (buyer, U, 49000000),
            (second, U, 49000000),
        ]
    ]
    tx(second, U, "095ea7b3", A["router"], 49000000)
    hash_method = next(x for x in artifact["abi"] if x.get("name") == "orderHash")
    fields = hash_method["inputs"][0]["components"]
    order_type = "(" + ",".join(x["type"] for x in fields) + ")"
    plan_type = f"(bytes32,uint256,(({order_type},bytes),uint256,uint256,uint256)[],uint256,uint256,bool)"
    deadline = (
        int(local("eth_getBlockByNumber", ["latest", False])["timestamp"], 16) + 86400
    )

    def leg(actor, selling, total, lot, cash, fall=False, min_gain=1):
        order = (
            actor,
            actor,
            W if selling else U,
            U if selling else W,
            int(not selling),
            total * UNIT if selling else 49000000 * total // 600,
            80000000 * total // 1000 if selling else total * UNIT,
            0,
            deadline,
            1,
            False,
            fall,
            int(fall),
            0,
            min_gain,
            operator,
            True,
            True,
        )
        domain = dict(
            name="HSK Smart Execution",
            version="1",
            chainId=31337,
            verifyingContract=contract,
        )
        dtypes = ["string", "string", "uint256", "address"]
        types = dict(
            EIP712Domain=[dict(name=n, type=t) for n, t in zip(domain, dtypes)],
            Order=[dict(name=x["name"], type=x["type"]) for x in fields],
        )
        msg = {
            f["name"]: str(v) if f["type"].startswith("uint") else v
            for f, v in zip(fields, order)
        }
        sig = local(
            "eth_signTypedData_v4",
            [
                actor,
                json.dumps(
                    dict(types=types, domain=domain, primaryType="Order", message=msg)
                ),
            ],
        )
        return ((order, bytes.fromhex(sig[2:])), lot * UNIT, cash, 0)

    actors = (seller, buyer, second)

    def balances():
        return {
            a: {
                s: int(
                    local(
                        "eth_call",
                        [{"to": t, "data": "0x70a08231" + word(a)}, "latest"],
                    ),
                    16,
                )
                for t, s in [(W, "WHSK"), (U, "USDT")]
            }
            for a in actors
        }

    rows = {}
    for case in (
        "direct",
        "partial",
        "multi",
        "multi_sell_first",
        "multi_buy_first",
        "no_trade",
        "fallback",
        "cancel",
        "expired",
    ):
        snap = local("evm_snapshot", [])
        initial = balances()
        size = 600 if case == "direct" else 1000
        participants = [buyer, second] if case == "multi" else [buyer]
        primary = leg(
            seller,
            True,
            size,
            600,
            48480000,
            case == "fallback",
            10000000 if case in ("no_trade", "fallback") else 1,
        )
        legs = [primary] + [
            leg(
                a,
                False,
                600 // len(participants),
                600 // len(participants),
                48480000 // len(participants),
            )
            for a in participants
        ]
        plan = (
            keccak(text=case),
            0 if case == "expired" else deadline,
            legs,
            (size - 600) * UNIT,
            32000000 if size > 600 else 0,
            case == "fallback",
        )
        if case.startswith("multi_"):

            def sell():
                return tx(
                    seller,
                    A["router"],
                    "04e45aaf",
                    W,
                    U,
                    3000,
                    seller,
                    1000 * UNIT,
                    80000000,
                    0,
                )

            def buys():
                return [
                    tx(
                        a,
                        A["router"],
                        "5023b4df",
                        U,
                        W,
                        3000,
                        a,
                        300 * UNIT,
                        24500000,
                        0,
                    )
                    for a in [buyer, second]
                ]

            receipts = (
                [sell(), *buys()] if case == "multi_sell_first" else [*buys(), sell()]
            )
            item = dict(
                gas_used=str(sum(int(r["gas_used"]) for r in receipts)),
                receipts=receipts,
            )
        else:
            if case == "cancel":
                method = next(k for k in mids if k.startswith("cancelOrder("))
                data = encode([order_type], [primary[0][0]])
                actor = seller
            else:
                method = next(k for k in mids if k.startswith("settle("))
                data = encode([plan_type], [plan])
                actor = operator
            rec = send(
                actor, contract, "0x" + mids[method] + data.hex(), case != "expired"
            )
            item = dict(
                calldata_bytes=4 + len(data),
                gas_used=str(int(rec["gasUsed"], 16)),
                payer=actor,
                local_tx_hash=rec["transactionHash"],
                logs=rec["logs"],
            )
            # Sum gas of the external Quoter calls, not the entire verification procedure.
            trace = local(
                "debug_traceTransaction",
                [rec["transactionHash"], {"tracer": "callTracer"}],
            )

            def quote_cost(frame):
                if frame.get("to", "").lower() == A["quoter"]:
                    return int(frame["gasUsed"], 16)
                return sum(quote_cost(c) for c in frame.get("calls", []))

            item["quoter_subcalls_gas"] = str(quote_cost(trace))
            if case not in ("cancel", "expired"):
                events = [
                    log
                    for log in rec["logs"]
                    if log["address"].lower() == contract.lower()
                    and log["topics"][0]
                    == "0x" + keccak(text="PlanResult(bytes32,uint8)").hex()
                ]
                if len(events) != 1 or int(events[0]["data"], 16) != {
                    "fallback": 2,
                    "no_trade": 0,
                }.get(case, 1):
                    raise ValueError(f"wrong settlement result: {case}")
        final = balances()
        delta = {
            a: {s: str(final[a][s] - initial[a][s]) for s in initial[a]} for a in actors
        }
        qty = 0 if case in ("cancel", "expired", "no_trade") else size
        if int(delta[seller]["WHSK"]) != -qty * UNIT:
            raise ValueError(f"wrong seller delta: {case}")
        for a in (buyer, second):
            bought = (
                (300 if case.startswith("multi") else 600 if a == buyer else 0)
                if case not in ("cancel", "expired", "no_trade", "fallback")
                else 0
            )
            if int(delta[a]["WHSK"]) != bought * UNIT:
                raise ValueError(f"wrong buyer delta: {case}")
        if qty and int(delta[seller]["USDT"]) < 80000000 * qty // 1000:
            raise ValueError("seller limit breached")
        if any(
            -int(delta[a]["USDT"]) > 49000000 * int(delta[a]["WHSK"]) // (600 * UNIT)
            for a in (buyer, second)
        ):
            raise ValueError("buyer limit breached")
        if not qty and any(int(x) for v in delta.values() for x in v.values()):
            raise ValueError("unexpected cash movement")
        rows[case] = {**item, "wallet_deltas": delta}
        if local("evm_revert", [snap]) is not True:
            raise ValueError("failed to restore settlement fork")
    return dict(
        artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        sources=artifact["metadata"]["sources"],
        creation_bytecode_sha256=hashlib.sha256(
            bytes.fromhex(artifact["bytecode"]["object"][2:])
        ).hexdigest(),
        contract=contract,
        approvals=approval,
        results=rows,
    )
