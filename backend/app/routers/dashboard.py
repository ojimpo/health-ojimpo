from fastapi import APIRouter, Query

from ..models.enums import TimeRange
from ..models.schemas import DashboardResponse
from ..services.aggregation import get_dashboard_data

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="ダッシュボードデータ取得",
    description="スコア・チャートデータ・カテゴリカード・トレンドコメント・最近の活動を返す",
)
async def get_dashboard(
    range: TimeRange = Query(TimeRange.THREE_MONTHS, alias="range"),
):
    return await get_dashboard_data(range)
