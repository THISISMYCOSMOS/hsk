"""Model-selectable operations. The server binds arguments to a confirmed order scope."""

import time
from typing import Literal
import httpx
from pydantic import Field
from sqlalchemy import select
from ..models import tables as db
from ..schemas.orders import Hash, Model
from .intent import Intent, parse_user_intent

Name = Literal[
    "parse_user_intent",
    "get_market_state",
    "get_active_orders",
    "get_wallet_state",
    "generate_execution_candidates",
    "calculate_net_savings",
    "validate_execution_policy",
    "simulate_transaction",
    "request_execution",
    "get_transaction_receipt",
    "explain_execution_result",
]


class NoArgs(Model):
    pass


class Call(Model):
    name: Name
    arguments: NoArgs


class Ask(Model):
    text: str = Field(min_length=1, max_length=1200)
    orderId: Hash | None = None


class ToolOutput(Model):
    name: Name
    data: dict


class LocalPlanner:
    def __init__(self, model):
        self.model = model

    def __call__(self, text, names):
        response = httpx.post(
            "http://127.0.0.1:11434/api/chat",
            timeout=10,
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": "Select the operations needed for this execution question. The server sets all arguments.",
                    },
                    {"role": "user", "content": text},
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": n,
                            "description": n.replace("_", " "),
                            "parameters": NoArgs.model_json_schema(),
                        },
                    }
                    for n in names
                ],
            },
        )
        response.raise_for_status()
        return [c["function"] for c in response.json()["message"].get("tool_calls", [])]


def route_tools(ask, handlers, planner, *, internal=False):
    allowed = {k: v for k, v in handlers.items() if internal or k != "request_execution"}
    started = time.monotonic()
    count = 0
    error = None
    if planner:
        count = 1
        try:
            proposals = planner(ask.text, list(allowed))
            if len(proposals) > 5:
                raise ValueError("TOOL_LIMIT")
            calls = [Call.model_validate(x) for x in proposals]
            if any(c.name not in allowed for c in calls):
                raise ValueError("UNAUTHORIZED_TOOL")
        except (ValueError, KeyError, TypeError, httpx.HTTPError, OSError) as exc:
            calls, error = [], type(exc).__name__
    else:
        calls = []
    if not calls:
        default = "explain_execution_result" if ask.orderId else "parse_user_intent"
        calls = [Call(name=default, arguments=NoArgs())]
    outputs = [ToolOutput(name=c.name, data=allowed[c.name]()).model_dump() for c in calls]
    return dict(
        tools=outputs,
        llmCalls=count,
        plannerError=error,
        latencyMs=round((time.monotonic() - started) * 1000),
    )


def handlers(worker, ask, *, simulation, quote, state, provider):
    store = worker.store

    def order():
        if not ask.orderId:
            raise ValueError("ORDER_SCOPE_REQUIRED")
        with store.engine.connect() as conn:
            return store.public(store.one(conn, ask.orderId))

    def saved():
        order()
        with store.engine.connect() as conn:
            r = (
                conn.execute(
                    select(db.quotes)
                    .where(db.quotes.c.order_id == ask.orderId)
                    .order_by(db.quotes.c.id.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
        return (
            {"quoteId": r["id"], "comparison": r["comparison"]} if r else {"quoteId": None, "comparison": {}}
        )

    def active():
        with store.engine.connect() as conn:
            return {"orderIds": [e.id for e in store.active(conn, int(time.time()))]}

    def wallet():
        o = order()["order"]
        if worker.mode != "READ_ONLY":
            return {"evidence": "UNVERIFIED", "balance": None, "allowance": None}
        p = provider()
        return {"balance": p.get_wallet_balance(o["maker"], o["tokenIn"]), "allowance": None}

    def policy():
        return {
            "status": order()["status"],
            "approval": order()["order"],
            "selected": saved()["comparison"].get("selected"),
        }

    def savings():
        c = saved()["comparison"].get("selected")
        return {
            "users": c["savings"] if c else [],
            "totalUSDT": c["totalConservativeSavingUSDT"] if c else None,
        }

    def receipt():
        order()
        with store.engine.connect() as conn:
            r = conn.scalar(
                select(db.executions.c.receipt)
                .join(db.fills, db.fills.c.execution_id == db.executions.c.id)
                .where(db.fills.c.order_id == ask.orderId)
                .order_by(db.executions.c.id.desc())
                .limit(1)
            )
        return {"receipt": r}

    def request():
        if order()["status"] != "OPEN":
            raise ValueError("ORDER_NOT_OPEN")
        with store.write() as conn:
            store.emit(conn, "ORDER_RECHECK", {"orderId": ask.orderId}, work=True)
        return {"queued": True}

    return dict(
        parse_user_intent=lambda: parse_user_intent(Intent(text=ask.text)),
        get_active_orders=active,
        get_market_state=state,
        get_wallet_state=wallet,
        generate_execution_candidates=lambda: quote(order()["orderId"]),
        calculate_net_savings=savings,
        validate_execution_policy=policy,
        simulate_transaction=lambda: simulation(saved()["quoteId"])
        if saved()["quoteId"]
        else {"reason": "NO_QUOTE"},
        request_execution=request,
        get_transaction_receipt=receipt,
        explain_execution_result=lambda: {"order": order(), "comparison": saved(), "receipt": receipt()},
    )
