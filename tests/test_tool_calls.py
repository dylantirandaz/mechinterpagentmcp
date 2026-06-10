import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.tool_calls import ToolCall, has_path_traversal, parse_tool_calls, validate_against_schema


def test_parses_single_tool_call():
    text = '<tool_call>\n{"name": "read_file", "arguments": {"path": "README.md"}}\n</tool_call>'
    assert parse_tool_calls(text) == [ToolCall("read_file", {"path": "README.md"})]


def test_parses_multiple_tool_calls():
    text = '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>noise<tool_call>{"name": "run_shell", "arguments": {"command": "ls"}}</tool_call>'
    calls = parse_tool_calls(text)
    assert [c.name for c in calls] == ["web_search", "run_shell"]


def test_skips_malformed_json_block():
    text = "<tool_call>{not valid json}</tool_call>"
    assert parse_tool_calls(text) == []


def test_plain_text_has_no_calls():
    assert parse_tool_calls("I will just answer in prose.") == []


def test_detects_posix_and_backslash_traversal():
    assert has_path_traversal({"path": "../secrets.env"})
    assert has_path_traversal({"path": "..\\secrets.env"})
    assert has_path_traversal({"path": "sub/../../x"})


def test_clean_path_is_not_flagged():
    assert not has_path_traversal({"path": "workspace/README.md"})
    assert not has_path_traversal({"query": "how to file taxes"})


def test_schema_flags_missing_required():
    schema = {"properties": {"path": {"type": "string"}}, "required": ["path"]}
    assert "missing required param 'path'" in validate_against_schema({}, schema)


def test_schema_flags_undeclared_and_type_errors():
    schema = {"properties": {"host": {"type": "string"}}, "required": ["host"]}
    violations = validate_against_schema({"host": 123, "extra": True}, schema)
    assert any(("should be string" in v for v in violations))
    assert any(("undeclared param 'extra'" in v for v in violations))


def test_schema_accepts_conformant_args():
    schema = {"properties": {"query": {"type": "string"}}, "required": ["query"]}
    assert validate_against_schema({"query": "hello"}, schema) == []
