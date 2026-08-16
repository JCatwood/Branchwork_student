"""The application's index and assessment pages."""

from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .git_service import (
    GitOperationError,
    get_git_status,
    pull_updates,
    submit_answer,
)

from .repository import (
    ContentError,
    answer_path,
    list_assessments,
    load_answers,
    load_assessment,
    load_solution,
    load_student_config,
    save_answers,
)


def _is_past_due(definition) -> bool:
    """Return True at or after the assessment deadline."""
    due_at = definition.get("due_at")
    return due_at is not None and timezone.now() >= due_at

def _content_error(request, error: ContentError):
    return render(request, "assessments/error.html", {"error": error}, status=500)


def _review_context(questions, solution):
    """Attach instructor feedback and summarize instructor-awarded points."""
    awarded_total = 0.0
    graded_points = 0.0
    total_points = sum(float(question["points"]) for question in questions)

    for question in questions:
        question_id = question["id"]
        entry = solution["questions"].get(question_id)
        if entry is not None and not isinstance(entry, dict):
            raise ContentError(f"Solution for {question_id} must be a mapping")
        entry = entry or {}

        raw_points = entry.get("points_awarded")
        has_points = raw_points not in (None, "")
        points_awarded = None
        if has_points:
            try:
                points_awarded = float(raw_points)
            except (TypeError, ValueError) as exc:
                raise ContentError(
                    f"points_awarded for {question_id} must be numeric"
                ) from exc
            if not 0 <= points_awarded <= float(question["points"]):
                raise ContentError(
                    f"points_awarded for {question_id} must be between 0 and "
                    f"{question['points']}"
                )
            awarded_total += points_awarded
            graded_points += float(question["points"])

        question["review"] = {
            "has_points": has_points,
            "points_awarded": points_awarded,
            "correct_answer": entry.get("correct_answer"),
            "solution": entry.get("solution", ""),
            "solution_html": entry.get("solution_html", ""),
            "comment": entry.get("comment", ""),
        }

    pending_points = total_points - graded_points
    complete = pending_points == 0
    percentage = (
        round(100 * awarded_total / total_points, 1)
        if complete and total_points
        else None
    )
    return {
        "points_awarded": awarded_total,
        "graded_points": graded_points,
        "total_points": total_points,
        "pending_points": pending_points,
        "complete": complete,
        "percentage": percentage,
    }


def home(request):
    """List every homework and exam discovered in ``src/data``."""
    try:
        summaries = []
        for definition in list_assessments():
            saved = load_answers(definition["id"])
            solution = load_solution(definition["id"])
            past_due = _is_past_due(definition)
            report = None
            if solution is not None:
                questions = [dict(question) for question in definition["questions"]]
                report = _review_context(questions, solution)
            summaries.append(
                {
                    "id": definition["id"],
                    "title": definition["title"],
                    "kind": definition["kind"],
                    "description": definition.get("description", ""),
                    "submitted": answer_path(definition["id"]).is_file(),
                    "solution_available": solution is not None,
                    "report": report,
                    "due_at": definition["due_at"],
                    "past_due": past_due,
                    "can_submit": (
                        answer_path(definition["id"]).is_file()
                        and not past_due
                        and solution is None
                    ),
                }
            )
    except ContentError as exc:
        return _content_error(request, exc)
    return render(
        request,
        "assessments/home.html",
        {
            "assessments": summaries,
            "git_status": get_git_status(),
        },
    )


@require_POST
def get_updates(request):
    """Download instructor changes with a fast-forward-only Git pull."""
    try:
        result = pull_updates()
    except GitOperationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, result.message)
        if result.restart_required:
            messages.warning(
                request,
                "Application code changed. Stop Branchwork with Ctrl+C and "
                "run python run.py again before continuing.",
            )
    return redirect("home")


@require_POST
def submit_assessment(request, assessment_id: str):
    """Commit and push one assessment's saved JSON answer file."""
    try:
        definition = load_assessment(assessment_id)
        if _is_past_due(definition):
            return HttpResponseForbidden(
                "The due time has passed. This assessment cannot be submitted."
            )
        if load_solution(assessment_id) is not None:
            return HttpResponseForbidden(
                "Solutions are available, so this assessment is locked."
            )
    except FileNotFoundError as exc:
        raise Http404("Assessment does not exist") from exc
    except ContentError as exc:
        return _content_error(request, exc)

    try:
        result = submit_answer(assessment_id, definition["title"])
    except GitOperationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, result.message)
        if result.restart_required:
            messages.warning(
                request,
                "Updates included application code. Restart Branchwork after "
                "confirming this submission.",
            )
    return redirect("home")


def assessment(request, assessment_id: str):
    """Display questions, save answers, or review instructor feedback."""
    try:
        config = load_student_config()
        definition = load_assessment(assessment_id)
        saved = load_answers(assessment_id)
        solution = load_solution(assessment_id)
        past_due = _is_past_due(definition)
        solution_available = solution is not None
        locked = past_due or solution_available
    except FileNotFoundError as exc:
        raise Http404("Assessment does not exist") from exc
    except ContentError as exc:
        return _content_error(request, exc)

    questions = [dict(question) for question in definition["questions"]]
    if request.method == "POST":
        # This is checked on POST, not just when displaying the page.
        # Therefore, a page opened before the deadline cannot be submitted afterward.
        if past_due:
            return HttpResponseForbidden(
                "The due time has passed. Answers are now read-only."
            )

        if solution_available:
            return HttpResponseForbidden(
                "Answers are locked because solutions are now available."
            )

        answers = {
            question["id"]: request.POST.get(
                f"answer__{question['id']}",
                "",
            )
            for question in questions
        }
        save_answers(assessment_id, config["student_id"], answers)
        return redirect(
            f"{reverse('assessment', args=[assessment_id])}?saved=1"
        )

    saved_answers = saved["answers"]
    for question in questions:
        question_id = question["id"]
        if question_id in saved_answers:
            answer = saved_answers[question_id]
        elif not locked and question["type"] == "code":
            answer = question.get("starter_code", "")
        else:
            answer = ""
        question["student_answer"] = str(answer)

    report = None
    if solution is not None:
        try:
            report = _review_context(questions, solution)
        except ContentError as exc:
            return _content_error(request, exc)

    return render(
        request,
        "assessments/assessment.html",
        {
            "assessment": definition,
            "questions": questions,
            "locked": locked,
            "past_due": past_due,
            "solution_available": solution_available,
            "report": report,
            "saved_notice": request.GET.get("saved") == "1",
        }
    )
