"""Pydantic models for LLM-generated aroma sequences (validated for hardware use)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

# 用户可见场景、人设、时长档位
SCENE_CHOICES: tuple[str, ...] = ("睡前安睡", "通勤提神", "阅读专注", "静心冥想", "晨间唤醒")
PERSONA_CHOICES: tuple[str, ...] = ("专业调香师", "温柔恋人", "松弛老友")
DURATION_LEVEL_CHOICES: tuple[str, ...] = ("速享", "标准", "沉浸")

# 系统内部偏好标签
PREFERENCE_CHOICES: tuple[str, ...] = ("助眠", "放松", "提神", "冥想", "阅读")

SCENE_TO_PREFERENCE: dict[str, str] = {
    "睡前安睡": "助眠",
    "通勤提神": "提神",
    "阅读专注": "阅读",
    "静心冥想": "冥想",
    "晨间唤醒": "提神",
}

DURATION_LEVEL_TO_RANGE: dict[str, tuple[int, int]] = {
    "速享": (180, 240),
    "标准": (360, 480),
    "沉浸": (540, 720),
}


class SequenceStep(BaseModel):
    """单段扩香步骤：香型标识、风扇强度、持续时长。"""

    aroma: str = Field(..., min_length=1, description="香型通道标识，例如 lavender")
    fan_speed: int = Field(..., ge=0, le=100, description="风扇强度百分比")
    duration_sec: int = Field(..., ge=60, le=300, description="该段持续秒数")


class AromaPlan(BaseModel):
    """完整香氛方案：兼顾执行控制与前端展示。"""

    scene: str = Field(..., description="用户选择的场景")
    preference: str = Field(..., description="场景映射后的内部偏好标签")
    persona: str = Field(..., description="角色人格")
    duration_level: str = Field(..., description="时长档位")
    plan_name: str = Field(..., min_length=2, max_length=12, description="方案名称")
    mood_tag: str = Field(..., min_length=2, max_length=8, description="氛围标签")
    opening_line: str = Field(..., min_length=10, max_length=80, description="角色开场语")
    explanation: str = Field(default="", max_length=240, description="方案说明")
    closing_line: str = Field(..., min_length=10, max_length=80, description="角色收尾语")
    total_duration_sec: int = Field(..., ge=120, description="方案总时长")
    sequence: list[SequenceStep] = Field(..., min_length=2, max_length=5, description="扩香序列")

    @field_validator("scene")
    @classmethod
    def scene_must_be_known(cls, v: str) -> str:
        if v not in SCENE_CHOICES:
            raise ValueError(f"scene must be one of {SCENE_CHOICES}, got {v!r}")
        return v

    @field_validator("preference")
    @classmethod
    def preference_must_be_known(cls, v: str) -> str:
        if v not in PREFERENCE_CHOICES:
            raise ValueError(f"preference must be one of {PREFERENCE_CHOICES}, got {v!r}")
        return v

    @field_validator("persona")
    @classmethod
    def persona_must_be_known(cls, v: str) -> str:
        if v not in PERSONA_CHOICES:
            raise ValueError(f"persona must be one of {PERSONA_CHOICES}, got {v!r}")
        return v

    @field_validator("duration_level")
    @classmethod
    def duration_level_must_be_known(cls, v: str) -> str:
        if v not in DURATION_LEVEL_CHOICES:
            raise ValueError(f"duration_level must be one of {DURATION_LEVEL_CHOICES}, got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_plan_consistency(self) -> AromaPlan:
        expected_preference = SCENE_TO_PREFERENCE[self.scene]
        if self.preference != expected_preference:
            object.__setattr__(self, "preference", expected_preference)

        summed = sum(step.duration_sec for step in self.sequence)
        if abs(self.total_duration_sec - summed) > 30:
            object.__setattr__(self, "total_duration_sec", summed)

        min_total, max_total = DURATION_LEVEL_TO_RANGE[self.duration_level]
        if not min_total <= self.total_duration_sec <= max_total:
            object.__setattr__(self, "total_duration_sec", summed)

        return self


class StartRequest(BaseModel):
    """前端发起任务时的输入载荷。"""

    scene: str = Field(..., description="用户选择的场景")
    persona: str = Field(..., description="用户选择的人格角色")
    duration_level: str = Field(..., description="用户选择的时长档位")

    @field_validator("scene")
    @classmethod
    def validate_scene(cls, v: str) -> str:
        if v not in SCENE_CHOICES:
            raise ValueError(f"scene must be one of {SCENE_CHOICES}, got {v!r}")
        return v

    @field_validator("persona")
    @classmethod
    def validate_persona(cls, v: str) -> str:
        if v not in PERSONA_CHOICES:
            raise ValueError(f"persona must be one of {PERSONA_CHOICES}, got {v!r}")
        return v

    @field_validator("duration_level")
    @classmethod
    def validate_duration_level(cls, v: str) -> str:
        if v not in DURATION_LEVEL_CHOICES:
            raise ValueError(f"duration_level must be one of {DURATION_LEVEL_CHOICES}, got {v!r}")
        return v


def mock_plan_for_request(scene: str, persona: str, duration_level: str) -> AromaPlan:
    """离线演示方案：覆盖场景、人设与时长档位。"""
    if scene not in SCENE_CHOICES:
        raise ValueError(f"Unknown scene {scene!r}")
    if persona not in PERSONA_CHOICES:
        raise ValueError(f"Unknown persona {persona!r}")
    if duration_level not in DURATION_LEVEL_CHOICES:
        raise ValueError(f"Unknown duration_level {duration_level!r}")

    preference = SCENE_TO_PREFERENCE[scene]

    base_sequences: dict[str, list[SequenceStep]] = {
        "睡前安睡": [
            SequenceStep(aroma="lavender", fan_speed=40, duration_sec=120),
            SequenceStep(aroma="chamomile", fan_speed=30, duration_sec=120),
            SequenceStep(aroma="lavender", fan_speed=20, duration_sec=180),
        ],
        "通勤提神": [
            SequenceStep(aroma="citrus", fan_speed=65, duration_sec=60),
            SequenceStep(aroma="mint", fan_speed=55, duration_sec=60),
            SequenceStep(aroma="citrus", fan_speed=45, duration_sec=60),
        ],
        "阅读专注": [
            SequenceStep(aroma="lemon", fan_speed=30, duration_sec=120),
            SequenceStep(aroma="rosemary", fan_speed=25, duration_sec=120),
            SequenceStep(aroma="lemon", fan_speed=20, duration_sec=120),
        ],
        "静心冥想": [
            SequenceStep(aroma="frankincense", fan_speed=25, duration_sec=180),
            SequenceStep(aroma="sandalwood", fan_speed=20, duration_sec=180),
            SequenceStep(aroma="frankincense", fan_speed=15, duration_sec=180),
        ],
        "晨间唤醒": [
            SequenceStep(aroma="citrus", fan_speed=55, duration_sec=120),
            SequenceStep(aroma="lemon", fan_speed=45, duration_sec=120),
            SequenceStep(aroma="mint", fan_speed=35, duration_sec=120),
        ],
    }

    persona_text: dict[str, dict[str, str]] = {
        "专业调香师": {
            "plan_name": "晨昏香气曲线" if scene == "晨间唤醒" else "层次调香方案",
            "mood_tag": "专业有序",
            "opening_line": f"我根据“{scene}”场景，为你设计了一套层次更清晰、节奏更稳定的扩香方案。",
            "explanation": f"MOCK_PLAN：当前方案以“{preference}”为核心目标，前段建立场景基调，中段稳定香气表现，后段适度收束强度，使整体扩香更符合{scene}的节奏需求。",
            "closing_line": "这样可以在保持香气存在感的同时，避免后段扩散过量，整体更适合持续体验。",
        },
        "温柔恋人": {
            "plan_name": "轻轻陪着你",
            "mood_tag": "柔和陪伴",
            "opening_line": f"这一次我想让香气慢一点靠近你，先轻轻把“{scene}”的状态带出来。",
            "explanation": f"MOCK_PLAN：我把前段做得更柔和一些，让环境先慢慢安静下来；中段再把气味铺稳，后段把强度收一点，这样会更舒服，也更贴合{scene}时的情绪节奏。",
            "closing_line": "不用着急，先让空气替你把状态安顿好就行。",
        },
        "松弛老友": {
            "plan_name": "先顺一顺",
            "mood_tag": "轻松上头",
            "opening_line": f"行，这回咱别整太猛，我给你按“{scene}”先配个顺一点、舒服一点的节奏。",
            "explanation": f"MOCK_PLAN：前段先把感觉带起来，中段把状态稳住，后段再把强度往下收一收，闻着不会太冲，整体更适合{scene}这类场景，人舒服了再说。",
            "closing_line": "就按这个节奏来，稳一手，气味和状态都顺了。",
        },
    }

    sequence = [step.model_copy(deep=True) for step in base_sequences[scene]]
    min_total, max_total = DURATION_LEVEL_TO_RANGE[duration_level]
    current_total = sum(step.duration_sec for step in sequence)

    if duration_level == "速享":
        while sum(step.duration_sec for step in sequence) > max_total and len(sequence) > 2:
            sequence.pop()
        current_total = sum(step.duration_sec for step in sequence)
    elif duration_level == "沉浸":
        extra = max(0, min_total - current_total)
        if extra > 0:
            sequence[-1] = sequence[-1].model_copy(
                update={"duration_sec": min(300, sequence[-1].duration_sec + extra)}
            )
        current_total = sum(step.duration_sec for step in sequence)

    return AromaPlan(
        scene=scene,
        preference=preference,
        persona=persona,
        duration_level=duration_level,
        plan_name=persona_text[persona]["plan_name"],
        mood_tag=persona_text[persona]["mood_tag"],
        opening_line=persona_text[persona]["opening_line"],
        explanation=persona_text[persona]["explanation"],
        closing_line=persona_text[persona]["closing_line"],
        total_duration_sec=current_total,
        sequence=sequence,
    )
