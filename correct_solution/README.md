# Instructor feedback and scores

Add a solution file with the same filename as its assessment:

```text
src/data/homework_01.yaml
correct_solution/homework_01.yaml
```

When the solution file appears, the app immediately locks student answers and
displays the instructor-provided score and solution for each question.

Each question entry can contain:

```yaml
questions:
  q1:
    points_awarded: 1.5
    correct_answer: B
    solution: Explanation shown to the student.
```

`points_awarded` must be between zero and the question's maximum points. When
every question has this field, the app displays the total and percentage. If
some questions do not yet have awarded points, it reports the remaining points
as pending.

For a coding question, use a YAML block for `correct_answer` so indentation and
line breaks are retained. Instructor-controlled formatted explanations can use
`solution_html` instead of `solution`.

Copy or rename `homework_01.yaml.example` to try the review workflow.
