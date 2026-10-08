import unittest
from pathlib import Path

import generator


class ProfileTextTest(unittest.TestCase):
    def test_returns_prose_body_unchanged(self):
        body = (
            "Hands-on technical contributor since 2007.\n\n"
            "Has worn many hats and works well with others"
        )
        notes = [(Path("profile.md"), {"type": "profile"}, f"\n{body}\n")]
        self.assertEqual(generator._profile_text(notes), body)

    def test_empty_body_exits(self):
        notes = [(Path("profile.md"), {"type": "profile"}, "\n\n")]
        with self.assertRaises(SystemExit) as raised:
            generator._profile_text(notes)
        self.assertEqual(raised.exception.code, "profile note has no body")


if __name__ == "__main__":
    unittest.main()
