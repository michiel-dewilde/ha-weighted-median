"""Core algorithm for the time-weighted median sensor.

History is a list of (posix_timestamp: float, value: float | None) pairs, sorted
by timestamp ascending.  Each entry means "the source had *value* from this
timestamp until the next entry (or *now* for the last entry)."  Non-numerical
values are stored as None and excluded from the median calculation.
"""
from __future__ import annotations

import math
from typing import Optional

# (value, weight, eff_start, eff_end)
_Segment = tuple[float | None, float, float, float]


def _is_numerical(val: object) -> bool:
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return not math.isnan(float(val))
    return False


def _build_segments(
    history: list[tuple[float, float | None]],
    window_start: float,
    now: float,
) -> list[_Segment]:
    result: list[_Segment] = []
    n = len(history)
    for i, (ts, val) in enumerate(history):
        eff_start = max(ts, window_start)
        eff_end = history[i + 1][0] if i < n - 1 else now
        if eff_start >= eff_end:
            continue
        result.append((val, eff_end - eff_start, eff_start, eff_end))
    return result


def _weighted_median(num_segs: list[tuple[float, float]]) -> float:
    """Return the time-weighted p50 of (value, weight) pairs."""
    sorted_segs = sorted(num_segs, key=lambda x: x[0])
    total = sum(w for _, w in sorted_segs)
    half = total / 2.0
    cumsum = 0.0
    for val, weight in sorted_segs:
        cumsum += weight
        if cumsum >= half:
            return val
    return sorted_segs[-1][0]


def trim_history(
    history: list[tuple[float, float | None]],
    window_start: float,
) -> list[tuple[float, float | None]]:
    """Keep at most one entry before *window_start*, plus all entries within the window."""
    last_before = -1
    for i, (ts, _) in enumerate(history):
        if ts < window_start:
            last_before = i
        else:
            break
    if last_before > 0:
        return history[last_before:]
    return history


def compute_time_weighted_median(
    history: list[tuple[float, float | None]],
    window_seconds: float,
    now: float,
) -> Optional[float]:
    """Return the time-weighted median over [now-window, now], or None if no numerical data."""
    if not history:
        return None
    window_start = now - window_seconds
    segs = _build_segments(history, window_start, now)
    num_segs = [(val, w) for val, w, _, _ in segs if _is_numerical(val)]
    if not num_segs:
        return None
    return _weighted_median(num_segs)


def compute_next_change_delta(
    history: list[tuple[float, float | None]],
    window_seconds: float,
    now: float,
) -> Optional[float]:
    """
    Return seconds until the weighted median will next change, assuming the source stays
    constant.  Returns None when the median is stable indefinitely (e.g. single segment
    or no further transitions within the window).

    Strategy — three candidate events, whichever comes first:
    1. Oldest segment exits the window entirely (eff_end reaches window_start).
    2. Oldest segment starts being clipped (rates change; recompute from there).
    3. p50 shifts to a different value bucket (solved analytically via linear weight dynamics).

    Candidates 2 and 3 are capped at whichever of 1/2 comes first.
    """
    if not history:
        return None

    window_start = now - window_seconds
    segs = _build_segments(history, window_start, now)
    if not segs:
        return None

    n = len(segs)
    oldest_val, oldest_weight, oldest_eff_start, oldest_eff_end = segs[0]
    newest_val, newest_weight, newest_eff_start, newest_eff_end = segs[-1]
    single_seg = n == 1

    oldest_natural_ts = history[0][0]
    oldest_clipped = oldest_natural_ts < window_start  # eff_start is clipped by window_start

    candidates: list[float] = []

    # ── Candidate 1: oldest segment exits the window ──────────────────────────
    # window_start advances at 1 s/s; oldest exits when window_start reaches oldest_eff_end.
    # Single segment: eff_end = now (advances with window_start), so it never exits.
    if not single_seg:
        delta_oldest_exits = oldest_eff_end - window_start
        if delta_oldest_exits > 1e-6:
            candidates.append(delta_oldest_exits)
    else:
        delta_oldest_exits = None

    # ── Candidate 2: oldest starts being clipped (weight rate changes to -1/s) ─
    # Not applicable for a single segment: oldest == newest, so rates cancel regardless.
    if not single_seg and not oldest_clipped and oldest_natural_ts > window_start:
        delta_clip = oldest_natural_ts - window_start
        if delta_clip > 1e-6:
            candidates.append(delta_clip)
        analysis_cap: Optional[float] = delta_clip
    else:
        delta_clip = None
        analysis_cap = delta_oldest_exits  # may be None for single_seg

    # ── Candidate 3: p50 shifts within the linear-dynamics window ────────────
    num_segs_info = [
        (val, w, i == 0, i == n - 1)
        for i, (val, w, _es, _ee) in enumerate(segs)
        if _is_numerical(val)
    ]

    if not num_segs_info:
        # No numerical data — only event is whichever candidate is earliest
        return min(candidates) if candidates else None

    sorted_num = sorted(num_segs_info, key=lambda x: x[0])
    weights = [w for _, w, _, _ in sorted_num]
    total_w = sum(weights)
    half_w = total_w / 2.0

    # Locate current median bucket j
    j = 0
    cumsum = 0.0
    for idx, w in enumerate(weights):
        cumsum += w
        j = idx
        if cumsum >= half_w:
            break

    oldest_is_num = _is_numerical(oldest_val)
    newest_is_num = _is_numerical(newest_val)

    # Weight-change rates (per second of elapsed time)
    # oldest clipped → its weight shrinks at 1 s/s; newest → grows at 1 s/s.
    # Single segment: oldest == newest → rates cancel.
    if single_seg:
        oldest_w_rate = 0.0
        newest_w_rate = 0.0
    else:
        oldest_w_rate = -1.0 if oldest_clipped else 0.0
        newest_w_rate = 1.0

    oldest_rank = next((i for i, (_, _, is_o, _) in enumerate(sorted_num) if is_o), None)
    newest_rank = next((i for i, (_, _, _, is_n) in enumerate(sorted_num) if is_n), None)

    def rate_up_to(k: int) -> float:
        r = 0.0
        if oldest_is_num and oldest_rank is not None and oldest_rank <= k:
            r += oldest_w_rate
        if newest_is_num and newest_rank is not None and newest_rank <= k:
            r += newest_w_rate
        return r

    rate_total = (oldest_w_rate if oldest_is_num else 0.0) + (
        newest_w_rate if newest_is_num else 0.0
    )

    cumsum_jm1 = sum(weights[:j]) if j > 0 else 0.0
    cumsum_j = sum(weights[: j + 1])

    # f(δ) = 2·cumsum[0..j-1] − total_w  →  median shifts UP  when f ≥ 0
    # g(δ) = 2·cumsum[0..j]   − total_w  →  median shifts DOWN when g < 0
    f0 = 2.0 * cumsum_jm1 - total_w
    g0 = 2.0 * cumsum_j - total_w

    rate_f = 2.0 * (rate_up_to(j - 1) if j > 0 else 0.0) - rate_total
    rate_g = 2.0 * rate_up_to(j) - rate_total

    def _within_cap(delta: float) -> bool:
        return analysis_cap is None or delta <= analysis_cap + 1e-6

    if rate_f > 1e-9 and f0 < -1e-9:
        delta_up = -f0 / rate_f
        if delta_up > 1e-6 and _within_cap(delta_up):
            candidates.append(delta_up)

    if rate_g < -1e-9 and g0 > 1e-9:
        delta_down = -g0 / rate_g
        if delta_down > 1e-6 and _within_cap(delta_down):
            candidates.append(delta_down)

    return min(candidates) if candidates else None
