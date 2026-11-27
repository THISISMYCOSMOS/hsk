"""Relational schema v1, portable between PostgreSQL and SQLite."""

from sqlalchemy import MetaData, Table, Column, Integer, String, Text, JSON, ForeignKey, UniqueConstraint

meta = MetaData()


def pk():
    return Column("id", Integer, primary_key=True)


orders = Table(
    "orders",
    meta,
    pk(),
    Column("digest", String(66), nullable=False, unique=True),
    Column("maker", String(42), nullable=False),
    Column("nonce", String(78), nullable=False),
    Column("body", JSON, nullable=False),
    Column("signature", Text, nullable=False),
    Column("remaining", String(78), nullable=False),
    Column("status", String, nullable=False, index=True),
    Column("settlement", JSON),
    Column("reservation", String),
    Column("lease_until", Integer),
    UniqueConstraint("maker", "nonce"),
)


def order_ref():
    return Column("order_id", String(66), ForeignKey("orders.digest"), nullable=False)


history = Table(
    "order_status_history",
    meta,
    pk(),
    order_ref(),
    Column("status", String, nullable=False),
    Column("at", Integer, nullable=False),
)
events = Table(
    "agent_events",
    meta,
    pk(),
    Column("kind", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("at", Integer, nullable=False),
    Column("source_key", String, unique=True),
)
outbox = Table(
    "event_outbox",
    meta,
    pk(),
    Column("event_id", Integer, ForeignKey("agent_events.id"), unique=True),
    Column("done", Integer, nullable=False),
)
quotes = Table("execution_candidates", meta, pk(), order_ref(), Column("comparison", JSON, nullable=False))
plans = Table(
    "execution_plans",
    meta,
    pk(),
    Column("quote_id", Integer, ForeignKey("execution_candidates.id")),
    Column("plan", JSON, nullable=False),
)
executions = Table(
    "executions",
    meta,
    pk(),
    Column("plan_id", Integer, ForeignKey("execution_plans.id"), unique=True),
    Column("status", String, nullable=False),
    Column("receipt", JSON),
)
fills = Table(
    "fills",
    meta,
    pk(),
    order_ref(),
    Column("execution_id", Integer, ForeignKey("executions.id")),
    Column("fixed", String(78), nullable=False),
    UniqueConstraint("order_id", "execution_id"),
)
costs = Table(
    "costs",
    meta,
    pk(),
    Column("execution_id", Integer, ForeignKey("executions.id")),
    Column("payer", String, nullable=False),
    Column("breakdown", JSON, nullable=False),
)


jobs = Table(
    "fork_jobs",
    meta,
    pk(),
    Column("execution_id", Integer, ForeignKey("executions.id"), unique=True),
    Column("plan_hash", String, unique=True),
    Column("tx", JSON),
    Column("mapping", JSON),
    Column("quantities", JSON),
    Column("block_hash", String),
    Column("estimate", String),
    Column("fallback", Integer),
)

cursor = Table(
    "market_cursor",
    meta,
    pk(),
    Column("height", Integer),
    Column("hash", String),
    Column("log_index", Integer),
    Column("state", JSON),
)
