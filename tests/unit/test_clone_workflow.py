from __future__ import annotations

from local_mcp_server.clone.model import WorkflowDefinition, WorkflowStep
from local_mcp_server.clone.workflow.engine import WorkflowEngine
from local_mcp_server.clone.workflow.registry import WorkflowRegistry


def test_registry_loads_all_clone_workflows() -> None:
    registry = WorkflowRegistry()
    for name, expected_steps in {"quick": 6, "accurate": 12, "forensic": 15, "verify": 2}.items():
        workflow = registry.get(name)
        assert workflow.name == name
        assert len(workflow.steps) == expected_steps


def test_registry_rejects_cycles() -> None:
    workflow = WorkflowDefinition(
        name="cycle",
        version="1",
        steps=(
            WorkflowStep("a", "noop", ("b",)),
            WorkflowStep("b", "noop", ("a",)),
        ),
    )
    try:
        WorkflowRegistry.validate(workflow)
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("Expected cyclic workflow to be rejected")


def test_engine_resolves_dependencies_and_inputs() -> None:
    workflow = WorkflowDefinition(
        name="test",
        version="1",
        steps=(
            WorkflowStep("first", "first", inputs={"value": "$input.value"}),
            WorkflowStep("second", "second", ("first",), inputs={"value": "$step.first.output"}),
        ),
    )
    engine = WorkflowEngine({"first": lambda value: value + 1, "second": lambda value: value * 2})
    result = engine.run(workflow, {"value": 2})
    assert result.status == "completed"
    assert result.steps[-1].output == 6
