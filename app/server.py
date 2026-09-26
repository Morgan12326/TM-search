# -*- coding: utf-8 -*-
"""Type-Moon Search public service facade.

The implementation is split by responsibility, while this module keeps the
historical ``app.server`` imports available for callers and tests.
"""
from __future__ import annotations

try:
    from . import core
    from . import store
    runtime_store = store
    from .core import *
    from .http_server import Handler
    from .main import main
    from .store import Store
except ImportError:  # Direct execution compatibility.
    import core
    import store
    runtime_store = store
    from core import *
    from http_server import Handler
    from main import main
    from store import Store

__all__ = list(core.__all__) + ["Store", "Handler", "main", "STORE"]


def __getattr__(name):
    if name == "STORE":
        return runtime_store.STORE
    raise AttributeError(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
