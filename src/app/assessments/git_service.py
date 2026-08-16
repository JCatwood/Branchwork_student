"""Small, guarded Git operations for the local Branchwork web interface."""

from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


SAFE_ASSESSMENT_ID = re.compile(r"^[A-Za-z0-9_-]+$")
GIT_LOCK = threading.Lock()


class GitOperationError(RuntimeError):
    """A Git operation could not be completed safely."""


@dataclass(frozen=True)
class GitStatus:
    available: bool
    repository: bool
    ready: bool
    branch: str = ""
    origin: str = ""
    user_name: str = ""
    user_email: str = ""
    changed_files: int = 0
    ahead: int = 0
    behind: int = 0
    message: str = ""


@dataclass(frozen=True)
class GitResult:
    message: str
    restart_required: bool = False
    commit: str = ""


def _repository_root() -> Path:
    return Path(settings.REPOSITORY_ROOT).resolve()


def _branch() -> str:
    return str(getattr(settings, "GIT_BRANCH", "main"))


def _redact(value: str) -> str:
    """Remove credentials that may have been embedded in an HTTPS URL."""
    value = re.sub(r"(https?://)[^/@\s]+@", r"\1***@", value)
    return value.strip()[:1200]


def _remote_identity(value: str) -> str:
    """Normalize common GitHub URL forms for template-origin detection."""
    value = value.strip().rstrip("/")
    value = re.sub(r"^https?://(?:[^/@]+@)?", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^ssh://git@", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^git@([^:]+):", r"\1/", value, flags=re.IGNORECASE)
    if value.lower().endswith(".git"):
        value = value[:-4]
    return value.lower()


def _friendly_failure(result: subprocess.CompletedProcess[str]) -> str:
    raw = _redact(result.stderr or result.stdout or "Git command failed")
    lowered = raw.lower()
    if any(
        phrase in lowered
        for phrase in (
            "authentication failed",
            "could not read username",
            "permission denied (publickey)",
            "repository not found",
        )
    ):
        return (
            "GitHub authentication failed. Run 'gh auth login' and "
            "'gh auth setup-git' in a terminal, then try again."
        )
    if "please tell me who you are" in lowered or "unable to auto-detect email" in lowered:
        return (
            "Git needs your commit identity. Configure git user.name and "
            "user.email, then try again."
        )
    if any(
        phrase in lowered
        for phrase in (
            "would be overwritten by merge",
            "not possible to fast-forward",
            "divergent branches",
            "conflict",
        )
    ):
        return (
            "Git could not apply the remote update safely because the local "
            "and remote repositories differ. Your files were not overwritten. "
            "Ask the instructor for help resolving the Git conflict."
        )
    if "could not resolve host" in lowered or "failed to connect" in lowered:
        return "GitHub could not be reached. Check the internet connection and retry."
    if "non-fast-forward" in lowered or "fetch first" in lowered:
        return (
            "GitHub received another update first. Your submission remains "
            "committed locally; get help synchronizing before retrying."
        )
    return f"Git reported: {raw}"


def _run_git(
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    root = _repository_root()
    command = ["git", "-C", str(root), *(str(argument) for argument in arguments)]
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=float(getattr(settings, "GIT_TIMEOUT_SECONDS", 45)),
            env=environment,
        )
    except FileNotFoundError as exc:
        raise GitOperationError(
            "Git is not installed or is not available on the application PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitOperationError(
            "Git did not finish in time. Check the network connection and retry."
        ) from exc

    if check and result.returncode != 0:
        raise GitOperationError(_friendly_failure(result))
    return result


def _config_value(key: str) -> str:
    result = _run_git("config", "--get", key, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def get_git_status() -> GitStatus:
    """Return local-only Git status suitable for the homepage."""
    root = _repository_root()
    if not root.is_dir():
        return GitStatus(
            available=True,
            repository=False,
            ready=False,
            message="The Branchwork repository directory does not exist.",
        )

    try:
        version = _run_git("--version", check=False)
        if version.returncode != 0:
            return GitStatus(
                available=False,
                repository=False,
                ready=False,
                message="Git is not available. Install Git and restart Branchwork.",
            )

        inside = _run_git("rev-parse", "--is-inside-work-tree", check=False)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return GitStatus(
                available=True,
                repository=False,
                ready=False,
                message="This Branchwork folder is not a Git repository.",
            )

        branch = _run_git("branch", "--show-current").stdout.strip()
        origin_result = _run_git("remote", "get-url", "origin", check=False)
        origin_raw = origin_result.stdout.strip() if origin_result.returncode == 0 else ""
        user_name = _config_value("user.name")
        user_email = _config_value("user.email")
        changes = _run_git("status", "--porcelain").stdout.splitlines()

        ahead = 0
        behind = 0
        remote_ref = f"refs/remotes/origin/{_branch()}"
        has_remote_ref = _run_git(
            "show-ref", "--verify", "--quiet", remote_ref, check=False
        )
        if has_remote_ref.returncode == 0:
            counts = _run_git(
                "rev-list",
                "--left-right",
                "--count",
                f"origin/{_branch()}...HEAD",
            ).stdout.split()
            if len(counts) == 2:
                behind, ahead = (int(value) for value in counts)

        template_remote = str(
            getattr(settings, "GIT_TEMPLATE_REMOTE", "")
        ).strip()
        is_template = bool(
            origin_raw
            and template_remote
            and _remote_identity(origin_raw) == _remote_identity(template_remote)
        )

        if branch != _branch():
            message = f"Branchwork must be on the {_branch()!r} branch, not {branch!r}."
            ready = False
        elif not origin_raw:
            message = "The repository does not have an origin remote."
            ready = False
        elif is_template:
            message = (
                "Origin still points to the course template. Clone your own "
                "private repository before using the GitHub buttons."
            )
            ready = False
        elif not user_name or not user_email:
            message = "Configure your Git name and email before submitting."
            ready = False
        else:
            message = "Git is configured. GitHub authentication is checked when a button is used."
            ready = True

        return GitStatus(
            available=True,
            repository=True,
            ready=ready,
            branch=branch,
            origin=_redact(origin_raw),
            user_name=user_name,
            user_email=user_email,
            changed_files=len(changes),
            ahead=ahead,
            behind=behind,
            message=message,
        )
    except GitOperationError as exc:
        return GitStatus(
            available=False,
            repository=False,
            ready=False,
            message=str(exc),
        )


def _require_ready_repository() -> GitStatus:
    status = get_git_status()
    if not status.ready:
        raise GitOperationError(status.message)
    return status


def _pull_locked(status: GitStatus) -> GitResult:
    old_head = _run_git("rev-parse", "HEAD").stdout.strip()
    _run_git("pull", "--ff-only", "origin", status.branch)
    new_head = _run_git("rev-parse", "HEAD").stdout.strip()

    if old_head == new_head:
        return GitResult("Already up to date with GitHub.")

    changed = _run_git(
        "diff", "--name-only", old_head, new_head
    ).stdout.splitlines()
    restart_required = any(
        Path(path).suffix == ".py"
        or path in {"requirements.txt", "run.py"}
        for path in changed
    )
    return GitResult(
        f"Downloaded {len(changed)} updated file(s) from GitHub.",
        restart_required=restart_required,
    )


def pull_updates() -> GitResult:
    """Fast-forward the local main branch without creating a merge commit."""
    with GIT_LOCK:
        status = _require_ready_repository()
        return _pull_locked(status)


def _index_is_clean() -> bool:
    result = _run_git("diff", "--cached", "--quiet", check=False)
    if result.returncode not in (0, 1):
        raise GitOperationError(_friendly_failure(result))
    return result.returncode == 0


def _unexpected_ahead_paths(branch: str) -> list[str]:
    paths = _run_git(
        "diff", "--name-only", f"origin/{branch}..HEAD"
    ).stdout.splitlines()
    return [
        path
        for path in paths
        if path != "student.yaml" and not path.startswith("student_answer/")
    ]


def submit_answer(assessment_id: str, title: str) -> GitResult:
    """Commit exactly one saved-answer JSON file and push ``main``."""
    if not SAFE_ASSESSMENT_ID.fullmatch(assessment_id):
        raise GitOperationError("The assessment ID is not safe for a filename.")

    root = _repository_root()
    answer_path = root / "student_answer" / f"{assessment_id}.json"
    if not answer_path.is_file():
        raise GitOperationError(
            "No saved answer file exists. Open the assessment and save answers first."
        )
    relative_answer = answer_path.relative_to(root).as_posix()

    with GIT_LOCK:
        status = _require_ready_repository()
        if not _index_is_clean():
            raise GitOperationError(
                "The repository already has staged files. Commit or unstage them "
                "before using the Submit button."
            )

        pull_result = _pull_locked(status)
        unexpected = _unexpected_ahead_paths(status.branch)
        if unexpected:
            raise GitOperationError(
                "The local branch has unpublished commits outside student_answer/: "
                + ", ".join(unexpected)
                + ". Ask the instructor for help before submitting."
            )

        staged_by_app = False
        commit_created = False
        try:
            _run_git("add", "--", relative_answer)
            staged_by_app = True
            staged_paths = set(
                filter(
                    None,
                    _run_git(
                        "diff", "--cached", "--name-only", "-z"
                    ).stdout.split("\0"),
                )
            )
            unexpected_staged = staged_paths.difference({relative_answer})
            if unexpected_staged:
                raise GitOperationError(
                    "Refusing to commit unexpected staged files: "
                    + ", ".join(sorted(unexpected_staged))
                )

            if relative_answer in staged_paths:
                clean_title = " ".join(str(title).split())[:100]
                _run_git(
                    "commit",
                    "-m",
                    f"Submit {clean_title} ({assessment_id})",
                )
                commit_created = True

            try:
                _run_git("push", "origin", status.branch)
            except GitOperationError as exc:
                if commit_created or status.ahead:
                    raise GitOperationError(
                        "Your answers were committed locally, but the push failed. "
                        "Do not delete the repository. Retry Submit or ask the "
                        f"instructor for help. {exc}"
                    ) from exc
                raise

            commit = _run_git("rev-parse", "--short", "HEAD").stdout.strip()
            action = "Committed and pushed" if commit_created else "Pushed"
            return GitResult(
                f"{action} {assessment_id} to GitHub at commit {commit}.",
                restart_required=pull_result.restart_required,
                commit=commit,
            )
        except Exception:
            if staged_by_app and not commit_created:
                _run_git(
                    "restore", "--staged", "--", relative_answer, check=False
                )
            raise

