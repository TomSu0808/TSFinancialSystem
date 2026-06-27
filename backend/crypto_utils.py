"""API Key 对称加密工具（Fernet）。

生成 APP_ENCRYPTION_KEY 的命令：
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

注意：如果 APP_ENCRYPTION_KEY 更换，旧的 encrypted_api_key 将无法解密，
需要让用户重新配置 API Key。
"""
from cryptography.fernet import Fernet, InvalidToken

from config import APP_ENCRYPTION_KEY


def _get_fernet() -> Fernet:
    if not APP_ENCRYPTION_KEY:
        raise RuntimeError(
            "APP_ENCRYPTION_KEY 未设置。请生成并配置：\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(APP_ENCRYPTION_KEY.encode())
    except Exception:
        raise RuntimeError(
            "APP_ENCRYPTION_KEY 格式无效，必须是 Fernet 格式（44 字符 base64）。\n"
            "生成命令：python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )


def encrypt_secret(plain: str) -> str:
    """加密明文 API Key，返回 Fernet token 字符串。"""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_secret(cipher: str) -> str:
    """解密 Fernet token，返回明文 API Key。"""
    try:
        return _get_fernet().decrypt(cipher.encode()).decode()
    except InvalidToken:
        raise RuntimeError(
            "API Key 解密失败，可能 APP_ENCRYPTION_KEY 已更换。请重新配置 API Key。"
        )


def mask_secret(plain: str) -> str:
    """只显示最后 4 位，例如 ****abcd。"""
    if len(plain) <= 4:
        return "****"
    return "****" + plain[-4:]
