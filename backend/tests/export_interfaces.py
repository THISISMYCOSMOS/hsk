"""Export API and signed, expired synthetic examples for frontend and contract consumers."""

import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from eth_account import Account
from fastapi.testclient import TestClient
from pydantic.json_schema import models_json_schema
from backend.app.api.main import create_app
from backend.app.schemas import results as r
from backend.app.schemas.orders import Order, SignedOrder
from backend.app.orderbook.signatures import recover, typed_data
from .conftest import sign, terms

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "shared" / "engine-0.1"
MODELS = [
    Order,
    SignedOrder,
    r.MarketSnapshot,
    r.DexQuote,
    r.ExecutionCandidate,
    r.ExecutionPlan,
    r.CostBreakdown,
    r.UserSavings,
    r.SimulationResult,
    r.ExecutionReceipt,
    r.AgentEvent,
]


def dump(path, data):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def export():
    SHARED.mkdir(exist_ok=True, parents=True)
    fixture = SHARED / "fixtures.json"
    if fixture.exists():
        inputs = json.loads(fixture.read_text())["signedOrders"]
    else:
        accounts = [Account.create() for _ in range(2)]
        inputs = [
            sign(a, terms(a, sell, allowPartial=False, expiry="1700001000")).model_dump()
            for a, sell in zip(accounts, (True, False))
        ]
    with tempfile.TemporaryDirectory() as folder, patch("time.time", return_value=1700000000):
        app = create_app("sqlite:///" + str(Path(folder) / "example.db"), "MOCK", run_worker=False)
        with TestClient(app) as api:
            ids = [api.post("/orders", json=s).json()["orderId"] for s in inputs]
            for s, d in zip(inputs, ids):
                order = Order(**s["order"])
                assert recover(typed_data(order), s["signature"], order.maker) == d
            q = api.post("/quotes", json={"orderId": ids[0]}).json()
            comp = q["comparison"]
            candidate = comp["selected"]
            cost = candidate["savings"][0]
            sim = api.post("/quotes/" + q["quoteId"] + "/simulate").json()
            app.state.worker.step()
            receipt = api.get("/executions/1/receipt").json()
            snapshot = api.get("/market/state").json()
            examples = dict(
                Order=inputs[0]["order"],
                SignedOrder=inputs[0],
                MarketSnapshot=snapshot,
                DexQuote=dict(
                    **snapshot,
                    tokenIn=order.tokenOut,
                    tokenOut=order.tokenIn,
                    amountIn=candidate["fixedFilled"],
                    amountOut=cost["dexGross"],
                ),
                ExecutionCandidate=candidate,
                ExecutionPlan=dict(orderId=ids[0], blockHash=comp["blockHash"], candidate=candidate),
                CostBreakdown=cost["costs"],
                UserSavings=cost,
                SimulationResult=sim,
                ExecutionReceipt=receipt,
                AgentEvent=api.get("/agent/events").json()[0],
            )
            for m in MODELS:
                m.model_validate(examples[m.__name__])
            dump(
                fixture,
                dict(
                    version="0.1",
                    evidence="SYNTHETIC",
                    signedOrders=inputs,
                    typedData=typed_data(Order(**inputs[0]["order"])),
                    examples=examples,
                ),
            )
            dump(ROOT / "docs/agents/agent-b/openapi.json", app.openapi())
    _, schema = models_json_schema([(m, "validation") for m in MODELS])
    dump(
        SHARED / "schemas.json",
        {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:hsk:engine:0.1", **schema},
    )


if __name__ == "__main__":
    export()
