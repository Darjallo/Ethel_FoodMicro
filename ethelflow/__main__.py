import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from ethelflow.assets.s3 import s3_manager
from ethelflow.routes.docs import router as docs_router
from ethelflow.routes.flows import router as flows_router
from ethelflow.settings.postgres_settings import postgres_settings

# from alembic.config import Config
# from alembic import command

logger = logging.getLogger("uvicorn.error")


async def init_checkpointer():
    async with AsyncPostgresSaver.from_conn_string(
        postgres_settings.db_url
    ) as checkpointer:
        await checkpointer.setup()
        logger.info("LangGraph checkpointer setup done")

    pool = AsyncConnectionPool(conninfo=postgres_settings.db_url, open=False)
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    app.state.checkpointer = checkpointer
    app.state.checkpointer_pool = pool


async def teardown_checkpointer():
    pool: AsyncConnectionPool = app.state.checkpointer_pool
    await pool.close()
    logger.info("LangGraph checkpointer PG pool closed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_checkpointer()
    await s3_manager.init()
    yield

    await s3_manager.close()
    await teardown_checkpointer()


app = FastAPI(lifespan=lifespan)
app.include_router(docs_router)
app.include_router(flows_router)


if __name__ == "__main__":
    import uvicorn

    # TODO: run alembic migrations programmatically on startup
    # alembic_cfg = Config()
    # alembic_cfg.set_main_option("script_location", "alembic")
    # alembic_cfg.set_main_option("sqlalchemy.url", postgres_settings.url)
    # command.upgrade(alembic_cfg, "head")

    uvicorn.run(app, host="0.0.0.0", port=8080)
