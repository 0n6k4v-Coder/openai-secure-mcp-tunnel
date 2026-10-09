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


def test_verification_workflows_pass_analysis_and_build_evidence() -> None:
    registry = WorkflowRegistry()

    accurate = registry.get("accurate")
    accurate_verify = next(step for step in accurate.steps if step.id == "verify")
    assert accurate_verify.inputs["analyze"] == "$step.analyze.output"
    assert accurate_verify.inputs["build"] == "$step.build.output"

    forensic = registry.get("forensic")
    forensic_verify = next(step for step in forensic.steps if step.id == "verify")
    assert forensic_verify.inputs["analyze"] == "$step.analyze.output"
    assert forensic_verify.inputs["build"] == "$step.build.output"
    assert forensic_verify.inputs["serve"] == "$step.serve.output"

    verify = registry.get("verify")
    verify_step = next(step for step in verify.steps if step.id == "verify")
    assert verify_step.inputs["analyze"] == "$input.analyze"
    assert verify_step.inputs["build"] == "$input.build"
    assert verify_step.inputs["serve"] == "$step.serve.output"


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
