"""Guard the Homebrew route.

The formula installs the package with `--no-deps` and takes every dependency from
`packaging/homebrew/requirements.txt`. That is what makes `brew install` fast
(wheels, not a MuPDF build), and also what makes it silently incomplete if the
lock falls behind `pyproject.toml`: an extra missing from the lock is an extra
that is simply not there, on a route where a keg cannot gain it afterwards.

So these tests are less about the Ruby than about that coupling — the exact
failure that retired the 0.3.0 tap, which shipped without `[mcp]`.
"""

import os
import re
import sys
import unittest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import gen_homebrew_formula as gen  # noqa: E402


def _read(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class TestFormula(unittest.TestCase):
    def test_formula_is_exactly_what_the_generator_produces(self):
        """Reuses the generator's own --check, so the rule lives in one place: the
        committed formula is generated output for the version and hash it declares,
        never a hand edit."""
        self.assertEqual(gen.check(), [])

    def test_desc_follows_homebrews_rules(self):
        self.assertLessEqual(len(gen.DESC), 80)
        self.assertTrue(gen.DESC.isascii(), "brew style rejects non-ASCII in desc")
        self.assertNotRegex(gen.DESC, r"^(?:An?\s|zotero-agent)")

    def test_python_pin_satisfies_requires_python(self):
        floor = re.search(r'^requires-python = ">=(\d+)\.(\d+)"$', _read("pyproject.toml"), re.M)
        self.assertLessEqual(tuple(int(p) for p in floor.groups()),
                             tuple(int(p) for p in gen.PYTHON_PIN.split(".")))

    def test_formula_and_lock_name_the_same_interpreter(self):
        formula = _read(os.path.join("packaging", "homebrew", "zotero-agent.rb"))
        self.assertIn('depends_on "python@%s"' % gen.PYTHON_PIN, formula)
        self.assertIn('virtualenv_create(libexec, "python%s")' % gen.PYTHON_PIN, formula)


class TestLock(unittest.TestCase):
    def test_lock_pins_everything_the_package_ships(self):
        """The guard the 0.3.0 tap lacked. Runs the generator's own refusal, so
        release time and test time cannot disagree about what "complete" means."""
        self.assertEqual(gen.guard_lock(), [])
        self.assertIn("mcp", gen.shipping_extras())   # the flagship path, not just any extra

    def test_lock_was_resolved_for_the_pinned_python_and_extras(self):
        """uv records its own command in the header, which is what ties the locked
        wheels to the interpreter the formula depends on."""
        header = _read(gen.LOCK_REL).split("\n\n")[0]
        self.assertIn("--python-version %s" % gen.PYTHON_PIN, header)
        self.assertIn("--generate-hashes", header)
        for extra in gen.shipping_extras():
            self.assertIn("--extra %s" % extra, header)

    def test_build_only_extras_stay_out(self):
        """`dev` is for contributors; it has no business in a user's keg."""
        self.assertNotIn("ruff", {name.lower() for name in gen.lock_pins()})

    def test_every_pin_carries_hashes(self):
        """The formula installs with --require-hashes: one unhashed pin fails the
        whole install."""
        lock = _read(gen.LOCK_REL)
        pins = re.findall(r"^[A-Za-z0-9._-]+==", lock, re.M)
        self.assertGreater(len(pins), 0)
        self.assertGreaterEqual(len(re.findall(r"--hash=sha256:", lock)), len(pins))

    def test_formula_embeds_the_whole_lock(self):
        """The formula carries the lock inline, so it installs the same wheels for
        any published version — including ones released before the lock existed."""
        formula = _read(os.path.join("packaging", "homebrew", "zotero-agent.rb"))
        lock = _read(gen.LOCK_REL)
        self.assertIn("--require-hashes", formula)
        for name, version in gen.lock_pins().items():
            self.assertIn("%s==%s" % (name, version), formula)
        self.assertEqual(len(re.findall(r"--hash=sha256:", formula)),
                         len(re.findall(r"--hash=sha256:", lock)))

    def test_embedded_lock_survives_ruby_quoting(self):
        """A plain heredoc would eat the `\\` line continuations pip needs, so the
        formula has to use the single-quoted form."""
        formula = _read(os.path.join("packaging", "homebrew", "zotero-agent.rb"))
        self.assertIn("<<~'REQS'", formula)


if __name__ == "__main__":
    unittest.main()
