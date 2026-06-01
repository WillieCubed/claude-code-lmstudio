"""Tests for CLI helpers that don't touch the network."""
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
