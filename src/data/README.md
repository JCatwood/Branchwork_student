# Assessment files

Each `.yaml` or `.yml` file in this directory becomes one assessment. The
filename stem is its URL and is also used for its answer and solution files.

Each repository receives its own instructor-generated question file. The app
does not generate or select variants.

The included `homework_01.yaml` demonstrates all supported question types:

- `choice`: radio buttons; `choices` may be a mapping or list.
- `number`: numeric input.
- `text`: a one-line response.
- `textarea`: a longer written response.
- `code`: a multiline, monospace editor intended for R code.
- `due_at`: ISO 8601 date and time string

A code question can set `language`, `rows`, and optional `starter_code`.

Prompts are plain text by default. Use `prompt_html` instead of `prompt` when an
instructor-controlled question needs tables, equations, or other HTML markup.
