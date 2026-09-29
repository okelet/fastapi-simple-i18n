# Building the docs

This documentation is built with [MkDocs](https://www.mkdocs.org/) using the
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) theme.

## Installing the docs tooling

MkDocs and the Material theme live in the `docs` dependency group, so they are
not installed by default. `uv run --group docs` pulls them in on demand:

```bash
uv run --group docs mkdocs --version
```

## Previewing locally

Serve the site with live reload and open the printed URL (usually
`http://127.0.0.1:8000`):

```bash
uv run --group docs mkdocs serve
```

## Building the static site

Generate the static HTML into the `site/` directory:

```bash
uv run --group docs mkdocs build
```

Use `--strict` in CI to fail on broken links or nav references:

```bash
uv run --group docs mkdocs build --strict
```

## Adding a page

Create a Markdown file under `docs/` and add it to the `nav` section of
`mkdocs.yml`. The configuration is intentionally minimal: the Material theme,
code-copy buttons, and the `admonition` and `superfences` Markdown extensions.
