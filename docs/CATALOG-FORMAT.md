# Language resource format

This project ships no translation data. A *catalog* is a directory you prepare,
and you are responsible for having the right to the messages it contains.

---

## Directory layout

```
my-catalog/
  catalog.json      manifest — required
  base.json         main interface messages — required
  dynamic.json      dynamic messages — optional
  overrides.json    overrides — optional
```

The file names are yours to choose; the manifest points at them. The names above
are conventions.

## Manifest

```json
{
  "schemaVersion": 1,
  "locale": "zh-Hans",
  "displayName": "简体中文",
  "license": "the licence you hold for these messages",
  "origin": "where they came from and under what authority",
  "files": {
    "base": "base.json",
    "dynamic": "dynamic.json"
  }
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `schemaVersion` | yes | Must be `1`. |
| `locale` | yes | `zh-Hans` or `zh-CN`. Both are written as aliases of one catalog. |
| `displayName` | no | Shown in reports. Defaults to the locale tag. |
| `license` | no | Your own declaration. Recorded in the install marker. |
| `origin` | no | Your own description. Recorded in the install marker. |
| `files.base` | yes | Must not be empty. |
| `files.dynamic` | no | |
| `files.overrides` | no | |

Machine-readable schema:
[`schema/catalog.schema.json`](../schema/catalog.schema.json).

`license` and `origin` are recorded, not enforced. They exist so that what you
claim about your resource travels with the installation and shows up in a report,
instead of being implicit. Declaring a licence does **not** create one, and does
not grant any right to Claude, Claude Desktop, or any Anthropic material.

## Message files

A flat JSON object mapping message key to [ICU
MessageFormat](https://unicode-org.github.io/icu/userguide/format_parse/messages/)
pattern:

```json
{
  "some.key": "一段文字",
  "another.key": "共 {count} 项",
  "plural.key": "{count, plural, other {# 项}}"
}
```

Machine-readable schema:
[`schema/messages.schema.json`](../schema/messages.schema.json).

## Where the keys come from

Ask the tool:

```bash
./zh-patch keys --out my-catalog/base.json
```

This writes every key the application expects, each with an empty value. It
deliberately does **not** export the application's English text. The reason is
the same reason this repository contains no translations: copying text out of the
application and redistributing it is not something this project does. To read what
a message says, look at the application you have installed.

## What the loader checks

| Check | Outcome |
| --- | --- |
| Manifest parses and `schemaVersion` is 1 | error with exit code 4 |
| `locale` is supported | error |
| Every referenced file exists, is relative, and stays inside the directory | error |
| Every file is a JSON object of string to string | error, offending key named |
| Every value is well-formed ICU MessageFormat | error, offending key named |
| `base` is not empty | error |
| `base` covers at least 70 % of the application's base keys | error |
| A message renders an argument the application does not provide | **error, no override** |
| A message drops an argument the application renders outside every branch | **error, no override** |
| A message drops an argument the application renders in a branch that was kept | **error, no override** |
| A message drops a branch and with it an argument only that branch used | accepted, listed and counted |
| Keys that do not exist in the application | warning, written but unused |

### Why format arguments are checked

The application renders these messages with its own formatter. If the English
message is `Saved {fileName}` and the translation is `已保存`, the interface
renders "已保存" with nothing where the file name belongs — a visible defect that
no amount of coverage percentage will reveal.

The check compares argument *names*, not text: it parses both patterns and
requires the sets to be equal. A dropped `{name}` and an invented `{total}` are
both reported. Nothing about the application's own wording is reproduced in any
output — only argument names, which are yours.

### Branches, and why the check does not simply match strings

A message like this uses `{name}` only in one branch:

```
{count, plural, one {{name} shared this} other {{names} shared this}}
```

A language that does not inflect writes it with the `other` branch alone, which
is correct *for that language* — but it necessarily drops `{name}`, and a naive
substring comparison would call that a defect.

The check therefore parses both patterns and records **where** each argument
appears: the chain of `(selector argument, label)` pairs it sits under. An
argument is excused only when **every** place the application uses it is under a
branch the translation no longer has.

| Application | Supplied | Verdict |
| --- | --- | --- |
| `{count, plural, one {{name}} other {{names}}}` | `{count, plural, other {{names}}}` | **Accepted.** The `one` branch is gone, so `{name}` with it. |
| `{count, plural, other {# of {total}}}` | `{count, plural, other {共 # 项}}` | **Refused.** The branch survived; `{total}` leaves a hole. |
| `{count, plural, other {#}}` | `{count, plural, other {# 项}}` | `{count}` is rendered outside the branches. Losing it is always refused. |
| `{a, select, other {{b, plural, one {{c}} other {{d}}}}}` | `{a, select, other {{b, plural, other {{d}}}}}` | **Accepted.** The removed `one` branch is where `{c}` lived. |

The narrowness matters in both directions: `{total}` above sits *inside* a
branch, but inside a branch that was **kept**, so removing it is a real defect and
is refused.

**There is no flag that overrides a refusal.** A refused catalog must be fixed.
Accepted branch collapses need no flag and no acknowledgement: they are listed by
`lint` and counted in the install marker so the acceptance is visible rather than
silent, not so that it can be granted or withheld.

### Why coverage is checked

Below 70 % the interface is an unpredictable mixture of languages, which is worse
than not installing. The threshold is deliberately blunt; raise it in your own
fork if you want a stricter bar.

## The `lint` command

`lint` reports everything about a resource, at the level of detail above, and
writes nothing anywhere. It has no acceptance flag, and neither does `apply` — the
verdict is the same either way.

```bash
./zh-patch lint --catalog-dir ~/my-catalog
./zh-patch lint --catalog-dir ~/my-catalog --report report.md
./zh-patch --json lint --catalog-dir ~/my-catalog
```

Exit code `0` means installable, `4` means defects are present.

The `--report` file is a Markdown document listing the catalogue metadata, the
coverage, every defect with its reason and both argument sets, and every accepted
branch collapse. It contains no application text, so it is safe to keep, share,
or attach to an issue.

## Validation example

```bash
./zh-patch check --catalog-dir ~/my-catalog
```

```
catalog          简体中文 (zh-Hans)
declared licence the licence you hold for these messages
coverage         base: 33,333/33,600 (99.2%); dynamic: 49/49 (100.0%)
  warning: 11 message(s) remove a plural or select branch and with it an argument
           only that branch used; accepted, because a language that does not inflect
           writes the message that way (base[xxxxxxxxxx], …)
  warning: 790 catalog key(s) do not exist in this application build and will be written but never used
```

Warnings do not block. Fix any errors, re-run, and install once the check passes.

---

## Obtaining a resource legitimately

There is a real question here, and this project takes a conservative position.

**What this project does not do.** It does not bundle a translation, does not
download one, and contains no code that extracts one from the application or from
claude.ai. Extracting a service's own translation catalog and redistributing it
is not something this project will help with, and it is why the repository is
empty of message text.

**What you can do.**

1. **Translate it yourself.** Run `keys`, fill in the values, and hold the
   copyright in what you wrote. This is unambiguous and is what the tool is
   designed around.

2. **Use text you are licensed to use.** If your employer, a client, or a
   translation vendor has given you a translated message set under terms that
   permit this use, put their terms in `license` and describe the arrangement in
   `origin`. The manifest fields exist for exactly this.

3. **Reuse a permissively licensed translation**, if one exists for this
   interface, and keep its attribution and licence intact.

**What is not a licence.** Installing a tool that reads text you have locally
does not authorise you to redistribute that text. Having a copy of the
application does not grant rights over its contents. Supplying a catalog does not
mean Anthropic has authorised anything. If you are unsure whether you may use a
particular message set, the answer this project acts on is "do not".

---

## Contributing a translation

Community translations may be contributed to a **separate** repository or
distribution channel, never to this one, and only under these conditions:

- **independent creation** — the text was written by a contributor, or comes from
  a source whose licence permits redistribution;
- **licence declared** — the contribution states its licence, and it is one that
  permits redistribution and modification;
- **reviewed** — a maintainer checks the declaration before it is published;
- **attribution kept** — the licence and contributors travel with the text.

Contributions that consist of text copied out of the application or out of
claude.ai will be rejected, whatever their quality.

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
