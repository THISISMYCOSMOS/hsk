"""Check two actual order workers against the same local MOCK order book."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event

WORK = Path(__file__).resolve().parent
REPO = WORK.parents[1]
sys.path[:0] = [str(REPO), str(REPO / "backend/tests")]

from conftest import UNIT, sign, terms
from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy import event

from backend.app.agent.worker import Worker
from backend.app.api.main import create_app
from backend.app.orderbook.store import Store


def register(api, account, *, sell, size):
    signed = sign(account, terms(account, sell=sell, size=size))
    response = api.post("/orders", json=signed.model_dump())
    assert response.status_code == 200, response.status_code
    return response.json()["orderId"]


def test_two_workers(db_url):
    seller, buyer_400, buyer_200 = (Account.create() for _ in range(3))
    app = create_app(db_url, "MOCK", run_worker=False)
    first = app.state.worker
    second = Worker(Store(db_url), first.market, mode="MOCK")
    first_in_transaction, second_attempted, second_acquired = Event(), Event(), Event()
    release_first = Event()

    @event.listens_for(second.store.engine, "before_cursor_execute")
    def note_second_attempt(conn, cursor, statement, *args):
        if statement == "BEGIN IMMEDIATE":
            second_attempted.set()

    @event.listens_for(second.store.engine, "after_cursor_execute")
    def note_second_acquisition(conn, cursor, statement, *args):
        if statement == "BEGIN IMMEDIATE":
            second_acquired.set()

    def submissions(api):
        return sum(item["kind"] == "SUBMISSION" for item in api.get("/agent/events").json())

    def held_market():
        first_in_transaction.set()
        assert release_first.wait(10), "timed out while holding the first write"
        return normal_market()

    try:
        with TestClient(app) as api:
            seller_id = register(api, seller, sell=True, size=600)
            first_buyer_id = register(api, buyer_400, sell=False, size=400)
            assert first.step()
            initial = api.get("/orders/" + seller_id).json()
            assert initial["status"] == "OPEN" and int(initial["remaining"]) == 200 * UNIT, initial
            assert api.get("/orders/" + first_buyer_id).json()["status"] == "FILLED"
            executions_before = {item["id"] for item in api.get("/executions").json()}
            submissions_before = submissions(api)
            assert len(executions_before) == submissions_before == 1

            second_buyer_id = register(api, buyer_200, sell=False, size=200)
            normal_market = first.market
            first.market = held_market
            with ThreadPoolExecutor(max_workers=2) as workers:
                try:
                    first_owning_write = workers.submit(first.step)
                    assert first_in_transaction.wait(5), "the first worker never entered its write"
                    second_waiting = workers.submit(second.step)
                    assert second_attempted.wait(5), "the second worker never attempted its write"
                    assert not second_acquired.is_set(), "the second worker acquired the same book during the first write"
                finally:
                    release_first.set()
                step_results = (first_owning_write.result(timeout=12), second_waiting.result(timeout=12))
            assert second_acquired.is_set()

            execution_ids = {item["id"] for item in api.get("/executions").json()}
            new_executions = execution_ids - executions_before
            new_submissions = submissions(api) - submissions_before
            assert len(execution_ids) == 2 and len(new_executions) == new_submissions == 1
            assert step_results == (True, False), step_results
            final = api.get("/orders/" + seller_id).json()
            assert final["status"] == "FILLED" and final["remaining"] == "0", final
            assert api.get("/orders/" + second_buyer_id).json()["status"] == "FILLED"

            def executed_amounts(order_id):
                amounts = []
                for execution_id in execution_ids:
                    receipt = api.get(f"/executions/{execution_id}/receipt").json()
                    assert receipt["evidence"] == "SYNTHETIC" and receipt["transactionHash"] is None
                    amounts.extend(int(fill["fixed"]) for fill in receipt["participants"] if fill["orderId"] == order_id)
                return sorted(amounts)

            assert executed_amounts(seller_id) == [200 * UNIT, 400 * UNIT]
            assert executed_amounts(second_buyer_id) == [200 * UNIT]
            return {
                "mode": "actual repository worker/API, local SQLite and synthetic settlement",
                "trials": 1,
                "registered_order_whsk": 600,
                "initial_fill_whsk": 400,
                "concurrent_workers": 2,
                "second_worker_attempted_while_first_had_write": True,
                "new_submission_events": new_submissions,
                "new_execution_records": len(new_executions),
                "total_seller_fill_whsk": sum(executed_amounts(seller_id)) // UNIT,
                "remaining_seller_whsk": int(final["remaining"]) // UNIT,
                "worker_step_results": step_results,
                "blockchain_broadcasts": 0,
            }
    finally:
        first.store.engine.dispose()
        second.store.engine.dispose()


if __name__ == "__main__":
    with TemporaryDirectory(prefix="hsk-concurrent-worker-", dir=WORK) as temp:
        db_url = "sqlite:///" + (Path(temp) / "orders.sqlite").as_posix()
        print(json.dumps(test_two_workers(db_url), indent=2))
