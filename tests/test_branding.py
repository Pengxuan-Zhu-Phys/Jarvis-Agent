import unittest
from pathlib import Path

from jarvis_agent.branding import (
    FALLBACK_LOGO_PATTERN,
    LOGO_DOT_PREFIX,
    JarvisBranding,
    _strip_logo_dot_prefix,
    load_jarvis_branding,
)


class BrandingTests(unittest.TestCase):
    def test_load_branding_has_8x8_logo(self) -> None:
        branding = load_jarvis_branding(Path("/tmp/not-a-jarvis-project"), command="definitely-not-jarvis")

        self.assertEqual(branding.logo_pattern, FALLBACK_LOGO_PATTERN)
        self.assertEqual(len(branding.logo_pattern), 8)
        self.assertTrue(all(len(row) == 8 for row in branding.logo_pattern))

    def test_logo_widths_match_jarvis_template(self) -> None:
        branding = load_jarvis_branding(Path("/tmp/not-a-jarvis-project"), command="definitely-not-jarvis")

        self.assertEqual(branding.logo_widths("left"), (1, 2, 3, 2, 1, 4, 2, 1))
        self.assertEqual(branding.logo_widths("right"), (0, 1, 1, 2, 1, 4, 2, 1))

    def test_strip_logo_dot_prefix_preserves_banner_indentation(self) -> None:
        line = LOGO_DOT_PREFIX + "              ██╗ █████╗"

        stripped = _strip_logo_dot_prefix(line)

        self.assertEqual(stripped, "            ██╗ █████╗")

    def test_compact_version_lines_drop_resources(self) -> None:
        branding = JarvisBranding(
            logo_pattern=FALLBACK_LOGO_PATTERN,
            banner_lines=(),
            version_lines=(
                "JARVIS",
                "Author: Pengxuan Zhu, Erdong Guo.  Version:  1.7.4",
                "Resources:",
                "  Online docs: https://example.invalid",
            ),
            source="test",
        )

        self.assertEqual(
            branding.compact_version_lines(),
            ("JARVIS", "Author: Pengxuan Zhu, Erdong Guo.  Version:  1.7.4"),
        )
