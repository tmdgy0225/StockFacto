"""재현 가능한 가상 가격 시계열 생성기 (A/B 테스트는 입력이 같아야 하므로 seed 고정)."""
from __future__ import annotations

import random


def generate_bars(spec: dict) -> list[dict]:
    rng = random.Random(spec.get("seed", 0))
    n = spec.get("n", 60)
    pattern = spec.get("pattern", "flat")
    close = float(spec.get("start", 10_000))
    bars = []
    for t in range(n):
        open_ = close * (1 + rng.gauss(0, 0.002))
        if pattern == "pump_dump":
            ret = 0.03 if 1 <= t <= 5 else (-0.05 if 6 <= t <= 15 else rng.gauss(0, 0.006))
        elif pattern == "uptrend":
            ret = rng.gauss(0.004, 0.012)
        elif pattern == "gap_down":
            gap_at = spec.get("gap_at", 8)
            if t == gap_at:
                open_ = close * (1 - spec.get("gap", 0.4))
                ret = -0.01
            else:
                ret = rng.gauss(0, 0.003)
        else:
            ret = rng.gauss(0, 0.008)
        new_close = open_ * (1 + ret) if pattern == "gap_down" else close * (1 + ret)
        wiggle = abs(rng.gauss(0, 0.003))
        high = max(open_, new_close) * (1 + wiggle)
        low = min(open_, new_close) * (1 - wiggle)
        bars.append({"t": t, "open": round(open_, 2), "high": round(high, 2), "low": round(low, 2), "close": round(new_close, 2)})
        close = new_close
    return bars
