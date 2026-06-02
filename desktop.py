"""桌面应用入口。

- 把 Flask 跑在后台线程(随机空闲端口、关闭 reloader 和 debug)
- 用 pywebview 打开一个原生窗口指向本地 Flask URL
- 数据目录:
    * 打包后(sys.frozen)放到 %APPDATA%/BookShelf/
    * 开发模式保持项目根目录下的 instance/
- 关闭窗口即退出程序(Flask 线程作为守护线程自动结束)

使用:
    python desktop.py
或双击 launch.bat
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path


# ---------------------------- 数据目录 ----------------------------

def get_instance_path() -> str:
    """返回 Flask instance 目录绝对路径(含 epubs 子目录的父目录)"""
    if getattr(sys, "frozen", False):
        # 打包后的 .exe:放到用户 AppData
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        base = Path(appdata) / "BookShelf"
    else:
        # 开发模式:项目目录/instance
        base = Path(__file__).resolve().parent / "instance"
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def ensure_initial_setup(instance_path: str) -> None:
    """首次启动时把数据库带到最新版本(走 Alembic 迁移)"""
    import app as app_module

    flask_app = app_module.create_app(instance_path=instance_path)
    app_module.bootstrap_db(flask_app)
    print(f"[setup] database at latest revision in {instance_path}/books.db")


# ---------------------------- Flask 线程 ----------------------------

def find_free_port() -> int:
    """让操作系统分配一个空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_flask(host: str, port: int, instance_path: str) -> None:
    """在当前线程启动 Flask(由外层包成 daemon 线程)"""
    import app as app_module

    # 从环境变量覆盖 SECRET_KEY(桌面模式也生成一个每次运行随机的值)
    os.environ.setdefault(
        "SECRET_KEY",
        os.urandom(32).hex(),
    )

    flask_app = app_module.create_app(instance_path=instance_path)
    # debug=False, reloader=False:桌面里不能有 reloader(会重启进程)
    flask_app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def wait_until_ready(host: str, port: int, timeout: float = 15.0) -> bool:
    """等 Flask 起来,能 TCP 连上就返回 True"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ---------------------------- 主入口 ----------------------------

def main() -> int:
    instance_path = get_instance_path()
    print(f"[desktop] instance: {instance_path}")

    # 首次启动的数据库建表 / 迁移
    try:
        ensure_initial_setup(instance_path)
    except Exception as e:
        print(f"[desktop] setup error: {e}")
        # 继续尝试启动,Flask 会报更明确的错

    host = "127.0.0.1"
    port = find_free_port()
    url = f"http://{host}:{port}"
    print(f"[desktop] flask url: {url}")

    # Flask 跑 daemon 线程,主线程负责 pywebview
    t = threading.Thread(
        target=start_flask,
        args=(host, port, instance_path),
        daemon=True,
        name="flask-thread",
    )
    t.start()

    if not wait_until_ready(host, port):
        print("[desktop] Flask 未能在超时时间内启动")
        return 1

    # 打开窗口
    try:
        import webview
    except ImportError:
        print("[desktop] pywebview 未安装,请运行: pip install pywebview")
        return 1

    webview.create_window(
        title="本棚 · 个人书架",
        url=url,
        width=1280,
        height=860,
        min_size=(900, 600),
        resizable=True,
        confirm_close=False,
    )
    # gui=None 让 pywebview 自选(Windows 下默认 EdgeChromium / WebView2)
    webview.start(gui=None, debug=False)

    print("[desktop] window closed, exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
