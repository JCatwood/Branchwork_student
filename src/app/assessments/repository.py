"""Read assessments and solutions, and write student answers."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone as datetime_timezone
from django.utils.dateparse import parse_datetime
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings


SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
QUESTION_TYPES = {"choice", "number", "text", "textarea", "code"}


class ContentError(ValueError):
    """An instructor- or student-managed file has invalid content."""


def read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML mapping and provide a useful validation error."""
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
    except yaml.YAMLError as exc:
        raise ContentError(f"Invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContentError(f"{path.name} must contain a YAML mapping")
    return data


def load_student_config() -> dict[str, str]:
    """Read the small repository-level student configuration file."""
    defaults = {
        "student_id": "replace-with-github-username",
        "course_title": "Course Homework and Exams",
        "theme": "minimal.css",
    }
    path = Path(settings.STUDENT_CONFIG)
    if not path.is_file():
        return defaults
    config = read_yaml(path)
    return {key: str(config.get(key, value)) for key, value in defaults.items()}


def _assessment_path(assessment_id: str) -> Path:
    if not SAFE_ID.fullmatch(assessment_id):
        raise FileNotFoundError(assessment_id)
    data_dir = Path(settings.DATA_DIR)
    for suffix in ("yaml", "yml"):
        path = data_dir / f"{assessment_id}.{suffix}"
        if path.is_file():
            return path
    raise FileNotFoundError(assessment_id)


def _normalize_choices(choices: Any, location: str) -> dict[str, str]:
    if isinstance(choices, list):
        return {chr(65 + index): str(choice) for index, choice in enumerate(choices)}
    if isinstance(choices, dict):
        return {str(value): str(label) for value, label in choices.items()}
    raise ContentError(f"{location} must provide choices as a list or mapping")

def _normalize_due_at(
    raw_due_at: Any,
    assessment_id: str,
) -> datetime | None:
    """Parse an ISO 8601 deadline and normalize it to UTC."""
    if raw_due_at in (None, ""):
        return None

    # PyYAML may already convert an unquoted timestamp into datetime.
    if isinstance(raw_due_at, datetime):
        due_at = raw_due_at
    elif isinstance(raw_due_at, str):
        due_at = parse_datetime(raw_due_at)
    else:
        due_at = None

    if due_at is None or due_at.utcoffset() is None:
        raise ContentError(
            f"{assessment_id}.yaml due_at must be an ISO 8601 timestamp "
            "with an explicit timezone, for example "
            "'2026-09-15T23:59:00-05:00'"
        )

    return due_at.astimezone(datetime_timezone.utc)

def _validate_assessment(data: dict[str, Any], assessment_id: str) -> dict[str, Any]:
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ContentError(f"{assessment_id}.yaml needs a non-empty questions list")

    normalized_questions = []
    seen_ids = set()
    for position, raw_question in enumerate(questions, start=1):
        if not isinstance(raw_question, dict):
            raise ContentError(f"Question {position} in {assessment_id} must be a mapping")
        question = dict(raw_question)
        question_id = str(question.get("id", ""))
        if not SAFE_ID.fullmatch(question_id) or question_id in seen_ids:
            raise ContentError(
                f"Question {position} in {assessment_id} needs a unique simple id"
            )
        seen_ids.add(question_id)

        question_type = str(question.get("type", "text"))
        if question_type not in QUESTION_TYPES:
            raise ContentError(
                f"Question {question_id} has unsupported type {question_type!r}"
            )
        question["id"] = question_id
        question["type"] = question_type
        question["points"] = float(question.get("points", 1))
        if question["points"] <= 0:
            raise ContentError(f"Question {question_id} must have positive points")
        if "prompt" not in question and "prompt_html" not in question:
            raise ContentError(f"Question {question_id} needs prompt or prompt_html")

        if question_type == "choice":
            question["choices"] = _normalize_choices(
                question.get("choices"), f"Question {question_id}"
            )
        if question_type == "code":
            question["language"] = str(question.get("language", "R"))
            question["starter_code"] = str(question.get("starter_code", ""))
            question["rows"] = int(question.get("rows", 12))

        normalized_questions.append(question)

    result = dict(data)
    result["id"] = assessment_id
    result["title"] = str(data.get("title", assessment_id.replace("_", " ").title()))
    result["kind"] = str(data.get("kind", "Assessment"))
    result["order"] = float(data.get("order", 999))
    result["questions"] = normalized_questions
    result["due_at"] = _normalize_due_at(data.get("due_at"), assessment_id,)
    return result


def load_assessment(assessment_id: str) -> dict[str, Any]:
    """Load one assessment by its filename stem."""
    path = _assessment_path(assessment_id)
    return _validate_assessment(read_yaml(path), assessment_id)


def list_assessments() -> list[dict[str, Any]]:
    """Load all YAML assessments in ``src/data``."""
    data_dir = Path(settings.DATA_DIR)
    if not data_dir.is_dir():
        return []
    assessment_ids = {
        path.stem
        for pattern in ("*.yaml", "*.yml")
        for path in data_dir.glob(pattern)
        if SAFE_ID.fullmatch(path.stem)
    }
    assessments = [load_assessment(item) for item in assessment_ids]
    return sorted(assessments, key=lambda item: (item["order"], item["title"]))


def answer_path(assessment_id: str) -> Path:
    if not SAFE_ID.fullmatch(assessment_id):
        raise ValueError("Invalid assessment id")
    return Path(settings.ANSWER_DIR) / f"{assessment_id}.json"


def load_answers(assessment_id: str) -> dict[str, Any]:
    """Load saved answers, returning an empty structure before first submission."""
    path = answer_path(assessment_id)
    if not path.is_file():
        return {"answers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ContentError(f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise ContentError(f"{path.name} must contain an answers JSON object")
    return data


def save_answers(
    assessment_id: str,
    student_id: str,
    answers: dict[str, str],
) -> Path:
    """Atomically save browser answers as a readable JSON file."""
    path = answer_path(assessment_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "assessment": assessment_id,
        "student_id": student_id,
        "saved_at": datetime.now(datetime_timezone.utc).isoformat(),
        "answers": answers,
    }
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary_path, path)
    return path


def load_solution(assessment_id: str) -> dict[str, Any] | None:
    """Return instructor-provided solutions and points, or ``None`` if unreleased."""
    solution_dir = Path(settings.SOLUTION_DIR)
    for suffix in ("yaml", "yml"):
        path = solution_dir / f"{assessment_id}.{suffix}"
        if path.is_file():
            solution = read_yaml(path)
            if not isinstance(solution.get("questions"), dict):
                raise ContentError(f"{path.name} needs a questions mapping")
            return solution
    return None
