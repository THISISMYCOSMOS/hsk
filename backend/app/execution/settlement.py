"""Agent C Settlement v1. Accept only complete contract signatures for the deployment."""

from dataclasses import dataclass
from eth_utils import keccak
from web3 import Web3
from web3.logs import DISCARD
from ..orderbook.signatures import DOMAIN_FIELDS, fields, recover


def contract_fields(contract):
    fn = contract.get_function_by_name("orderHash")
    return [{k: f[k] for k in ("name", "type")} for f in fn.abi["inputs"][0]["components"]]


def chain_message(contract, chain_id, terms):
    spec = contract_fields(contract)
    if set(terms) != {f["name"] for f in spec}:
        raise ValueError("ABI_ORDER_MISMATCH")
    return dict(
        types={"EIP712Domain": fields(DOMAIN_FIELDS), "Order": spec},
        primaryType="Order",
        domain=dict(
            name="HSK Smart Execution", version="1", chainId=chain_id, verifyingContract=contract.address
        ),
        message=terms,
    )


def project(order, *, recipient, operator, valid_after, max_service_fee):
    """Caller presents these fields to wallet. Every added field needs an actual signature."""
    sell = order.selling
    return dict(
        owner=order.maker,
        recipient=recipient,
        tokenIn=order.tokenIn,
        tokenOut=order.tokenOut,
        orderKind=0 if sell else 1,
        amountIn=order.fixedAmount if sell else order.limitAmount,
        amountOut=order.limitAmount if sell else order.fixedAmount,
        validAfter=str(valid_after),
        deadline=order.expiry,
        nonce=order.nonce,
        partiallyFillable=order.allowPartial,
        allowDexFallback=order.allowFallback,
        executionPriority=1 if order.priority == "SPEED" else 0,
        maxFeeAmount=str(max_service_fee),
        minImprovementAmount=order.minSaving,
        allowedExecutor=operator,
        allowDex=order.allowDex,
        immediate=order.timing == "IMMEDIATE",
    )


def abi_order(contract, body):
    return tuple(
        int(body[f["name"]]) if f["type"].startswith("uint") else body[f["name"]]
        for f in contract_fields(contract)
    )


@dataclass(frozen=True)
class Prepared:
    arguments: tuple
    transaction: dict
    plan_id: bytes
    quantities: dict
    block_hash: str


def build(contract, chain_id, operator, comparison, primary, signed, deadline):
    candidate = comparison["selected"]
    if not candidate or not candidate["eligible"] or candidate["kind"] == "VALID_DEX_ROUTE":
        raise ValueError("NO_EXECUTABLE_PLAN")
    direct = sum(int(f["fixed"]) for f in candidate["fills"])
    cash = sum(int(f["cash"]) for f in candidate["fills"])
    rows = [(primary, direct, cash)] + [
        (f["orderId"], int(f["fixed"]), int(f["cash"])) for f in candidate["fills"]
    ]
    legs, quantities = [], {}
    dex = int(candidate["dexFixed"])
    fallback = candidate["kind"] == "DEX_ONLY"
    for i, ((id_, qty, usdt), s) in enumerate(zip(rows, candidate["savings"], strict=True)):
        body, sig = signed[id_]
        msg = chain_message(contract, chain_id, body)
        if recover(msg, sig, body["owner"]) != id_ or s["orderId"] != id_:
            raise ValueError("ORDER_DIGEST_MISMATCH")
        total = int(body["amountIn"] if int(body["orderKind"]) == 0 else body["amountOut"])
        size = qty + (dex if i == 0 else 0)
        if not 0 < size <= total or size != total and (body["immediate"] or not body["partiallyFillable"]):
            raise ValueError("QUANTITY_LIMIT")
        if fallback and not (
            body["immediate"]
            and body["allowDexFallback"]
            and body["allowDex"]
            and int(body["executionPriority"]) == 1
            and int(body["minImprovementAmount"]) == 0
        ):
            raise ValueError("DEX_FALLBACK_POLICY")
        fee = 0 if fallback else int(s["costs"]["service"])
        if fee > int(body["maxFeeAmount"]) * size // total:
            raise ValueError("FEE_LIMIT")
        quantities[id_] = size
        legs.append(((abi_order(contract, body), sig), qty, usdt, fee))
    rest_cash = int(candidate["savings"][0]["gross"]) - cash if dex else 0
    core = (bytes(32), deadline, legs, dex, rest_cash, fallback)
    # Include actual proportions, every order hash, block, deadline and deployment.
    seed = contract.encode_abi("settle", args=[core])
    plan_id = keccak(bytes.fromhex(contract.address[2:] + comparison["blockHash"][2:] + seed[2:]))
    args = (plan_id, *core[1:])
    tx = {
        "from": operator,
        "to": contract.address,
        "value": 0,
        "data": contract.encode_abi("settle", args=[args]),
    }
    return Prepared(args, tx, plan_id, quantities, comparison["blockHash"])


def preflight(w3, contract, plan, *, gas_limit, fee_cap_wei, l1_upper_wei, budget_wei):
    """Pin economic snapshot and use exactly the same to/from/value/data for all gates."""
    head = w3.eth.get_block("latest")
    if Web3.to_hex(head.hash) != plan.block_hash:
        raise ValueError("STALE_SNAPSHOT")
    if l1_upper_wei is None:
        raise ValueError("L1_COST_UNVERIFIED")
    if min(gas_limit, fee_cap_wei, budget_wei) <= 0 or l1_upper_wei < 0:
        raise ValueError("INVALID_GAS_BUDGET")
    tx = dict(plan.transaction, gas=gas_limit, gasPrice=fee_cap_wei)
    result = int.from_bytes(w3.eth.call(tx, head.number), "big")
    if result != (2 if plan.arguments[-1] else 1):
        raise ValueError("NO_TRADE")
    estimate = w3.eth.estimate_gas(tx)
    if estimate > gas_limit or gas_limit * fee_cap_wei + l1_upper_wei > budget_wei:
        raise ValueError("GAS_BUDGET_EXCEEDED")
    if w3.eth.get_block("latest").hash != head.hash:
        raise ValueError("STALE_SNAPSHOT")
    return tx, estimate


def reconcile(w3, contract, plan, receipt):
    if receipt.status != 1:
        raise ValueError("TRANSACTION_FAILED")
    if receipt.to != contract.address or w3.eth.get_block(receipt.blockNumber).hash != receipt.blockHash:
        raise ValueError("NON_CANONICAL_RECEIPT")
    tx = w3.eth.get_transaction(receipt.transactionHash)
    if (
        tx["from"] != plan.transaction["from"]
        or tx["value"] != 0
        or Web3.to_hex(tx["input"]).lower() != plan.transaction["data"].lower()
    ):
        raise ValueError("TRANSACTION_MISMATCH")
    results = contract.events.PlanResult().process_receipt(receipt, errors=DISCARD)
    confirmed = [
        r["args"] for r in results if r["address"] == contract.address and r["args"]["planId"] == plan.plan_id
    ]
    if len(confirmed) != 1 or confirmed[0]["result"] != (2 if plan.arguments[-1] else 1):
        raise ValueError("UNEXPECTED_SETTLEMENT_RESULT")
    fills = {}
    for log in contract.events.OrderFilled().process_receipt(receipt, errors=DISCARD):
        a = log["args"]
        if log["address"] == contract.address and a["planId"] == plan.plan_id:
            key = Web3.to_hex(a["digest"])
            if key not in plan.quantities or key in fills:
                raise ValueError("UNEXPECTED_FILL")
            sell = int(plan.arguments[2][list(plan.quantities).index(key)][0][0][4]) == 0
            if a["spent" if sell else "received"] != plan.quantities[key]:
                raise ValueError("FILL_QUANTITY_MISMATCH")
            fills[key] = {
                k: str(a[k]) for k in ("spent", "received", "feeUSDT", "cumulativeWHSK", "benchmarkUSDT")
            }
    if fills.keys() != plan.quantities.keys():
        raise ValueError("MISSING_FILL")
    return fills
