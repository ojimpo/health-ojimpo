import secrets

from fastapi import APIRouter, HTTPException

from ..database import get_db_context
from ..models.schemas import (
    BaselineCreate,
    BaselineHistoryItem,
    SharedViewSettingsResponse,
    SharedViewSettingsUpdate,
    SourceSettingsResponse,
    SourceSettingsUpdate,
    ThresholdsResponse,
    ThresholdsUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/sources",
    response_model=list[SourceSettingsResponse],
    summary="全データソース設定取得",
)
async def get_sources():
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM source_settings ORDER BY sort_order"
        )
        sources = []
        for row in rows:
            src = dict(row)
            src["show_personal"] = bool(src["show_personal"])
            src["show_shared"] = bool(src["show_shared"])
            baselines = await db.execute_fetchall(
                "SELECT * FROM baseline_history WHERE source_id = ? ORDER BY effective_from DESC",
                (src["id"],),
            )
            src["baseline_history"] = [dict(b) for b in baselines]
            sources.append(src)
        return sources


@router.put(
    "/sources/{source_id}",
    response_model=SourceSettingsResponse,
    summary="データソース設定更新",
)
async def update_source(source_id: str, update: SourceSettingsUpdate):
    async with get_db_context() as db:
        row = await db.execute_fetchall(
            "SELECT * FROM source_settings WHERE id = ?", (source_id,)
        )
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        updates = {k: v for k, v in update.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [source_id]
        await db.execute(
            f"UPDATE source_settings SET {set_clause} WHERE id = ?", values
        )
        await db.commit()
        # Re-fetch
        rows = await db.execute_fetchall(
            "SELECT * FROM source_settings WHERE id = ?", (source_id,)
        )
        src = dict(rows[0])
        src["show_personal"] = bool(src["show_personal"])
        src["show_shared"] = bool(src["show_shared"])
        baselines = await db.execute_fetchall(
            "SELECT * FROM baseline_history WHERE source_id = ? ORDER BY effective_from DESC",
            (source_id,),
        )
        src["baseline_history"] = [dict(b) for b in baselines]
        return src


@router.get(
    "/sources/{source_id}/baselines",
    response_model=list[BaselineHistoryItem],
    summary="基準値履歴取得",
)
async def get_baselines(source_id: str):
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM baseline_history WHERE source_id = ? ORDER BY effective_from DESC",
            (source_id,),
        )
        return [dict(r) for r in rows]


@router.post(
    "/sources/{source_id}/baselines",
    response_model=BaselineHistoryItem,
    summary="基準値追加",
)
async def create_baseline(source_id: str, baseline: BaselineCreate):
    async with get_db_context() as db:
        cursor = await db.execute(
            "INSERT INTO baseline_history (source_id, effective_from, base_value, base_unit, memo) VALUES (?, ?, ?, ?, ?)",
            (
                source_id,
                baseline.effective_from,
                baseline.base_value,
                baseline.base_unit,
                baseline.memo,
            ),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "effective_from": baseline.effective_from,
            "base_value": baseline.base_value,
            "base_unit": baseline.base_unit,
            "memo": baseline.memo,
        }


@router.delete(
    "/sources/{source_id}/baselines/{baseline_id}",
    summary="基準値削除",
)
async def delete_baseline(source_id: str, baseline_id: int):
    async with get_db_context() as db:
        await db.execute(
            "DELETE FROM baseline_history WHERE id = ? AND source_id = ?",
            (baseline_id, source_id),
        )
        await db.commit()
        return {"ok": True}


@router.get(
    "/thresholds",
    response_model=ThresholdsResponse,
    summary="閾値設定取得",
)
async def get_thresholds():
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT key, value FROM global_settings WHERE key LIKE '%threshold'"
        )
        return {row[0]: float(row[1]) for row in rows}


@router.put(
    "/thresholds",
    response_model=ThresholdsResponse,
    summary="閾値設定更新",
)
async def update_thresholds(update: ThresholdsUpdate):
    async with get_db_context() as db:
        for key, value in update.model_dump(exclude_none=True).items():
            await db.execute(
                "UPDATE global_settings SET value = ?, updated_at = datetime('now') WHERE key = ?",
                (str(value), key),
            )
        await db.commit()
        rows = await db.execute_fetchall(
            "SELECT key, value FROM global_settings WHERE key LIKE '%threshold'"
        )
        return {row[0]: float(row[1]) for row in rows}


@router.get(
    "/shared",
    response_model=SharedViewSettingsResponse,
    summary="共有ビュー設定取得",
)
async def get_shared_settings():
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT key, value FROM global_settings WHERE key IN ('shared_view_token', 'shared_view_enabled')"
        )
        data = {row[0]: row[1] for row in rows}
        token = data.get("shared_view_token", "")
        return {
            "token": token,
            "enabled": data.get("shared_view_enabled") == "true",
            "url": f"health.ojimpo.com/shared/{token}",
        }


@router.put(
    "/shared",
    response_model=SharedViewSettingsResponse,
    summary="共有ビュー設定更新",
)
async def update_shared_settings(update: SharedViewSettingsUpdate):
    async with get_db_context() as db:
        await db.execute(
            "UPDATE global_settings SET value = ?, updated_at = datetime('now') WHERE key = 'shared_view_enabled'",
            ("true" if update.enabled else "false",),
        )
        await db.commit()
        return await get_shared_settings()


@router.post(
    "/shared/regenerate-token",
    response_model=SharedViewSettingsResponse,
    summary="共有ビュートークン再生成",
)
async def regenerate_token():
    new_token = secrets.token_hex(16)
    async with get_db_context() as db:
        await db.execute(
            "UPDATE global_settings SET value = ?, updated_at = datetime('now') WHERE key = 'shared_view_token'",
            (new_token,),
        )
        await db.commit()
        return {
            "token": new_token,
            "enabled": True,
            "url": f"health.ojimpo.com/shared/{new_token}",
        }
