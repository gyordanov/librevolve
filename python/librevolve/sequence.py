"""Motion sequences: step type, compact-string parser and per-step wait timeouts."""

from __future__ import annotations

import math
import re
from typing import Iterable, List, NamedTuple, Optional, Sequence, Union

from librevolve import protocol as proto

ACTIONS = ('rotate', 'tilt', 'zero', 'wait')

# Half the ~6.5 deg/s observed at the default TURNSPEED, so a slow table still fits.
SEQUENCE_MIN_SPEED_DEG_S = 3.0
SEQUENCE_TIMEOUT_MARGIN_S = 15.0

_TOKEN_RE = re.compile(r'^(?P<code>[rtzw])(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+))?$', re.IGNORECASE)
_CODE_ACTION = {'r': 'rotate', 't': 'tilt', 'z': 'zero', 'w': 'wait'}
_ACTION_CODE = {action: code for code, action in _CODE_ACTION.items()}


class SequenceError(ValueError):
    """A sequence step or sequence string is malformed or out of range."""


class SequenceStep(NamedTuple):
    """``rotate`` relative deg, ``tilt`` absolute deg, ``zero`` both axes, ``wait`` seconds."""

    action: str
    value: Optional[float] = None

    def __str__(self) -> str:
        code = _ACTION_CODE[self.action]
        return code if self.value is None else f'{code}{self.value:g}'


StepLike = Union[SequenceStep, Sequence]


def make_step(step: StepLike) -> SequenceStep:
    """Validate ``(action, value)`` / ``("zero",)``; raises :class:`SequenceError`."""
    if isinstance(step, str) or not isinstance(step, (tuple, list)) or not 1 <= len(step) <= 2:
        raise SequenceError(f'step must be (action, value), got {step!r}')
    action = step[0]
    value = step[1] if len(step) == 2 else None
    if action not in ACTIONS:
        raise SequenceError(f'unknown action {action!r}; expected one of {", ".join(ACTIONS)}')
    if action == 'zero':
        if value is not None:
            raise SequenceError('zero takes no value')
        return SequenceStep('zero')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SequenceError(f'{action} needs a finite number, got {value!r}')
    value = float(value)
    if action == 'tilt' and not proto.TILT_MIN <= value <= proto.TILT_MAX:
        raise SequenceError(f'tilt {value:g} outside {proto.TILT_MIN:g}..{proto.TILT_MAX:g}')
    if action == 'wait' and value < 0:
        raise SequenceError(f'wait must be >= 0 seconds, got {value:g}')
    return SequenceStep(action, value)


def make_steps(steps: Iterable[StepLike]) -> List[SequenceStep]:
    result = [make_step(step) for step in steps]
    if not result:
        raise SequenceError('sequence is empty')
    return result


def parse_sequence(text: str) -> List[SequenceStep]:
    """Parse ``"r380 t30 r380 t-30 z w2"`` (whitespace or comma separated)."""
    tokens = [token for token in re.split(r'[\s,]+', text.strip()) if token]
    steps = []
    for index, token in enumerate(tokens, start=1):
        match = _TOKEN_RE.match(token)
        if not match:
            raise SequenceError(
                f'step {index} {token!r}: expected r<deg>, t<deg>, z or w<sec>'
            )
        code = match.group('code').lower()
        raw = match.group('value')
        if code == 'z':
            if raw is not None:
                raise SequenceError(f'step {index} {token!r}: z takes no value')
            step = ('zero',)
        elif raw is None:
            raise SequenceError(f'step {index} {token!r}: missing number')
        else:
            step = (_CODE_ACTION[code], float(raw))
        try:
            steps.append(make_step(step))
        except SequenceError as exc:
            raise SequenceError(f'step {index} {token!r}: {exc}') from None
    if not steps:
        raise SequenceError('sequence is empty')
    return steps


def step_timeout(
    step: SequenceStep,
    *,
    base_timeout: float,
    current_tilt: Optional[float] = None,
    current_rotation: Optional[float] = None,
    min_speed_deg_s: float = SEQUENCE_MIN_SPEED_DEG_S,
    margin_s: float = SEQUENCE_TIMEOUT_MARGIN_S,
) -> float:
    """Seconds to wait for *step* to settle: ``max(base, travel / min_speed + margin)``.

    Travel is unknown for an unread axis, so tilt then assumes the full range.
    """
    if step.action == 'rotate':
        travel = abs(step.value)
    elif step.action == 'tilt':
        travel = (
            abs(step.value - current_tilt)
            if current_tilt is not None
            else proto.TILT_MAX - proto.TILT_MIN
        )
    elif step.action == 'zero':
        travel = max(
            abs(current_rotation) if current_rotation is not None else 0.0,
            abs(current_tilt) if current_tilt is not None else proto.TILT_MAX - proto.TILT_MIN,
        )
    else:
        return step.value
    return max(base_timeout, travel / min_speed_deg_s + margin_s)
