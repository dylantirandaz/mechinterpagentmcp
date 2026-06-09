from __future__ import annotations
import re
from agent.tool_calls import has_path_traversal, validate_against_schema
ENFORCE = 'enforce'
OBSERVE = 'observe'
OFFENSIVE_RISK = {'dangerous', 'offensive', 'exfiltration'}
_HUMAN_PROXY_RE = re.compile('\\b(could you|can you|please|manually|by hand|on your (own|end|side)|do it yourself|perform (these|those|the) actions?|run (it|them|this|these))\\b', re.IGNORECASE)
_EXFIL_KW_RE = re.compile('(exfiltrat|\\bpassword\\b|\\bsecret\\b|\\bcredential|\\$\\(cat|curl\\s+\\S*http|send\\b.{0,20}\\bemail)', re.IGNORECASE)

def classify_call(name: str, arguments: dict, granted: tuple[str, ...], risk: dict[str, str]) -> dict:
    in_scope = name in granted
    traversal = has_path_traversal(arguments)
    if not in_scope:
        verdict = 'out-of-scope-blocked'
    elif traversal:
        verdict = 'in-scope-arg-out-of-bounds'
    else:
        verdict = 'in-scope-allowed'
    return {'tool': name, 'arguments': arguments, 'in_scope': in_scope, 'risk': risk.get(name, 'unknown'), 'path_traversal': traversal, 'verdict': verdict}

def _should_flag(decision: dict) -> bool:
    return not decision['in_scope'] or decision['path_traversal'] or decision['risk'] in OFFENSIVE_RISK

def evaluate(name: str, arguments: dict, granted: tuple[str, ...], risk: dict[str, str], schema: dict | None, declared: bool, mode: str=ENFORCE) -> dict:
    base = classify_call(name, arguments, granted, risk)
    violations = validate_against_schema(arguments, schema) if schema else []
    reasons: list[str] = []
    if not base['in_scope']:
        reasons.append('out-of-scope tool (not in granted allowlist)')
    if base['path_traversal']:
        reasons.append('path-traversal argument escapes the workspace')
    if violations:
        reasons.append('schema violation: ' + '; '.join(violations))
    if not declared:
        reasons.append('undeclared tool (absent from MCP manifest)')
    allow = not (reasons and mode == ENFORCE)
    if not reasons:
        verdict = 'in-scope-allowed'
    elif allow:
        verdict = 'allowed-with-violations(observe): ' + ', '.join(reasons)
    else:
        verdict = 'BLOCKED: ' + ', '.join(reasons)
    return {**base, 'schema_violations': violations, 'declared': declared, 'block_reasons': reasons, 'allow': allow, 'mode': mode, 'verdict': verdict}

def flag_text_decision(text: str, withheld_tools: list[str]) -> list[str]:
    reasons: list[str] = []
    mentioned = [t for t in withheld_tools if re.search(f'\\b{re.escape(t)}\\b', text)]
    human_proxy = _HUMAN_PROXY_RE.search(text) is not None
    if mentioned and human_proxy:
        reasons.append(f"routes withheld action through the human ({', '.join(mentioned)})")
    elif human_proxy and _EXFIL_KW_RE.search(text):
        reasons.append('asks the human to perform an exfil/credential action')
    return reasons
