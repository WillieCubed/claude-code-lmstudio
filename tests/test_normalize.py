"""Unit tests for the system-message normalizer.

These pin the exact behavior that makes strict chat templates (Qwen) accept Claude
Code's requests: after normalization there is at most one ``system`` field and no
``system``-role message anywhere in ``messages``.
"""
from claude_lms.proxy import normalize


def _no_system_in_messages(payload):
    return all(m.get("role") != "system" for m in payload["messages"])


def test_mid_conversation_system_message_is_folded():
    # This is the shape Claude Code sends that breaks the Qwen template.
    payload = {
        "system": [{"type": "text", "text": "leading system"}],
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "SessionStart hook context"},
        ],
    }
    normalize(payload)

    assert _no_system_in_messages(payload)
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    texts = [b["text"] for b in payload["system"]]
    assert texts == ["leading system", "SessionStart hook context"]


def test_string_system_field_becomes_single_block_list():
    payload = {"system": "be terse", "messages": [{"role": "user", "content": "hi"}]}
    normalize(payload)
    assert payload["system"] == [{"type": "text", "text": "be terse"}]


def test_block_list_system_content_is_flattened_when_folded():
    payload = {
        "system": "top",
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "line one"},
                    {"type": "text", "text": "line two"},
                ],
            },
        ],
    }
    normalize(payload)
    assert _no_system_in_messages(payload)
    assert payload["system"][-1] == {"type": "text", "text": "line one\nline two"}


def test_multiple_stray_system_messages_all_folded():
    payload = {
        "system": "top",
        "messages": [
            {"role": "user", "content": "a"},
            {"role": "system", "content": "one"},
            {"role": "assistant", "content": "b"},
            {"role": "system", "content": "two"},
        ],
    }
    normalize(payload)
    assert _no_system_in_messages(payload)
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant"]
    assert [b["text"] for b in payload["system"]] == ["top", "one", "two"]


def test_clean_request_is_left_untouched():
    payload = {
        "system": [{"type": "text", "text": "s"}],
        "messages": [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ],
    }
    normalize(payload)
    assert payload["system"] == [{"type": "text", "text": "s"}]
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant"]


def test_no_system_field_at_all():
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    normalize(payload)
    assert "system" not in payload or payload["system"] == []
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
