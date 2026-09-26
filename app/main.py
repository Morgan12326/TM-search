# -*- coding: utf-8 -*-
"""Service startup."""
from __future__ import annotations

try:
    from . import store as runtime_store
    from .core import *
    from .http_server import Handler
    from .store import Store
except ImportError:  # Direct execution compatibility.
    import store as runtime_store
    from core import *
    from http_server import Handler
    from store import Store

def main():
    runtime_store.STORE = Store()
    url = f"http://127.0.0.1:{PORT}/"
    print(f"\n型月搜索 v1.1.7 已启动：{url}\n"
          f"运行版本：{SERVER_BUILD}\n（关闭本窗口即可结束程序）\n")
    if os.environ.get("TM_DICT_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()











