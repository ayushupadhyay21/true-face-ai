"""Active liveness challenges: random action sequences and per-frame action evaluation.

Sign conventions (frames are the RAW, un-mirrored camera image; see SECURITY.md):
  - Subject turns to THEIR left  -> nose moves to IMAGE right -> yaw proxy increases.
  - Subject looks up             -> nose moves toward the eye line -> pitch proxy decreases.
If a client sends mirrored frames, set CAMERA_MIRRORED=true and yaw is negated.

Head-turn actions compare against the subject's own baseline pose measured during the
passive phase, so natural asymmetries and camera placement do not bias the check.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from enum import Enum

from app.core.config import Settings


class Action(str, Enum):
    LOOK_LEFT = "LOOK_LEFT"
    LOOK_RIGHT = "LOOK_RIGHT"
    LOOK_UP = "LOOK_UP"
    LOOK_DOWN = "LOOK_DOWN"
    BLINK = "BLINK"
    CENTER = "CENTER"


RANDOM_POOL = (Action.LOOK_LEFT, Action.LOOK_RIGHT, Action.LOOK_UP, Action.LOOK_DOWN, Action.BLINK)
INSTRUCTIONS = {
    Action.LOOK_LEFT: "Turn your head to your LEFT",
    Action.LOOK_RIGHT: "Turn your head to your RIGHT",
    Action.LOOK_UP: "Tilt your head UP",
    Action.LOOK_DOWN: "Tilt your head DOWN",
    Action.BLINK: "BLINK your eyes",
    Action.CENTER: "Look straight at the camera",
}
CONSECUTIVE_FRAMES = 2  # a head-turn must hold for 2 consecutive frames (rejects single noisy frames)


def generate_actions(length: int, rng: secrets.SystemRandom | None = None,
                     required: tuple[Action, ...] = ()) -> list[Action]:
    """Random sequence from a CSPRNG, no action repeated, always ending with CENTER.

    `required` actions (e.g. LOOK_LEFT/LOOK_RIGHT for enrollment poses) are always included,
    at random positions.
    """
    rng = rng or secrets.SystemRandom()
    length = max(length, len(required))
    pool = [a for a in RANDOM_POOL if a not in required]
    actions = list(required) + rng.sample(pool, length - len(required))
    rng.shuffle(actions)
    return actions + [Action.CENTER]


@dataclass
class Baseline:
    yaw: float
    pitch: float
    eye_openness: float


@dataclass
class Observation:
    yaw: float
    pitch: float
    eye_openness: float | None = None  # only computed when needed (BLINK)


@dataclass
class ActionEvaluator:
    """Stateful checker for one action. `update` returns True once the action is completed."""
    action: Action
    baseline: Baseline
    settings: Settings
    _streak: int = 0
    _closed_seen: bool = False
    history: list[float] = field(default_factory=list)

    def needs_eyes(self) -> bool:
        return self.action == Action.BLINK

    def update(self, obs: Observation) -> bool:
        s, b = self.settings, self.baseline
        sign = -1.0 if s.camera_mirrored else 1.0
        dyaw = sign * (obs.yaw - b.yaw)
        dpitch = obs.pitch - b.pitch
        a = self.action
        if a == Action.BLINK:
            if obs.eye_openness is None or b.eye_openness <= 0:
                return False
            ratio = obs.eye_openness / b.eye_openness
            self.history.append(ratio)
            if ratio < s.blink_closed_ratio:
                self._closed_seen = True
            return self._closed_seen and ratio > s.blink_open_ratio
        if a == Action.LOOK_LEFT:
            ok = dyaw > s.yaw_delta
        elif a == Action.LOOK_RIGHT:
            ok = dyaw < -s.yaw_delta
        elif a == Action.LOOK_UP:
            ok = dpitch < -s.pitch_delta
        elif a == Action.LOOK_DOWN:
            ok = dpitch > s.pitch_delta
        else:  # CENTER
            ok = abs(dyaw) < s.center_tolerance and abs(dpitch) < s.center_tolerance
        self._streak = self._streak + 1 if ok else 0
        return self._streak >= CONSECUTIVE_FRAMES
