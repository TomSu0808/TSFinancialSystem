"""后端管理命令（在 venv 内运行，可直接操作数据库）。

用法（一般通过根目录 dev.py 调用）：
    python manage.py list-users
    python manage.py reset-password <用户名> [新密码]
        不给新密码则随机生成并打印出来。
"""
import secrets
import sys

from sqlmodel import Session, select

from auth import hash_password
from database import engine, init_db
from models import User


def list_users() -> None:
    with Session(engine) as s:
        users = s.exec(select(User)).all()
        if not users:
            print("（还没有任何用户）")
            return
        print(f"共 {len(users)} 个用户：")
        for u in users:
            print(f"  - id={u.id}  用户名={u.username}  邮箱={u.email or '—'}")


def reset_password(username: str, new_password: str | None) -> None:
    with Session(engine) as s:
        user = s.exec(select(User).where(User.username == username)).first()
        if not user:
            sys.exit(f"[X] 没找到用户：{username}")
        if not new_password:
            new_password = secrets.token_urlsafe(9)
            print(f"已为「{username}」生成新密码： {new_password}")
        user.password_hash = hash_password(new_password)
        s.add(user)
        s.commit()
        print(f"[OK] 已重置「{username}」的密码，请用新密码登录。")


def main() -> None:
    init_db()  # 确保表存在
    args = sys.argv[1:]
    if not args:
        sys.exit("用法：python manage.py list-users | reset-password <用户名> [新密码]")
    cmd = args[0]
    if cmd == "list-users":
        list_users()
    elif cmd == "reset-password":
        if len(args) < 2:
            sys.exit("用法：python manage.py reset-password <用户名> [新密码]")
        reset_password(args[1], args[2] if len(args) > 2 else None)
    else:
        sys.exit(f"未知命令：{cmd}")


if __name__ == "__main__":
    main()
