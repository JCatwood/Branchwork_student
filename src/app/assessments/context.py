"""Values shared by every HTML template."""

from pathlib import Path

from .repository import ContentError, load_student_config


def course_context(request):
    try:
        config = load_student_config()
        config_error = ""
    except ContentError as exc:
        config = {
            "student_id": "configuration-error",
            "course_title": "Course Homework and Exams",
            "theme": "minimal.css",
        }
        config_error = str(exc)

    theme = Path(config["theme"]).name
    if Path(theme).suffix.lower() != ".css":
        theme = "minimal.css"
    return {
        "course_title": config["course_title"],
        "student_id": config["student_id"],
        "theme_css": theme,
        "student_config_warning": (
            config["student_id"] == "replace-with-github-username"
        ),
        "config_error": config_error,
    }
