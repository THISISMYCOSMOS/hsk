import time
from contextlib import contextmanager
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.pool import StaticPool
from ..models import tables as db
from ..schemas.orders import Order
from ..optimizer.search import Entry
from .signatures import recover, typed_data


class Store:
    def __init__(self, url):
        opts = {}
        if url.startswith("sqlite"):
            opts["connect_args"] = {"check_same_thread": False, "timeout": 15}
            if url.endswith(":memory:"):
                opts["poolclass"] = StaticPool
        self.engine = create_engine(url, **opts)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def foreign_keys(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")

            db.meta.create_all(self.engine)

    @contextmanager
    def write(self):
        with self.engine.begin() as conn:
            if self.engine.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            elif self.engine.dialect.name == "postgresql":
                # A single pair book. Serializes wallet reuse as well as order reuse.
                conn.execute(text("SELECT pg_advisory_xact_lock(177031337)"))
            yield conn

    @staticmethod
    def emit(conn, kind, payload, *, work=False, key=None):
        if key is not None and conn.scalar(select(db.events.c.id).where(db.events.c.source_key == key)):
            return None
        id_ = conn.execute(
            db.events.insert().values(kind=kind, payload=payload, source_key=key, at=int(time.time()))
        ).inserted_primary_key[0]
        if work:
            conn.execute(db.outbox.insert().values(event_id=id_, done=0))
        return id_

    @staticmethod
    def status(conn, digest, status, **kw):
        conn.execute(db.orders.update().where(db.orders.c.digest == digest).values(status=status, **kw))
        conn.execute(db.history.insert().values(order_id=digest, status=status, at=int(time.time())))

    def register(self, signed, now, settlement=None):
        o = signed.order
        digest = recover(typed_data(o), signed.signature, o.maker)
        with self.write() as conn:
            existing = conn.execute(
                select(db.orders.c.digest).where(db.orders.c.maker == o.maker, db.orders.c.nonce == o.nonce)
            ).scalar()
            if existing == digest:
                return digest
            if existing:
                raise ValueError("NONCE_ALREADY_USED")
            if int(o.expiry) < now:
                raise ValueError("ORDER_EXPIRED")
            conn.execute(
                db.orders.insert().values(
                    digest=digest,
                    maker=o.maker,
                    nonce=o.nonce,
                    body=o.model_dump(),
                    signature=signed.signature,
                    settlement=settlement,
                    remaining=o.fixedAmount,
                    status="OPEN",
                )
            )
            self.status(conn, digest, "OPEN")
            self.emit(conn, "ORDER_CREATED", {"orderId": digest}, work=True)
        return digest

    def cancel(self, digest, signature):
        with self.write() as conn:
            row = self.one(conn, digest)
            recover(typed_data(cancel=digest), signature, row["maker"])
            if row["status"] == "CANCELLED":
                return
            if row["status"] != "OPEN":
                raise ValueError("ORDER_NOT_OPEN")
            self.status(conn, digest, "CANCELLED")
            self.emit(conn, "ORDER_CANCELLED", {"orderId": digest}, work=True)

    def expire(self, conn, now):
        rows = conn.execute(select(db.orders).where(db.orders.c.status.in_(["OPEN", "RESERVED"]))).mappings()
        for row in list(rows):
            if row["status"] == "RESERVED" and row["lease_until"] and row["lease_until"] <= now:
                self.status(conn, row["digest"], "OPEN", lease_until=None, reservation=None)
            if int(row["body"]["expiry"]) < now:
                self.status(conn, row["digest"], "EXPIRED", lease_until=None, reservation=None)
                self.emit(conn, "ORDER_EXPIRED", {"orderId": row["digest"]}, work=True)

    @staticmethod
    def one(conn, digest):
        row = conn.execute(select(db.orders).where(db.orders.c.digest == digest)).mappings().first()
        if not row:
            raise KeyError(digest)
        return row

    @staticmethod
    def active(conn, now):
        rows = conn.execute(
            select(db.orders).where(db.orders.c.status == "OPEN").order_by(db.orders.c.id)
        ).mappings()
        return [
            Entry(r["digest"], Order(**r["body"]), int(r["remaining"]), r["id"])
            for r in rows
            if int(r["body"]["expiry"]) >= now
        ]

    @staticmethod
    def public(row):
        return dict(
            orderId=row["digest"], order=row["body"], remaining=row["remaining"], status=row["status"]
        )
