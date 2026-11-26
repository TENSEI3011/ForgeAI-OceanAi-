"""Today's date and time (local clock)."""
from __future__ import annotations

import datetime as dt
from typing import Any


def run(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    now = dt.datetime.now()
    return f"Today is {now:%A, %d %B %Y} (ISO {now:%Y-%m-%d}), local time {now:%H:%M}."
