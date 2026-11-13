"""Single interface to the language model (spec §8): local backend now, cloud later.

The model's role is narrow: split a reference into fields (copied verbatim), answer yes/no
proper-noun questions, and rewrite ALL-CAPS titles in sentence case. It never decides
whether something is correct. Callers verify every answer (fidelity and case-only checks).

Backend selection: environment variable CHECKREF_LLM = "ollama" | "none" (default "none").
Ollama settings: CHECKREF_OLLAMA_URL (default http://localhost:11434), CHECKREF_MODEL.
"""

from __future__ import annotations

import json
import os
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from checkref.rules.rulebook import rulebook

BATCH_SIZE = 10


class ExtractedFields(BaseModel):
    """What the model returns for one reference. Every value is a verbatim substring."""

    id: str
    type: str | None = None
    author_text: str | None = None
    year: str | None = None
    title: str | None = None
    container: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    article_number: str | None = None
    edition: str | None = None
    publisher: str | None = None
    publisher_location: str | None = None
    doi: str | None = None
    url: str | None = None
    retrieval_statement: str | None = None
    retrieval_date: str | None = None
    description: str | None = None


class LLMBackend(Protocol):
    name: str

    def extract_fields(self, items: list[tuple[str, str]]) -> dict[str, ExtractedFields]:
        """(id, reference text) pairs -> fields by id. Missing ids mean 'no answer'."""
        ...

    def is_proper_noun(self, word: str, context: str) -> bool | None: ...

    def to_sentence_case(self, title: str) -> str | None: ...


class NullBackend:
    """No model configured: every question goes unanswered, so callers fall back to
    'Needs review'."""

    name = "none"

    def extract_fields(self, items: list[tuple[str, str]]) -> dict[str, ExtractedFields]:
        return {}

    def is_proper_noun(self, word: str, context: str) -> bool | None:
        return None

    def to_sentence_case(self, title: str) -> str | None:
        return None


class FakeBackend:
    """Canned answers, for tests."""

    name = "fake"

    def __init__(self, fields=None, proper_nouns=None, sentence_case=None) -> None:
        self.fields: dict[str, ExtractedFields] = fields or {}
        self.proper_nouns: dict[str, bool] = proper_nouns or {}
        self.sentence_case: dict[str, str] = sentence_case or {}
        self.calls: list[tuple[str, object]] = []

    def extract_fields(self, items: list[tuple[str, str]]) -> dict[str, ExtractedFields]:
        self.calls.append(("extract_fields", items))
        return {i: self.fields[i] for i, _ in items if i in self.fields}

    def is_proper_noun(self, word: str, context: str) -> bool | None:
        self.calls.append(("is_proper_noun", word))
        return self.proper_nouns.get(word)

    def to_sentence_case(self, title: str) -> str | None:
        self.calls.append(("to_sentence_case", title))
        return self.sentence_case.get(title)


EXTRACT_INSTRUCTIONS = """You split academic references into fields.
Copy every value EXACTLY as it appears in the reference — same spelling, capitals,
punctuation and dashes. Never correct, complete, reorder or reformat anything.
Leave a field null when the reference does not contain it.
Choose "type" from this list, or null if none fits: {types}.
Return JSON: {{"references": [{{"id": ..., "type": ..., "author_text": ..., ...}}]}}."""


class OllamaBackend:
    """A local model served by Ollama, with output restricted to a JSON schema."""

    name = "ollama"

    def __init__(
        self, model: str, url: str = "http://localhost:11434", timeout: float = 600
    ) -> None:
        self.model = model
        self.client = httpx.Client(base_url=url, timeout=timeout)

    def _chat(self, system: str, user: str, schema: dict) -> dict | None:
        try:
            resp = self.client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": schema,
                    "options": {"temperature": 0, "seed": 0},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            return json.loads(resp.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, json.JSONDecodeError):
            return None

    def extract_fields(self, items: list[tuple[str, str]]) -> dict[str, ExtractedFields]:
        types = ", ".join(t.id for t in rulebook().templates)
        schema = {
            "type": "object",
            "properties": {
                "references": {"type": "array", "items": ExtractedFields.model_json_schema()}
            },
            "required": ["references"],
        }
        answers: dict[str, ExtractedFields] = {}
        for start in range(0, len(items), BATCH_SIZE):
            batch = items[start : start + BATCH_SIZE]
            user = "\n".join(f"[{i}] {text}" for i, text in batch)
            data = self._chat(EXTRACT_INSTRUCTIONS.format(types=types), user, schema) or {}
            wanted = {i for i, _ in batch}
            seen: dict[str, int] = {}
            for item in data.get("references", []):
                try:
                    fields = ExtractedFields.model_validate(item)
                except ValidationError:
                    continue
                seen[fields.id] = seen.get(fields.id, 0) + 1
                if fields.id in wanted:
                    answers[fields.id] = fields
            # Every id must come back exactly once; anything else is treated as no answer.
            for i, n in seen.items():
                if n != 1:
                    answers.pop(i, None)
        return answers

    def is_proper_noun(self, word: str, context: str) -> bool | None:
        schema = {
            "type": "object",
            "properties": {"proper_noun": {"type": "boolean"}},
            "required": ["proper_noun"],
        }
        data = self._chat(
            "Answer whether the given word is a proper noun (a name of a specific person, place, "
            "organisation, species, product or similar) in the given title.",
            f"Word: {word}\nTitle: {context}",
            schema,
        )
        return data.get("proper_noun") if isinstance(data, dict) else None

    def to_sentence_case(self, title: str) -> str | None:
        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        }
        data = self._chat(
            "Rewrite the title in sentence case: capitalise only the first word, the first word "
            "after a colon, proper nouns, acronyms and scientific genus names. Change nothing "
            "except letter case.",
            title,
            schema,
        )
        return data.get("title") if isinstance(data, dict) else None


def get_backend() -> LLMBackend:
    kind = os.environ.get("CHECKREF_LLM", "none").lower()
    if kind == "ollama":
        model = os.environ.get("CHECKREF_MODEL", "qwen2.5:7b-instruct")
        return OllamaBackend(model, os.environ.get("CHECKREF_OLLAMA_URL", "http://localhost:11434"))
    return NullBackend()
