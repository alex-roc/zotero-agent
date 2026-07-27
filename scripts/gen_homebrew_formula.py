#!/usr/bin/env python3
"""Regenerate the Homebrew formula — the only file the tap carries.

The formula is a *mirror* of the PyPI sdist, never a second build: `url` +
`sha256` name the exact artifact a release published, so nobody edits a hash by
hand — the 0.3.0 tap died of exactly that (plus shipping without the `[mcp]`
extra, which the embedded lock now makes impossible).

`packaging/homebrew/requirements.txt` is inlined into the formula rather than
read out of the unpacked sdist. That was the first design, and the tap's CI killed
it on its first run: a formula could then only install versions whose sdist
already carried the lock, so it could not be tested against anything already
published. Embedding also means `--check` fails if the lock moves without the
formula being regenerated.

The `sha256` has to come from the artifact CI actually uploads: hatchling sdists
are not byte-identical across machines, so it cannot be precomputed while
preparing a release. Hence `--sdist`, run by `.github/workflows/release.yml`
right after the PyPI publish, in the same step that bumps `updates.json`.

    python scripts/gen_homebrew_formula.py --sdist dist/zotero_agent-0.5.0.tar.gz
    python scripts/gen_homebrew_formula.py --from-pypi --version 0.5.0
    python scripts/gen_homebrew_formula.py --check     # verify without writing
    python scripts/gen_homebrew_formula.py --relock              # after a pyproject change
    python scripts/gen_homebrew_formula.py --relock --upgrade    # take newer extras
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from zotero_agent import __version__  # noqa: E402

OUT = os.path.join(_ROOT, "packaging", "homebrew", "zotero-agent.rb")
LOCK_REL = "packaging/homebrew/requirements.txt"
LOCK = os.path.join(_ROOT, LOCK_REL)
HOMEPAGE = "https://github.com/alex-roc/zotero-agent"

# Homebrew's current default python. The lock is resolved for this exact version
# (`--python-version`), so the two move together: bump this, regenerate the lock,
# and CI checks they still agree.
PYTHON_PIN = "3.14"

# Homebrew's own `desc` rules: no leading article, must not repeat the formula
# name, 80 characters max. pyproject's description is longer than that, so this
# is a deliberate short form rather than a copy.
DESC = "Local read-write control of a Zotero library, from your terminal or AI agent"

# A build-time extra: it never reaches a user, so the lock ignores it. Everything
# else in [project.optional-dependencies] must be in there, because a keg is
# replaced wholesale on every upgrade — whatever a user pip-installs into it
# afterwards disappears silently, so there is no "add the extra later" here.
BUILD_ONLY_EXTRAS = ("dev",)


def _pyproject():
    with open(os.path.join(_ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        return fh.read()


def _distribution_names(deps):
    """`["mcp>=1.2.0"]` -> `["mcp"]` — a requirement's project name, lowercased."""
    return [re.match(r"[A-Za-z0-9._-]+", d).group(0).lower() for d in deps]


def shipping_extras():
    """{extra: [distribution names]} for the extras a user can actually install."""
    block = re.search(r"\[project\.optional-dependencies\]\n(.*?)(?=\n\[|\Z)",
                      _pyproject(), re.S).group(1)
    return {extra: _distribution_names(re.findall(r'"([^"]+)"', deps))
            for extra, deps in re.findall(r"^([a-z]+) = \[(.*?)\]", block, re.M | re.S)
            if extra not in BUILD_ONLY_EXTRAS}


def core_dependencies():
    """The package's own runtime dependencies — empty today, on purpose. The
    formula installs the project with --no-deps, so these have to be in the lock
    too, or they would be missing at runtime."""
    core = re.search(r"^dependencies = \[(.*?)\]", _pyproject(), re.M | re.S).group(1)
    return _distribution_names(re.findall(r'"([^"]+)"', core))


def lock_command(upgrade=False):
    """The one place the lock's resolution is defined: same extras the package
    offers, resolved for the interpreter the formula depends on."""
    cmd = ["uv", "pip", "compile", "pyproject.toml"]
    for extra in sorted(shipping_extras()):
        cmd += ["--extra", extra]
    # --quiet keeps uv from echoing the whole lock to stdout as well.
    cmd += ["--universal", "--generate-hashes", "--python-version", PYTHON_PIN,
            "--quiet", "-o", os.path.relpath(LOCK, _ROOT)]
    if upgrade:
        cmd.append("--upgrade")
    return cmd


def sdist_url(version, blake2b):
    """PyPI's real download path: packages/<b2[:2]>/<b2[2:4]>/<b2[4:]>/<file>, where
    b2 is the file's blake2b-256 digest.

    Not the friendlier `/packages/source/z/zotero-agent/…` form, which 302s to this
    one but **404s for a freshly published release** — the tap's macOS job caught it
    minutes after 0.5.0 went out. Deriving the path from the artifact's own digest
    needs no API call, cannot lag a CDN, and is valid the instant the file exists.
    """
    return ("https://files.pythonhosted.org/packages/%s/%s/%s/zotero_agent-%s.tar.gz"
            % (blake2b[:2], blake2b[2:4], blake2b[4:], version))


def pypi_sdist(version, attempts=6):
    """(url, sha256) for a published version, straight from PyPI. Only needed when
    regenerating without the artifact at hand; the release path stays offline."""
    import time
    import urllib.error
    import urllib.request
    api = "https://pypi.org/pypi/zotero-agent/%s/json" % version
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(api, timeout=30) as fh:
                files = json.load(fh)["urls"]
            for f in files:
                if f["packagetype"] == "sdist":
                    return f["url"], f["digests"]["sha256"]
            raise RuntimeError("%s has no sdist on PyPI" % version)
        except urllib.error.HTTPError as e:
            if e.code != 404 or attempt == attempts - 1:
                raise
            time.sleep(5)   # just-published releases can take a moment to appear
    raise RuntimeError("PyPI never served %s" % version)


def project_license():
    """Read the licence from pyproject, so a relicensing cannot leave the formula
    claiming the old one (the retired tap still said MIT after the AGPL move)."""
    with open(os.path.join(_ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        return re.search(r'^license = "(.+)"$', fh.read(), re.M).group(1)


def lock_pins():
    """version pins declared in the lock, as {name: version}."""
    with open(LOCK, encoding="utf-8") as fh:
        return dict(re.findall(r"^([A-Za-z0-9._-]+)==([^\s;\\]+)", fh.read(), re.M))


def embedded_lock(indent):
    """The lock, verbatim, indented for a Ruby squiggly heredoc.

    Inlined rather than read out of the unpacked sdist, which is what the first
    cut did: that made the formula only installable for versions whose sdist
    already carried the lock, so it could not be tested against anything already
    on PyPI — the tap's own CI caught it on the first run.
    """
    with open(LOCK, encoding="utf-8") as fh:
        lines = fh.read().rstrip("\n").split("\n")
    return "\n".join(indent + line if line else "" for line in lines)


def render(version, sha256, url):
    return '''\
# Generated by scripts/gen_homebrew_formula.py — do not edit by hand.
#
# A mirror of the PyPI sdist: url/sha256 name the artifact release.yml published.
# The dependency lock is embedded below, so the formula is self-contained and
# installs wheels; Homebrew would otherwise build from source
# (`--no-binary=:all:`), which for this dependency set means compiling MuPDF plus
# three Rust extensions — 20+ minutes per user, per release.
class ZoteroAgent < Formula
  include Language::Python::Virtualenv

  desc "%(desc)s"
  homepage "%(homepage)s"
  url "%(url)s"
  sha256 "%(sha256)s"
  license "%(license)s"

  depends_on "python@%(python)s"

  def install
    venv = virtualenv_create(libexec, "python%(python)s")

    # The extras, as wheels. `zot mcp` and `zot toc` have to work on a plain
    # `brew install`: a keg cannot gain them later, since every upgrade replaces
    # it. Generated from %(lock)s in the tagged tree.
    lock = buildpath/"homebrew-requirements.txt"
    lock.write <<~'REQS'
%(requirements)s
    REQS
    system Formula["python@%(python)s"].opt_libexec/"bin/python", "-m", "pip",
           "--python=#{libexec}/bin/python", "install", "--require-hashes",
           "--only-binary=:all:", "--no-deps", "--no-compile", "-r", lock

    # The package itself, which is pure Python and stdlib-only.
    venv.pip_install_and_link buildpath
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/zot --version")

    # The reason this formula exists in this shape: the extras must be there.
    system libexec/"bin/python", "-c", "import mcp.server.fastmcp, pymupdf"

    # The agent surfaces ride inside the wheel; this fails if the sdist ever
    # stops carrying them.
    assert_predicate Pathname.new(shell_output("#{bin}/zot skill path").strip)/"SKILL.md", :exist?
  end
end
''' % {"desc": DESC, "homepage": HOMEPAGE, "url": url, "sha256": sha256,
       "license": project_license(), "python": PYTHON_PIN, "lock": LOCK_REL,
       "requirements": embedded_lock("      ")}


def _as_tuple(version):
    return tuple(int(p) for p in re.findall(r"\d+", version))


def guard_lock():
    """Fail loudly rather than generate a formula that would install less than the
    PyPI package does. This is the check the 0.3.0 tap lacked: it shipped without
    the [mcp] extra and nothing noticed."""
    if not os.path.exists(LOCK):
        return ["%s is missing; run --relock" % LOCK_REL]
    pinned = {name.lower() for name in lock_pins()}
    problems = []
    for extra, names in sorted(shipping_extras().items()):
        for name in names:
            if name not in pinned:
                problems.append("the [%s] extra needs %s, which the lock does not pin — "
                                "`brew install` would ship without it (run --relock)"
                                % (extra, name))
    problems += ["%s is a runtime dependency the lock does not pin (run --relock)" % name
                 for name in core_dependencies() if name not in pinned]
    return problems


def check():
    """Verify the committed formula without writing: it must be exactly what this
    generator produces for the version and hash it declares. That tolerates the
    formula lagging `__version__` between releases (the hash of an unpublished
    sdist is unknowable) while rejecting any hand edit or template drift."""
    problems = guard_lock()
    if not os.path.exists(OUT):
        problems.append("%s is missing; the release workflow generates it" % OUT)
        return problems
    with open(OUT, encoding="utf-8") as fh:
        current = fh.read()
    declared = re.search(r'^  url "(https://\S*/zotero_agent-(.+?)\.tar\.gz)"$', current, re.M)
    sha = re.search(r'^  sha256 "([0-9a-f]{64})"$', current, re.M)
    if not declared or not sha:
        problems.append("cannot read a url + sha256 out of the formula")
        return problems
    url, version = declared.group(1), declared.group(2)
    if _as_tuple(version) > _as_tuple(__version__):
        problems.append("formula announces %s, ahead of the package's %s" % (version, __version__))
    if "/packages/source/" in url:
        problems.append("the url uses PyPI's /packages/source/ alias, which 404s for a "
                        "freshly published release — regenerate from the sdist")
    if current != render(version, sha.group(1), url):
        problems.append("formula does not match the generator's output for %s "
                        "(hand-edited, or the template moved)" % version)
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdist", help="the sdist being published; its sha256 goes into the "
                                    "formula and its filename must match the package version")
    ap.add_argument("--from-pypi", action="store_true",
                    help="take the url and sha256 from PyPI's API instead of a local sdist — "
                         "for regenerating a formula for an already-published version")
    ap.add_argument("--version", default=__version__,
                    help="the released version (default: the package's own)")
    ap.add_argument("--check", action="store_true",
                    help="fail if the committed formula is not this generator's output")
    ap.add_argument("--relock", action="store_true",
                    help="recompile the dependency lock with uv. Keeps the current pins "
                         "(uv only moves them with --upgrade), so CI can run this and diff")
    ap.add_argument("--upgrade", action="store_true",
                    help="with --relock, take newer versions of the extras")
    args = ap.parse_args()

    if args.relock:
        cmd = lock_command(upgrade=args.upgrade)
        print("$ %s" % " ".join(cmd))
        result = subprocess.run(cmd, cwd=_ROOT)
        if result.returncode:
            return result.returncode
        problems = guard_lock()
        if problems:
            print("The recompiled lock is not usable: %s" % "; ".join(problems), file=sys.stderr)
            return 1
        print("Locked %d distributions for python@%s" % (len(lock_pins()), PYTHON_PIN))
        return 0

    if args.check:
        problems = check()
        if problems:
            print("The Homebrew formula is stale: %s\nRun: python scripts/gen_homebrew_formula.py "
                  "--sdist dist/zotero_agent-<version>.tar.gz" % "; ".join(problems),
                  file=sys.stderr)
            return 1
        print("The Homebrew formula is in sync (%s)" % os.path.relpath(OUT, _ROOT))
        return 0

    problems = guard_lock()
    if problems:
        print("Refusing to generate: %s" % "; ".join(problems), file=sys.stderr)
        return 1

    version = args.version
    if args.sdist:
        name = os.path.basename(args.sdist)
        expected = "zotero_agent-%s.tar.gz" % version
        if name != expected:
            print("%s is not %s — the sdist and the version disagree" % (name, expected),
                  file=sys.stderr)
            return 1
        with open(args.sdist, "rb") as fh:
            blob = fh.read()
        # Both digests come from the one artifact: sha256 is what brew verifies, and
        # blake2b-256 *is* PyPI's storage path, so no API call and no CDN lag.
        sha256 = hashlib.sha256(blob).hexdigest()
        url = sdist_url(version, hashlib.blake2b(blob, digest_size=32).hexdigest())
    elif args.from_pypi:
        url, sha256 = pypi_sdist(version)
    else:
        print("Need --sdist (offline, from the artifact being published) or --from-pypi. "
              "The hash comes from the published artifact: sdists are not byte-identical "
              "across machines.", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(render(version, sha256, url))
    print("Wrote %s (v%s, python@%s)" % (os.path.relpath(OUT, _ROOT), version, PYTHON_PIN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
