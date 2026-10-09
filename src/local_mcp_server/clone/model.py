from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    operation: str
    depends_on: tuple[str, ...] = ()
    inputs: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None
    retry: int = 0


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    version: str
    steps: tuple[WorkflowStep, ...]


@dataclass
class StepResult:
    step_id: str
    operation: str
    status: str
    output: Any = None
    error: str | None = None
    attempts: int = 0


@dataclass
class WorkflowResult:
    run_id: str
    workflow: str
    status: str
    steps: list[StepResult]
    output: dict[str, Any] = field(default_factory=dict)
