"""Internal-only execution on a local Anvil IPC fork. Separate signed policy and settlement order."""

import copy
from sqlalchemy import select
from web3 import Web3, IPCProvider
from ..models import tables as db
from ..orderbook.signatures import recover
from .settlement import Prepared, abi_order, build, chain_message, preflight, project, reconcile


class ForkExecution:
    def __init__(self, w3, contract, signer, journal, *, gas_limit, fee_cap_wei, l1_upper_wei, budget_wei):
        if (
            not isinstance(w3.provider, IPCProvider)
            or w3.eth.chain_id != 31337
            or "anvil" not in w3.client_version.lower()
            or contract.functions.operator().call() != signer.address
        ):
            raise ValueError("LOCAL_FORK_REQUIRED")
        self.w3, self.contract, self.signer, self.journal = w3, contract, signer, journal
        self.budgets = dict(
            gas_limit=gas_limit, fee_cap_wei=fee_cap_wei, l1_upper_wei=l1_upper_wei, budget_wei=budget_wei
        )

    def typed(self, order):
        # Full policy and this exact derived transaction authority are both shown to the signer.
        body = project(
            order,
            recipient=order.maker,
            operator=self.signer.address,
            valid_after=0,
            max_service_fee=int(order.maxCost),
        )
        return chain_message(self.contract, 31337, body)

    def authorization(self, order, signature):
        if not signature:
            raise ValueError("SETTLEMENT_SIGNATURE_REQUIRED")
        msg = self.typed(order)
        digest = recover(msg, signature, order.maker)
        return dict(digest=digest, body=msg["message"], signature=signature)

    def prepare(self, store, conn, entry, result, qid, now, *, preview=False):
        if conn.scalar(
            select(db.executions.c.id).where(db.executions.c.status == "PENDING_CONFIRMATION").limit(1)
        ):
            raise ValueError("OPERATOR_NONCE_PENDING")
        selected = copy.deepcopy(result["selected"])
        ids = [entry.id] + [f["orderId"] for f in selected["fills"]]
        mapping, signed = {}, {}
        header = self.w3.eth.get_block("latest")
        deadlines = [header.timestamp + 60]
        for id_ in ids:
            row = store.one(conn, id_)
            proof = row["settlement"]
            if not proof:
                raise ValueError("SETTLEMENT_SIGNATURE_REQUIRED")
            chain_id = proof["digest"]
            body = proof["body"]
            if self.contract.functions.filledAmount(chain_id).call() != int(row["body"]["fixedAmount"]) - int(
                row["remaining"]
            ):
                raise ValueError("CUMULATIVE_FILL_MISMATCH")
            mapping[id_] = chain_id
            signed[chain_id] = body, proof["signature"]
            deadlines.append(int(body["deadline"]))
        for item in selected["fills"] + selected["savings"]:
            item["orderId"] = mapping[item["orderId"]]
        plan = build(
            self.contract,
            31337,
            self.signer.address,
            result | {"selected": selected},
            mapping[entry.id],
            signed,
            min(deadlines),
        )
        tx, estimate = preflight(self.w3, self.contract, plan, **self.budgets)
        if preview:
            return {"gasEstimate": str(estimate), "blockHash": plan.block_hash, "evidence": "FORK_SIMULATION"}
        plan_view = dict(orderId=entry.id, blockHash=plan.block_hash, candidate=result["selected"])
        pid = conn.execute(db.plans.insert().values(quote_id=qid, plan=plan_view)).inserted_primary_key[0]
        eid = conn.execute(
            db.executions.insert().values(plan_id=pid, status="PENDING_CONFIRMATION")
        ).inserted_primary_key[0]
        conn.execute(
            db.jobs.insert().values(
                execution_id=eid,
                plan_hash=Web3.to_hex(plan.plan_id),
                tx=tx,
                block_hash=plan.block_hash,
                mapping=mapping,
                quantities={k: str(v) for k, v in plan.quantities.items()},
                estimate=str(estimate),
                fallback=bool(plan.arguments[-1]),
            )
        )
        for id_ in ids:
            store.status(conn, id_, "PENDING_CONFIRMATION", reservation=str(pid), lease_until=None)
        store.emit(conn, "PENDING_CONFIRMATION", {"executionId": str(eid), "mode": "FORK"})
        return eid

    def process(self, store):
        with store.write() as conn:
            job = (
                conn.execute(
                    select(db.jobs)
                    .join(db.executions, db.executions.c.id == db.jobs.c.execution_id)
                    .where(db.executions.c.status == "PENDING_CONFIRMATION")
                    .order_by(db.jobs.c.execution_id)
                )
                .mappings()
                .first()
            )
            if not job:
                return False
            eid, tx = job["execution_id"], job["tx"]
            # Decode only persisted internally generated calldata. SQL API never returns the jobs table.
            _, decoded = self.contract.decode_function_input(tx["data"])
            args = next(iter(decoded.values()))
            legs = []
            for leg in args["legs"]:
                body = leg["signedOrder"]["order"]
                legs.append(
                    (
                        (abi_order(self.contract, body), leg["signedOrder"]["signature"]),
                        leg["directWHSK"],
                        leg["directUSDT"],
                        leg["feeUSDT"],
                    )
                )
            plan = Prepared(
                (
                    args["planId"],
                    args["executionDeadline"],
                    legs,
                    args["dexWHSK"],
                    args["dexCashLimit"],
                    args["tryFallback"],
                ),
                {k: tx[k] for k in ("from", "to", "data", "value")},
                bytes.fromhex(job["plan_hash"][2:]),
                {k: int(v) for k, v in job["quantities"].items()},
                job["block_hash"],
            )
            try:
                digest = self.journal.submit_local(self.w3, plan, tx, self.signer)
            except ValueError as exc:
                if str(exc) != "STALE_SNAPSHOT":
                    raise
                self.release(store, conn, job, "STALE_SNAPSHOT", None)
                return True
            receipt = self.journal.lookup(self.w3, digest)
            if receipt is None:
                return False
            common = dict(
                mode="FORK",
                evidence="FORK_SIMULATION",
                transactionHash=digest,
                blockHash=Web3.to_hex(receipt.blockHash),
                gasUnits=str(receipt.gasUsed),
                effectiveGasPriceWei=str(receipt.effectiveGasPrice),
                walletDeltas=[],
            )
            if receipt.status != 1:
                self.release(store, conn, job, "TRANSACTION_FAILED", common | {"participants": []})
                self.journal.confirm(digest, "FAILED")
                return True
            actual = reconcile(self.w3, self.contract, plan, receipt)
            participants = []
            for local, chain in job["mapping"].items():
                row = store.one(conn, local)
                remaining = int(row["body"]["fixedAmount"]) - int(actual[chain]["cumulativeWHSK"])
                if not 0 <= remaining == int(row["remaining"]) - plan.quantities[chain]:
                    raise ValueError("RECONCILIATION_MISMATCH")
                store.status(
                    conn, local, "OPEN" if remaining else "FILLED", remaining=str(remaining), reservation=None
                )
                conn.execute(
                    db.fills.insert().values(
                        order_id=local, execution_id=eid, fixed=str(plan.quantities[chain])
                    )
                )
                participants.append(dict(orderId=local, settlementDigest=chain, **actual[chain]))
                conn.execute(
                    db.costs.insert().values(
                        execution_id=eid,
                        payer=local,
                        breakdown={"serviceUSDT": actual[chain]["feeUSDT"], "evidence": "FORK_SIMULATION"},
                    )
                )
            result = common | {"participants": participants}
            conn.execute(
                db.executions.update()
                .where(db.executions.c.id == eid)
                .values(status="FORK_CONFIRMED", receipt=result)
            )
            self.journal.confirm(digest, "CONFIRMED")
            store.emit(
                conn, "TRANSACTION_CONFIRMED", {"executionId": str(eid), "evidence": "FORK_SIMULATION"}
            )
            store.emit(conn, "RECONCILIATION", {"executionId": str(eid)})
            store.emit(conn, "BALANCE_CHANGED", {"executionId": str(eid)}, work=True)
            return True

    def release(self, store, conn, job, reason, receipt):
        for id_ in job["mapping"]:
            row = store.one(conn, id_)
            status = "UNFILLED" if row["body"]["timing"] == "IMMEDIATE" else "OPEN"
            store.status(conn, id_, status, reservation=None)
        conn.execute(
            db.executions.update()
            .where(db.executions.c.id == job["execution_id"])
            .values(status=reason, receipt=receipt)
        )
        store.emit(conn, reason, {"executionId": str(job["execution_id"])})
