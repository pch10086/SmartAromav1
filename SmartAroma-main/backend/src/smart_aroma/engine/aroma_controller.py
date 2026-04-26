"""Run aroma sequence with pause/resume/stop; abstract fan backend for GPIO swap-in."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from smart_aroma.config import Settings, get_settings
from smart_aroma.llm.qwen_client import generate_plan_from_llm
from smart_aroma.models.sequence_schema import AromaPlan

log = logging.getLogger(__name__)


class Phase(str, Enum):
    IDLE = "idle"
    GENERATING = "generating"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


class FanBackend(Protocol):
    def set_fan_speed(self, speed: int) -> None: ...


class LoggingFanBackend:
    """Prototype backend: log only. Replace with GPIOFanBackend on Raspberry Pi."""

    def set_fan_speed(self, speed: int) -> None:
        log.info("FanBackend.set_fan_speed(%s)", speed)


@dataclass
class PublicState:
    phase: Phase = Phase.IDLE
    scene: str | None = None
    preference: str | None = None
    persona: str | None = None
    duration_level: str | None = None
    plan_name: str | None = None
    mood_tag: str | None = None
    opening_line: str | None = None
    explanation: str | None = None
    closing_line: str | None = None
    current_aroma: str | None = None
    fan_speed: int = 0
    segment_index: int = -1
    segment_count: int = 0
    segment_remaining_sec: int = 0
    total_remaining_sec: int = 0
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "scene": self.scene,
            "preference": self.preference,
            "persona": self.persona,
            "duration_level": self.duration_level,
            "plan_name": self.plan_name,
            "mood_tag": self.mood_tag,
            "opening_line": self.opening_line,
            "explanation": self.explanation,
            "closing_line": self.closing_line,
            "current_aroma": self.current_aroma,
            "fan_speed": self.fan_speed,
            "segment_index": self.segment_index,
            "segment_count": self.segment_count,
            "segment_remaining_sec": self.segment_remaining_sec,
            "total_remaining_sec": self.total_remaining_sec,
            "error_message": self.error_message,
        }


@dataclass
class AromaController:
    settings: Settings | None = None
    fan: FanBackend = field(default_factory=LoggingFanBackend)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _state: PublicState = field(default_factory=PublicState, repr=False)
    _worker: threading.Thread | None = field(default=None, repr=False)
    _pause: threading.Event = field(default_factory=threading.Event, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def __post_init__(self) -> None:
        if self.settings is None:
            object.__setattr__(self, "settings", get_settings())

    def get_public_state(self) -> dict[str, Any]:
        with self._lock:
            return self._state.as_dict()

    def _set_state(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if k == "phase":
                    old = self._state.phase
                    self._state.phase = v
                    log.info("State phase: %s -> %s", old.value, v.value)
                else:
                    setattr(self._state, k, v)

    def start(self, scene: str, persona: str, duration_level: str) -> tuple[bool, str]:
        """Begin generation + execution in a background thread."""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                if self._state.phase in (Phase.GENERATING, Phase.RUNNING, Phase.PAUSED):
                    return False, "已有任务进行中"
            self._stop.clear()
            self._pause.clear()
            self._worker = threading.Thread(
                target=self._run_job,
                args=(scene, persona, duration_level),
                daemon=True,
            )
            self._worker.start()
        log.info(
            "User action: start scene=%s persona=%s duration_level=%s",
            scene,
            persona,
            duration_level,
        )
        return True, "已开始生成香氛方案"

    def pause(self) -> tuple[bool, str]:
        with self._lock:
            if self._state.phase != Phase.RUNNING:
                return False, "当前不可暂停"
            self._pause.set()
            self._set_state(phase=Phase.PAUSED)
        log.info("User action: pause")
        return True, "已暂停"

    def resume(self) -> tuple[bool, str]:
        with self._lock:
            if self._state.phase != Phase.PAUSED:
                return False, "当前未处于暂停"
            self._pause.clear()
            self._set_state(phase=Phase.RUNNING)
        log.info("User action: resume")
        return True, "已恢复"

    def stop(self) -> tuple[bool, str]:
        self._stop.set()
        self._pause.clear()
        log.info("User action: stop")
        self.fan.set_fan_speed(0)
        return True, "已发送终止"

    def _wait_unpause_or_stop(self) -> bool:
        """If paused, block until resume or stop. Returns True if should abort."""
        while self._pause.is_set():
            if self._stop.is_set():
                return True
            time.sleep(0.05)
        return self._stop.is_set()

    def _run_job(self, scene: str, persona: str, duration_level: str) -> None:
        self._set_state(
            phase=Phase.GENERATING,
            scene=scene,
            preference=None,
            persona=persona,
            duration_level=duration_level,
            plan_name=None,
            mood_tag=None,
            opening_line=None,
            explanation=None,
            closing_line=None,
            current_aroma=None,
            fan_speed=0,
            segment_index=-1,
            segment_count=0,
            segment_remaining_sec=0,
            total_remaining_sec=0,
            error_message=None,
        )
        self.fan.set_fan_speed(0)

        if self._stop.is_set():
            self._finish_stopped()
            return

        try:
            plan = generate_plan_from_llm(scene, persona, duration_level, self.settings)
        except Exception as e:
            log.exception("Plan generation failed")
            self._set_state(phase=Phase.ERROR, error_message=str(e))
            self.fan.set_fan_speed(0)
            return

        if self._stop.is_set():
            self._finish_stopped()
            return

        self._execute_plan(plan)

    def _execute_plan(self, plan: AromaPlan) -> None:
        seq = plan.sequence
        n = len(seq)
        total_left = sum(step.duration_sec for step in seq)

        self._set_state(
            phase=Phase.RUNNING,
            scene=plan.scene,
            preference=plan.preference,
            persona=plan.persona,
            duration_level=plan.duration_level,
            plan_name=plan.plan_name,
            mood_tag=plan.mood_tag,
            opening_line=plan.opening_line,
            explanation=plan.explanation,
            closing_line=plan.closing_line,
            segment_count=n,
            total_remaining_sec=total_left,
            error_message=None,
        )

        for idx, step in enumerate(seq):
            if self._stop.is_set():
                self._finish_stopped()
                return

            seg_left = step.duration_sec
            self._set_state(
                segment_index=idx,
                current_aroma=step.aroma,
                fan_speed=step.fan_speed,
                segment_remaining_sec=seg_left,
                total_remaining_sec=total_left,
            )
            self.fan.set_fan_speed(step.fan_speed)

            while seg_left > 0:
                if self._wait_unpause_or_stop():
                    self._finish_stopped()
                    self.fan.set_fan_speed(0)
                    return
                if self._stop.is_set():
                    self._finish_stopped()
                    self.fan.set_fan_speed(0)
                    return

                for _ in range(10):
                    if self._wait_unpause_or_stop():
                        self._finish_stopped()
                        self.fan.set_fan_speed(0)
                        return
                    if self._stop.is_set():
                        self._finish_stopped()
                        self.fan.set_fan_speed(0)
                        return
                    time.sleep(0.1)

                seg_left -= 1
                total_left -= 1
                self._set_state(segment_remaining_sec=seg_left, total_remaining_sec=max(0, total_left))

        self.fan.set_fan_speed(0)
        self._set_state(
            phase=Phase.COMPLETED,
            fan_speed=0,
            segment_remaining_sec=0,
            total_remaining_sec=0,
        )
        log.info("Sequence completed")
        self._reset_to_idle_keep_summary()

    def _reset_to_idle_keep_summary(self) -> None:
        """Clear runtime fields after a finished session; keep summary for UI."""
        with self._lock:
            self._state.phase = Phase.IDLE
            self._state.fan_speed = 0
            self._state.current_aroma = None
            self._state.segment_index = -1
            self._state.segment_count = 0
            self._state.segment_remaining_sec = 0
            self._state.total_remaining_sec = 0
        log.info("State reset to idle after session end")

    def _finish_stopped(self) -> None:
        self.fan.set_fan_speed(0)
        with self._lock:
            if self._state.phase != Phase.ERROR:
                self._state.phase = Phase.STOPPED
                self._state.fan_speed = 0
        log.info("Sequence stopped")
        self._reset_to_idle_keep_summary()
