import asyncio
from contextlib import asynccontextmanager, suppress
import json
import os
import time
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from ..agent.intent import Intent, parse_user_intent
from ..agent.worker import Worker
from ..agent.tools import Ask, LocalPlanner, handlers, route_tools
from ..execution.mock import check
from ..models import tables as db
from ..monitoring.usage import Usage
from ..economics.operator import operator_summary
from fastapi.exceptions import RequestValidationError
from ..orderbook.signatures import typed_data
from ..orderbook.store import Store
from ..quote_engine.market import synthetic_snapshot
from ..quote_engine.provider import read_market
from ..schemas.orders import Cancel, Order, Registration
from ..schemas.results import (
    AgentEvent,
    ExecutionReceipt,
    OrderView,
    QuoteRequest,
    QuoteView,
    SimulationResult,
)


def create_app(url=None, mode=None, market=None, run_worker=True, fork_execution=None, planner=None):
    mode = mode or os.getenv("HSK_EXECUTION_MODE", "READ_ONLY")
    store = Store(url or os.getenv("HSK_ENGINE_DB", "sqlite:///backend/hsk-engine.db"))
    use_default_reads = mode == "READ_ONLY" and market is None
    use_monitor = use_default_reads and run_worker
    usage = Usage()
    market = market or (synthetic_snapshot if mode == "MOCK" else lambda: read_market(usage.provider()))
    worker = Worker(store, market, mode, fork_execution=fork_execution)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker.run()) if run_worker else None
        monitor_task = None
        if use_monitor:
            from ..monitoring.chain import ChainMonitor

            monitor = ChainMonitor(worker, usage.provider, os.getenv("HSK_MONITOR_SPENDER"))
            monitor_task = asyncio.create_task(monitor.run())
        yield
        if monitor_task:
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        store.engine.dispose()

    app = FastAPI(title="HSK Smart Execution", version="0.1.0", lifespan=lifespan)
    app.state.worker = worker
    model = os.getenv("HSK_LOCAL_PLANNER_MODEL")
    planner = planner or (LocalPlanner(model) if model else None)

    @app.post("/agent/ask")
    def ask_tools(ask: Ask):
        tools = handlers(
            worker,
            ask,
            simulation=simulate,
            quote=lambda id_: quote(QuoteRequest(orderId=id_)),
            state=state,
            provider=usage.provider,
        )
        result = route_tools(ask, tools, planner)
        if result["llmCalls"]:
            with store.write() as conn:
                store.emit(
                    conn,
                    "AI_CALL",
                    {"latencyMs": result["latencyMs"], "error": result["plannerError"], "costUSDT": None},
                )
        return result

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}, status_code=422
        )

    @app.exception_handler(ValueError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "NOT_FOUND"}, status_code=404)

    def snapshot():
        try:
            return market()
        except (RuntimeError, OSError, ValueError) as exc:
            raise HTTPException(503, "MARKET_UNAVAILABLE") from exc

    def row(conn, table, id_):
        result = conn.execute(select(table).where(table.c.id == id_)).mappings().first()
        if not result:
            raise KeyError(id_)
        return result

    @app.post("/orders/typed-data")
    def sign(order: Order):
        return typed_data(order)

    @app.post("/orders/settlement-typed-data")
    def settlement_typed(order: Order):
        if mode != "FORK" or fork_execution is None:
            raise HTTPException(409, "FORK_ADAPTER_REQUIRED")
        return fork_execution.typed(order)

    @app.post("/orders", response_model=OrderView)
    async def register(request: Registration):
        proof = None
        if mode == "FORK":
            if not fork_execution:
                raise HTTPException(503, "FORK_ADAPTER_REQUIRED")
            proof = fork_execution.authorization(request.order, request.settlementSignature)
        elif request.settlementSignature:
            raise ValueError("UNEXPECTED_SETTLEMENT_SIGNATURE")
        digest = await asyncio.to_thread(store.register, request, int(time.time()), proof)
        worker.wakeup.set()
        return order_by_id(digest)

    @app.get("/orders", response_model=list[OrderView])
    def orders(limit: int = Query(100, ge=1, le=500)):
        with store.engine.connect() as conn:
            return [
                store.public(r)
                for r in conn.execute(
                    select(db.orders).order_by(db.orders.c.id.desc()).limit(limit)
                ).mappings()
            ]

    @app.get("/orderbook", response_model=list[OrderView])
    def book():
        with store.engine.connect() as conn:
            return [store.public(store.one(conn, e.id)) for e in store.active(conn, int(time.time()))]

    @app.get("/orders/{order_id}", response_model=OrderView)
    def order_by_id(order_id: str):
        with store.engine.connect() as conn:
            return store.public(store.one(conn, order_id))

    @app.get("/orders/{order_id}/cancel-typed-data")
    def cancel_data(order_id: str):
        order_by_id(order_id)
        return typed_data(cancel=order_id)

    @app.post("/orders/{order_id}/cancel", response_model=OrderView)
    async def cancel(order_id: str, request: Cancel):
        await asyncio.to_thread(store.cancel, order_id, request.signature)
        worker.wakeup.set()
        return order_by_id(order_id)

    @app.post("/quotes", response_model=QuoteView)
    def quote(request: QuoteRequest):
        now = int(time.time())
        with store.write() as conn:
            book = store.active(conn, now)
            entry = next((e for e in book if e.id == request.orderId), None)
            if entry is None:
                raise ValueError("ORDER_NOT_OPEN")
            try:
                id_, result = worker.evaluate(conn, entry, book, snapshot(), now, execute=False)
            except OSError as exc:
                raise HTTPException(503, "RPC_UNAVAILABLE") from exc
            return dict(quoteId=str(id_), orderId=entry.id, comparison=result)

    @app.get("/quotes/{quote_id}", response_model=QuoteView)
    def get_quote(quote_id: int):
        with store.engine.connect() as conn:
            r = row(conn, db.quotes, quote_id)
            return dict(quoteId=str(quote_id), orderId=r["order_id"], comparison=r["comparison"])

    @app.post("/quotes/{quote_id}/simulate", response_model=SimulationResult)
    def simulate(quote_id: int):
        with store.write() as conn:
            q = row(conn, db.quotes, quote_id)
            receipt, reason = None, "SETTLEMENT_ADAPTER_REQUIRED"
            if mode == "MOCK":
                m = snapshot()
                if q["comparison"]["blockHash"] != m.block_hash:
                    reason = "STALE_SNAPSHOT"
                else:
                    receipt, reason = check(
                        store,
                        conn,
                        q["order_id"],
                        q["comparison"]["selected"],
                        m,
                        int(time.time()),
                        worker.limits,
                    )
            elif fork_execution and mode == "FORK":
                from web3.exceptions import ContractLogicError

                entry = next((e for e in store.active(conn, int(time.time())) if e.id == q["order_id"]), None)
                reason = "ORDER_NOT_OPEN" if not entry else "NO_MATCH"
                if entry and q["comparison"]["selected"]:
                    try:
                        fork_execution.prepare(
                            store, conn, entry, q["comparison"], quote_id, int(time.time()), preview=True
                        )
                        reason = None
                    except (ValueError, ContractLogicError) as exc:
                        reason = str(exc)[:160]
            return dict(
                mode=mode,
                evidence="SYNTHETIC"
                if mode == "MOCK"
                else "FORK_SIMULATION"
                if fork_execution
                else "UNVERIFIED",
                success=reason is None,
                reason=reason,
                receipt=receipt,
            )

    @app.post("/agent/intent")
    def intent(request: Intent):
        return parse_user_intent(request)

    @app.get("/agent/status")
    def status():
        with store.engine.connect() as conn:
            last = conn.scalar(select(db.events.c.kind).order_by(db.events.c.id.desc()).limit(1))
            pending = conn.scalar(select(func.count()).select_from(db.outbox).where(db.outbox.c.done == 0))
        return dict(
            mode=mode,
            state=last or "IDLE",
            pending=pending,
            lastError=worker.last_error,
            policyDomain="SandboxOrder",
            broadcastEnabled=bool(fork_execution and mode == "FORK"),
            mainnetBroadcastEnabled=False,
        )

    def read_events(after):
        with store.engine.connect() as conn:
            return [
                AgentEvent(**{k: r[k] for k in ("id", "at", "kind", "payload")}).model_dump()
                for r in conn.execute(
                    select(db.events).where(db.events.c.id > after).order_by(db.events.c.id).limit(200)
                ).mappings()
            ]

    @app.get("/agent/events", response_model=list[AgentEvent])
    def event_list(after: int = Query(0, ge=0)):
        return read_events(after)

    @app.get("/agent/events/stream", response_class=StreamingResponse)
    async def stream(request: Request, after: int = Query(0, ge=0), last_event_id: int = Header(0, ge=0)):
        async def generate():
            cursor = max(after, last_event_id)
            while not await request.is_disconnected():
                items = await asyncio.to_thread(read_events, cursor)
                for item in items:
                    cursor = item["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(item)}\n\n"
                if not items:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(1)

        return StreamingResponse(
            generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.get("/executions")
    def executions():
        with store.engine.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    select(db.executions).order_by(db.executions.c.id.desc()).limit(100)
                ).mappings()
            ]

    @app.get("/executions/{execution_id}")
    def execution(execution_id: int):
        with store.engine.connect() as conn:
            return dict(row(conn, db.executions, execution_id))

    @app.get("/executions/{execution_id}/comparison", response_model=QuoteView)
    def comparison(execution_id: int):
        with store.engine.connect() as conn:
            plan = row(conn, db.plans, row(conn, db.executions, execution_id)["plan_id"])
            return get_quote(plan["quote_id"])

    @app.get("/executions/{execution_id}/receipt", response_model=ExecutionReceipt)
    def receipt(execution_id: int):
        result = execution(execution_id)["receipt"]
        if result is None:
            raise HTTPException(409, "RECEIPT_UNAVAILABLE")
        return result

    @app.get("/market/state")
    def state():
        m = snapshot()
        return dict(evidence=m.evidence, blockNumber=str(m.block_number), blockHash=m.block_hash)

    @app.get("/market/pools")
    def pools():
        if use_default_reads:
            try:
                row = usage.provider().get_pool_state("0x4ff515761864e7838b0adb8b5b2b8b7a068905dc")
                if row.get("error"):
                    raise ValueError("POOL_UNAVAILABLE")
                return row
            except (OSError, RuntimeError, ValueError) as exc:
                raise HTTPException(503, "POOL_UNAVAILABLE") from exc
        return dict(
            pair="WHSK/USDT",
            source="HSKSwap",
            feePips=3000,
            address="0x4ff515761864e7838b0adb8b5b2b8b7a068905dc",
            evidence="SYNTHETIC" if mode == "MOCK" else "UNVERIFIED",
        )

    @app.get("/market/gas")
    def gas():
        if use_default_reads:
            try:
                p = usage.provider()
                gas_price = int(p.rpc.one("eth_gasPrice", []), 16)
                return dict(
                    chainId="177",
                    gasPriceWei=str(gas_price),
                    evidence="OBSERVED_MAINNET",
                    l1UpperWei=None,
                    l2UpperWei=None,
                    queriedAt=int(time.time()),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                raise HTTPException(503, "GAS_UNAVAILABLE") from exc
        return dict(mode=mode, l1UpperWei=None, l2UpperWei=None, evidence="UNVERIFIED")

    @app.get("/metrics")
    def metrics():
        with store.engine.connect() as conn:
            return {
                **{
                    t.name: conn.scalar(select(func.count()).select_from(t))
                    for t in (db.orders, db.events, db.quotes, db.executions)
                },
                "agentARpcMethodsSinceStart": usage.snapshot(),
                "llmCalls": conn.scalar(
                    select(func.count()).select_from(db.events).where(db.events.c.kind == "AI_CALL")
                ),
            }

    @app.get("/health")
    def health():
        metrics()
        return dict(status="ok", mode=mode)

    @app.get("/costs")
    def costs():
        with store.engine.connect() as conn:
            return dict(
                userCosts=[dict(r) for r in conn.execute(select(db.costs)).mappings()],
                operator=operator_summary(
                    conn.execute(select(db.executions)).mappings(),
                    chain_mode=mode,
                    ai_calls=metrics()["llmCalls"],
                ),
                evidence="SYNTHETIC" if mode == "MOCK" else "UNVERIFIED",
            )

    return app
