"""Skill Registry action functions."""

import tempfile
import uuid
from pathlib import Path

import mlflow

from ..shared import ActiveSkill, TestContext


def _active_skill(test_context: TestContext) -> ActiveSkill:
    if test_context.active_skill is None or not test_context.active_skill.name:
        raise AssertionError("No active Skill is available in the test context")
    return test_context.active_skill


def _skill_name(test_context: TestContext) -> str:
    return (
        test_context.active_skill.name
        if test_context.active_skill and test_context.active_skill.name
        else f"test-skill-{uuid.uuid4().hex[:12]}"
    )


def action_create_skill_shell(test_context: TestContext) -> None:
    name = _skill_name(test_context)
    description = "MLflow Skill Registry E2E test Skill"
    skill = test_context.user_client.create_skill(
        name=name,
        description=description,
    )
    test_context.active_skill = ActiveSkill(
        name=skill.name,
        organization=skill.organization,
        description=description,
    )
    test_context.add_skill_for_cleanup(
        name=skill.name,
        organization=skill.organization,
        workspace=test_context.active_workspace,
    )


def action_get_skill(test_context: TestContext) -> None:
    active_skill = _active_skill(test_context)
    skill = test_context.user_client.get_skill(
        name=active_skill.name,
        organization=active_skill.organization or "",
    )
    active_skill.name = skill.name
    active_skill.description = skill.description


def action_search_skills(test_context: TestContext) -> None:
    test_context.skill_search_results = list(
        test_context.user_client.search_skills()
    )


def action_update_skill(test_context: TestContext) -> None:
    active_skill = _active_skill(test_context)
    test_context.user_client.update_skill(
        name=active_skill.name,
        organization=active_skill.organization or "",
        description="Updated Skill Registry E2E description",
    )


def action_delete_skill(test_context: TestContext) -> None:
    active_skill = _active_skill(test_context)
    test_context.user_client.delete_skill(
        name=active_skill.name,
        organization=active_skill.organization or "",
    )


def action_register_local_skill(test_context: TestContext) -> None:
    """Register a local Skill directory and retain its artifact source."""
    name = _skill_name(test_context)
    test_context.active_skill = ActiveSkill(name=name)
    skill_content = "# Skill Registry E2E test Skill\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir)
        skill_markdown = (
            f"---\nname: {name}\ndescription: E2E test Skill\n---\n{skill_content}"
        )
        (skill_dir / "SKILL.md").write_text(skill_markdown, encoding="utf-8")
        version = mlflow.genai.register_skill(source=str(skill_dir))

    test_context.active_skill.name = version.name
    test_context.active_skill.organization = version.organization
    test_context.active_skill.version = version.version
    test_context.active_skill.source = version.source
    test_context.expected_skill_artifact_content = skill_markdown
    test_context.add_skill_for_cleanup(
        name=version.name,
        organization=version.organization,
        workspace=test_context.active_workspace,
    )


def action_read_skill_artifact(test_context: TestContext) -> None:
    """Read SKILL.md through the MLflow artifact endpoint."""
    active_skill = _active_skill(test_context)
    source = active_skill.source
    artifact_uri = getattr(source, "artifact_path", None) or str(source)
    active_skill.artifact_content = mlflow.artifacts.load_text(
        f"{artifact_uri}/SKILL.md"
    )
