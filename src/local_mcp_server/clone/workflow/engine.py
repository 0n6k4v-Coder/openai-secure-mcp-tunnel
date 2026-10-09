from __future__ import annotations

import inspect
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ..model import StepResult, WorkflowDefinition, WorkflowResult
from .registry import WorkflowRegistry

_REFERENCE = re.compile(r'^\$step\.([A-Za-z0-9_-]+)\.output(?:\.(.*))?$')


class WorkflowEngine:
    def __init__(self, operations: dict[str, Callable[..., Any]], registry: WorkflowRegistry | None = None, max_workers: int = 4) -> None:
        self.operations = operations
        self.registry = registry or WorkflowRegistry()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def run(self, workflow: str | WorkflowDefinition, inputs: dict[str, Any] | None = None) -> WorkflowResult:
        definition = self.registry.get(workflow) if isinstance(workflow, str) else workflow
        values = dict(inputs or {})
        results: dict[str, StepResult] = {}
        remaining = {step.id: step for step in definition.steps}
        run_id = uuid.uuid4().hex

        while remaining:
            ready = [step for step in remaining.values() if all(dep in results for dep in step.depends_on)]
            if not ready:
                raise RuntimeError('Workflow cannot make progress; dependency graph is invalid.')

            runnable = []
            for step in ready:
                if step.condition and not self._condition(step.condition, values, results):
                    results[step.id] = StepResult(step.id, step.operation, 'skipped')
                else:
                    runnable.append(step)

            futures = {self.executor.submit(self._execute_step, step, values, results): step for step in runnable}
            for future, step in futures.items():
                results[step.id] = future.result()
                if results[step.id].status == 'failed':
                    return WorkflowResult(run_id, definition.name, 'failed', [results[s.id] for s in definition.steps if s.id in results], {'failed_step': step.id})
            remaining = {key: value for key, value in remaining.items() if key not in results}

        return WorkflowResult(run_id, definition.name, 'completed', [results[s.id] for s in definition.steps], values)

    def _execute_step(self, step: Any, inputs: dict[str, Any], results: dict[str, StepResult]) -> StepResult:
        operation = self.operations.get(step.operation)
        if operation is None:
            return StepResult(step.id, step.operation, 'failed', error=f'Unknown operation: {step.operation}')
        resolved = {key: self._resolve(value, inputs, results) for key, value in step.inputs.items()}
        attempts = 0
        last_error = None
        while attempts <= step.retry:
            attempts += 1
            try:
                value = operation(**resolved)
                if inspect.isawaitable(value):
                    raise RuntimeError('Async workflow operations are not supported by this executor.')
                return StepResult(step.id, step.operation, 'completed', value, attempts=attempts)
            except Exception as exc:
                last_error = str(exc)
        return StepResult(step.id, step.operation, 'failed', error=last_error, attempts=attempts)

    def _resolve(self, value: Any, inputs: dict[str, Any], results: dict[str, StepResult]) -> Any:
        if isinstance(value, str):
            if value.startswith('$input.'):
                return inputs.get(value[7:])
            match = _REFERENCE.match(value)
            if match:
                result = results[match.group(1)].output
                for part in match.group(2).split('.') if match.group(2) else ():
                    result = result[part] if isinstance(result, dict) else getattr(result, part)
                return result
        if isinstance(value, list):
            return [self._resolve(item, inputs, results) for item in value]
        if isinstance(value, dict):
            return {key: self._resolve(item, inputs, results) for key, item in value.items()}
        return value

    def _condition(self, condition: str, inputs: dict[str, Any], results: dict[str, StepResult]) -> bool:
        expression = condition.strip()
        if expression.endswith(' == true'):
            return bool(self._resolve(expression[:-8].strip(), inputs, results))
        if expression.endswith(' == false'):
            return not bool(self._resolve(expression[:-9].strip(), inputs, results))
        return bool(self._resolve(expression, inputs, results))
