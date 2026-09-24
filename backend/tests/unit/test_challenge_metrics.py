import sys
from pathlib import Path

import numpy as np

from app.core.config import Settings
from app.services.challenge import RANDOM_POOL, Action, ActionEvaluator, Baseline, Observation, generate_actions

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evaluation"))
from recognition.metrics import eer, far_frr, threshold_at_far  # noqa: E402

S = Settings()
B = Baseline(yaw=0.02, pitch=0.01, eye_openness=0.4)


def test_actions_random_unique_and_end_with_center():
    seqs = {tuple(generate_actions(3)) for _ in range(200)}
    assert len(seqs) > 20  # not a fixed sequence
    for seq in seqs:
        assert seq[-1] == Action.CENTER and len(seq) == 4
        assert len(set(seq[:-1])) == 3 and all(a in RANDOM_POOL for a in seq[:-1])


def test_required_actions_always_included():
    for _ in range(50):
        seq = generate_actions(3, required=(Action.LOOK_LEFT, Action.LOOK_RIGHT))
        assert Action.LOOK_LEFT in seq and Action.LOOK_RIGHT in seq and seq[-1] == Action.CENTER


def _run(action, obs_list, settings=S):
    ev = ActionEvaluator(action, B, settings)
    return [ev.update(o) for o in obs_list]


def test_look_left_needs_two_consecutive_frames():
    turned = Observation(B.yaw + S.yaw_delta + 0.05, B.pitch)
    center = Observation(B.yaw, B.pitch)
    assert _run(Action.LOOK_LEFT, [turned, center, turned]) == [False, False, False]
    assert _run(Action.LOOK_LEFT, [turned, turned]) == [False, True]


def test_wrong_direction_does_not_pass():
    right = Observation(B.yaw - S.yaw_delta - 0.05, B.pitch)
    assert not any(_run(Action.LOOK_LEFT, [right] * 5))
    assert _run(Action.LOOK_RIGHT, [right] * 2)[-1]


def test_mirrored_flag_swaps_left_right():
    turned = Observation(B.yaw + S.yaw_delta + 0.05, B.pitch)
    assert _run(Action.LOOK_RIGHT, [turned] * 2, Settings(camera_mirrored=True))[-1]


def test_up_down():
    up = Observation(B.yaw, B.pitch - S.pitch_delta - 0.05)
    down = Observation(B.yaw, B.pitch + S.pitch_delta + 0.05)
    assert _run(Action.LOOK_UP, [up] * 2)[-1] and not any(_run(Action.LOOK_UP, [down] * 3))
    assert _run(Action.LOOK_DOWN, [down] * 2)[-1]


def test_blink_requires_close_then_open():
    open_ = Observation(B.yaw, B.pitch, 0.4)
    closed = Observation(B.yaw, B.pitch, 0.4 * (S.blink_closed_ratio - 0.1))
    assert not any(_run(Action.BLINK, [open_] * 5))  # never closed
    assert not any(_run(Action.BLINK, [closed] * 5))  # never reopened (e.g. photo with closed eyes)
    assert _run(Action.BLINK, [open_, closed, open_]) == [False, False, True]
    assert not any(_run(Action.BLINK, [Observation(0, 0, None)] * 3))


def test_center():
    assert _run(Action.CENTER, [Observation(B.yaw, B.pitch)] * 2)[-1]
    assert not any(_run(Action.CENTER, [Observation(B.yaw + 0.3, B.pitch)] * 3))


def test_far_frr_and_threshold():
    g = np.array([0.6, 0.7, 0.8, 0.9])
    i = np.array([0.0, 0.1, 0.2, 0.65])
    far, frr = far_frr(g, i, np.array([0.5, 0.65, 0.95]))
    assert far.tolist() == [0.25, 0.25, 0.0]
    assert frr.tolist() == [0.0, 0.25, 1.0]
    t = threshold_at_far(i, 0.0)
    assert t > 0.65 and far_frr(g, i, np.array([t]))[0][0] == 0.0
    assert threshold_at_far(i, 0.25) > 0.2


def test_eer_separable():
    e, _ = eer(np.array([0.8, 0.9]), np.array([0.1, 0.2]))
    assert e == 0.0
