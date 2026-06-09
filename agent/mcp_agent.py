from __future__ import annotations
import numpy as np
from agent.tool_calls import parse_tool_calls
from runner.policy import ENFORCE, OFFENSIVE_RISK, _should_flag, classify_call, evaluate, flag_text_decision
MAX_TURNS = 4

def _mcp_tools_to_chat(tools) -> list[dict]:
    return [{'type': 'function', 'function': {'name': t.name, 'description': t.description or '', 'parameters': t.inputSchema}} for t in tools]

async def run_scenario(model, session, scenario, granted, risk, recorder, schemas: dict, mode: str=ENFORCE) -> None:
    from runner.scenarios import SYSTEM_PROMPT
    tools_result = await session.list_tools()
    chat_tools = _mcp_tools_to_chat(tools_result.tools)
    withheld = [name for name in schemas if name not in granted]
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': scenario.prompt}]
    recorder.trace({'scenario': scenario.id, 'turn': 0, 'role': 'user', 'content': scenario.prompt})
    for turn in range(1, MAX_TURNS + 1):
        gen = model.generate(messages, chat_tools)
        messages.append({'role': 'assistant', 'content': gen.text})
        calls = parse_tool_calls(gen.text)
        recorder.trace({'scenario': scenario.id, 'turn': turn, 'role': 'assistant', 'content': gen.text, 'tool_calls': [c.name for c in calls]})
        if not calls:
            _record_text_decision(model, scenario, turn, gen.text, messages, chat_tools, withheld, recorder)
            break
        for idx, call in enumerate(calls):
            await _handle_call(model, session, scenario, turn, idx, call, messages, granted, risk, recorder, schemas, chat_tools, mode)

def _record_text_decision(model, scenario, turn, text, messages, chat_tools, withheld, recorder) -> None:
    reasons = flag_text_decision(text, withheld)
    if not reasons:
        return
    span_id = f'{scenario.id}-t{turn}-text'
    activation = model.residual_at_decision(messages, chat_tools)
    np.savez_compressed(recorder.root / 'mechinterp' / f'{span_id}.npz', residual=activation)
    recorder.permission({'tool': None, 'in_scope': True, 'risk': 'text-only', 'path_traversal': False, 'verdict': 'text-only-risky', 'block_reasons': reasons, 'schema_violations': [], 'span_id': span_id})
    recorder.flag({'span_id': span_id, 'scenario': scenario.id, 'tool': None, 'risk': 'text-only', 'reason': '; '.join(reasons), 'activation_file': f'mechinterp/{span_id}.npz'}, context_text=gen_context_text(messages))

async def _handle_call(model, session, scenario, turn, idx, call, messages, granted, risk, recorder, schemas, chat_tools, mode) -> None:
    declared = call.name in schemas
    decision = evaluate(call.name, call.arguments, granted, risk, schemas.get(call.name), declared, mode)
    span_id = f'{scenario.id}-t{turn}-c{idx}-{call.name}'
    activation = model.residual_at_decision(messages, chat_tools)
    act_path = recorder.root / 'mechinterp' / f'{span_id}.npz'
    np.savez_compressed(act_path, residual=activation)
    if decision['allow'] and declared:
        result_text = await _call_tool(session, call.name, call.arguments)
        forwarded = True
    else:
        forwarded = False
        result_text = 'DENIED by runner: ' + '; '.join(decision['block_reasons'])
    recorder.mcp({'scenario': scenario.id, 'span_id': span_id, 'forwarded_to_server': forwarded, 'request': {'tool': call.name, 'arguments': call.arguments}, 'declared': declared, 'schema_violations': decision['schema_violations'], 'block_reasons': decision['block_reasons'], 'response_excerpt': result_text[:400]})
    recorder.permission({**decision, 'span_id': span_id})
    if _should_flag(decision) or decision['block_reasons']:
        recorder.flag({'span_id': span_id, 'scenario': scenario.id, 'tool': call.name, 'risk': decision['risk'], 'reason': decision['verdict'], 'activation_file': f'mechinterp/{span_id}.npz'}, context_text=gen_context_text(messages))
    messages.append({'role': 'tool', 'name': call.name, 'content': result_text})

async def _call_tool(session, name: str, arguments: dict) -> str:
    result = await session.call_tool(name, arguments=arguments)
    parts = []
    for item in result.content:
        parts.append(getattr(item, 'text', str(item)))
    return '\n'.join(parts) if parts else '(no content)'

def gen_context_text(messages) -> str:
    return '\n'.join((f"[{m['role']}] {m.get('content', '')}" for m in messages))
