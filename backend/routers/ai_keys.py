"""用户 AI Key 管理接口（BYOK - Bring Your Own Key）。

所有接口只能操作当前登录用户自己的 key，不暴露明文 key，不返回 encrypted_api_key。
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from crypto_utils import decrypt_secret, encrypt_secret
from database import get_session
from models import User, UserAIKey, UserAIKeyCreate, UserAIKeyRead, UserAIKeyTestInput, UserAIKeyUpdate
import ai_client

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _owned_key(session: Session, key_id: int, user: User) -> UserAIKey:
    key = session.get(UserAIKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(404, "Key 不存在")
    return key


def _clear_other_defaults(session: Session, user_id: int, keep_id: int) -> None:
    """取消同一用户其他 key 的 is_default 标记。"""
    for k in session.exec(
        select(UserAIKey).where(
            UserAIKey.user_id == user_id,
            UserAIKey.is_default == True,  # noqa: E712
        )
    ).all():
        if k.id != keep_id:
            k.is_default = False
            session.add(k)


@router.get("/ai-keys", response_model=List[UserAIKeyRead])
def list_ai_keys(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """列出当前用户所有已保存的 AI Key（只返回后四位，不返回明文）。"""
    return session.exec(
        select(UserAIKey).where(UserAIKey.user_id == user.id)
    ).all()


@router.post("/ai-keys", response_model=UserAIKeyRead)
def save_ai_key(
    data: UserAIKeyCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """创建或更新当前用户某 provider 的 key（同 provider 只存一条，重复保存则更新）。"""
    provider = ai_client.normalize_provider(data.provider)
    encrypted = encrypt_secret(data.api_key)
    last4 = data.api_key[-4:] if len(data.api_key) >= 4 else data.api_key

    # Upsert by user + provider
    existing = session.exec(
        select(UserAIKey).where(
            UserAIKey.user_id == user.id,
            UserAIKey.provider == provider,
        )
    ).first()

    if existing:
        existing.encrypted_api_key = encrypted
        existing.key_last4 = last4
        if data.base_url is not None:
            existing.base_url = data.base_url
        if data.default_model is not None:
            existing.default_model = data.default_model
        existing.is_default = data.is_default
        existing.updated_at = datetime.utcnow()
        key = existing
        session.add(key)
        session.flush()
    else:
        key = UserAIKey(
            user_id=user.id,
            provider=provider,
            encrypted_api_key=encrypted,
            key_last4=last4,
            base_url=data.base_url,
            default_model=data.default_model,
            is_default=data.is_default,
        )
        session.add(key)
        session.flush()

    if data.is_default and key.id is not None:
        _clear_other_defaults(session, user.id, keep_id=key.id)

    session.commit()
    session.refresh(key)
    return key


@router.put("/ai-keys/{key_id}", response_model=UserAIKeyRead)
def update_ai_key(
    key_id: int,
    data: UserAIKeyUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """更新指定 key 的配置（只能修改自己的 key）。"""
    key = _owned_key(session, key_id, user)

    if data.api_key is not None:
        key.encrypted_api_key = encrypt_secret(data.api_key)
        key.key_last4 = data.api_key[-4:] if len(data.api_key) >= 4 else data.api_key
    if data.base_url is not None:
        key.base_url = data.base_url
    if data.default_model is not None:
        key.default_model = data.default_model
    if data.is_default is not None:
        key.is_default = data.is_default
        if data.is_default and key.id is not None:
            _clear_other_defaults(session, user.id, keep_id=key.id)

    key.updated_at = datetime.utcnow()
    session.add(key)
    session.commit()
    session.refresh(key)
    return key


@router.delete("/ai-keys/{key_id}")
def delete_ai_key(
    key_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """删除指定 key（只能删除自己的 key）。"""
    key = _owned_key(session, key_id, user)
    session.delete(key)
    session.commit()
    return {"ok": True}


@router.post("/ai-keys/test")
def test_ai_key(
    data: UserAIKeyTestInput,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """测试连接。传 api_key 则测试临时 key（不保存）；不传则测试已保存的 key。

    错误信息不包含 API Key 内容，截断并清洗后返回。
    """
    provider = ai_client.normalize_provider(data.provider)

    if data.api_key:
        api_key = data.api_key
        base_url = data.base_url
    else:
        saved = session.exec(
            select(UserAIKey).where(
                UserAIKey.user_id == user.id,
                UserAIKey.provider == provider,
            )
        ).first()
        if not saved:
            raise HTTPException(400, f"未找到已保存的 {provider} API Key，请先保存后再测试")
        api_key = decrypt_secret(saved.encrypted_api_key)
        base_url = data.base_url or saved.base_url

    result = ai_client.test_provider_connection(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=data.model,
    )

    if not result["ok"]:
        raise HTTPException(502, result["message"])

    return result
