"""集中配置：全部从环境变量 / .env 读取，密钥绝不写进代码。

本地开发：复制 .env.example 为 .env 并按需修改。
上云：在服务器/容器里设置同名环境变量即可（无需 .env 文件）。
"""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# 加载 backend/.env（存在才加载；上云用真实环境变量时可不放此文件）
load_dotenv(Path(__file__).resolve().parent / ".env")

# JWT 签名密钥。务必在生产环境通过环境变量设置一个固定值；
# 缺省时随机生成——方便首次跑通，但进程重启会让已签发的 token 失效。
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)

# token 算法与有效期（天）
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", "7"))

# 允许跨域的前端来源，逗号分隔。上云后收紧成你的正式域名。
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
]

# 是否开放自助注册（开源公开部署可设 false 临时关闭注册）
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() != "false"
