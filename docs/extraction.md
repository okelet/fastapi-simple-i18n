# Extracting translations

The extraction script keeps your locale files in sync with the `t("...")` calls
in your code. It parses Python sources with the `ast` module and templates with
Jinja's own parser (never regex), so only **literal** string arguments are
collected.

## Running it

Pass a reference to your module translation class:

```bash
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation
```

You can also use the dotted form `myapp.i18n.AppTranslation`.

## Choosing locales

Locales are the union of:

* Those auto-detected from the JSON files already in the module's translation
  directory.
* Any extra locale codes you pass on the command line.

```bash
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation es fr
```

## What it writes

For each locale file:

* New `(key, variant)` pairs are added with an empty `value` and `draft: true`.
* Existing entries are preserved (their value and draft flag are kept).
* With `--prune`, entries no longer present in the source are removed.

Use `--dry-run` to preview changes without writing:

```bash
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation --dry-run
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation --prune
```

## What gets extracted

The script collects the first positional string argument of any `t(...)` call,
plus a literal `_variant` keyword when present:

```python
t("Yes")                        # ("Yes", None)
t("Archive", _variant="noun")   # ("Archive", "noun")
t("Hello {name}", name=user)    # ("Hello {name}", None)
t(some_variable)                # skipped: warns, not a literal
```

Anything that is not a string literal cannot be extracted, and the script says
so on `stderr` with the file, the line and the offending expression:

```text
Warning: myapp/views.py:12: t() called with a non-literal key some_variable; skipped.
Warning: myapp/views.py:20: non-literal _variant kind for key "Archive"; extracted with no variant.
```

The second case is the dangerous one: the runtime lookup uses the real variant
value, while the extracted entry is created without it, so the translation file
ends up with a `(key, None)` draft that nothing will ever look up.

!!! warning
    Because extraction is literal-only, avoid `t(variable)` for strings you want
    extracted. Keep the source string literal at the call site.

## Aliased or wrapped functions

A call is matched on the name alone, so `helpers.t("Yes")` is found the same way
`t("Yes")` is. Anything else your code calls the translation function has to be
named, which is what `--python-function` is for:

```bash
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation \
    --python-function translate --python-function tr
```

* **An aliased import.** `from fastapi_simple_i18n.helpers import t as translate`
  gives calls to `translate`, so that is the name to pass.
* **A wrapper.** A function of your own that a call goes through is matched on
  its own name:

```python
def tr(key, **params):
    return t(key, **params)
```

```python
tr("Archive")  # extracted as ("Archive", None)
```

!!! warning
    The extractor sees the call, never the body of your wrapper, so a wrapper
    that supplies the variant itself is the one case that goes wrong. With
    `def tr(key, **params): return t(key, _variant="verb", **params)`, the call
    `tr("Archive")` extracts as `("Archive", None)` while the runtime looks up
    `("Archive", "verb")`, and nothing ever reads that entry. It is the same trap
    as a non-literal `_variant` above. Pass the variant at the call site, or add
    the entry by hand.

The option defaults to `t` and **replaces** that default, so name every one of
your functions in a single run:

```bash
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation \
    --python-function t --python-function translate
```

The names in use are printed with the rest of the summary, so a run that comes
back empty tells you which names it was looking for:

```text
Python functions: t, translate
```

## Templates

If your module declares template directories with `get_template_dirs()`, the
script parses those files too and collects the same `(key, variant)` pairs into
the same catalog:

```html
{{ t("Welcome") }}                    <!-- ("Welcome", None) -->
{{ t("Archive", _variant="verb") }}   <!-- ("Archive", "verb") -->
{{ "Inbox" | t }}                     <!-- ("Inbox", None) -->
{% trans %}Signed in{% endtrans %}    <!-- ("Signed in", None) -->
{% trans "noun" %}Archive{% endtrans %}  <!-- ("Archive", "noun") -->
```

Only the suffixes the module declares are read, and only the names the module's
environment (or the `--jinja-function` / `--jinja-filter` options) names are
looked for. Both options can be repeated, so a project that wraps the helper
under several names can have all of them extracted:

```bash
python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation \
    --jinja-function tr --jinja-function translate \
    --jinja-filter tx --jinja-filter tr
```

They replace the names stored on the environment rather than adding to them, so
list every name your templates use. Non-literal keys, `{% pluralize %}` blocks
and templates that fail to parse are all reported on `stderr` and skipped, so a
broken template never blocks extraction. See [Templates](jinja.md).
