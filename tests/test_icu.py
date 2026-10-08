"""Tests for the ICU MessageFormat validator."""

from __future__ import annotations

import unittest

from claude_zh_patch import icu


class ValidatePatternAcceptsTests(unittest.TestCase):
    def test_plain_text(self):
        for pattern in ("", "Sign in", "您好，世界", "issue #12"):
            with self.subTest(pattern=pattern):
                icu.validate_pattern(pattern)

    def test_simple_argument(self):
        icu.validate_pattern("Hello, {name}!")

    def test_plural(self):
        icu.validate_pattern("{count, plural, one {# item} other {# items}}")

    def test_select(self):
        icu.validate_pattern("{gender, select, male {他} female {她} other {TA}}")

    def test_selectordinal(self):
        icu.validate_pattern("{n, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}")

    def test_explicit_plural_value(self):
        icu.validate_pattern("{n, plural, =0 {none} =1 {one} other {#}}")

    def test_negative_explicit_value(self):
        icu.validate_pattern("{n, plural, =-1 {negative} other {#}}")

    def test_simple_types(self):
        for pattern in ("{n, number}", "{n, number, ::percent}", "{d, date}", "{d, date, medium}"):
            with self.subTest(pattern=pattern):
                icu.validate_pattern(pattern)

    def test_nested_select_around_plural(self):
        icu.validate_pattern("{g, select, other {{n, plural, other {# 项}}}}")

    def test_plural_around_plural(self):
        icu.validate_pattern("{a, plural, other {{b, plural, other {#}}}}")

    def test_quoted_braces_are_literal(self):
        icu.validate_pattern("Use '{'name'}' literally")

    def test_doubled_apostrophe_is_literal(self):
        icu.validate_pattern("it''s fine")

    def test_whitespace_inside_argument(self):
        icu.validate_pattern("{ count , plural , other {#} }")

    def test_apostrophe_without_following_brace_is_literal(self):
        icu.validate_pattern("{name}'s profile")

    def test_digit_and_dotted_argument_names(self):
        icu.validate_pattern("{0} {user.name} {a-b} {a_b}")


class ValidatePatternRejectsTests(unittest.TestCase):
    def assertRejects(self, pattern: str):
        with self.assertRaises(icu.ICUError, msg=f"expected rejection: {pattern!r}"):
            icu.validate_pattern(pattern)

    def test_unmatched_open(self):
        self.assertRejects("Hello {name")

    def test_unmatched_close(self):
        self.assertRejects("Hello name}")

    def test_empty_argument(self):
        self.assertRejects("{}")

    def test_unknown_type(self):
        self.assertRejects("{n, foo}")

    def test_plural_without_other(self):
        self.assertRejects("{n, plural, one {#}}")

    def test_select_without_other(self):
        self.assertRejects("{g, select, male {他}}")

    def test_plural_with_no_branches(self):
        self.assertRejects("{n, plural, }")

    def test_invalid_plural_keyword(self):
        self.assertRejects("{n, plural, singular {#} other {#}}")

    def test_invalid_explicit_value(self):
        self.assertRejects("{n, plural, =x {#} other {#}}")

    def test_unterminated_branch(self):
        self.assertRejects("{n, plural, other {#}")

    def test_missing_comma_after_name(self):
        self.assertRejects("{name plural, other {#}}")

    def test_missing_comma_after_type(self):
        self.assertRejects("{n, plural other {#}}")

    def test_missing_identifier(self):
        self.assertRejects("{, plural, other {#}}")

    def test_non_string(self):
        self.assertRejects(123)  # type: ignore[arg-type]


class ArgumentNamesTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(icu.argument_names("Hello, {name}!"), frozenset({"name"}))

    def test_plural_argument_is_counted_once(self):
        self.assertEqual(
            icu.argument_names("{count, plural, one {# item} other {# items}}"),
            frozenset({"count"}),
        )

    def test_hash_is_not_an_argument(self):
        self.assertNotIn("#", icu.argument_names("{count, plural, other {#}}"))

    def test_nested_arguments_are_collected(self):
        self.assertEqual(
            icu.argument_names("{a, select, other {{b, plural, other {#}}}}"),
            frozenset({"a", "b"}),
        )

    def test_plain_text_has_no_arguments(self):
        self.assertEqual(icu.argument_names("plain text"), frozenset())

    def test_quoted_braces_are_not_arguments(self):
        self.assertEqual(icu.argument_names("'{'literal'}'"), frozenset())

    def test_style_text_is_not_an_argument(self):
        self.assertEqual(icu.argument_names("{n, number, ::percent}"), frozenset({"n"}))


class ArgumentProfileTests(unittest.TestCase):
    """Conditional-branch classification, which stops a legitimate translation
    choice from being reported as a dropped placeholder."""

    def test_top_level_argument_is_unconditional(self):
        profile = icu.argument_profile("Hello, {name}!")
        self.assertEqual(profile.all, frozenset({"name"}))
        self.assertEqual(profile.conditional, frozenset())
        self.assertEqual(profile.unconditional, frozenset({"name"}))

    def test_branch_arguments_are_conditional(self):
        profile = icu.argument_profile("{n, plural, one {{name}} other {{names}}}")
        self.assertEqual(profile.all, frozenset({"n", "name", "names"}))
        self.assertEqual(profile.conditional, frozenset({"name", "names"}))
        self.assertEqual(profile.unconditional, frozenset({"n"}))

    def test_mixed_top_level_and_branch(self):
        # ``n`` selects the branch, so it is needed at the top level even though
        # it also appears as the argument of a plural.
        profile = icu.argument_profile("{count} of {n, plural, other {{total}}}")
        self.assertEqual(profile.unconditional, frozenset({"count", "n"}))
        self.assertEqual(profile.conditional, frozenset({"total"}))

    def test_the_selector_argument_stays_unconditional(self):
        profile = icu.argument_profile("{count, plural, one {{name}} other {{names}}}")
        self.assertEqual(profile.unconditional, frozenset({"count"}))
        self.assertEqual(profile.conditional, frozenset({"name", "names"}))

    def test_nested_branches_stay_conditional(self):
        profile = icu.argument_profile("{a, select, other {{b, plural, other {{c}}}}}")
        self.assertEqual(profile.conditional, frozenset({"b", "c"}))
        self.assertEqual(profile.unconditional, frozenset({"a"}))

    def test_select_branch_arguments_are_conditional(self):
        profile = icu.argument_profile("{g, select, male {{he}} other {{they}}}")
        self.assertEqual(profile.conditional, frozenset({"he", "they"}))

    def test_plain_text_has_no_arguments(self):
        profile = icu.argument_profile("nothing here")
        self.assertEqual(profile.all, frozenset())
        self.assertEqual(profile.conditional, frozenset())

    def test_argument_names_still_returns_every_argument(self):
        self.assertEqual(
            icu.argument_names("{a, select, other {{b}}}"), frozenset({"a", "b"})
        )

    def test_profile_reports_parse_failure_with_context(self):
        with self.assertRaises(icu.ICUError) as caught:
            icu.argument_profile("{", context="base[xyz]")
        self.assertIn("base[xyz]", str(caught.exception))


class BranchCollapseTests(unittest.TestCase):
    """The rule that decides whether a dropped argument is idiomatic or a defect.

    It is deliberately narrow: an argument is excused only when every place the
    application uses it sits under a branch the translation removed.
    """

    def collapsed(self, source: str, translation: str, name: str) -> bool:
        return icu.is_branch_collapse(
            icu.argument_profile(source), icu.argument_profile(translation), name
        )

    def test_removing_the_only_branch_that_used_it_excuses_it(self):
        self.assertTrue(
            self.collapsed(
                "{count, plural, one {{name}} other {{names}}}",
                "{count, plural, other {{names}}}",
                "name",
            )
        )

    def test_keeping_the_branch_does_not_excuse_it(self):
        self.assertFalse(
            self.collapsed(
                "{count, plural, other {# of {total}}}",
                "{count, plural, other {共 # 项}}",
                "total",
            )
        )

    def test_a_top_level_argument_is_never_excused(self):
        self.assertFalse(self.collapsed("Saved {fileName}", "已保存", "fileName"))

    def test_removing_the_whole_plural_excuses_its_branch_arguments(self):
        self.assertTrue(
            self.collapsed(
                "{count, plural, one {{name}} other {{names}}}",
                "静态文本",
                "name",
            )
        )

    def test_a_nested_collapse_reaches_deep_arguments(self):
        self.assertTrue(
            self.collapsed(
                "{a, select, other {{b, plural, one {{c}} other {{d}}}}}",
                "{a, select, other {{b, plural, other {{d}}}}}",
                "c",
            )
        )

    def test_an_outer_collapse_excuses_everything_beneath_it(self):
        self.assertTrue(
            self.collapsed(
                "{g, select, male {{he}} other {{they}}}",
                "{g, select, other {{they}}}",
                "he",
            )
        )

    def test_a_sibling_branch_being_removed_does_not_excuse_this_one(self):
        self.assertFalse(
            self.collapsed(
                "{g, select, male {{he} {topic}} other {{they} {topic}}}",
                "{g, select, male {{he} {topic}} other {{they}}}",
                "topic",
            )
        )

    def test_an_unknown_argument_is_not_excused(self):
        self.assertFalse(self.collapsed("plain text", "纯文本", "whatever"))


class ContextTests(unittest.TestCase):
    def test_context_is_included_in_the_message(self):
        with self.assertRaises(icu.ICUError) as caught:
            icu.validate_pattern("{", context="base[abc]")
        self.assertIn("base[abc]", str(caught.exception))

    def test_context_is_included_by_argument_names(self):
        with self.assertRaises(icu.ICUError) as caught:
            icu.argument_names("{", context="dynamic[xyz]")
        self.assertIn("dynamic[xyz]", str(caught.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
