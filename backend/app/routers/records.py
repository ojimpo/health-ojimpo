from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db_context
from ..models.schemas import (
    ActivityRecordItem,
    RecordsAggregateItem,
    RecordsResponse,
)

router = APIRouter(tags=["records"])

_PERIOD_FORMATS = {
    "week": "%Y-W%W",
    "month": "%Y-%m",
}


def _validate_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid {name} date: {value} (expected YYYY-MM-DD)"
        )


@router.get(
    "/records",
    response_model=RecordsResponse,
    summary="活動レコード生データ取得",
    description="activity_recordsを日付範囲で取得（読み取り専用）。group_by指定で週/月集計",
)
async def get_records(
    from_date: Annotated[str, Query(alias="from")],
    to_date: Annotated[str, Query(alias="to")],
    source: str | None = None,
    category: str | None = None,
    group_by: Annotated[str | None, Query(pattern="^(week|month)$")] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
):
    start = _validate_date(from_date, "from")
    end = _validate_date(to_date, "to")
    if start > end:
        raise HTTPException(status_code=400, detail="from must be <= to")

    where = "date BETWEEN ? AND ?"
    params: list = [from_date, to_date]
    if source:
        where += " AND source = ?"
        params.append(source)
    if category:
        where += " AND category = ?"
        params.append(category)

    async with get_db_context() as db:
        if group_by:
            period_fmt = _PERIOD_FORMATS[group_by]
            rows = await db.execute_fetchall(
                f"""SELECT strftime('{period_fmt}', date) AS period, source, category,
                    SUM(minutes) AS minutes, SUM(raw_value) AS raw_value, COUNT(*) AS days
                FROM activity_records WHERE {where}
                GROUP BY period, source, category
                ORDER BY period, source, category LIMIT ?""",
                (*params, limit),
            )
            total_row = await db.execute_fetchall(
                f"""SELECT COUNT(*) AS cnt FROM (
                    SELECT 1 FROM activity_records WHERE {where}
                    GROUP BY strftime('{period_fmt}', date), source, category)""",
                params,
            )
            total = total_row[0]["cnt"]
            aggregates = [RecordsAggregateItem(**dict(r)) for r in rows]
            return RecordsResponse(
                total=total,
                returned=len(aggregates),
                truncated=total > len(aggregates),
                aggregates=aggregates,
            )

        total_row = await db.execute_fetchall(
            f"SELECT COUNT(*) AS cnt FROM activity_records WHERE {where}", params
        )
        total = total_row[0]["cnt"]
        rows = await db.execute_fetchall(
            f"""SELECT id, date, source, category, minutes, raw_value, raw_unit, metadata
            FROM activity_records WHERE {where}
            ORDER BY date, source, category LIMIT ?""",
            (*params, limit),
        )
        records = [ActivityRecordItem(**dict(r)) for r in rows]
        return RecordsResponse(
            total=total,
            returned=len(records),
            truncated=total > len(records),
            records=records,
        )
