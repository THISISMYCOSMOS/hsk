from types import SimpleNamespace
from sqlalchemy import select
from eth_account import Account
import pytest
from fastapi.testclient import TestClient
from backend.app.api.main import create_app
from backend.app.monitoring.chain import ChainMonitor, TOPICS, POOL
from backend.app.models import tables as db
from conftest import terms, sign


def test_monitor_resume(app):
    worker = app.state.worker

    class RPC:
        height = 20
        down = False

        def block(self, n):
            if self.down:
                raise OSError("unavailable")
            n = self.height if n == "finalized" else n
            return {"hash": hex(n), "number": hex(n)}

        def one(self, method, args):
            if method == "eth_gasPrice":
                return "0x10"
            return [
                dict(
                    blockNumber=hex(self.height),
                    blockHash=hex(self.height),
                    logIndex="0x1",
                    topics=[next(iter(TOPICS))],
                    address=POOL,
                )
            ]

    rpc = RPC()
    provider = SimpleNamespace(
        rpc=rpc, get_wallet_balance=lambda *args: {"data": "1", "block_hash": hex(rpc.height)}
    )
    monitor = ChainMonitor(worker, lambda: provider)
    assert not monitor.poll()
    a = Account.create()
    worker.store.register(sign(a, terms(a)), 0)
    assert monitor.poll()
    assert not monitor.poll()
    rpc.down = True
    with pytest.raises(OSError):
        monitor.poll()
    rpc.down = False
    rpc.height += 1
    assert ChainMonitor(worker, lambda: provider).poll()
    with worker.store.engine.connect() as conn:
        ids = list(conn.scalars(select(db.events.c.source_key).where(db.events.c.kind == "POOL_SWAP")))
        assert ids == ["0x14:1", "0x15:1"]
        assert conn.scalar(select(db.cursor.c.height)) == 21


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "request_execution", "arguments": {}},
        {"name": "simulate_transaction", "arguments": {"calldata": "0x0000"}},
    ],
)
def test_planner_scope(tmp_path, bad):
    app = create_app(
        "sqlite:///" + str(tmp_path / "p.db"), "MOCK", run_worker=False, planner=lambda *_: [bad]
    )
    api = TestClient(app)
    r = api.post("/agent/ask", json={"text": "WHSK 1개 매도"}).json()
    assert r["plannerError"] and r["tools"][0]["name"] == "parse_user_intent"
    assert api.get("/metrics").json()["llmCalls"] == 1
    assert api.get("/executions").json() == []
    assert api.get("/costs").json()["operator"]["aiUSDT"] is None


def test_planner_reads_only_selected_tools(tmp_path):
    app = create_app(
        "sqlite:///" + str(tmp_path / "q.db"),
        "MOCK",
        run_worker=False,
        planner=lambda *_: [{"name": "get_active_orders", "arguments": {}}],
    )
    r = TestClient(app).post("/agent/ask", json={"text": "주문장 확인"}).json()
    assert r["tools"] == [{"name": "get_active_orders", "data": {"orderIds": []}}]


def test_hidden_signature_in_validation_error(app):
    s = "0xdeadbeef"
    r = TestClient(app).post("/orders", json={"signature": s})
    assert r.status_code == 422 and s not in r.text


def test_pending_receipt_is_unknown():
    from backend.app.execution.journal import Journal
    from web3.exceptions import TransactionNotFound

    def missing(_):
        raise TransactionNotFound("pending")

    w3 = SimpleNamespace(eth=SimpleNamespace(get_transaction_receipt=missing))
    assert Journal.lookup(None, w3, "0x00") is None
