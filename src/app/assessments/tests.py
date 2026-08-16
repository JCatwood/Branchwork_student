import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .git_service import (
    GitOperationError,
    GitResult,
    get_git_status,
    pull_updates,
    submit_answer,
)
from .repository import load_answers


ASSESSMENT_YAML = """
title: Test Homework
kind: Homework
questions:
  - id: q1
    type: choice
    points: 2
    prompt: Choose B.
    choices: {A: First, B: Second}
  - id: r_question
    type: code
    language: R
    points: 3
    prompt: Calculate the mean.
    starter_code: |
      x <- c(2, 4, 6)
"""


class ViewWorkflowTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data_dir = self.root / "data"
        self.answer_dir = self.root / "student_answer"
        self.solution_dir = self.root / "correct_solution"
        self.style_dir = self.root / "styles"
        self.data_dir.mkdir()
        self.answer_dir.mkdir()
        self.solution_dir.mkdir()
        self.style_dir.mkdir()
        self.student_file = self.root / "student.yaml"

        (self.data_dir / "homework_test.yaml").write_text(
            ASSESSMENT_YAML, encoding="utf-8"
        )
        self.student_file.write_text(
            "student_id: test-student\ncourse_title: Test Course\ntheme: minimal.css\n",
            encoding="utf-8",
        )
        self.settings_override = override_settings(
            DATA_DIR=self.data_dir,
            ANSWER_DIR=self.answer_dir,
            SOLUTION_DIR=self.solution_dir,
            STYLE_DIR=self.style_dir,
            STUDENT_CONFIG=self.student_file,
            STATICFILES_DIRS=[self.style_dir],
            REPOSITORY_ROOT=self.root,
            GIT_TEMPLATE_REMOTE="",
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.temporary.cleanup()

    def test_r_code_is_saved_verbatim_and_solution_points_are_displayed(self):
        first_page = self.client.get("/assessment/homework_test/")
        self.assertContains(first_page, "x &lt;- c(2, 4, 6)")

        r_code = "x <- c(2, 4, 6)\nmean(x)\n"
        response = self.client.post(
            "/assessment/homework_test/",
            {"answer__q1": "B", "answer__r_question": r_code},
        )
        self.assertEqual(response.status_code, 302)

        saved = load_answers("homework_test")
        self.assertEqual(saved["answers"]["r_question"], r_code)
        raw_json = json.loads(
            (self.answer_dir / "homework_test.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("variants", raw_json)

        (self.solution_dir / "homework_test.yaml").write_text(
            """
questions:
  q1:
    points_awarded: 2
    correct_answer: B
    solution: Correct choice.
  r_question:
    points_awarded: 2.5
    correct_answer: |
      x <- c(2, 4, 6)
      mean(x)
    solution: Use mean().
""".strip(),
            encoding="utf-8",
        )

        review = self.client.get("/assessment/homework_test/")
        self.assertEqual(review.status_code, 200)
        self.assertContains(review, "4.5/5")
        self.assertContains(review, "90.0%")
        self.assertContains(review, "2.5 / 3 points")

        locked = self.client.post(
            "/assessment/homework_test/", {"answer__r_question": "changed"}
        )
        self.assertEqual(locked.status_code, 403)

    def test_git_actions_require_post(self):
        self.assertEqual(self.client.get("/git/pull/").status_code, 405)
        self.assertEqual(
            self.client.get("/assessment/homework_test/submit/").status_code,
            405,
        )

    @patch("assessments.views.pull_updates")
    def test_get_updates_redirects_with_success_message(self, mocked_pull):
        mocked_pull.return_value = GitResult("Already up to date with GitHub.")
        response = self.client.post("/git/pull/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already up to date with GitHub.")

    @patch("assessments.views.submit_answer")
    def test_submit_button_publishes_only_named_assessment(self, mocked_submit):
        mocked_submit.return_value = GitResult(
            "Committed and pushed homework_test to GitHub."
        )
        response = self.client.post(
            "/assessment/homework_test/submit/", follow=True
        )
        self.assertEqual(response.status_code, 200)
        mocked_submit.assert_called_once_with("homework_test", "Test Homework")
        self.assertContains(response, "pushed homework_test")


@unittest.skipUnless(shutil.which("git"), "Git is required for integration tests")
class GitServiceTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        temporary_root = Path(self.temporary.name)
        self.repository = temporary_root / "student"
        self.remote = temporary_root / "remote.git"
        self.instructor = temporary_root / "instructor"

        self._git("init", "--bare", "--initial-branch=main", self.remote)
        self._git("init", "--initial-branch=main", self.repository)
        self._git("config", "user.name", "Test Student", cwd=self.repository)
        self._git(
            "config", "user.email", "student@example.test", cwd=self.repository
        )
        (self.repository / "README.md").write_text(
            "Branchwork test repository\n", encoding="utf-8"
        )
        self._git("add", "README.md", cwd=self.repository)
        self._git("commit", "-m", "Initial template", cwd=self.repository)
        self._git(
            "remote", "add", "origin", str(self.remote), cwd=self.repository
        )
        self._git("push", "-u", "origin", "main", cwd=self.repository)

        self.settings_override = override_settings(
            REPOSITORY_ROOT=self.repository,
            GIT_BRANCH="main",
            GIT_TEMPLATE_REMOTE="",
            GIT_TIMEOUT_SECONDS=10,
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.temporary.cleanup()

    @staticmethod
    def _git(*arguments, cwd=None, check=True):
        return subprocess.run(
            ["git", *(str(argument) for argument in arguments)],
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True,
        )

    def test_submit_pushes_exact_answer_and_pull_gets_remote_update(self):
        status = get_git_status()
        self.assertTrue(status.ready, status.message)

        answer_directory = self.repository / "student_answer"
        answer_directory.mkdir()
        answer_path = answer_directory / "homework_01.json"
        answer_path.write_text(
            '{"answers": {"q01": "B"}}\n', encoding="utf-8"
        )
        unrelated = self.repository / "notes.txt"
        unrelated.write_text("Do not publish me.\n", encoding="utf-8")

        result = submit_answer("homework_01", "Homework 1")
        self.assertTrue(result.commit)
        remote_answer = self._git(
            f"--git-dir={self.remote}",
            "show",
            "main:student_answer/homework_01.json",
        )
        self.assertIn('"q01": "B"', remote_answer.stdout)
        missing_note = self._git(
            f"--git-dir={self.remote}",
            "show",
            "main:notes.txt",
            check=False,
        )
        self.assertNotEqual(missing_note.returncode, 0)

        self._git("clone", str(self.remote), self.instructor)
        self._git("config", "user.name", "Test Instructor", cwd=self.instructor)
        self._git(
            "config", "user.email", "instructor@example.test", cwd=self.instructor
        )
        update_path = self.instructor / "src" / "data" / "homework_02.yaml"
        update_path.parent.mkdir(parents=True)
        update_path.write_text("title: Homework 2\n", encoding="utf-8")
        self._git("add", "src/data/homework_02.yaml", cwd=self.instructor)
        self._git("commit", "-m", "Publish Homework 2", cwd=self.instructor)
        self._git("push", "origin", "main", cwd=self.instructor)

        pull_result = pull_updates()
        self.assertFalse(pull_result.restart_required)
        self.assertTrue(
            (self.repository / "src" / "data" / "homework_02.yaml").is_file()
        )

    def test_submit_refuses_preexisting_staged_files(self):
        answer_directory = self.repository / "student_answer"
        answer_directory.mkdir()
        (answer_directory / "homework_01.json").write_text(
            '{"answers": {}}\n', encoding="utf-8"
        )
        staged = self.repository / "unrelated.txt"
        staged.write_text("staged\n", encoding="utf-8")
        self._git("add", "unrelated.txt", cwd=self.repository)

        with self.assertRaisesRegex(GitOperationError, "already has staged"):
            submit_answer("homework_01", "Homework 1")
