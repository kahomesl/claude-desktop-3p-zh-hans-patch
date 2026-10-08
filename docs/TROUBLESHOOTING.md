# Troubleshooting

Find your symptom, run the diagnostic, and read what it means.

---

## The tool refuses to install

That is usually correct behaviour. Each refusal names its cause.

### Exit code 3 — version not supported

```
error: Claude Desktop 2.26454.2 is not a supported version.
```

Your installed version has not been verified. Nothing is wrong with your setup.
Install from a copy of a supported version instead — see
[installing from a backup](INSTALL.md#installing-from-a-backup).

Do **not** edit the version string in `Info.plist` to get past this. The
structure and digest checks will refuse the result anyway, and if they did not,
you would be installing an untested combination.

### Exit code 4 — language resource rejected

The output names the keys at fault. For the full picture — every finding, its
reason, and both argument sets — use `lint`:

```bash
./zh-patch lint --catalog-dir ~/my-catalog
./zh-patch lint --catalog-dir ~/my-catalog --report report.md
```

Common causes:

| Message | Meaning |
| --- | --- |
| `base coverage is N%, below the required 70%` | The catalog covers too few keys. |
| `drops a format argument the application's message provides` | A placeholder that the application renders outside every branch, or inside a branch you kept, is missing. Fix the translation. |
| `uses a format argument the application's message does not provide` | The translation invented a placeholder. It throws when the message is formatted. |
| `unsupported argument type` | A pattern is not valid ICU MessageFormat. |
| `1 message(s) remove a plural or select branch …accepted` | A warning, not an error. Nothing to do: see below. |
| `does not exist in this application build` | A warning, not an error. The key is written but unused. |
| `no language resource was supplied` | `--catalog-dir` was omitted. |

For a dropped argument, the fix is in your resource: the application is
`saved {fileName}`, so the translation must contain `{fileName}` too. See
[the format arguments section](CATALOG-FORMAT.md#why-format-arguments-are-checked).

**There is no flag that overrides a refusal.** An error here means the interface
would visibly lose information, so the answer is to fix the message, not to force
the install.

### "remove a plural or select branch … accepted"

This is a warning, and it needs nothing from you. The message omits a branch the
application has, along with an argument used only by that branch. A language that
does not inflect writes the message that way, so it installs without a flag. The
count is recorded in the install marker and `verify` reports it back, so the
acceptance is visible rather than silent.

If you want to see exactly which messages and which arguments, run `lint`.

### Exit code 5 — bundle structure not recognised

The build does not have the layout this tool knows how to patch. Usually this
means the version string says one thing and the files say another, or the bundle
has already been modified.

Diagnose with:

```bash
./zh-patch check --app /path/to/Claude.app
```

### `target already exists`

```bash
./zh-patch rollback --target /Applications/Claude-3P-ZH.app
```

or pass a different `--target`. The tool will not overwrite a bundle, because the
existing one might be the only working copy you have.

### `the source bundle's signature does not verify`

The bundle you are patching is damaged or has been modified. Restore a clean copy
of the application. Do not patch a bundle that is already failing its own
integrity check.

---

## The copy will not start

### First: is it quarantined?

```bash
xattr -l /Applications/Claude-3P-ZH.app
```

If the output mentions `com.apple.quarantine`, the bundle has been downloaded,
archived, or copied through something that added the attribute. A copy *created
locally* by this tool does not have it.

The fix for a quarantined copy is to build it locally rather than transfer it.
**Do not** run `xattr -d`, `spctl --master-disable`, or disable Gatekeeper
globally. If a locally built copy is quarantined, that is worth reporting.

### Second: check the signature

```bash
codesign --verify --deep --strict --verbose=2 /Applications/Claude-3P-ZH.app
```

Expect `valid on disk` and `satisfies its Designated Requirement`. Anything else
means the copy is damaged; remove it and install again.

### Third: check it from a terminal

Launching from a terminal surfaces the error that the Finder only reports as
"the application cannot be opened":

```bash
/Applications/Claude-3P-ZH.app/Contents/MacOS/Claude
```

Note what it prints, then close it.

### Fourth: confirm the original still works

```bash
open -a /Applications/Claude.app
```

If the original also fails, the problem is not this tool.

---

## The interface is still in English

1. **Check the setting.** Settings → Language, and select Chinese (Simplified).
   The copy does not change your saved preference by itself.
2. **Confirm the catalog is actually installed.**

   ```bash
   ./zh-patch verify --target /Applications/Claude-3P-ZH.app
   ```

   Every locale file should read `ok`, and `catalog digest` should read
   `matches marker`.

3. **Confirm the picker was patched.**

   ```bash
   grep -c 'zh-Hans' /Applications/Claude-3P-ZH.app/Contents/Resources/ion-dist/assets/v1/c49da61a8-BM3hC-jO.js
   ```

   A count of zero means the rewrite did not take.

### The language entry is not in the picker at all

Stop here rather than editing configuration files. Forcing the value elsewhere
will not explain why the picker lacks the entry, and it hides the actual fault.

Collect:

```bash
./zh-patch verify --target /Applications/Claude-3P-ZH.app > report.txt 2>&1
./zh-patch version >> report.txt
sw_vers >> report.txt
uname -m >> report.txt
csrutil status >> report.txt
codesign -dv --verbose=4 /Applications/Claude-3P-ZH.app >> report.txt 2>&1
```

Then open an issue with that file attached. It contains no credentials and no
personal data, and it does not contain your translation resource.

### Some strings are English, some are Chinese

Expected to a degree. The catalog and the application are versioned separately,
so keys the catalog does not contain fall back to English. `check` reports the
coverage figure; a coverage below 100 % will show up as mixed-language text in
the places you did not cover.

If a *specific* control reads oddly — a sentence with a gap where a name should
be — that is a dropped format argument. See
[the format arguments section](CATALOG-FORMAT.md#why-format-arguments-are-checked).

---

## Sign-in fails, or the copy asks for credentials again

Expected, and explained in [`DISCLAIMER.md`](DISCLAIMER.md). The ad-hoc signature
cannot carry the team-scoped keychain access groups the original build has, so
the copy cannot reach the credentials stored under them. Treat the copy as a
separate application with respect to stored secrets.

---

## A feature does not work in the copy but works in the original

Some capabilities depend on the code signature. Record which feature, then check
whether it works in the original — if it fails in both, it is unrelated to this
tool.

Report it as a limitation rather than a bug unless you can show that the tool's
changes caused it. It is useful information either way, and the disclaimer lists
these as unverified precisely because nobody has gone through them.

---

## The gateway or switching tool stopped working

This tool does not read or write your gateway or switching configuration, and it
does not touch user data. If a setting appears to have been lost, confirm which
application you changed it in: the two copies share their user data but are
separate bundles, and it is easy to configure one while looking at the other.

Diagnose by switching back to the original:

```bash
osascript -e 'quit app "Claude"'
open -a /Applications/Claude.app
```

If the problem persists there, it is not caused by this tool.

---

## Rollback

```bash
./zh-patch rollback --target /Applications/Claude-3P-ZH.app
```

Refused with `no install marker`? Then the bundle is not this tool's output and
is deliberately left alone. Delete it yourself if you are certain of what it is.

The copy goes to the Trash, so nothing is destroyed. User data under
`~/Library/Application Support` is untouched and should not be deleted as part of
any rollback.

---

## Reporting a problem

Include:

- the output of `./zh-patch version`;
- the output of `./zh-patch check` and, if it got that far, `./zh-patch verify`;
- `sw_vers` and `uname -m`;
- `csrutil status` — the verification machine had SIP disabled, so this matters;
- what you expected and what happened.

Do **not** attach your language resource, a copy of the application, or anything
containing credentials or chat content. The report file described above is enough.
