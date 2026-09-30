# Templates

Templates get their strings from the same catalog as your Python code. The
optional `jinja` extra adds a Jinja2 environment installer and teaches the
extraction script to parse your templates:

```bash
pip install "fastapi-simple-i18n[jinja]"
```

## Installing the helpers

Templates call the same `t()` as your Python code, so the catalog, the
`(key, variant)` pairs and the `{name}` placeholders work exactly as they do in
Python. Installation is a single call on the environment:

```python
from fastapi.templating import Jinja2Templates
from fastapi_simple_i18n.jinja import install_translation_support

templates = Jinja2Templates(directory="templates")
install_translation_support(templates.env)
```

With FastAPI or Starlette that is all. The helpers read the locale that
`TranslationMiddleware` negotiated for the current request, at render time, so
one compiled template serves every locale.

## What templates can call

* `t("Key")`, the global translation function, and `"Key" | t`, the filter. Both
  take the variant and the format parameters.
* `{% trans %}...{% endtrans %}` blocks, and `{{ gettext("Key") }}`.
* `t_number`, `t_money`, `t_amount`, `t_date`, `t_time` and `t_datetime`, the same
  formatters the Python helpers provide.
* The lazy forms: `lazy_t("Key")` / `"Key" | lazy_t`, `lazy_t_number`,
  `lazy_t_money`, `lazy_t_amount`, `lazy_t_date`, `lazy_t_time` and
  `lazy_t_datetime`. They resolve when the template renders, which inside
  `{{ }}` means the locale of the request being rendered.
* `get_current_locale()` and `get_current_tz()`, the request context as the
  template sees it.

```html
<h1>{{ t("Welcome to the example app") }}</h1>

<p>{{ t("Hello, {name}!", name=user.name) }}</p>

<p>{{ "Archive" | t(variant="verb") }}</p>

<p>{% trans %}Signed in{% endtrans %}</p>

<p>{{ t_number(total) }} &mdash; {{ t_money(total, "EUR") }} &mdash; {{ t_date(today) }}</p>
```

The variant can be given as `_variant=`, which is what the Python `t()` takes, or
as `variant=`, which reads better in a template. Both work in the function and
in the filter, and `_variant=` wins if you pass both.

There is no need to wrap a lazy value in `str()` here: Jinja's default
`finalize` already calls `str()` on whatever a `{{ }}` outputs, so
`{{ lazy_t("Key") }}` and `{{ lazy_t_number(total) }}` render correctly. Inside a
`{% trans %}` block, or through `| tojson`, wrap it yourself.

## The request context in a template

Two globals expose the request context, so a template does not need the locale
or the timezone threaded through its render context:

```html
<html lang="{{ get_current_locale().language }}">
```

`get_current_locale()` returns a [`babel.core.Locale`](https://babel.pocoo.org/en/latest/api/core.html#babel.core.Locale),
so any subtag or display name is reachable from it:

```html
<html lang="{{ get_current_locale().language }}">
<meta name="description" content="{{ get_current_locale().get_display_name() }}">
<span>{{ get_current_locale().territory or "—" }}</span>
```

`{{ get_current_locale() }}` on its own renders the full identifier
(`es_ES`), which is what a `lang` attribute does *not* want: a region is a
`territory`, not a language.

`get_current_tz()` returns the active `tzinfo`. It is never `None` — the library
always has one in effect, `UTC` until something is configured — so a template
can render it without a guard:

```html
<p>{{ t_datetime(moment) }} ({{ get_current_tz() }})</p>
```

Both names are installed only if the environment does not already define them,
so an application that wants its own `get_current_locale` global keeps it.

## Renaming the helpers

The function and the filter can be given any name, and several names at once:

```python
install_translation_support(templates.env, function_name="translate", filter_name="trans")
```

Now templates use `{{ translate("Key") }}` and `{{ "Key" | trans }}`.

A tuple of names registers them all as aliases, which is what you want when your
code reaches the helper through more than one name:

```python
install_translation_support(templates.env, function_name=("t", "tr", "translate"))
```

Every name is looked for by the extraction script, so this covers the two cases
that come up in practice:

* **A wrapper you wrote yourself.** A function that defaults the variant, or adds
  a parameter, and is registered next to the original:

```python
install_translation_support(templates.env, function_name=("t", "tr"))
```

```html
{{ t("Archive") }}
{{ tr("Archive", variant="verb") }}
```

* **An attribute of another object.** When the helper reaches the template as
  `i18n.t(...)`, the object does not matter, only the name after the dot. This
  works out of the box, with no configuration:

```html
{{ i18n.t("Archive") }}
{{ i18n.translate("Archive") }}
```

  Only the last name is matched, so an alias under another name still has to be
  listed: `install_translation_support(templates.env, function_name=("t", "tr"))`.

The names are remembered on the environment, so the extraction script picks them
up without being told. If you also renamed the function on the Python side, the
script has to be told there too, with
[`--python-function`](extraction.md#aliased-or-wrapped-functions).

## Variants from trans blocks

A `{% trans %}` block accepts a context, and a context is exactly what this
library calls a variant:

```html
{% trans "verb" %}Archive{% endtrans %}
{% trans "noun" %}Archive{% endtrans %}
```

Those two blocks extract as `("Archive", "verb")` and `("Archive", "noun")`, the
same pairs the Python `t("Archive", _variant="verb")` produces.

## Two things to know

### Trans blocks interpolate with %s, not {}

`{% trans %}` is Jinja's own tag, so it builds its message with `%(name)s`
placeholders and interpolates them itself:

```html
{% trans count=item_count %}There are {{ item_count }} items in your cart{% endtrans %}
```

extracts as the key `There are %(item_count)s items in your cart`. Braces are
not substituted there, so use `t("There are {item_count} items", ...)` when you
want the `str.format` style. This is the one place where a template and the same
sentence written in Python do not produce the same key.

### The catalog holds plain text

With autoescape on, which is Starlette's default, the translated string is
escaped along with the values interpolated into it. That keeps user-supplied
values safe, but it also means a translation must not contain HTML: a `<b>` in a
translation renders as literal text. `|safe` does not survive interpolation into
a translation, because the whole result is escaped after `str.format` runs.

## Extracting from templates

Tell your module where the templates are, and the extraction script parses them
with Jinja's own parser, never a regex:

```python
class AppTranslation(BaseModuleTranslation):

    @classmethod
    def get_template_dirs(cls) -> list[Path]:
        return [Path(__file__).parent / "templates"]
```

Then run the same command as before:

```bash
python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation
```

Every `(key, variant)` pair found in a template lands in the same JSON files as
the ones found in Python, as a draft. Keys that are not string literals are
skipped and reported with file and line, exactly as with Python sources.

By default the files ending in `.jinja`, `.jinja2`, `.html`, `.html.j2` or
`.j2.html` are read. Override `get_template_suffixes()` for anything else, such
as `.j2` or `.tpl`:

```python
    @classmethod
    def get_template_suffixes(cls) -> tuple[str, ...]:
        return (".j2",)
```

A suffix is matched against the whole file name, so a compound one like
`.html.j2` works even though `pathlib.Path.suffix` would only report `.j2`.

To let the script see the same Jinja configuration the application renders with,
return that very environment from `get_jinja_environment()`. Custom delimiters,
custom extensions and `{% raw %}` blocks are then handled the way your
application experiences them. It also saves repeating the names in the command
line:

```python
from myapp.templating import templates


class AppTranslation(BaseModuleTranslation):

    @classmethod
    def get_jinja_environment(cls) -> Environment:
        return templates.env
```

Creating the environment in its own module, as above, keeps this free of import
cycles: the app and the translation module both import it.

If you cannot reach the environment from your module class, name the helpers on
the command line instead:

```bash
python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation \
    --jinja-function translate --jinja-filter trans
```

Both options can be repeated, once per name, which is the equivalent of the tuple
above:

```bash
python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation \
    --jinja-function t --jinja-function tr \
    --jinja-filter t --jinja-filter tx
```

Note that they *replace* the names stored on the environment instead of adding
to them, so list every name your templates use. A template calling a name that is
not on the list is skipped silently, the same as a call to any other unknown
function.

## What is not supported

Pluralization. `{% trans count=n %}{{ n }} item{% pluralize %}{{ n }} items{% endtrans %}`
raises a `NotImplementedError` at render time, and the extraction script reports
it as a warning rather than extracting half of it. There is no locale-aware
plural rule in this library, so a `pluralize` block would need the translator to
supply the forms, and it would silently pick the wrong one for most languages.

Use one key per form with the variant instead, which is what the Python API
already does:

```python
if item_count == 1:
    label = t("There is {n} item in your cart", n=item_count)
else:
    label = t("There are {n} items in your cart", n=item_count)
```

The form of that helper is application code, so the plural rule lives with the
rest of your domain logic. ICU MessageFormat would handle it inside the library
and is a possible future addition.
