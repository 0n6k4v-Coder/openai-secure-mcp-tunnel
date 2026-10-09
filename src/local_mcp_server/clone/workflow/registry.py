from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..model import WorkflowDefinition, WorkflowStep

_WORKFLOW_DIR = Path(__file__).with_name('definitions')


class WorkflowRegistry:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _WORKFLOW_DIR

    def get(self, name: str) -> WorkflowDefinition:
        path = self.directory / f'{name}.json'
        if not path.is_file():
            raise ValueError(f'Unknown clone workflow: {name}')
        data: dict[str, Any] = json.loads(path.read_text(encoding='utf-8'))
        definition = WorkflowDefinition(
            name=str(data.get('name', name)),
            version=str(data.get('version', '1')),
            steps=tuple(
                WorkflowStep(
                    id=item['id'],
                    operation=item['operation'],
                    depends_on=tuple(item.get('depends_on', [])),
                    inputs=dict(item.get('inputs', {})),
                    condition=item.get('condition'),
                    retry=int(item.get('retry', 0)),
                )
                for item in data.get('steps', [])
            ),
        )
        self.validate(definition)
        return definition

    @staticmethod
    def validate(definition: WorkflowDefinition) -> None:
        ids = [step.id for step in definition.steps]
        if len(ids) != len(set(ids)):
            raise ValueError('Workflow contains duplicate step ids.')
        known = set(ids)
        for step in definition.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f'Step {step.id!r} depends on unknown steps: {sorted(missing)}')
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {step.id: step for step in definition.steps}

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError(f'Workflow contains a dependency cycle at {step_id!r}.')
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in by_id[step_id].depends_on:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in ids:
            visit(step_id)
