# Install guide

Read [`DISCLAIMER.md`](DISCLAIMER.md) first. It is short, and it is the part
that tells you what you are agreeing to.

---

## Before you start

You need:

1. **An installable application version.** Check with `./zh-patch version`. Only
   the versions in [`COMPATIBILITY.md`](COMPATIBILITY.md) work. If yours is not
   listed, see [installing from a backup](#installing-from-a-backup).
2. **A language resource you prepared.** This project ships none — see
   [`CATALOG-FORMAT.md`](CATALOG-FORMAT.md). Without one, `apply` stops with exit
   code 4.
3. **A pristine source bundle.** If the bundle you are patching has already been
   patched, installation is refused. Keep a backup of the unmodified
   application before you start.

## Step 1 — Check, without writing anything

```bash
./zh-patch check --app /Applications/Claude.app --catalog-dir ~/my-catalog
```

Expected output names the version, the signing identity, the three files that
will be rewritten, the entitlements that will be removed and added, and the
coverage of your catalog.

Nothing is written. If a check fails, fix the cause before continuing — the tool
will refuse to install, and that refusal is the feature working.

Exit codes: `3` unsupported version, `4` language resource rejected, `5` bundle
structure not recognised.

## Step 2 — Install

```bash
./zh-patch apply --app /Applications/Claude.app --target /Applications/Claude-3P-ZH.app --catalog-dir ~/my-catalog
```

`--target` defaults to `/Applications/Claude-3P-ZH.app`. Writing there needs
administrator rights; `apply` will fail with a permission error rather than
silently writing elsewhere. Pick a location you can write to, or run it with
`sudo` if you understand what that implies.

The step by step:

1. The source bundle is copied. **It is not modified.**
2. Three JavaScript assets are rewritten, each at a site verified to occur
   exactly the expected number of times.
3. Your catalog is written into the copy's `i18n` directory, under both the
   `zh-Hans` and `zh-CN` names.
4. A marker file recording what was done is written into the copy.
5. The copy is re-signed ad-hoc, inside-out, with the restricted entitlements
   removed and `com.apple.security.cs.disable-library-validation` added.
6. The result is verified with `codesign --verify --deep --strict`.

If anything fails, the partially created copy is removed and the source is
untouched.

## Step 3 — Verify

```bash
./zh-patch verify --target /Applications/Claude-3P-ZH.app
```

This is a **static** check. It confirms the signature, that the marker is
present, that the catalog on disk matches the digest recorded at install time,
and that no restricted entitlement survived. It cannot confirm that the
application starts or that the interface renders in Chinese.

`gatekeeper rejected` in this output is expected — see
[What changes](../README.md#what-changes).

## Step 4 — Start the copy

Quit the original first. The two share a user data directory, and running both
at once risks conflicting writes.

```bash
osascript -e 'quit app "Claude"'
open -n -a /Applications/Claude-3P-ZH.app
```

`-n` opens a new instance even if the original is registered.

## Step 5 — Choose the language

If the interface does not already appear in Simplified Chinese, open
**Settings → Language** and select the entry for Chinese (Simplified).

If the entry is **not** in the list, stop. Do not edit configuration files by
hand to force it — that will not reveal why the picker is missing the locale, and
it obscures the actual fault. Collect the information described in
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) and report it.

## Step 6 — Going back

```bash
osascript -e 'quit app "Claude"'
open -a /Applications/Claude.app
```

That is all that is needed: the original was never modified. Only delete the
copy once you have confirmed the original runs normally.

```bash
./zh-patch rollback --target /Applications/Claude-3P-ZH.app
```

`rollback` moves the copy to the Trash, so it is reversible. It refuses to act
on any bundle that does not carry this tool's marker, so it cannot remove the
original application or your backup by mistake.

Your user data is at `~/Library/Application Support/Claude-3p` (or a
similarly-named directory) and is **not** managed by this tool. Do not delete it
as part of a rollback.

---

## Installing from a backup

If your installed application has been updated to a version that is not
installable, patch a copy of a supported build instead. Nothing about the target
changes; only the source does.

```bash
# 1. Keep a backup of the unmodified application while it is still a
#    supported version, before it updates itself:
cp -R /Applications/Claude.app /Applications/Claude-2.26454.0.app

# 2. Point the tool at the backup rather than at the live application:
./zh-patch check --app /Applications/Claude-2.26454.0.app --catalog-dir ~/my-catalog
./zh-patch apply --app /Applications/Claude-2.26454.0.app --catalog-dir ~/my-catalog
```

The backup must be a genuine copy of that version with an intact signature. Do
not edit a version string in `Info.plist` to make a build qualify — the structure
and digest checks will refuse it, which is the intended outcome.

Beware that the copy you produce is based on the older build. It will behave like
that version, not like the newer one you have installed.

---

## Installing the command instead

Installing the package is optional; `./zh-patch` works from a checkout and needs
nothing installed. If you would rather have a command on your `PATH`:

```bash
python3 -m pip install --user .
```

That provides `claude-zh-patch` with the same subcommands.

This path needs `pip` 22 or newer. The `pip` bundled with Apple's Command Line
Tools Python is 21.x, which misreads modern package metadata and produces a wheel
named `UNKNOWN-0.0.0`. Check with `python3 -m pip --version`; if it is old, use a
Homebrew Python (`brew install python`), or upgrade pip first:

```bash
python3 -m pip install --user --upgrade pip
```

If you would rather not deal with any of that, `./zh-patch` does the same job
with no installation at all.

---

## Uninstalling

```bash
./zh-patch rollback              # move the copy to the Trash
python3 -m pip uninstall claude-desktop-3p-zh-hans-patch
```

Then delete the directory you cloned. Your user data is untouched by all of it.
