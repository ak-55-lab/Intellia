from __future__ import annotations

import logging
import sys
from typing import Optional

_CONFIGURED = False


def configure(debug: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s"))
    root = logging.getLogger("intellia")
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger("intellia" if not name else "intellia.{}".format(name))
