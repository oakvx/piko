"""Conservative, typed parameter binding for user-reviewed Skills.

Parameters are data, never instructions: only literal text entered into a
control and text-valued observation expectations may contain {{name}} tokens.
Targets, action types, hotkeys and permissions cannot be parameterized.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from piko.contracts import Plan

_TOKEN = re.compile(r"\{\{([a-z][a-z0-9_]{0,31})\}\}")
_MAX_PARAMETERS = 12
_MAX_VALUE_LENGTH = 1000


class SkillParameterError(ValueError):
    pass


def _names(value: str) -> set[str]:
    matches = set(_TOKEN.findall(value))
    remainder = _TOKEN.sub("", value)
    if "{{" in remainder or "}}" in remainder:
        raise SkillParameterError("Malformed Skill text placeholder")
    return matches


def parameter_names(plan: Plan) -> list[str]:
    """Read allowed placeholders without interpreting raw document Markdown."""
    names: set[str] = set()
    for action in plan.actions:
        if action.automation_id and ("{{" in action.automation_id or "}}" in action.automation_id):
            raise SkillParameterError("UIA targets may not be parameterized")
        expected = action.expected
        if "{{" in expected.automation_id or "}}" in expected.automation_id:
            raise SkillParameterError("Verification targets may not be parameterized")
        if any("{{" in key or "}}" in key for key in action.keys):
            raise SkillParameterError("Hotkeys may not be parameterized")
        if action.text is not None:
            names.update(_names(action.text))
        if isinstance(expected.value, str):
            names.update(_names(expected.value))
    if len(names) > _MAX_PARAMETERS:
        raise SkillParameterError("Skill has too many parameters")
    return sorted(names)


def bind_plan(plan: Plan, values: Mapping[str, str]) -> Plan:
    """Return a new validated plan with user-provided literal values substituted.

    Never change automation IDs, app identity, action kind or keyboard shortcuts.
    A text value containing another placeholder is NOT recursively interpolated.
    """
    names = parameter_names(plan)
    if not isinstance(values, Mapping):
        raise SkillParameterError("Skill parameter values must be a string mapping")
    if set(values) != set(names):
        missing = sorted(set(names) - set(values))
        unexpected = sorted(set(values) - set(names))
        raise SkillParameterError(
            f"Skill parameters do not match: missing={missing}, unexpected={unexpected}"
        )
    for name, value in values.items():
        if not isinstance(value, str) or len(value) > _MAX_VALUE_LENGTH:
            raise SkillParameterError(f"Invalid text value for Skill parameter {name!r}")

    def substitute(text: str) -> str:
        return _TOKEN.sub(lambda match: values[match.group(1)], text)

    data = plan.model_dump(mode="python")
    for action in data["actions"]:
        if action["text"] is not None:
            action["text"] = substitute(action["text"])
        if isinstance(action["expected"]["value"], str):
            action["expected"]["value"] = substitute(action["expected"]["value"])
    # Re-run strict length/schema validation after substitution: templated plans
    # may fit source limits but not after substitution.
    return Plan.model_validate(data)
