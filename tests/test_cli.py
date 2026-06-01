"""Tests for CLI helpers that don't touch the network."""
from claude_lms import cli
from claude_lms.cli import match_model

AVAILABLE = [
    "qwen/qwen3.6-35b-a3b",
    "qwen/qwen3.5-35b-a3b",
    "openai/gpt-oss-20b",
    "mistralai/magistral-small-2509",
]


def test_exact_id_matches():
    assert match_model("openai/gpt-oss-20b", AVAILABLE) == ("openai/gpt-oss-20b", [])


def test_unique_substring_resolves_to_full_id():
    assert match_model("qwen3.6", AVAILABLE) == ("qwen/qwen3.6-35b-a3b", [])


def test_case_insensitive_substring():
    assert match_model("GPT-OSS", AVAILABLE) == ("openai/gpt-oss-20b", [])


def test_ambiguous_substring_returns_candidates():
    resolved, candidates = match_model("qwen", AVAILABLE)
    assert resolved is None
    assert candidates == ["qwen/qwen3.6-35b-a3b", "qwen/qwen3.5-35b-a3b"]


def test_no_match_returns_nothing():
    assert match_model("llama", AVAILABLE) == (None, [])


def test_empty_available_is_no_match():
    assert match_model("qwen3.6", []) == (None, [])


def test_set_and_clear_default_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("CLL_MODEL", raising=False)
    assert cli.configured_default() is None
    assert cli.main(["--set-default", "qwen/qwen3.6-27b"]) == 0
    assert cli.configured_default() == "qwen/qwen3.6-27b"
    assert cli.effective_default() == "qwen/qwen3.6-27b"
    assert cli.main(["--clear-default"]) == 0
    assert cli.configured_default() is None


def test_env_overrides_configured_default(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cli.save_config({"default_model": "config-model"})
    monkeypatch.setenv("CLL_MODEL", "env-model")
    assert cli.effective_default() == "env-model"
    monkeypatch.delenv("CLL_MODEL", raising=False)
    assert cli.effective_default() == "config-model"
