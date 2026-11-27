import os
from alembic import context
from sqlalchemy import create_engine
from backend.app.models.tables import meta

engine = create_engine(os.environ.get("HSK_ENGINE_DB", context.config.get_main_option("sqlalchemy.url")))
with engine.begin() as conn:
    context.configure(connection=conn, target_metadata=meta)
    with context.begin_transaction():
        context.run_migrations()
