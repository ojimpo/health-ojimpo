import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

from .config import settings

_db_path = settings.database_path


def get_db_path() -> str:
    return _db_path


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


@asynccontextmanager
async def get_db_context():
    db = await get_db()
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    migrations_dir = Path(__file__).parent / "migrations"
    async with get_db_context() as db:
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            sql = sql_file.read_text()
            try:
                await db.executescript(sql)
            except Exception as e:
                err = str(e)
                if "duplicate column" in err or "already exists" in err:
                    logger.debug("Skipping (already applied): %s", sql_file.name)
                else:
                    raise
        await db.commit()
