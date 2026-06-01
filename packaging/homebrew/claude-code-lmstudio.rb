class ClaudeCodeLmstudio < Formula
  include Language::Python::Virtualenv

  desc "Run Claude Code against local models in LM Studio"
  homepage "https://github.com/WillieCubed/claude-code-lmstudio"
  url "https://github.com/WillieCubed/claude-code-lmstudio/archive/refs/tags/v0.1.0.tar.gz"
  # Fill in at release time:  shasum -a 256 v0.1.0.tar.gz
  sha256 "REPLACE_WITH_RELEASE_TARBALL_SHA256"
  license "MIT"
  head "https://github.com/WillieCubed/claude-code-lmstudio.git", branch: "main"

  depends_on "python@3.12"

  # Pure standard library — no Python resources to vendor.
  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "usage: cll", shell_output("#{bin}/cll --help")
  end
end
