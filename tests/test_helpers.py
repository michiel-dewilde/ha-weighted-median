"""Tests for the time-weighted median algorithm."""
from __future__ import annotations

import importlib.util
import math
import os

# Load helpers.py directly so the HA-dependent package __init__ is never executed.
_helpers_path = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "weighted_median", "helpers.py"
)
_spec = importlib.util.spec_from_file_location("helpers", _helpers_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

compute_next_change_delta = _mod.compute_next_change_delta
compute_time_weighted_median = _mod.compute_time_weighted_median
trim_history = _mod.trim_history

EPS = 1e-6


# ── helpers ───────────────────────────────────────────────────────────────────

def h(*pairs):
    """Build history list from alternating (ts, value) pairs."""
    return list(pairs)


# ── trim_history ──────────────────────────────────────────────────────────────

class TestTrimHistory:
    def test_all_inside_window(self):
        hist = [(5.0, 1.0), (8.0, 2.0), (12.0, 3.0)]
        assert trim_history(hist, 3.0) == hist

    def test_keeps_one_before_window(self):
        hist = [(1.0, 1.0), (3.0, 2.0), (6.0, 3.0), (9.0, 4.0)]
        result = trim_history(hist, 5.0)
        # ts=3 is the last entry before window_start=5
        assert result[0] == (3.0, 2.0)
        assert result[-1] == (9.0, 4.0)

    def test_trims_multiple_before_window(self):
        hist = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (10.0, 4.0)]
        result = trim_history(hist, 5.0)
        assert result[0] == (3.0, 3.0)
        assert len(result) == 2

    def test_all_before_window_keeps_last(self):
        hist = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
        result = trim_history(hist, 10.0)
        assert result == [(3.0, 3.0)]

    def test_single_entry_in_window(self):
        hist = [(5.0, 1.0)]
        assert trim_history(hist, 3.0) == hist


# ── compute_time_weighted_median ──────────────────────────────────────────────

class TestComputeMedian:
    def test_empty_history(self):
        assert compute_time_weighted_median([], 10.0, 10.0) is None

    def test_single_constant_value(self):
        # value=42 for the entire window
        hist = [(0.0, 42.0)]
        assert compute_time_weighted_median(hist, 10.0, 10.0) == 42.0

    def test_two_equal_time_segments_lower_wins(self):
        # value=10 for 5 s, then value=20 for 5 s
        hist = [(0.0, 10.0), (5.0, 20.0)]
        result = compute_time_weighted_median(hist, 10.0, 10.0)
        # cumsum after 10: 5 >= 5 (half) → median = 10
        assert result == 10.0

    def test_two_segments_majority_wins(self):
        # value=10 for 3 s, value=20 for 7 s → median = 20
        hist = [(0.0, 10.0), (3.0, 20.0)]
        result = compute_time_weighted_median(hist, 10.0, 10.0)
        assert result == 20.0

    def test_three_values_selects_correct_bucket(self):
        # values: 1 for 3 s, 3 for 7 s, 2 for 2 s (window=12)
        # But times: t=0→1, t=3→3, t=10→2, now=12, window=12
        hist = [(0.0, 1.0), (3.0, 3.0), (10.0, 2.0)]
        result = compute_time_weighted_median(hist, 12.0, 12.0)
        # Sorted: (1,3), (2,2), (3,7); half=6
        # cumsum: 3 < 6, 5 < 6, 12 >= 6 → median = 3
        assert result == 3.0

    def test_non_numerical_values_excluded(self):
        # 5 s of 10, 3 s of None (unavailable), 2 s of 20
        hist = [(0.0, 10.0), (5.0, None), (8.0, 20.0)]
        result = compute_time_weighted_median(hist, 10.0, 10.0)
        # Numerical: (10, 5), (20, 2); half=3.5; cumsum after 10: 5 >= 3.5 → 10
        assert result == 10.0

    def test_all_non_numerical_returns_none(self):
        hist = [(0.0, None), (5.0, None)]
        assert compute_time_weighted_median(hist, 10.0, 10.0) is None

    def test_only_oldest_partially_in_window(self):
        # window=5, now=10, window_start=5
        # history[0] started at t=2 (value=100), history[1] started at t=7 (value=200)
        # Effective: 100 for [5,7]=2 s, 200 for [7,10]=3 s
        hist = [(2.0, 100.0), (7.0, 200.0)]
        result = compute_time_weighted_median(hist, 5.0, 10.0)
        # half=2.5; cumsum after 100: 2 < 2.5; cumsum after 200: 5 >= 2.5 → 200
        assert result == 200.0

    def test_window_clips_old_entry(self):
        # Only the newest value is in the window
        hist = [(0.0, 1.0), (9.0, 99.0)]
        result = compute_time_weighted_median(hist, 5.0, 10.0)
        # window=[5,10]; entry at t=0 covers [5,9]=4 s with value=1
        # entry at t=9 covers [9,10]=1 s with value=99
        # half=2.5; cumsum(1)=4 >= 2.5 → 1
        assert result == 1.0

    def test_nan_treated_as_non_numerical(self):
        hist = [(0.0, float("nan")), (5.0, 42.0)]
        result = compute_time_weighted_median(hist, 10.0, 10.0)
        assert result == 42.0


# ── compute_next_change_delta ─────────────────────────────────────────────────

class TestNextChangeDelta:
    def test_empty_history_returns_none(self):
        assert compute_next_change_delta([], 10.0, 10.0) is None

    def test_single_segment_stable(self):
        # Single segment = single value; oldest == newest, rates cancel → None
        hist = [(0.0, 42.0)]
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert delta is None

    def test_oldest_exits_schedules_correctly(self):
        # window=10, now=15, window_start=5
        # history[0] at t=0 (v=10), window_end at t=8: exits at window_start=8 → delta=8-5=3
        hist = [(0.0, 10.0), (8.0, 20.0)]
        delta = compute_next_change_delta(hist, 10.0, 15.0)
        # oldest_eff_end=8, window_start=5, delta=3
        assert abs(delta - 3.0) < EPS

    def test_median_shifts_before_oldest_exits(self):
        # window=10, now=10, window_start=0
        # v=10 for 6 s (oldest, clipped), v=20 for 4 s (newest)
        # Sorted: (10,6),(20,4); half=5; j=0 (cumsum=6>=5, median=10)
        # As time passes: weight(10) -= 1/s, weight(20) += 1/s
        # Shift happens when cumsum(10) = 5 → weight(10) = 5 → after 1 s
        hist = [(0.0, 10.0), (6.0, 20.0)]
        # oldest at t=0 < window_start=0: not strictly before, so not clipped.
        # Let's set oldest to be strictly before: use t=-1 and window=10, now=10
        hist = [(-1.0, 10.0), (6.0, 20.0)]
        # window_start=-1+1=... let me set clearly:
        # now=10, window=10, window_start=0, oldest at t=-1 → clipped
        # oldest eff_start=0, eff_end=6, weight=6
        # newest eff_start=6, eff_end=10, weight=4
        # Sorted: (10,6),(20,4); half=5; j=0 (cumsum=6>=5)
        # rate_g for j=0: 2*rate_up_to(0) - rate_total
        #   oldest_rank=0, newest_rank=1
        #   rate_up_to(0) = oldest_rate=-1 + (newest if rank<=0 else 0) = -1
        #   rate_total = -1+1=0
        #   rate_g = 2*(-1)-0 = -2
        # g0 = 2*6-10=2; delta_down = -2/(-2)=1
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 1.0) < EPS

    def test_oldest_exits_earlier_than_median_shift(self):
        # v=10 for 2 s (oldest, clipped, exits quickly), v=20 for 8 s
        # At oldest_exit (delta=2): median = 20 (would shift)
        # But median shift analytically happens at... let's compute:
        hist = [(-2.0, 10.0), (2.0, 20.0)]
        # window=10, now=10, window_start=0; oldest eff_start=0, eff_end=2, weight=2
        # oldest exits at delta=2-0=2
        # Sorted: (10,2),(20,8); half=5; j=1 (cumsum=2, 10; 2<5, so j=1, median=20)
        # No shift candidates because median is already at j=1 (upper bucket).
        # Only candidate: delta_oldest_exits=2
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 2.0) < EPS

    def test_newest_non_numerical_oldest_shrinking_shifts_down(self):
        # v=10 for 8 s (oldest, clipped), v=None for 2 s (newest)
        # Numerical: (10, 8); total=8, half=4, j=0, median=10
        # Rates: oldest_rate=-1 (clipped), newest_rate=0 (non-num)
        # rate_total = -1; rate_g = 2*rate_up_to(0) - rate_total
        #   rate_up_to(0): oldest_rank=0, rate=-1; newest is non-num, no rank
        #   rate_total = -1
        #   rate_g = 2*(-1) - (-1) = -1
        # g0 = 2*8-8=8; delta_down = -8/(-1)=8
        # oldest exits at delta=8-0=8 (eff_end=8, window_start=0)
        # Both are 8 → same
        hist = [(-2.0, 10.0), (8.0, None)]
        # window=10, now=10, window_start=0
        # oldest eff_start=0, eff_end=8, weight=8
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        # Both candidates are ~8, so delta ≈ 8
        assert abs(delta - 8.0) < EPS

    def test_oldest_not_clipped_schedules_clip_event(self):
        # oldest starts INSIDE the window → will be clipped in future
        # window=10, now=10, window_start=0
        # oldest at t=3 (inside window, not clipped), eff_start=3, eff_end=7
        hist = [(3.0, 10.0), (7.0, 20.0)]
        # oldest_natural_ts=3 > window_start=0 → not clipped
        # delta_clip = 3 - 0 = 3
        # oldest exits: eff_end=7, delta = 7-0=7
        # median: (10,4),(20,3); half=3.5; cumsum(10)=4 >= 3.5; j=0, median=10
        # rate_g with rates 0,+1: rate_up_to(0): 0 + (newest_rank=1>0→0)=0
        #   rate_total=+1; rate_g=2*0-1=-1
        #   g0=2*4-7=1; delta_down=-1/(-1)=1
        # But analysis_cap=delta_clip=3; 1 <= 3 → candidate
        # candidates: delta_oldest_exits=7, delta_clip=3, delta_down=1
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 1.0) < EPS

    def test_median_shift_capped_at_analysis_boundary(self):
        # oldest not clipped; median shift would occur at delta=5 but delta_clip=3
        # → delta_clip=3 must fire first, shift is not a valid candidate
        # window=10, now=10, window_start=0
        # oldest at t=3, eff_start=3, eff_end=5, weight=2 (value=100)
        # newest at t=5, eff_end=10, weight=5 (value=200)
        hist = [(3.0, 100.0), (5.0, 200.0)]
        # oldest_natural_ts=3 > 0 → not clipped; delta_clip=3
        # Sorted: (100,2),(200,5); total=7, half=3.5; cumsum(100)=2<3.5; j=1; median=200
        # (Already past the shift, median stable at 200 given current rates with oldest_rate=0)
        # rate_g = 2*(oldest:0+newest:rate_up_to(1))−rate_total
        #   rate_up_to(1)=0+1=1; rate_total=0+1=1; rate_g=2*1-1=1>0 → no shift down
        # rate_f = 2*(rate_up_to(0))−rate_total = 2*(0+0)−1=−1<0 → no shift up
        # candidates: delta_oldest_exits=5-0=5, delta_clip=3
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 3.0) < EPS

    def test_all_non_numerical_schedules_oldest_exit(self):
        hist = [(-5.0, None), (3.0, None)]
        # window=10, now=10, window_start=0; oldest eff_end=3, delta=3-0=3
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 3.0) < EPS

    def test_no_change_when_rates_cancel(self):
        # Two segments, same value: median won't shift regardless of weight changes
        hist = [(-2.0, 42.0), (5.0, 42.0)]
        # window=10, now=10, window_start=0
        # Sorted: only one distinct value; j=0 (len=2 but same value)
        # Wait — two segments with same value are two distinct entries in sorted_num
        # Let me reconsider: oldest at t=-2 (clipped), eff_start=0, eff_end=5, weight=5
        # newest at t=5, eff_end=10, weight=5
        # Sorted: [(42,5,oldest,False),(42,5,False,newest)] → two entries same value
        # Actually oldest_rank=0, newest_rank=1 (sorted by value, stable)
        # total=10, half=5; j=0: cumsum=5>=5 → median=42
        # rates: oldest=-1, newest=+1; rate_total=0
        # rate_g = 2*(rate_up_to(0)) - 0 = 2*(-1)=-2; g0=2*5-10=0
        # g0=0: not > 1e-9, no delta_down candidate
        # rate_f = 2*(rate_up_to(-1)) - 0 = 0 → no delta_up
        # candidates: delta_oldest_exits=5-0=5 only
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        # Only oldest_exits is scheduled (weights shift but value stays the same)
        assert abs(delta - 5.0) < EPS

    def test_newest_value_growing_shifts_median_up(self):
        # v=10 for 8 s (not clipped, inside window), v=20 for 2 s
        # window=10, now=10, window_start=0, oldest at t=0 (= window_start, so clipped)
        hist = [(0.0, 10.0), (8.0, 20.0)]
        # oldest_natural_ts=0 = window_start=0 → NOT strictly less, so not clipped
        # Wait: oldest_clipped = oldest_natural_ts < window_start = 0 < 0 = False
        # So oldest_rate=0, delta_clip=0-0=0 → not > 1e-6, skip
        # newest_rate=+1; rate_total=+1
        # Sorted: (10,8),(20,2); half=5; cumsum(10)=8>=5; j=0, median=10
        # rate_g = 2*(rate_up_to(0)) - rate_total
        #   rate_up_to(0): oldest_rank=0, rate=0; newest_rank=1>0→0; total=0
        #   rate_g = 0-1=-1
        # g0=2*8-10=6; delta_down=-6/(-1)=6
        # analysis_cap: no delta_clip (=0, skipped), delta_oldest_exits=8-0=8
        # 6 <= 8 → candidate
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 6.0) < EPS

    def test_verify_median_after_shift(self):
        """After the predicted shift time, median should equal a different value."""
        hist = [(-1.0, 10.0), (6.0, 20.0)]
        now = 10.0
        window = 10.0
        delta = compute_next_change_delta(hist, window, now)
        assert delta is not None

        # Median at now
        m0 = compute_time_weighted_median(hist, window, now)
        # Median just after the predicted shift
        m1 = compute_time_weighted_median(hist, window, now + delta + 0.001)
        assert m0 != m1, f"Expected median to change: {m0} → {m1}"

    def test_single_value_eventually_only_value(self):
        """If only one value remains and oldest exits, sensor becomes unavailable."""
        # After oldest exits, if the single remaining value is the current state, that's the outcome.
        hist = [(-3.0, 10.0), (8.0, 20.0)]
        now = 10.0
        window = 10.0
        # oldest exits at delta = 8 - 0 = 8
        delta = compute_next_change_delta(hist, window, now)
        assert delta is not None

        # At now+delta, oldest has just exited; only (8, 20) remains
        new_now = now + delta + 0.001
        m = compute_time_weighted_median(hist, window, new_now)
        # Only entry (8, 20) is in window [now+delta-10, now+delta]
        assert m == 20.0

    def test_median_stable_no_future_change(self):
        # Single numerical value, no other data → median never changes on its own
        hist = [(5.0, 7.0)]
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        # Single segment: None
        assert delta is None


# ── non-numerical oldest / newest (explicit coverage) ────────────────────────

class TestNonNumericalEndpoints:
    """
    Verify that the rate analysis correctly ignores non-numerical endpoints
    while still tracking their effect on scheduling.
    """

    def test_oldest_non_numerical_median_shifts_as_newest_grows(self):
        # window=10, now=10, window_start=0
        # seg0: None (oldest, clipped, eff=[0,3], w=3)
        # seg1: v=10 (eff=[3,6], w=3)
        # seg2: v=20 (newest, eff=[6,10], w=4)
        hist = [(-1.0, None), (3.0, 10.0), (6.0, 20.0)]
        # total_w=7, half=3.5; sorted: (10,3),(20,4); cumsum: 3<3.5 → j=1; median=20
        assert compute_time_weighted_median(hist, 10.0, 10.0) == 20.0

        # oldest_is_num=False → does NOT contribute to rate_total or rate_up_to
        # newest_is_num=True, newest_rank=1 → rate_total=+1
        # j=1: rate_up_to(1) includes newest → +1; rate_g = 2*1-1=1>0 (g increasing, no shift down)
        # rate_up_to(0): newest_rank=1 > 0 → 0; rate_f = 2*0-1=-1<0 (f decreasing, no shift up)
        # Only candidate: delta_oldest_exits = 3-0=3
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 3.0) < EPS

        # After oldest non-num exits at delta=3: only (10,3),(20,7) remain in window
        # new total=10, half=5; cumsum(10)=3<5 → median=20 (unchanged value)
        m_after = compute_time_weighted_median(hist, 10.0, 10.0 + 3.001)
        assert m_after == 20.0

    def test_oldest_non_numerical_causes_median_shift_after_its_exit(self):
        # seg0: None (oldest, clipped, w=6)
        # seg1: v=10 (w=2)
        # seg2: v=20 (newest, w=2)
        # window=10, now=10, window_start=0
        hist = [(-2.0, None), (6.0, 10.0), (8.0, 20.0)]
        # total_w=4, half=2; sorted: (10,2),(20,2); cumsum: 2>=2 → j=0; median=10
        assert compute_time_weighted_median(hist, 10.0, 10.0) == 10.0

        # oldest_is_num=False → rate_total = newest_rate = +1
        # j=0; rate_up_to(0): newest_rank=1>0 → 0; rate_g = 0-1=-1
        # g0=2*2-4=0 → NOT > 1e-9, no delta_down candidate
        # rate_f = 0 → no delta_up
        # Only candidate: delta_oldest_exits = 6-0=6
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 6.0) < EPS

        # After oldest (None) exits at delta=6: (10,2),(20,2+6=8) in window
        # total=10, half=5; cumsum(10)=2<5 → median=20
        m_after = compute_time_weighted_median(hist, 10.0, 10.0 + 6.001)
        assert m_after == 20.0

    def test_newest_non_numerical_oldest_numerical_clipped_shifts_median(self):
        # seg0: v=10 (oldest, clipped at t=-2, eff=[0,6], w=6)
        # seg1: v=20 (eff=[6,8], w=2)   ← None starts at t=8, so this is only 2 s
        # seg2: None (newest, eff=[8,10], w=2)
        # window=10, now=10, window_start=0
        hist = [(-2.0, 10.0), (6.0, 20.0), (8.0, None)]
        # total_w=8 (6+2), half=4; sorted: (10,6),(20,2); cumsum: 6>=4 → j=0; median=10
        assert compute_time_weighted_median(hist, 10.0, 10.0) == 10.0

        # newest_is_num=False → rate_total = oldest_w_rate = -1
        # j=0; rate_up_to(0): oldest_rank=0 → -1; newest non-num → skip; = -1
        # rate_g = 2*(-1)-(-1) = -1; g0=2*6-8=4; delta_down=-4/(-1)=4
        # At delta=δ: weight(10)=6-δ, weight(20)=2, total=8-δ, half=(8-δ)/2
        # Median shifts when 6-δ < (8-δ)/2 → δ > 4
        # delta_oldest_exits = 6-0=6; analysis_cap=6; 4<=6 → candidate
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 4.0) < EPS

        # At delta=4 (boundary): weight(10)=2, weight(20)=2, total=4, half=2
        # cumsum(10)=2 >= 2 → still 10 (lower wins at exact boundary)
        m_at = compute_time_weighted_median(hist, 10.0, 10.0 + 4.0)
        assert m_at == 10.0

        # Just after: weight(10)<2=half → median shifts to 20
        m_after = compute_time_weighted_median(hist, 10.0, 10.0 + 4.001)
        assert m_after == 20.0

    def test_both_endpoints_non_numerical_median_stable(self):
        # Both oldest and newest non-numerical; middle segments numerical and fixed weight
        # seg0: None (oldest, clipped, eff=[0,4], w=4)
        # seg1: v=10 (eff=[4,6], w=2)
        # seg2: v=20 (eff=[6,8], w=2)
        # seg3: None (newest, eff=[8,10], w=2)
        hist = [(-2.0, None), (4.0, 10.0), (6.0, 20.0), (8.0, None)]
        # window=10, now=10, window_start=0
        # total_w=4 (2+2), half=2; sorted: (10,2),(20,2); cumsum(10)=2>=2 → j=0; median=10
        assert compute_time_weighted_median(hist, 10.0, 10.0) == 10.0

        # oldest_is_num=False, newest_is_num=False → rate_total=0, rate_up_to=0 for all k
        # rate_f=rate_g=0 → no shift candidates
        # Only candidate: delta_oldest_exits = 4-0=4
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 4.0) < EPS

        # Median stays 10 throughout (numerical weights fixed until oldest non-num exits)
        assert compute_time_weighted_median(hist, 10.0, 10.0 + 2.0) == 10.0

    def test_newest_non_numerical_sole_numerical_exits_becomes_unavailable(self):
        # seg0: v=42 (oldest, clipped, w=5)
        # seg1: None (newest)
        hist = [(-2.0, 42.0), (5.0, None)]
        # window=10, now=10, window_start=0; total_w=5, median=42
        assert compute_time_weighted_median(hist, 10.0, 10.0) == 42.0

        # oldest_is_num=True, clipped → oldest_w_rate=-1
        # newest_is_num=False → rate_total=-1
        # j=0 (only one bucket); rate_g = 2*(-1)-(-1)=-1; g0=2*5-5=5
        # delta_down=5; delta_oldest_exits=5; both=5 → same
        delta = compute_next_change_delta(hist, 10.0, 10.0)
        assert abs(delta - 5.0) < EPS

        # After delta=5: the only numerical segment exits → unavailable
        assert compute_time_weighted_median(hist, 10.0, 10.0 + 5.001) is None
