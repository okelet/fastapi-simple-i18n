# Translation files

Each locale is a single JSON file (for example `es.json`) with a `translations`
list. Every entry has a `key` and a `value`, plus two optional fields:

```json
{
  "translations": [
    { "key": "Yes", "value": "Sí" },
    { "key": "Archive", "value": "Archivar", "variant": "verb" },
    { "key": "Archive", "value": "Archivo", "variant": "noun" },
    { "key": "My items", "value": "Mis elementos", "draft": true }
  ]
}
```

## Fields

* `key` — the source string used in the code, written in the built-in language.
* `value` — the translated string for this locale.
* `variant` (optional) — disambiguates entries that share the same key.
* `draft` (optional) — marks a value as provisional.

## Variants

Some words translate differently depending on context. "Archive" can be a verb
(the action) or a noun (the thing). Variants let both live under the same key:

```python
t("Archive", _variant="verb")  # -> "Archivar"
t("Archive", _variant="noun")  # -> "Archivo"
```

The unique unit of a translation is the pair `(key, variant)`. Calling
`t("Archive")` with no variant looks for an entry that has *no* variant; if only
variant entries exist, it falls back to the key itself and logs a warning.

## Drafts

A `draft` entry is a provisional translation. It is **used at runtime exactly
like any other entry** — the flag is purely informational, so you can review and
finalize drafts later. The extraction script marks newly discovered strings as
drafts (see [Extracting translations](extraction.md)).

## The built-in locale

The built-in locale is the language your source strings are written in. It needs
**no file**: its keys are returned verbatim. If you register a file whose locale
equals the built-in locale, it is skipped.
