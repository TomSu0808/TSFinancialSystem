#!/usr/bin/env python3
"""跨平台启动器（Mac / Windows 通用，逻辑只维护这一份）。

用法：
    python dev.py          # = start
    python dev.py start     # 自动补齐环境 + 起前后端 + 开浏览器
    python dev.py stop      # 按端口停掉前后端 (8000 / 5173)
    python dev.py setup     # 只装环境，不启动

自愈逻辑：检测到 backend/.venv、依赖、frontend/node_modules 缺失（或 venv 来自
别的操作系统跑不起来）时，会自动为「当前系统」重建，所以在 Mac / Win 之间切换
不用再手动配环境，也绝不会出现「Mac 的 venv 拿到 Win 上崩溃」的问题。
"""
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Windows 控制台常是 GBK，强制 UTF-8 输出，避免日志里非 GBK 字符导致崩溃
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def child_env() -> dict:
    """给子进程统一 UTF-8 IO，避免 uvicorn/akshare 日志在 GBK 控制台崩溃。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
PID_FILE = ROOT / ".dev-server-pids.json"


def platform_tag() -> str:
    system = platform.system().lower()
    if system.startswith("windows"):
        system = "win"
    elif system == "darwin":
        system = "mac"
    return f"{system}-py{sys.version_info.major}{sys.version_info.minor}"


LEGACY_VENV = BACKEND / ".venv"
PREFERRED_VENV = BACKEND / f".venv-{platform_tag()}"
VENV = PREFERRED_VENV


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if IS_WIN else "bin/python")


VENV_PY = venv_python(VENV)


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def run(cmd, cwd=None, env=None) -> int:
    """前台执行并继承控制台输出，返回退出码。"""
    return subprocess.run(cmd, cwd=cwd, env=env).returncode


def npm_cmd() -> str:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("[X] 没找到 npm，请先安装 Node.js（https://nodejs.org）")
    return npm


# ----------------------------- 自愈安装 -----------------------------
def _check(code: str, python_path=None) -> bool:
    """在 venv 里跑一段 import 检测；捕获输出（不继承控制台，避免编码崩溃）。"""
    python_path = python_path or VENV_PY
    try:
        return subprocess.run(
            [str(python_path), "-c", code],
            capture_output=True, env=child_env(),
        ).returncode == 0
    except OSError:
        return False


def venv_is_healthy() -> bool:
    return VENV_PY.exists() and _check("import sys")


def legacy_venv_is_healthy() -> bool:
    legacy_python = venv_python(LEGACY_VENV)
    return legacy_python.exists() and _check("import sys", legacy_python)


def select_venv() -> None:
    """Use one backend venv per OS/Python, but keep a healthy legacy .venv usable."""
    global VENV, VENV_PY
    if PREFERRED_VENV.exists():
        VENV = PREFERRED_VENV
    elif LEGACY_VENV.exists() and legacy_venv_is_healthy():
        VENV = LEGACY_VENV
    else:
        VENV = PREFERRED_VENV
    VENV_PY = venv_python(VENV)


def deps_installed() -> bool:
    return _check("import fastapi, uvicorn, sqlmodel, akshare, openai")


def ensure_backend() -> None:
    select_venv()
    log(f"使用后端虚拟环境 {VENV.relative_to(ROOT)}")

    # 1) venv：不存在 / 当前系统跑不起来 → 重建当前系统专属环境
    if VENV.exists() and not venv_is_healthy():
        log("检测到无效的虚拟环境，正在重建…")
        shutil.rmtree(VENV, ignore_errors=True)
    fresh = not VENV.exists()
    if fresh:
        log(f"创建后端虚拟环境 {VENV.relative_to(ROOT)} …")
        if run([sys.executable, "-m", "venv", str(VENV)]) != 0:
            sys.exit("[X] 创建虚拟环境失败")

    # 2) 依赖：新建的 venv 或缺依赖 → 安装
    if fresh or not deps_installed():
        log("安装后端依赖（首次或环境变更，需联网，请稍候）…")
        env = os.environ.copy()
        env.setdefault("SETUPTOOLS_USE_DISTUTILS", "stdlib")  # Win + Store Python 兼容
        run([str(VENV_PY), "-m", "pip", "install", "--upgrade",
             "pip", "setuptools", "wheel"], env=env)
        if run([str(VENV_PY), "-m", "pip", "install", "-r",
                str(BACKEND / "requirements.txt")], env=env) != 0:
            sys.exit("[X] 后端依赖安装失败")
    log("后端环境就绪 [OK]")


def ensure_frontend() -> None:
    if not (FRONTEND / "node_modules").exists():
        log("安装前端依赖 npm install（首次，需联网）…")
        if run([npm_cmd(), "install"], cwd=str(FRONTEND)) != 0:
            sys.exit("[X] 前端依赖安装失败")
    log("前端环境就绪 [OK]")


# ----------------------------- 启停 -----------------------------
def kill_by_port(*ports) -> None:
    plist = ",".join(str(p) for p in ports)
    if IS_WIN:
        subprocess.run([
            "powershell", "-NoProfile", "-Command",
            f"Get-NetTCPConnection -LocalPort {plist} -State Listen "
            f"-ErrorAction SilentlyContinue | Select-Object -ExpandProperty "
            f"OwningProcess -Unique | ForEach-Object {{ Stop-Process -Id $_ "
            f"-Force -ErrorAction SilentlyContinue }}",
        ])
    else:
        for port in ports:
            result = subprocess.run(
                ["lsof", "-ti", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True, text=True,
            )
            for pid in result.stdout.splitlines():
                if pid.strip():
                    _kill_pid(int(pid.strip()))


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int) -> bool:
    if not _pid_running(pid):
        return False
    try:
        if IS_WIN:
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue",
            ])
        else:
            os.kill(pid, 15)
            time.sleep(0.4)
            if _pid_running(pid):
                os.kill(pid, 9)
        return True
    except OSError:
        return False


def write_pid_file(backend, frontend, backend_port: int, frontend_port: int) -> None:
    payload = {
        "backend_pid": backend.pid,
        "frontend_pid": frontend.pid,
        "backend_port": backend_port,
        "frontend_port": frontend_port,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    PID_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_pid_file() -> dict:
    if not PID_FILE.exists():
        return {}
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def port_listeners(*ports) -> list[tuple[int, str]]:
    """Return listening processes for the given ports as (port, pid) pairs."""
    if IS_WIN:
        script = (
            f"$ports=@({','.join(str(p) for p in ports)}); "
            "Get-NetTCPConnection -LocalPort $ports -State Listen "
            "-ErrorAction SilentlyContinue | "
            "Select-Object LocalPort,OwningProcess | "
            "ForEach-Object { \"$($_.LocalPort) $($_.OwningProcess)\" }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, env=child_env(),
        )
        rows: list[tuple[int, str]] = []
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) == 2:
                rows.append((int(parts[0]), parts[1]))
        return rows

    rows = []
    for port in ports:
        result = subprocess.run(
            ["sh", "-c", f"lsof -ti :{port}"],
            capture_output=True, text=True,
        )
        for pid in result.stdout.splitlines():
            if pid.strip():
                rows.append((port, pid.strip()))
    return rows


def find_free_port(start_port: int, attempts: int = 20) -> int:
    """Find a localhost port that can be bound by a new server."""
    for port in range(start_port, start_port + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"找不到可用端口：{start_port}-{start_port + attempts - 1}")


def stop() -> None:
    info = read_pid_file()
    backend_port = int(info.get("backend_port") or BACKEND_PORT)
    frontend_port = int(info.get("frontend_port") or FRONTEND_PORT)
    print(f"停止后端({backend_port})与前端({frontend_port})…", flush=True)

    for key in ("backend_pid", "frontend_pid"):
        pid = int(info.get(key) or 0)
        _kill_pid(pid)

    # 兼容旧版本启动器：没有 pid 文件时仍按端口兜底清理。
    kill_by_port(backend_port, frontend_port)
    if PID_FILE.exists():
        PID_FILE.unlink()
    print("已停止。", flush=True)


def start() -> None:
    ensure_backend()
    ensure_frontend()

    backend_port = find_free_port(BACKEND_PORT)
    frontend_port = find_free_port(FRONTEND_PORT)
    if backend_port != BACKEND_PORT:
        listeners = port_listeners(BACKEND_PORT)
        detail = ", ".join(f"{port}->PID {pid}" for port, pid in listeners) or "未知进程"
        print(f"[!] 端口 {BACKEND_PORT} 被占用（{detail}），本次改用后端端口 {backend_port}", flush=True)
    if frontend_port != FRONTEND_PORT:
        print(f"[!] 端口 {FRONTEND_PORT} 被占用，本次改用前端端口 {frontend_port}", flush=True)

    print(f"\n启动中：后端 http://localhost:{backend_port} ｜ 前端 http://localhost:{frontend_port}", flush=True)
    print("（两个服务的日志都会打印在本窗口；按 Ctrl+C 同时停止）\n", flush=True)

    backend = subprocess.Popen(
        [str(VENV_PY), "-m", "uvicorn", "main:app",
         "--port", str(backend_port)],
        cwd=str(BACKEND), env=child_env(),
    )
    frontend_env = child_env()
    frontend_env["BACKEND_PORT"] = str(backend_port)
    frontend = subprocess.Popen(
        [npm_cmd(), "run", "dev", "--", "--port", str(frontend_port)],
        cwd=str(FRONTEND), env=frontend_env,
    )
    write_pid_file(backend, frontend, backend_port, frontend_port)

    threading.Timer(
        7.0, lambda: webbrowser.open(f"http://localhost:{frontend_port}")
    ).start()

    try:
        while True:
            if backend.poll() is not None or frontend.poll() is not None:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (backend, frontend):
            p.terminate()
        kill_by_port(backend_port, frontend_port)  # 确保 reload 子进程也清掉
        if PID_FILE.exists():
            PID_FILE.unlink()
        print("\n已全部停止。", flush=True)


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "start").lower()
    if cmd == "stop":
        stop()
    elif cmd == "setup":
        ensure_backend()
        ensure_frontend()
        log("环境已就绪，可运行：python dev.py")
    elif cmd == "start":
        start()
    elif cmd in ("reset-password", "list-users"):
        # 账号管理：在 venv 内跑 backend/manage.py（需要 bcrypt 等依赖）
        ensure_backend()
        sys.exit(run(
            [str(VENV_PY), str(BACKEND / "manage.py"), cmd, *sys.argv[2:]],
            cwd=str(BACKEND), env=child_env(),
        ))
    else:
        sys.exit(f"未知命令：{cmd}（可用：start / stop / setup / "
                 f"reset-password / list-users）")


if __name__ == "__main__":
    main()
