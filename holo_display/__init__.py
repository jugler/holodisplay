from __future__ import annotations

__all__ = ["main"]


def main(*args, **kwargs):
    from .app import main as app_main

    return app_main(*args, **kwargs)
