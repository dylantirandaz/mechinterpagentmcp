import json
import re
from dataclasses import dataclass
_TOOL_CALL_RE = re.compile('<tool_call>\\s*(\\{.*?\\})\\s*</tool_call>', re.DOTALL)
_TRAVERSAL_RE = re.compile('(^|[\\\\/])\\.\\.([\\\\/]|$)')

@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict

def parse_tool_calls(assistant_text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for match in _TOOL_CALL_RE.finditer(assistant_text):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        name = payload.get('name')
        if not isinstance(name, str):
            continue
        args = payload.get('arguments', {})
        if not isinstance(args, dict):
            args = {}
        calls.append(ToolCall(name=name, arguments=args))
    return calls

def has_path_traversal(arguments: dict) -> bool:
    return any((isinstance(value, str) and _TRAVERSAL_RE.search(value) is not None for value in arguments.values()))

def validate_against_schema(arguments: dict, schema: dict) -> list[str]:
    violations: list[str] = []
    properties = schema.get('properties', {})
    required = schema.get('required', [])
    for key in required:
        if key not in arguments:
            violations.append(f"missing required param '{key}'")
    type_map = {'string': str, 'integer': int, 'number': (int, float), 'boolean': bool, 'object': dict, 'array': list}
    for key, value in arguments.items():
        if key not in properties:
            violations.append(f"undeclared param '{key}'")
            continue
        declared = properties[key].get('type')
        expected = type_map.get(declared)
        if expected and (not isinstance(value, expected)):
            violations.append(f"param '{key}' should be {declared}, got {type(value).__name__}")
    return violations
