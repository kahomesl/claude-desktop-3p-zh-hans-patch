# Catalog template

**This is a format example, not a usable language resource.** Installing it will
be refused: its keys do not exist in the application, so coverage is 0 %, and
coverage below 70 % is a hard stop.

It exists to show the shape of the two files you need to write.

## Files

`catalog.json` — the manifest. See
[`schema/catalog.schema.json`](../../schema/catalog.schema.json).

`base.json` — a flat map of message key to [ICU
MessageFormat](https://unicode-org.github.io/icu/userguide/format_parse/messages/)
pattern. Every value must be a well-formed ICU message.

## What to do instead

1. Produce the list of keys the application expects:

   ```bash
   ./zh-patch keys --out my-catalog/base.json
   ```

   This writes every required key with an empty value. It deliberately does not
   export the application's English text: see `docs/CATALOG-FORMAT.md`.

2. Replace the empty values with translations you have the right to use.

3. Point the installer at the directory:

   ```bash
   ./zh-patch check --catalog-dir my-catalog
   ./zh-patch apply --catalog-dir my-catalog
   ```

## Rules the loader enforces

| Rule | Consequence |
| --- | --- |
| Every value parses as ICU MessageFormat | rejected, key reported |
| Every value keeps the same format arguments as the application's own English message for that key | rejected by default, key reported |
| `base` covers at least 70 % of the application's base keys | rejected |
| Keys absent from the application | accepted, reported as unused |
| File references are relative and stay inside the directory | rejected otherwise |

## Licensing

Nothing about this project grants you rights to any text. You are responsible for
having the right to use whatever you put in these files. Declaring a licence in
`catalog.json` records your own claim; it does not create one.
