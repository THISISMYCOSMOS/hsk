from concurrent.futures import ThreadPoolExecutor
import time
import pytest
from eth_account.messages import encode_typed_data
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from conftest import sign, terms
from backend.app.orderbook.signatures import typed_data
from backend.app.models import tables as db


def test_concurrent_idempotency_and_signature(app, actors):
    store = app.state.worker.store
    o = terms(actors[0])
    signed = sign(actors[0], o)
    with ThreadPoolExecutor(6) as pool:
        ids = list(pool.map(lambda _: store.register(signed, int(time.time())), range(10)))
    assert len(set(ids)) == 1
    with store.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.outbox)) == 1
    with pytest.raises(ValueError, match="INVALID_SIGNATURE"):
        store.register(signed.model_copy(update={"order": terms(actors[0], allowDex=True)}), 0)
    with pytest.raises(ValueError, match="NONCE_ALREADY_USED"):
        store.register(sign(actors[0], terms(actors[0], allowDex=True)), 0)


def test_register_cancel_expire(app, actors):
    api = TestClient(app)
    s = sign(actors[0], terms(actors[0]))
    res = api.post("/orders", json=s.model_dump())
    assert res.status_code == 200 and "signature" not in res.text
    digest = res.json()["orderId"]
    data = api.get("/orders/" + digest + "/cancel-typed-data").json()
    for actor, status in [(actors[1], 409), (actors[0], 200)]:
        sig = actor.sign_message(encode_typed_data(full_message=data)).signature
        assert (
            api.post("/orders/" + digest + "/cancel", json={"signature": "0x" + bytes(sig).hex()}).status_code
            == status
        )
    assert not api.get("/orderbook").json()
    store = app.state.worker.store
    past = sign(actors[1], terms(actors[1], expiry="2"))
    id_ = store.register(past, 1)
    with store.write() as conn:
        store.expire(conn, 3)
        assert store.one(conn, id_)["status"] == "EXPIRED"


@pytest.mark.parametrize(
    "flag,problem",
    [
        ("balance_usdt", "INSUFFICIENT_BALANCE"),
        ("allowance", "INSUFFICIENT_ALLOWANCE"),
        ("gas_budget", "GAS_BUDGET_EXCEEDED"),
        ("revert", "SIMULATION_FAILED"),
    ],
)
def test_rejections(app, actors, flag, problem):
    w = app.state.worker
    setattr(w.limits, flag, True if flag == "revert" else 0)
    for i, a in enumerate(actors[:2]):
        w.store.register(sign(a, terms(a, not i)), 0)
        w.step()
    with w.store.engine.connect() as conn:
        assert problem in list(conn.scalars(select(db.events.c.kind)))
        assert not conn.scalar(select(func.count()).select_from(db.executions))


def test_rpc_recovery_and_idle(app, actors):
    w = app.state.worker
    original = w.market

    def down():
        raise OSError("offline")

    w.market = down
    assert not w.step()
    w.store.register(sign(actors[0], terms(actors[0])), 0)
    with pytest.raises(OSError):
        w.step()
    w.market = original
    assert w.step()
    with w.store.write() as conn:
        assert w.store.emit(conn, "POOL_SWAP", {"block": "12", "logIndex": "0"}, key="12:0", work=True)
        assert w.store.emit(conn, "POOL_SWAP", {}, key="12:0", work=True) is None
    assert w.step()
    assert not w.step()


def test_automatic_worker_public_api(tmp_path, actors):
    from backend.app.api.main import create_app

    app = create_app("sqlite:///" + str(tmp_path / "worker.db"), "MOCK")
    with TestClient(app) as api:
        ids = []
        for a, sell in [(actors[0], True), (actors[1], False)]:
            order = terms(a, sell)
            signed = sign(a, order)
            assert api.post("/orders/typed-data", json=order.model_dump()).json() == typed_data(order)
            ids.append(api.post("/orders", json=signed.model_dump()).json()["orderId"])
        for _ in range(120):
            if api.get("/executions").json():
                break
            time.sleep(0.025)
        (execution,) = api.get("/executions").json()
        receipt = api.get(f"/executions/{execution['id']}/receipt").json()
        assert receipt["evidence"] == "SYNTHETIC" and receipt["transactionHash"] is None
        assert all(api.get("/orders/" + id_).json()["remaining"] == "0" for id_ in ids)
        comp = api.get(f"/executions/{execution['id']}/comparison").json()
        assert comp["comparison"]["selected"]["kind"] == "DIRECT_MATCH"
        assert api.get("/metrics").json()["llmCalls"] == 0
        assert api.get("/agent/events").json()[-1]["kind"] == "IDLE"
        assert (
            api.post(
                "/agent/intent",
                json={"text": "WHSK 1,000개를 0.081 USDT 이상에 팔고 싶어. 24시간 부분 체결 허용"},
            ).json()["whskAmount"]
            == "1000"
        )
        assert api.post("/orders", json={"calldata": "0x00"}).status_code == 422
        assert api.post("/executions", json={"quoteId": "1"}).status_code == 405
