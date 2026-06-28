"""导入与对账 API 路由。

POST   /api/imports/preview       — 上传文件 → 解析预览
POST   /api/imports/{id}/commit   — 确认导入
GET    /api/imports/{id}/recon    — 对账结果
GET    /api/imports               — 列出导入历史
GET    /api/imports/{id}          — 导入详情
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from import_service import commit_import, preview_import
from models import ImportSession, Platform, User
from reconciliation_service import compute_reconciliation

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _check_platform(session: Session, platform_id: Optional[int], user: User) -> None:
    """校验平台存在且属于当前用户。"""
    if platform_id is None:
        return
    plat = session.get(Platform, platform_id)
    if plat is None or plat.user_id != user.id:
        raise HTTPException(404, "平台不存在或无权访问")


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    platform_id: Optional[int] = Form(None),
    broker_type: str = Form("futu"),
    mapping: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """上传券商 CSV/Statement 文件，解析并返回逐行预览。

    - broker_type: futu / ibkr / generic
    - mapping: 可选 JSON 字符串，用户自定义字段映射
    """
    _check_platform(session, platform_id, user)

    # 解析 mapping
    user_mapping = None
    if mapping:
        try:
            user_mapping = json.loads(mapping)
        except json.JSONDecodeError:
            raise HTTPException(400, "mapping 格式无效，应为 JSON 对象")

    # 验证 broker_type
    if broker_type not in ("futu", "ibkr", "generic"):
        raise HTTPException(400, f"不支持的券商类型: {broker_type}，支持: futu / ibkr / generic")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "上传文件为空")

    result = preview_import(
        session=session,
        user=user,
        broker_type=broker_type,
        file_data=contents,
        file_name=file.filename or "upload.csv",
        platform_id=platform_id,
        user_mapping=user_mapping,
    )

    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


@router.post("/{import_session_id}/commit")
def commit(
    import_session_id: int,
    selected_rows: Optional[str] = Form(None),
    edited_rows: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """确认导入：将 preview 中的交易写入数据库。

    - selected_rows: 逗号分隔的行号列表（如 "1,2,5-10"），为空则导入所有 valid 行
    - edited_rows: JSON 字符串，{row_number: {field: new_value}} 用户修正的数据
    """
    # 解析 selected_rows
    selected = None
    if selected_rows:
        selected = _parse_row_ranges(selected_rows)

    # 解析 edited_rows
    edited = None
    if edited_rows:
        try:
            edited = {int(k): v for k, v in json.loads(edited_rows).items()}
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(400, "edited_rows 格式无效")

    result = commit_import(
        session=session,
        user=user,
        import_session_id=import_session_id,
        selected_rows=selected,
        edited_rows=edited,
    )

    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


@router.get("/{import_session_id}/reconciliation")
def reconciliation(
    import_session_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """获取导入后的对账结果。"""
    result = compute_reconciliation(session, user, import_session_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("")
def list_imports(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """列出当前用户的导入历史（最近 20 条）。"""
    sessions = session.exec(
        select(ImportSession)
        .where(ImportSession.user_id == user.id)
        .order_by(ImportSession.created_at.desc())
        .limit(20)
    ).all()

    return [
        {
            "id": s.id,
            "broker_type": s.broker_type,
            "file_name": s.file_name,
            "status": s.status,
            "created_transaction_count": s.created_transaction_count,
            "skipped_duplicate_count": s.skipped_duplicate_count,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ]


@router.get("/{import_session_id}")
def get_import_detail(
    import_session_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """获取单次导入详情（含 preview 行数据）。"""
    s = session.get(ImportSession, import_session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "导入记录不存在")

    return {
        "id": s.id,
        "broker_type": s.broker_type,
        "file_name": s.file_name,
        "platform_id": s.platform_id,
        "status": s.status,
        "detected_fields": json.loads(s.detected_fields) if s.detected_fields else {},
        "user_mapping": json.loads(s.user_mapping) if s.user_mapping else None,
        "rows": json.loads(s.rows_json) if s.rows_json else [],
        "summary": json.loads(s.summary_json) if s.summary_json else {},
        "created_transaction_count": s.created_transaction_count,
        "skipped_duplicate_count": s.skipped_duplicate_count,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _parse_row_ranges(s: str) -> list:
    """解析行号范围字符串，如 "1,2,5-10" → [1, 2, 5, 6, 7, 8, 9, 10]"""
    result = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.extend(range(int(a.strip()), int(b.strip()) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))
