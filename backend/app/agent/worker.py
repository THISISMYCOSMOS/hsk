import asyncio
import time
from sqlalchemy import select
from web3.exceptions import ContractLogicError, Web3Exception
from sqlalchemy.exc import OperationalError
from ..models import tables as db
from ..optimizer.search import Search, compare, select_candidate
from ..execution.mock import MockLimits, check, settle

MARKET_EVENTS = {
    "POOL_SWAP",
    "POOL_LIQUIDITY_CHANGED",
    "GAS_COST_CHANGED",
    "BALANCE_CHANGED",
    "ALLOWANCE_CHANGED",
}


class Worker:
    def __init__(self, store, market, mode="READ_ONLY", limits=None, fork_execution=None):
        if mode not in {"READ_ONLY", "MOCK", "FORK", "TESTNET", "MAINNET"}:
            raise ValueError("invalid mode")
        self.store, self.market, self.mode = store, market, mode
        self.limits = limits or MockLimits()
        self.fork = fork_execution if mode == "FORK" else None
        self.wakeup = asyncio.Event()
        self.last_error = None

    def evaluate(self, conn, entry, book, market, now, *, execute):
        def state(name, **items):
            self.store.emit(conn, name, dict(orderId=entry.id, **items))

        state("FILTERING")
        state("QUOTE_GENERATION")
        others = [e for e in book if e.sequence <= entry.sequence or entry.order.timing != "IMMEDIATE"]
        sizes = tuple(entry.remaining // 2**k for k in range(1, 9)) if entry.order.allowPartial else ()
        result = compare(entry, others, market, now, Search(sizes=sizes))
        state("OPTIMIZATION")
        qid = conn.execute(
            db.quotes.insert().values(order_id=entry.id, comparison=result)
        ).inserted_primary_key[0]
        state("ECONOMIC_VALIDATION", quoteId=str(qid))
        while (selected := result["selected"]) and (self.mode == "MOCK" or self.fork):
            state("SIMULATION")
            receipt = None
            reason = None
            if self.fork:
                try:
                    self.fork.prepare(self.store, conn, entry, result, qid, now, preview=not execute)
                except (ValueError, ContractLogicError) as exc:
                    reason = str(exc)[:160] if isinstance(exc, ValueError) else "SIMULATION_FAILED"
            else:
                receipt, reason = check(
                    self.store, conn, entry.id, selected, market, int(time.time()), self.limits
                )
            if reason:
                selected.update(eligible=False, reason=reason)
                state(reason)
                result["selected"] = select_candidate(entry, result["candidates"])
                continue
            state("FINAL_STATE_CHECK")
            if execute and self.mode == "MOCK":
                plan = dict(orderId=entry.id, blockHash=market.block_hash, candidate=selected)
                pid = conn.execute(db.plans.insert().values(quote_id=qid, plan=plan)).inserted_primary_key[0]
                state("SUBMISSION", mode="MOCK")
                eid = settle(self.store, conn, pid, selected, receipt, now)
                state("CONFIRMATION", executionId=str(eid), evidence="SYNTHETIC")
                state("RECONCILIATION")
            break
        if not result["selected"]:
            reasons = {c["reason"] for c in result["candidates"]}
            state(
                next((r for r in ("COST_BOUND_UNKNOWN", "INSUFFICIENT_SAVING") if r in reasons), "NO_MATCH")
            )
        tested = [
            int(c["fixedFilled"]) - int(c["dexFixed"])
            for c in result["candidates"]
            if c["eligible"] and c["fills"]
        ]
        result["smallestEconomicFillTested"] = str(min(tested)) if tested else None
        conn.execute(db.quotes.update().where(db.quotes.c.id == qid).values(comparison=result))
        if (
            execute
            and entry.order.timing == "IMMEDIATE"
            and self.store.one(conn, entry.id)["status"] == "OPEN"
        ):
            self.store.status(conn, entry.id, "UNFILLED")
        return qid, result

    def step(self):
        if self.fork and self.fork.process(self.store):
            return True
        now = int(time.time())
        with self.store.write() as conn:
            self.store.expire(conn, now)
            rows = list(
                conn.execute(
                    select(db.outbox.c.id, db.events.c.kind, db.events.c.payload)
                    .join(db.events, db.events.c.id == db.outbox.c.event_id)
                    .where(db.outbox.c.done == 0)
                    .order_by(db.outbox.c.id)
                    .limit(64)
                ).mappings()
            )
            if not rows:
                return False
            book = self.store.active(conn, now)
            by_id = {e.id: e for e in book}
            ids = dict.fromkeys(
                r["payload"]["orderId"] for r in rows if r["kind"] in ("ORDER_CREATED", "ORDER_RECHECK")
            )
            if any(r["kind"] in MARKET_EVENTS for r in rows):
                ids.update(by_id)
            ids = [i for i in ids if i in by_id]
            if ids:
                self.store.emit(conn, "EVENT_DETECTED", {"orders": len(ids)})
                market = self.market()
                for id_ in ids:
                    book = self.store.active(conn, int(time.time()))
                    entry = next((e for e in book if e.id == id_), None)
                    if entry:
                        self.evaluate(conn, entry, book, market, now, execute=True)
            conn.execute(db.outbox.update().where(db.outbox.c.id.in_([r["id"] for r in rows])).values(done=1))
            self.store.emit(conn, "IDLE", {})
            return True

    async def run(self):
        delay = 1
        while True:
            self.wakeup.clear()
            try:
                more = await asyncio.to_thread(self.step)
                delay = 1
                self.last_error = None
                if more:
                    continue
            except (OSError, ValueError, RuntimeError, Web3Exception, OperationalError) as exc:
                if self.last_error is None:
                    with self.store.write() as conn:
                        self.store.emit(conn, "RPC_UNAVAILABLE", {"reason": type(exc).__name__})
                self.last_error = type(exc).__name__
                delay = min(30, 2 * delay)
            try:
                await asyncio.wait_for(self.wakeup.wait(), delay)
            except TimeoutError:
                pass
