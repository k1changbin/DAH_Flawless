"""Lightweight dataclasses used by the MVP simulation.

The state itself stays as dictionaries because the report evidence is emitted
as JSON. Dataclasses keep agent decisions and scorer results explicit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Attack:
    name: str
    feasibility: str
    weight: float
    preferred_tags: tuple[str, ...]
    target_domain: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["preferred_tags"] = list(self.preferred_tags)
        return data


@dataclass(frozen=True)
class Threat:
    target: str
    confidence: float
    tags: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = list(self.tags)
        data["evidence"] = list(self.evidence)
        return data


@dataclass(frozen=True)
class DefenseAction:
    action: str
    target: str
    priority: int
    duration_ticks: int
    availability_cost: float
    status: str = "PENDING"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionRisk:
    target: str
    impact: str
    availability_risk: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Score:
    winner: str
    attack_success: bool
    detection_success: bool
    false_positive: bool
    recovery_success: bool
    availability: float
    target_domain: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decision(agent: str, event: str, reason: str, before: Any = None, after: Any = None) -> dict[str, Any]:
    return {
        "agent": agent,
        "event": event,
        "reason": reason,
        "before": before,
        "after": after,
    }
