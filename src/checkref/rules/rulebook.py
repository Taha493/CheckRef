"""Load and validate the rulebook in rulebook/*.yaml (see rulebook/README.md)."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

RULEBOOK_DIR = Path(__file__).resolve().parents[3] / "rulebook"

SourceType = Literal["ruling", "guide_text", "guide_template", "guide_examples", "derived"]
# applies_to values that are not template ids or groups
SCOPES = {"all", "list", "in_text"}


class Source(BaseModel):
    type: SourceType
    page: str | None = None
    section: str | None = None
    quote: str | None = None
    ruling: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _has_reference(self) -> Source:
        if self.type == "ruling" and not self.ruling:
            raise ValueError("a ruling source needs a ruling number")
        if self.type == "guide_text" and not (self.page and self.quote):
            raise ValueError("a guide_text source needs a page and a quote")
        return self


class Template(BaseModel):
    id: str
    name: str
    group: str
    pattern: str
    alternatives: list[str] = Field(default_factory=list)
    source: dict[str, str]
    notes: list[str] = Field(default_factory=list)
    examples: list[str]


class InTextOnly(BaseModel):
    id: str
    name: str
    source: dict[str, str]
    in_text_example: str | None = None


class Ruling(BaseModel):
    """A project ruling (spec §6) in the words shown in reports."""

    title: str
    text: str


class Rule(BaseModel):
    id: str
    title: str
    level: Literal["error", "needs_review"]
    applies_to: list[str]
    source: Source
    check: str


class Rulebook(BaseModel):
    templates: list[Template]
    in_text_only: list[InTextOnly]
    deferred: list[dict[str, str]]
    rules: list[Rule]
    rulings: dict[str, Ruling]
    excluded_examples: list[dict[str, str]]
    excluded_in_text: list[dict[str, str]]
    settings: dict[str, Any]

    def template(self, template_id: str) -> Template:
        return next(t for t in self.templates if t.id == template_id)

    def rule(self, rule_id: str) -> Rule:
        return next(r for r in self.rules if r.id == rule_id)

    @property
    def groups(self) -> set[str]:
        return {t.group for t in self.templates}

    def rules_for(self, template_id: str) -> list[Rule]:
        """Rules that apply to one reference of the given source type."""
        targets = {"all", template_id, f"group:{self.template(template_id).group}"}
        return [r for r in self.rules if targets & set(r.applies_to)]

    @model_validator(mode="after")
    def _consistent(self) -> Rulebook:
        problems: list[str] = []
        id_lists = {"template": [t.id for t in self.templates], "rule": [r.id for r in self.rules]}
        for kind, ids in id_lists.items():
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                problems.append(f"duplicate {kind} ids: {sorted(dupes)}")
        template_ids = {t.id for t in self.templates}
        for r in self.rules:
            for target in r.applies_to:
                if target in SCOPES or target in template_ids:
                    continue
                if target.startswith("group:") and target[6:] in self.groups:
                    continue
                problems.append(f"{r.id}: unknown applies_to target {target!r}")
            if r.source.ruling and r.source.ruling not in self.rulings:
                problems.append(f"{r.id}: unknown ruling {r.source.ruling!r}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _read(name: str, directory: Path) -> Any:
    return yaml.safe_load((directory / name).read_text(encoding="utf-8"))


def load_rulebook(directory: Path = RULEBOOK_DIR) -> Rulebook:
    templates = _read("templates.yaml", directory)
    excluded = _read("excluded_examples.yaml", directory)
    rules = _read("rules.yaml", directory)
    return Rulebook(
        templates=templates["templates"],
        in_text_only=templates.get("in_text_only", []),
        deferred=templates.get("deferred", []),
        rules=rules["rules"],
        rulings=rules.get("rulings", {}),
        excluded_examples=excluded.get("examples", []),
        excluded_in_text=excluded.get("in_text", []),
        settings=_read("settings.yaml", directory),
    )


@cache
def rulebook() -> Rulebook:
    """The project rulebook, loaded once."""
    return load_rulebook()
