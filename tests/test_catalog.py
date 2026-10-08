"""Tests for catalog loading, ICU validation wiring and coverage comparison."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from claude_zh_patch import catalog as catalog_mod
from claude_zh_patch.errors import CatalogError

from . import support


class LoadCatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_loads_a_well_formed_catalog(self):
        directory = support.build_catalog(self.root)
        loaded = catalog_mod.load_catalog(directory)
        self.assertEqual(loaded.locale, "zh-Hans")
        self.assertEqual(loaded.counts["base"], len(support.EN_BASE) - 2)
        self.assertEqual(loaded.counts["dynamic"], 2)
        self.assertEqual(loaded.license, "CC0-1.0 (test fixture)")

    def test_accepts_the_zh_cn_alias(self):
        directory = support.build_catalog(self.root, locale="zh-CN")
        self.assertEqual(catalog_mod.load_catalog(directory).locale, "zh-CN")

    def test_missing_directory(self):
        with self.assertRaises(CatalogError):
            catalog_mod.load_catalog(self.root / "absent")

    def test_missing_manifest(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(empty)
        self.assertIn("catalog.json", str(caught.exception))

    def test_unsupported_schema_version(self):
        directory = support.build_catalog(self.root, manifest_overrides={"schemaVersion": 99})
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("schemaVersion", str(caught.exception))

    def test_unsupported_locale(self):
        directory = support.build_catalog(self.root, manifest_overrides={"locale": "fr-FR"})
        with self.assertRaises(CatalogError):
            catalog_mod.load_catalog(directory)

    def test_files_must_be_an_object(self):
        directory = support.build_catalog(self.root, manifest_overrides={"files": ["base.json"]})
        with self.assertRaises(CatalogError):
            catalog_mod.load_catalog(directory)

    def test_base_entry_is_required(self):
        directory = support.build_catalog(self.root, manifest_overrides={"files": {}})
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("base", str(caught.exception))

    def test_referenced_file_must_exist(self):
        directory = support.build_catalog(self.root, write_base_file=False)
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("missing catalog file", str(caught.exception))

    def test_absolute_path_is_rejected(self):
        directory = support.build_catalog(
            self.root, manifest_overrides={"files": {"base": "/etc/passwd"}}
        )
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("relative", str(caught.exception))

    def test_parent_traversal_is_rejected(self):
        directory = support.build_catalog(
            self.root, manifest_overrides={"files": {"base": "../outside.json"}}
        )
        with self.assertRaises(CatalogError):
            catalog_mod.load_catalog(directory)

    def test_empty_base_is_rejected(self):
        directory = support.build_catalog(self.root, base={})
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("empty", str(caught.exception).lower())

    def test_non_string_value_is_rejected(self):
        directory = support.build_catalog(self.root, base={"greeting": 42})  # type: ignore[dict-item]
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("greeting", str(caught.exception.detail))

    def test_invalid_icu_is_rejected_and_the_key_named(self):
        directory = support.build_catalog(self.root, base={"greeting": "Hello, {name"})
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("greeting", str(caught.exception.detail))

    def test_missing_optional_sections_default_to_empty(self):
        directory = support.build_catalog(self.root, dynamic=None)
        loaded = catalog_mod.load_catalog(directory)
        self.assertEqual(loaded.sections["dynamic"], {})
        self.assertEqual(loaded.sections["overrides"], {})

    def test_manifest_is_not_a_json_object(self):
        directory = self.root / "listy"
        directory.mkdir()
        (directory / "catalog.json").write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(CatalogError):
            catalog_mod.load_catalog(directory)

    def test_malformed_json_is_reported_with_the_path(self):
        directory = self.root / "broken"
        directory.mkdir()
        (directory / "catalog.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(CatalogError) as caught:
            catalog_mod.load_catalog(directory)
        self.assertIn("catalog.json", str(caught.exception))


class CompareWithApplicationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _english(self):
        return {"base": dict(support.EN_BASE), "dynamic": dict(support.EN_DYNAMIC), "overrides": {}}

    def test_counts_coverage_and_unused_keys(self):
        directory = support.build_catalog(self.root)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, self._english())
        self.assertEqual(report.totals["base"], len(support.EN_BASE))
        self.assertEqual(report.covered["base"], len(support.EN_BASE) - 2)
        self.assertAlmostEqual(report.base_ratio, (len(support.EN_BASE) - 2) / len(support.EN_BASE))
        self.assertEqual(report.unused_keys, 0)

    def test_detects_a_dropped_format_argument(self):
        base = catalog_base()
        base["greeting"] = "您好！"  # {name} was dropped
        directory = support.build_catalog(self.root, base=base)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, self._english())
        self.assertEqual(len(report.placeholder_mismatches), 1)
        found = report.placeholder_mismatches[0]
        self.assertEqual(found.section, "base")
        self.assertEqual(found.key, "greeting")
        self.assertEqual(found.source, ("name",))
        self.assertEqual(found.supplied, ())
        self.assertEqual(found.missing, ("name",))
        self.assertEqual(found.extra, ())
        self.assertIn("drops a format argument", found.reason)

    def test_detects_an_invented_format_argument(self):
        # "Sign in" has no arguments at all, so any argument is an addition.
        base = catalog_base()
        base["signIn"] = "登录 {extra}"
        directory = support.build_catalog(self.root, base=base)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, self._english())
        self.assertEqual(len(report.placeholder_mismatches), 1)
        found = report.placeholder_mismatches[0]
        self.assertEqual(found.key, "signIn")
        self.assertEqual(found.source, ())
        self.assertEqual(found.supplied, ("extra",))
        self.assertEqual(found.extra, ("extra",))
        self.assertEqual(found.missing, ())
        self.assertIn("uses a format argument", found.reason)
        self.assertTrue(found.is_defect)

    def test_detects_a_rename_that_neither_adds_nor_removes(self):
        base = catalog_base()
        base["saved"] = "已保存 {other}"
        directory = support.build_catalog(self.root, base=base)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, self._english())
        found = report.placeholder_mismatches[0]
        self.assertEqual(found.key, "saved")
        self.assertEqual(found.missing, ("fileName",))
        self.assertEqual(found.extra, ("other",))
        self.assertTrue(found.is_defect)
        # An argument the application does not supply throws at render time, so the
        # rename is refused rather than treated as a collapse.
        self.assertIn("does not provide", found.reason)

    def test_the_report_never_contains_the_message_text(self):
        base = catalog_base()
        base["greeting"] = "您好！"
        directory = support.build_catalog(self.root, base=base)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, self._english())
        rendered = report.placeholder_mismatches[0].render()
        self.assertNotIn("Hello", rendered)
        self.assertNotIn("您好", rendered)
        self.assertIn("{name}", rendered)

    def test_a_removed_branch_excuses_its_own_argument(self):
        # The application selects {name}/{names} by count. Keeping only the plural
        # branch is how a language that does not inflect writes this, so the
        # argument that branch used is excused rather than reported as a defect.
        english = {
            "base": {"k": "{count, plural, one {{name}} other {{names}}}"},
            "dynamic": {},
            "overrides": {},
        }
        directory = support.build_catalog(
            self.root, base={"k": "{count, plural, other {{names}}}"}, dynamic=None
        )
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, english)

        self.assertEqual(len(report.defects), 0)
        self.assertEqual(len(report.branch_collapses), 1)
        found = report.branch_collapses[0]
        self.assertEqual(found.missing, ("name",))
        self.assertEqual(found.excused, ("name",))
        self.assertFalse(found.is_defect)
        self.assertIn("branch the translation removed", found.note)
        self.assertIn("accepted automatically", found.note)

    def test_an_argument_dropped_from_a_kept_branch_is_a_defect(self):
        # The plural survives; only its contents changed. Nothing was collapsed,
        # so losing {total} leaves a hole and must be reported.
        english = {
            "base": {"k": "{count, plural, other {# of {total}}}"},
            "dynamic": {},
            "overrides": {},
        }
        directory = support.build_catalog(
            self.root, base={"k": "{count, plural, other {共 # 项}}"}, dynamic=None
        )
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, english)

        self.assertEqual(report.branch_collapses, ())
        found = report.defects[0]
        self.assertEqual(found.required_missing, ("total",))
        self.assertEqual(found.excused, ())
        self.assertIn("drops a format argument", found.reason)

    def test_a_nested_collapse_excuses_a_deeply_nested_argument(self):
        english = {
            "base": {"k": "{a, select, other {{b, plural, one {{c}} other {{d}}}}}"},
            "dynamic": {},
            "overrides": {},
        }
        directory = support.build_catalog(
            self.root, base={"k": "{a, select, other {{b, plural, other {{d}}}}}"}, dynamic=None
        )
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, english)

        self.assertEqual(report.defects, ())
        self.assertEqual(report.branch_collapses[0].excused, ("c",))

    def test_a_top_level_argument_is_never_excused(self):
        english = {"base": {"k": "Saved {fileName}"}, "dynamic": {}, "overrides": {}}
        directory = support.build_catalog(self.root, base={"k": "已保存"}, dynamic=None)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, english)

        found = report.defects[0]
        self.assertEqual(found.excused, ())
        self.assertEqual(found.required_missing, ("fileName",))
        self.assertIn("drops a format argument", found.reason)

    def test_losing_the_whole_plural_still_blocks_on_its_selector(self):
        english = {
            "base": {"k": "{count, plural, one {{name}} other {{names}}}"},
            "dynamic": {},
            "overrides": {},
        }
        directory = support.build_catalog(self.root, base={"k": "静态文本"}, dynamic=None)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, english)

        # {name} and {names} went with the branches, but {count} is rendered
        # outside them, so the message cannot be installed.
        found = report.defects[0]
        self.assertIn("count", found.required_missing)
        self.assertIn("name", found.excused)

    def test_a_partly_excused_difference_names_both_kinds(self):
        english = {
            "base": {"k": "{top} {n, plural, other {{inner}}}"},
            "dynamic": {},
            "overrides": {},
        }
        directory = support.build_catalog(self.root, base={"k": "文本"}, dynamic=None)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, english)

        found = report.defects[0]
        self.assertIn("top", found.required_missing)
        self.assertIn("n", found.required_missing)
        self.assertIn("inner", found.excused)
        self.assertIn("explained by a removed branch", found.note)

    def test_unused_keys_are_counted(self):
        base = catalog_base()
        base["no.such.key"] = "无用"
        directory = support.build_catalog(self.root, base=base)
        loaded = catalog_mod.load_catalog(directory)
        report = catalog_mod.compare_with_application(loaded, self._english())
        self.assertEqual(report.unused_keys, 1)

    def test_coverage_line_lists_each_section(self):
        directory = support.build_catalog(self.root)
        loaded = catalog_mod.load_catalog(directory)
        line = catalog_mod.compare_with_application(loaded, self._english()).line()
        self.assertIn("base:", line)
        self.assertIn("dynamic:", line)


class FindingsTests(unittest.TestCase):
    def _report(self, mismatches=(), covered=8, total=10):
        return catalog_mod.CoverageReport(
            totals={"base": total, "dynamic": 2, "overrides": 0},
            covered={"base": covered, "dynamic": 2, "overrides": 0},
            unused_keys=0,
            placeholder_mismatches=tuple(mismatches),
        )

    def test_a_visible_difference_blocks(self):
        errors, warnings = catalog_mod.findings_for(self._report([a_mismatch()]), 0.7)
        self.assertTrue(errors)
        self.assertFalse(warnings)
        self.assertIn("rejected", errors[0])

    def test_the_blocking_message_names_the_key_and_both_argument_sets(self):
        errors, _ = catalog_mod.findings_for(self._report([a_mismatch()]), 0.7)
        rendered = "\n".join(errors)
        self.assertIn("base[k]", rendered)
        self.assertIn("{a}", rendered)
        self.assertIn("(none)", rendered)
        self.assertIn("drops a format argument", rendered)

    def test_a_branch_collapse_does_not_block(self):
        """A language choosing not to inflect must install without a flag."""
        collapse = a_mismatch(source=("count", "name"), supplied=("count",), excused=("name",))
        errors, warnings = catalog_mod.findings_for(self._report([collapse]), 0.7)
        self.assertEqual(errors, [])
        self.assertTrue(any("branch" in line for line in warnings))
        self.assertIn("base[k]", warnings[0])

    def test_a_collapse_is_reported_rather_than_hidden(self):
        collapse = a_mismatch(source=("count", "name"), supplied=("count",), excused=("name",))
        _, warnings = catalog_mod.findings_for(self._report([collapse]), 0.7)
        self.assertIn("accepted", warnings[0])

    def test_a_partly_excused_difference_still_blocks(self):
        """Dropping one argument because a branch went does not excuse another."""
        mixed = a_mismatch(
            source=("count", "name", "total"),
            supplied=("count",),
            excused=("name",),
        )
        errors, _ = catalog_mod.findings_for(self._report([mixed]), 0.7)
        self.assertTrue(errors)
        self.assertIn("{total}", "\n".join(errors))

    def test_an_invented_argument_always_blocks_even_if_something_is_excused(self):
        mixed = a_mismatch(source=("a", "b"), supplied=("b", "c"), excused=("a",))
        errors, _ = catalog_mod.findings_for(self._report([mixed]), 0.7)
        self.assertTrue(errors)

    def test_low_coverage_blocks(self):
        errors, _ = catalog_mod.findings_for(self._report(covered=3, total=10), 0.7)
        self.assertTrue(any("coverage" in line for line in errors))

    def test_coverage_at_the_threshold_passes(self):
        errors, _ = catalog_mod.findings_for(self._report(covered=7, total=10), 0.7)
        self.assertFalse(errors)

    def test_unused_keys_warn(self):
        report = catalog_mod.CoverageReport(
            totals={"base": 10}, covered={"base": 8}, unused_keys=5, placeholder_mismatches=()
        )
        errors, warnings = catalog_mod.findings_for(report, 0.7)
        self.assertFalse(errors)
        self.assertTrue(any("do not exist" in line for line in warnings))


class NestedStructureTests(unittest.TestCase):
    """Format-argument comparison must understand structure, not match strings.

    Every pattern here is a shape the application's own formatter renders. A
    comparison based on substring matching would misjudge several of them, in both
    directions, which is why the check parses both messages.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def compare(self, source: str, supplied: str) -> catalog_mod.CoverageReport:
        english = {"base": {"k": source}, "dynamic": {}, "overrides": {}}
        directory = support.build_catalog(self.root, base={"k": supplied}, dynamic=None)
        loaded = catalog_mod.load_catalog(directory)
        return catalog_mod.compare_with_application(loaded, english)

    def assertAccepts(self, source: str, supplied: str):
        report = self.compare(source, supplied)
        self.assertEqual(
            report.placeholder_mismatches,
            (),
            "should not have been flagged:\n"
            + "\n".join(m.render() for m in report.placeholder_mismatches),
        )

    def assertRejects(self, source: str, supplied: str) -> catalog_mod.PlaceholderMismatch:
        report = self.compare(source, supplied)
        self.assertTrue(report.placeholder_mismatches, "should have been flagged")
        return report.placeholder_mismatches[0]

    # --- structures that must be accepted -----------------------------------

    def test_nested_plural_inside_select_with_the_same_argument(self):
        self.assertAccepts(
            "{g, select, other {{n, plural, other {#}}}}",
            "{g, select, other {{n, plural, other {共 # 项}}}}",
        )

    def test_reordered_plural_branches(self):
        self.assertAccepts(
            "{n, plural, one {#} other {#}}",
            "{n, plural, other {#} one {#}}",
        )

    def test_translation_may_add_a_plural_keyword_branch(self):
        self.assertAccepts(
            "{n, plural, other {#}}",
            "{n, plural, zero {无} other {#}}",
        )

    def test_translation_may_add_an_explicit_value_branch(self):
        self.assertAccepts(
            "{n, plural, other {#}}",
            "{n, plural, =0 {无} other {#}}",
        )

    def test_hash_introduced_by_the_translation_is_not_an_argument(self):
        self.assertAccepts(
            "{n, plural, other {things}}",
            "{n, plural, other {共 # 项}}",
        )

    def test_style_suffix_differences_do_not_matter(self):
        self.assertAccepts("{n, number}", "{n, number, ::percent}")

    def test_select_branches_may_be_relabelled(self):
        self.assertAccepts(
            "{g, select, male {他} other {TA}}",
            "{g, select, male {他} female {她} other {TA}}",
        )

    def test_quoted_braces_are_not_arguments_in_either_message(self):
        self.assertAccepts("'{'literal'}'", "'{'完全不同'}'")

    def test_apostrophe_is_literal(self):
        self.assertAccepts("{name}'s profile", "这是 {name} 的资料")

    def test_three_levels_of_nesting(self):
        self.assertAccepts(
            "{a, select, other {{b, plural, other {{c}}}}}",
            "{a, select, other {{b, plural, other {{c} 项}}}}",
        )

    # --- structures that must be rejected -----------------------------------

    def test_nested_argument_dropped(self):
        found = self.assertRejects(
            "{g, select, other {{n, plural, other {#}}}}",
            "{g, select, other {已选择}}",
        )
        self.assertEqual(found.missing, ("n",))
        self.assertEqual(found.source, ("g", "n"))

    def test_plural_flattened_to_plain_text(self):
        found = self.assertRejects(
            "{count, plural, other {# items}}",
            "若干项目",
        )
        self.assertEqual(found.missing, ("count",))
        self.assertEqual(found.supplied, ())

    def test_argument_added_inside_a_branch(self):
        found = self.assertRejects("{a, select, other {x}}", "{a, select, other {{b}}}")
        self.assertEqual(found.extra, ("b",))

    def test_argument_dropped_but_hash_kept(self):
        found = self.assertRejects(
            "{n, plural, other {# of {total}}}",
            "{n, plural, other {共 # 项}}",
        )
        self.assertEqual(found.missing, ("total",))
        self.assertEqual(found.source, ("n", "total"))

    def test_outer_argument_dropped_from_a_nested_structure(self):
        found = self.assertRejects(
            "{g, select, other {{n, plural, other {#}}}}",
            "{n, plural, other {#}}",
        )
        self.assertEqual(found.missing, ("g",))

    def test_three_levels_with_a_deep_argument_dropped(self):
        found = self.assertRejects(
            "{a, select, other {{b, plural, other {{c}}}}}",
            "{a, select, other {{b, plural, other {项}}}}",
        )
        self.assertEqual(found.missing, ("c",))


def a_mismatch(key: str = "k", source=("a",), supplied=(), excused=()):
    """A placeholder difference for tests that do not need a real catalog."""
    return catalog_mod.PlaceholderMismatch(
        section="base",
        key=key,
        source=tuple(source),
        supplied=tuple(supplied),
        excused=tuple(excused),
    )


def catalog_base():
    """The synthetic catalog base with a low-coverage-safe key set."""
    return {
        "greeting": "您好，{name}！",
        "itemCount": "{count, plural, other {# 项}}",
        "signIn": "登录",
        "signOut": "退出登录",
        "saved": "已保存 {fileName}",
        "deleted": "已删除 1 个{noun}",
        "retry": "重试",
        "settings": "设置",
    }


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
