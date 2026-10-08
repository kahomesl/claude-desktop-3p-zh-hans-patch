# Disclaimer

Read this before relying on anything in this repository.

## Not an official project

This is an independent, unofficial community tool. It is **not produced,
endorsed, sponsored, or affiliated with Anthropic PBC**, with Claude, with Claude
Desktop, or with any provider of third-party model routing or switching software.

"Claude" and "Anthropic" are trademarks of Anthropic PBC. They appear in this
project only to state which application the tool operates on. Their use does not
imply any endorsement, and grants no rights.

## No third-party material is distributed

This repository contains no Anthropic application, no Anthropic source code, no
modified application assets, no extracted translation catalog, and no
provisioning profile or signing material.

It ships no language resource at all. Producing one is a prerequisite of use and
is entirely your responsibility — including having the right to use whatever text
you put in it. Nothing in this project grants you any such right, and specifying
a licence in your own catalog manifest records a claim rather than creating one.

## What modifying an application entails

Installing produces a **separate copy** with a modified interface. The original
application is left untouched. The copy is, however, a substantially different
artifact:

- **The signature is replaced.** The copy is ad-hoc signed, not Developer ID
  signed, and not notarised. It no longer carries the identity of its original
  publisher.

- **Gatekeeper reports it as rejected.** `spctl` assessment of the copy fails.
  A copy created locally by this tool is not quarantined, which is why it can
  start. A copy that has been archived, uploaded, or otherwise transferred will
  pick up a quarantine attribute and will be blocked at launch.

- **Keychain access changes.** The original build's team-scoped
  `keychain-access-groups` entitlement cannot be carried by an ad-hoc signature
  and is removed. Credentials the original application stored under those groups
  are not reachable by the copy. Expect to authenticate again, and expect the two
  to behave as separate applications with respect to stored secrets.

- **Native features may break.** Any capability that depends on the code
  signature — certain permissions, helpers, system integrations, and anything
  that validates the calling application — may behave differently or not at all.

- **The two copies share user data.** They read and write the same directory
  under `~/Library/Application Support`. Running both at once risks conflicting
  writes. Quit one before starting the other.

## Do not weaken your system to work around this

Do not disable **System Integrity Protection**, and do not turn off **Gatekeeper**
globally, in order to make the copy run. Those are system-wide reductions in
security undertaken for one application's convenience, and they expose everything
else on the machine.

If a copy created by this tool will not start, that is a bug worth reporting —
see [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## Scope of verification, and its absence

The tool has been verified on **one** configuration:

> macOS 26.5.2 (25F84), Apple Silicon (arm64), Claude Desktop 2.26454.0,
> **System Integrity Protection disabled** on the verification machine,
> and a copy created locally so that it carried no quarantine attribute.

On that machine the interface renders in Simplified Chinese, the language picker
offers the locale, a conversation through a third-party gateway completed, and
the locale survived a restart.

**Everything else is unverified.** In particular, none of the following has been
tested:

- SIP enabled, which is the default on essentially every Mac;
- Intel Macs;
- any macOS release other than the one above;
- any application version other than the one above;
- Keychain behaviour, sign-in flows, or credential storage;
- native integrations of any kind;
- compliance with any particular gateway, proxy, or switching tool;
- whether the result is acceptable to any service's terms.

Passing the checks in this repository is **not a guarantee** that the result will
work, render correctly, or remain working after the application updates.

## Maintenance

An update to the application can invalidate this tool's assumptions at any time.
The installer detects that and refuses rather than proceeding. Support for a new
version arrives only when someone completes the verification procedure in
[`COMPATIBILITY.md`](COMPATIBILITY.md), and absence of support for your version is
the expected state rather than a bug.

## No warranty

The software is provided "as is", without warranty of any kind, as set out in the
[Apache License 2.0](../LICENSE), sections 7 and 8. You use it at your own risk,
and you are responsible for the consequences, including any effect on your
installation, your data, your credentials, or your account standing.
