"""One-click launcher shared by ``start.bat`` and ``start.sh``.

逻辑放在 Python 而不是批处理里，有三个原因：

1. Windows 的 .bat 用非 ASCII 字符会被代码页弄坏，中文提示只能从这里输出；
2. 判端口、查依赖、开浏览器三个平台行为要一致，shell 写两遍必然漂移；
3. 依赖缺失时要能自己装，而不是甩一句 "ModuleNotFoundError" 给用户。

它只负责“把服务拉起来并照顾好周边”，真正的启动仍是 ``webapp/__main__.py``，
所以 ``python -m webapp`` 这条路永远等价可用。
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"

# 与 webapp/config.py 的默认值保持一致。这里刻意不 import 它：
# 依赖缺失时配置模块也可能导不进来，而启动器必须先能跑起来报错。
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8770

# 工作台必需的运行时依赖：(import 名, pip 名)
CORE_DEPS: tuple[tuple[str, str], ...] = (
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("jinja2", "jinja2"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
)

# 有则更好，缺了不影响页面浏览，只影响训练/绘图等进阶功能
OPTIONAL_DEPS: tuple[tuple[str, str], ...] = (
    ("scipy", "scipy"),
    ("sklearn", "scikit-learn"),
    ("matplotlib", "matplotlib"),
    ("openpyxl", "openpyxl"),
    ("torch", "torch"),
)

HELP = """用法: start.bat [选项]   （Linux/macOS: ./start.sh [选项]）

选项
  --restart       先停止本机已在运行的工作台，再启动（需确认）
  --no-browser    不自动打开浏览器
  --port <端口>   临时改用指定端口
  --help          显示本帮助

环境变量
  EEG_PYTHON      指定解释器路径（默认自动探测 .venv / py -3.12 / python）
  EEG_WEB_HOST    监听地址，默认 0.0.0.0（被试需局域网可达）
  EEG_WEB_PORT    监听端口，默认 8770
  EEG_WEB_TOKEN   管理端访问令牌；正式采集务必设置
  EEG_NO_BROWSER  设为 1 等价于 --no-browser
"""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _ask(question: str) -> bool:
    """交互确认；非交互环境（脚本/CI）一律视为否。"""

    if not sys.stdin.isatty():
        return False
    try:
        return input(question).strip().lower() not in {"n", "no", "否", "不"}
    except EOFError:
        return False


def _health_ok(port: int, timeout: float = 1.5) -> bool:
    """确认端口上跑的是不是本工作台，避免误判/误杀别的程序。"""

    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    target = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    try:
        with socket.create_connection((target, port), timeout=timeout):
            return True
    except OSError:
        return False


def _decode(raw: bytes) -> str:
    """中文 Windows 的 netstat 输出是 GBK，按 UTF-8 硬解会直接抛异常。"""

    for encoding in ("utf-8", "mbcs", "gbk"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def _run_text(command: list[str], timeout: float = 10) -> str:
    """执行命令并稳健解码；任何失败都退回空字符串，由调用方当作“查不到”。"""

    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return _decode(completed.stdout or b"")


def _listening_pids(port: int) -> list[int]:
    """查出监听指定端口的进程号；拿不到就返回空，调用方按“无法定位”处理。"""

    pids: list[int] = []
    if os.name == "nt":
        for line in _run_text(["netstat", "-ano", "-p", "TCP"]).splitlines():
            parts = line.split()
            # 形如: TCP  0.0.0.0:8770  0.0.0.0:0  LISTENING  43152
            if len(parts) >= 5 and parts[3].upper() == "LISTENING":
                if parts[1].rsplit(":", 1)[-1] == str(port) and parts[4].isdigit():
                    pids.append(int(parts[4]))
    elif shutil.which("lsof"):
        for value in _run_text(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"]).split():
            if value.isdigit():
                pids.append(int(value))
    return sorted(set(pids))


def _stop(pids: list[int], port: int) -> bool:
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            else:
                os.kill(pid, 15)
        except (OSError, subprocess.SubprocessError):
            return False
    deadline = time.time() + 6
    while time.time() < deadline:
        if not _port_open("127.0.0.1", port):
            return True
        time.sleep(0.2)
    return False


def _missing_core() -> list[str]:
    return [pip_name for module, pip_name in CORE_DEPS if find_spec(module) is None]


def _missing_optional() -> list[str]:
    return [pip_name for module, pip_name in OPTIONAL_DEPS if find_spec(module) is None]


def _install(packages: list[str]) -> bool:
    print(f"  正在安装: {' '.join(packages)}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", *packages],
        cwd=str(ROOT),
    )
    return result.returncode == 0


def _browser(url: str, delay: float = 1.8) -> None:
    """等服务真正开始监听再开浏览器，否则会先看到“无法连接”。"""

    def worker() -> None:
        deadline = time.time() + 25
        while time.time() < deadline:
            if _health_ok(_PORT_HOLDER[0], timeout=0.8):
                break
            time.sleep(0.3)
        else:
            return
        try:
            webbrowser.open(url)
        except Exception:  # 浏览器打不开不该让服务退出
            pass

    threading.Thread(target=worker, daemon=True).start()


_PORT_HOLDER = [DEFAULT_PORT]


def _resolve_options(argv: list[str]) -> tuple[int, str, bool, bool]:
    """解析命令行，返回 (端口, 监听地址, 是否开浏览器, 是否重启)。"""

    host = (os.environ.get("EEG_WEB_HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST
    raw_port = os.environ.get("EEG_WEB_PORT") or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
    except ValueError:
        print(f"[错误] EEG_WEB_PORT 不是数字: {raw_port!r}")
        raise SystemExit(2)

    no_browser = _truthy(os.environ.get("EEG_NO_BROWSER"))
    restart = False
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg in {"--help", "-h", "/?"}:
            print(HELP)
            raise SystemExit(0)
        if arg == "--no-browser":
            no_browser = True
        elif arg == "--restart":
            restart = True
        elif arg == "--port":
            if not rest:
                print("[错误] --port 后面要跟端口号")
                raise SystemExit(2)
            try:
                port = int(rest.pop(0))
            except ValueError:
                print("[错误] --port 需要数字")
                raise SystemExit(2)
        else:
            print(f"[提示] 忽略未知参数: {arg}")
    return port, host, not no_browser, restart


def main(argv: list[str] | None = None) -> int:
    port, host, open_browser, restart = _resolve_options(list(argv or sys.argv[1:]))
    _PORT_HOLDER[0] = port
    local_url = f"http://127.0.0.1:{port}"

    print("=" * 62)
    print(" EEG-EmoStudio 一键启动")
    print("=" * 62)
    print(f" 解释器 : {sys.executable}")
    print(f" 端口   : {port}（监听 {host}）")

    # 1) 端口已被占用：区分“自己的服务”和“别人的程序”
    if _port_open(host, port):
        if _health_ok(port):
            print()
            print(f"[提示] 工作台已经在运行：{local_url}")
            if restart:
                if not _ask("  --restart 会强制停止现有进程，继续？[y/N] "):
                    print("  已取消，保持现有服务。")
                    if open_browser:
                        webbrowser.open(local_url)
                    return 0
                pids = _listening_pids(port)
                if not pids:
                    print(f"[错误] 无法定位监听 {port} 的进程，请手动关闭后重试。")
                    return 1
                print(f"  正在停止 PID {', '.join(map(str, pids))} ...")
                if not _stop(pids, port):
                    print(f"[错误] 停止失败，端口 {port} 仍被占用。")
                    return 1
                print("  已停止，重新启动。")
            else:
                if not _ask("  要重启吗？[y/N] "):
                    if open_browser:
                        webbrowser.open(local_url)
                    print("  直接打开现有页面即可；需要重启请加 --restart。")
                    return 0
                pids = _listening_pids(port)
                if not pids or not _stop(pids, port):
                    print(f"[错误] 无法重启：端口 {port} 仍被占用。")
                    return 1
                print("  已重启。")
        else:
            print()
            print(f"[错误] 端口 {port} 被其他程序占用（{local_url} 不是本工作台）。")
            print(f"       换个端口重试：start.bat --port {port + 1}")
            return 1

    # 2) 依赖自检：只装 Web 运行必需的那几个，不把 torch 拽进来
    missing = _missing_core()
    if missing:
        print()
        print(f"[缺少依赖] {', '.join(missing)}")
        if not sys.stdin.isatty():
            print(f"  请执行: {sys.executable} -m pip install -r requirements.txt")
            return 1
        if not _ask("  现在安装这些 Web 运行依赖？[Y/n] "):
            print(f"  已跳过；请手动执行: {sys.executable} -m pip install -r requirements.txt")
            return 1
        if not _install(missing):
            print("[错误] 安装失败，请检查网络或代理后重试。")
            return 1
        print("  安装完成。")

    absent_optional = _missing_optional()
    if absent_optional:
        print(f" [提示] 未安装的可选依赖: {', '.join(absent_optional)}")
        print("        工作台可以正常浏览；训练与绘图请执行 pip install -r requirements.txt")

    # 3) 起来之后再开浏览器，避免先看到一个连不上的页面
    if open_browser:
        _browser(local_url)

    sys.path.insert(0, str(ROOT))
    from webapp.__main__ import main as run_server

    try:
        run_server()
    except KeyboardInterrupt:
        print("\n已停止。")
        return 0
    except OSError as exc:
        print(f"\n[错误] 启动失败: {exc}")
        if "address already in use" in str(exc).lower() or getattr(exc, "errno", None) == 98:
            print(f"       端口 {port} 已被占用，用 start.bat --port {port + 1} 换一个。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
