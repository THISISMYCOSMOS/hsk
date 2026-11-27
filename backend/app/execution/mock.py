"""Deterministic local ledger. MOCK state has no EVM transaction hash or receipt."""

from collections import defaultdict
from dataclasses import dataclass
from sqlalchemy import select
from ..models import tables as db
from ..orderbook.signatures import recover, typed_data
from ..schemas.orders import Order, WHSK, USDT


@dataclass
class MockLimits:
    balance_whsk: int = 100_000 * 10**18
    balance_usdt: int = 100_000 * 10**6
    allowance: int = 2**256 - 1
    gas_budget: int = 5_000_000
    gas_base: int = 60_000
    gas_per_user: int = 30_000
    revert: bool = False


def check(store, conn, taker_id, candidate, market, now, limits):
    if not candidate or not candidate["eligible"]:
        return None, "NO_MATCH"
    if market.evidence != "SYNTHETIC":
        return None, "MOCK_MARKET_REQUIRED"
    participants = [(taker_id, int(candidate["fixedFilled"]))] + [
        (f["orderId"], int(f["fixed"])) for f in candidate["fills"]
    ]
    gas = limits.gas_base + limits.gas_per_user * len(participants)
    # Funding is shared across every order from the same wallet.
    deltas = defaultdict(int)
    spent = defaultdict(int)
    for receipt in conn.scalars(
        select(db.executions.c.receipt).where(db.executions.c.status == "MOCK_CONFIRMED")
    ):
        for w in receipt["walletDeltas"]:
            key = (w["maker"], w["token"])
            deltas[key] += int(w["change"])
            spent[key] += int(w["debited"])
    changes = []
    for (id_, size), s in zip(participants, candidate["savings"], strict=True):
        r = store.one(conn, id_)
        o = Order(**r["body"])
        if (
            r["status"] != "OPEN"
            or int(o.expiry) < now
            or not 0 < size <= int(r["remaining"])
            or (not o.allowPartial or o.timing == "IMMEDIATE")
            and size != int(r["remaining"])
        ):
            return None, "INVALID_ORDER"
        if recover(typed_data(o), r["signature"], r["maker"]) != id_:
            return None, "INVALID_ORDER"
        cash = int(s["gross"])
        fee = sum(int(v) for k, v in s["costs"].items() if k != "dex_lower")
        # Fixture charges the full upper bound including margin; explicitly conservative.
        if (
            fee > int(o.maxCost)
            or (cash - fee < o.limit(size) if o.selling else cash + fee > o.limit(size))
            or int(s["conservativeSaving"]) < int(o.minSaving)
        ):
            return None, "ORDER_LIMIT"
        for token, delta in (
            (WHSK, -size if o.selling else size),
            (USDT, cash - fee if o.selling else -cash - fee),
        ):
            key = (o.maker, token)
            initial = limits.balance_whsk if token == WHSK else limits.balance_usdt
            debit = max(0, -delta)
            # Credits within the same candidate may not fund other orders.
            if initial + deltas[key] < debit:
                return None, "INSUFFICIENT_BALANCE"
            if spent[key] + debit > limits.allowance:
                return None, "INSUFFICIENT_ALLOWANCE"
            if debit:
                deltas[key] -= debit
            spent[key] += debit
            changes.append(dict(maker=o.maker, token=token, change=str(delta), debited=str(debit)))
    if limits.revert:
        return None, "SIMULATION_FAILED"
    if gas > limits.gas_budget:
        return None, "GAS_BUDGET_EXCEEDED"
    return dict(
        evidence="SYNTHETIC",
        mode="MOCK",
        blockHash=market.block_hash,
        gasUnits=str(gas),
        walletDeltas=changes,
        transactionHash=None,
        participants=[dict(orderId=i, fixed=str(q)) for i, q in participants],
    ), None


def settle(store, conn, plan_id, candidate, receipt, now):
    ids = receipt["participants"]
    for fill in ids:
        store.status(conn, fill["orderId"], "RESERVED", reservation=str(plan_id), lease_until=now + 30)
    eid = conn.execute(
        db.executions.insert().values(plan_id=plan_id, status="MOCK_CONFIRMED", receipt=receipt)
    ).inserted_primary_key[0]
    for fill, s in zip(ids, candidate["savings"], strict=True):
        digest = fill["orderId"]
        row = store.one(conn, digest)
        left = int(row["remaining"]) - int(fill["fixed"])
        store.status(
            conn,
            digest,
            "OPEN" if left else "FILLED",
            remaining=str(left),
            lease_until=None,
            reservation=None,
        )
        conn.execute(db.fills.insert().values(order_id=digest, execution_id=eid, fixed=fill["fixed"]))
        conn.execute(db.costs.insert().values(execution_id=eid, payer=digest, breakdown=s["costs"]))
    return eid
