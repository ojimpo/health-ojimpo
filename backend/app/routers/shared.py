from fastapi import APIRouter, HTTPException, Query

from ..models.enums import TimeRange
from ..models.schemas import SharedViewResponse
from ..services.aggregation import get_shared_view_data
from ..database import get_db_context

router = APIRouter(tags=["shared"])


@router.get(
    "/shared/{token}",
    response_model=SharedViewResponse,
    summary="共有ビューデータ取得",
    description="トークンで認証された共有ビュー。活動詳細は非表示。演出マトリクス情報付き。",
)
async def get_shared_view(
    token: str,
    range: TimeRange = Query(TimeRange.THREE_MONTHS, alias="range"),
):
    async with get_db_context() as db:
        row = await db.execute_fetchall(
            "SELECT value FROM global_settings WHERE key = 'shared_view_token'"
        )
        if not row or row[0][0] != token:
            raise HTTPException(status_code=404, detail="Not found")
        enabled_row = await db.execute_fetchall(
            "SELECT value FROM global_settings WHERE key = 'shared_view_enabled'"
        )
        if enabled_row and enabled_row[0][0] != "true":
            raise HTTPException(status_code=404, detail="Not found")
    return await get_shared_view_data(range)
