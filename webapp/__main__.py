"""Run the local web console: ``python -m webapp``.

配置全部来自 :mod:`webapp.config`（可用环境变量覆盖），这里只负责启动与
把访问地址打印出来——之前地址藏在代码里，换台机器就要翻源码找端口。
"""

from __future__ import annotations

import socket

import uvicorn

from .config import ACCESS_TOKEN, LOOPBACK_HOSTS, WEB_HOST, WEB_PORT, WEB_RELOAD


def _lan_ip() -> str:
    """本机在局域网中的地址；拿不到就退回回环地址。"""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    lan = _lan_ip()
    local_url = f"http://127.0.0.1:{WEB_PORT}"
    lan_url = f"http://{lan}:{WEB_PORT}"

    print("=" * 62)
    print("EEG-EmoStudio 工作台")
    print(f"  本机访问 : {local_url}")
    if WEB_HOST in LOOPBACK_HOSTS:
        print("  局域网   : 未开放（EEG_WEB_HOST=127.0.0.1，被试无法访问）")
    else:
        print(f"  被试访问 : {lan_url}   ← 问卷链接基地址")
    if ACCESS_TOKEN:
        print("  管理端令牌: 已启用（打开页面时加 ?token=... 一次即可）")
    else:
        print("  管理端令牌: 未启用 —— 同网段任何人可查看并导出全部答卷")
        print("             正式采集请先设置 EEG_WEB_TOKEN=自定义字符串")
    print("=" * 62)

    uvicorn.run(
        "webapp.main:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=WEB_RELOAD,
        log_level="info",
    )


if __name__ == "__main__":
    main()
