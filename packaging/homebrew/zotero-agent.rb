# Homebrew formula for zotero-agent.
#
# Destination: a personal tap repo `alex-roc/homebrew-tap` (file
# `Formula/zotero-agent.rb`), so users can:
#     brew install alex-roc/tap/zotero-agent
#
# The core is stdlib-only, so there are no Python resource dependencies. After
# publishing to PyPI, fill in `url` + `sha256` for the sdist. Get the sha256 with:
#     curl -sL <sdist-url> | shasum -a 256
# (Homebrew-core is a later step; a personal tap has no notability bar.)
class ZoteroAgent < Formula
  include Language::Python::Virtualenv

  desc "Local read-write control of a Zotero library, from your terminal or AI agent"
  homepage "https://github.com/alex-roc/zotero-agent"
  # TODO(release): point at the PyPI sdist and set the real sha256.
  url "https://files.pythonhosted.org/packages/source/z/zotero-agent/zotero_agent-0.2.0.tar.gz"
  sha256 "PLACEHOLDER_FILL_AT_RELEASE"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "zotero-agent", shell_output("#{bin}/zot --version")
  end
end
