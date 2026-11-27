"""Disposable PostgreSQL migration, worker settlement and concurrent idempotency check."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import pgserver
from alembic import command
from alembic.config import Config
from eth_account import Account
from sqlalchemy import func, select
from .conftest import sign, terms
from backend.app.api.main import create_app
from backend.app.models import tables as db


def run():
    os.environ["LC_ALL"] = "C"
    with tempfile.TemporaryDirectory(prefix="hsk-pg-", dir="/tmp") as folder:
        pg = pgserver.get_server(Path(folder), cleanup_mode="stop")
        try:
            url = pg.get_uri().replace("postgresql://", "postgresql+psycopg://")
            os.environ["HSK_ENGINE_DB"] = url
            config = Config("backend/migrations/alembic.ini")
            command.upgrade(config, "head")
            app = create_app(url, "MOCK", run_worker=False)
            w = app.state.worker
            signed = [
                sign(a, terms(a, sell)) for a, sell in [(Account.create(), True), (Account.create(), False)]
            ]
            with ThreadPoolExecutor(8) as threads:
                ids = list(threads.map(lambda s: w.store.register(s, int(time.time())), signed * 8))
            assert len(set(ids)) == 2
            while w.step():
                pass
            with w.store.engine.connect() as conn:
                assert conn.scalar(select(func.count()).select_from(db.fills)) == 2
                assert conn.scalar(select(func.count()).select_from(db.executions)) == 1
                assert (
                    conn.scalar(
                        select(func.count()).select_from(db.orders).where(db.orders.c.status == "FILLED")
                    )
                    == 2
                )
            w.store.engine.dispose()
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            print(
                "PASS PostgreSQL upgrade/downgrade/upgrade; 16 concurrent registrations, two orders, one mock settlement"
            )
        finally:
            pg.cleanup()


if __name__ == "__main__":
    run()
