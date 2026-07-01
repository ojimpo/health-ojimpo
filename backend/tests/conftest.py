"""Shared test fixtures: isolated SQLite DB with real migrations applied."""
import pytest_asyncio

from app import database


@pytest_asyncio.fixture
async def test_db(tmp_path, monkeypatch):
    """Fresh DB per test: run all migrations, then clear seeded sources.

    Thresholds in global_settings (score_normal=70 / score_caution=40)
    are kept as seeded by migrations.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "_db_path", db_path)
    await database.init_db()
    async with database.get_db_context() as db:
        await db.execute("PRAGMA foreign_keys=OFF")
        await db.execute("DELETE FROM activity_records")
        await db.execute("DELETE FROM baseline_history")
        await db.execute("DELETE FROM source_settings")
        await db.commit()
    yield db_path


async def add_source(
    source_id: str,
    category: str,
    *,
    base_value: float = 100.0,
    aggregation_period: int = 7,
    spontaneity_coefficient: float = 1.0,
    classification: str = "baseline",
    display_type: str = "activity",
    score_method: str = "sum",
    decay_half_life: float | None = None,
    category_weights: str | None = None,
    status: str = "active",
    color: str = "#FFFFFF",
):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO source_settings
            (id, name, category, icon, display_type, classification, phase, status,
             color, aggregation_period, base_value, base_unit,
             spontaneity_coefficient, score_method, decay_half_life, category_weights)
            VALUES (?, ?, ?, '?', ?, ?, 'mvp', ?, ?, ?, ?, 'unit', ?, ?, ?, ?)""",
            (
                source_id, source_id, category, display_type, classification,
                status, color, aggregation_period, base_value,
                spontaneity_coefficient, score_method, decay_half_life,
                category_weights,
            ),
        )
        await db.commit()


async def add_record(
    date_str: str,
    source: str,
    category: str,
    raw_value: float,
    *,
    minutes: float = 0,
):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO activity_records (date, source, category, minutes, raw_value, raw_unit)
            VALUES (?, ?, ?, ?, ?, 'unit')""",
            (date_str, source, category, minutes, raw_value),
        )
        await db.commit()


async def add_baseline_history(source_id: str, effective_from: str, base_value: float):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO baseline_history (source_id, effective_from, base_value, base_unit)
            VALUES (?, ?, ?, 'unit')""",
            (source_id, effective_from, base_value),
        )
        await db.commit()
