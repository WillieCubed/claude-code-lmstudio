"""Tests for the turnkey shell-completion installer."""
import os

import pytest

from claude_lms import completions


def test_install_zsh_writes_file_and_rc(tmp_path):
    home = str(tmp_path)
    completions.install("zsh", home=home)
    assert os.path.exists(os.path.join(home, ".zsh", "completions", "_cll"))
    assert "claude-lms completion" in open(os.path.join(home, ".zshrc")).read()


def test_install_bash_writes_file_and_rc(tmp_path):
    home = str(tmp_path)
    completions.install("bash", home=home)
    assert os.path.exists(os.path.join(home, ".local", "share", "claude-lms", "cll.bash"))
    assert "claude-lms completion" in open(os.path.join(home, ".bashrc")).read()


def test_install_is_idempotent(tmp_path):
    home = str(tmp_path)
    completions.install("zsh", home=home)
    completions.install("zsh", home=home)
    rc = open(os.path.join(home, ".zshrc")).read()
    assert rc.count(">>> claude-lms completion >>>") == 1


def test_install_unsupported_shell_raises(tmp_path):
    with pytest.raises(ValueError):
        completions.install("fish", home=str(tmp_path))


def test_detect_shell(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    assert completions.detect_shell() == "zsh"
    monkeypatch.setenv("SHELL", "/usr/bin/bash")
    assert completions.detect_shell() == "bash"
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    assert completions.detect_shell() is None
