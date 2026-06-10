from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from agent.mcp_io import call_tool, mcp_tools_to_chat
from agent.tool_calls import parse_tool_calls
from runner.policy import ENFORCE, _should_flag, evaluate, flag_text_decision

MAX_TURNS = 4


@dataclass
class ScenarioRun:
    model: Any
    session: Any
    scenario: Any
    granted: tuple
    risk: dict
    recorder: Any
    schemas: dict
    chat_tools: list
    withheld: list
    mode: str

    def save_activation(self, span_id: str, messages: list) -> str:
        activation = self.model.residual_at_decision(messages, self.chat_tools)
        np.savez_compressed(
            self.recorder.root / "mechinterp" / f"{span_id}.npz", residual=activation
        )
        return f"mechinterp/{span_id}.npz"


async def run_scenario(
    model, session, scenario, granted, risk, recorder, schemas: dict, mode: str = ENFORCE
) -> None:
    from runner.scenarios import SYSTEM_PROMPT

    tools_result = await session.list_tools()
    chat_tools = mcp_tools_to_chat(tools_result.tools)
    withheld = [name for name in schemas if name not in granted]
    ctx = ScenarioRun(
        model, session, scenario, granted, risk, recorder, schemas, chat_tools, withheld, mode
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": scenario.prompt},
    ]
    recorder.trace({"scenario": scenario.id, "turn": 0, "role": "user", "content": scenario.prompt})
    for turn in range(1, MAX_TURNS + 1):
        gen = model.generate(messages, chat_tools)
        messages.append({"role": "assistant", "content": gen.text})
        calls = parse_tool_calls(gen.text)
        recorder.trace(
            {
                "scenario": scenario.id,
                "turn": turn,
                "role": "assistant",
                "content": gen.text,
                "tool_calls": [c.name for c in calls],
            }
        )
        if not calls:
            _record_text_decision(ctx, turn, gen.text, messages)
            break
        for idx, call in enumerate(calls):
            await _handle_call(ctx, turn, idx, call, messages)


def _record_text_decision(ctx: ScenarioRun, turn: int, text: str, messages: list) -> None:
    reasons = flag_text_decision(text, ctx.withheld)
    if not reasons:
        return
    span_id = f"{ctx.scenario.id}-t{turn}-text"
    activation_file = ctx.save_activation(span_id, messages)
    ctx.recorder.permission(
        {
            "tool": None,
            "in_scope": True,
            "risk": "text-only",
            "path_traversal": False,
            "verdict": "text-only-risky",
            "block_reasons": reasons,
            "schema_violations": [],
            "span_id": span_id,
        }
    )
    ctx.recorder.flag(
        {
            "span_id": span_id,
            "scenario": ctx.scenario.id,
            "tool": None,
            "risk": "text-only",
            "reason": "; ".join(reasons),
            "activation_file": activation_file,
        },
        context_text=gen_context_text(messages),
    )


async def _handle_call(ctx: ScenarioRun, turn: int, idx: int, call, messages: list) -> None:
    declared = call.name in ctx.schemas
    decision = evaluate(
        call.name,
        call.arguments,
        ctx.granted,
        ctx.risk,
        ctx.schemas.get(call.name),
        declared,
        ctx.mode,
    )
    span_id = f"{ctx.scenario.id}-t{turn}-c{idx}-{call.name}"
    activation_file = ctx.save_activation(span_id, messages)
    if decision["allow"] and declared:
        result_text = await call_tool(ctx.session, call.name, call.arguments)
        forwarded = True
    else:
        forwarded = False
        result_text = "DENIED by runner: " + "; ".join(decision["block_reasons"])
    ctx.recorder.mcp(
        {
            "scenario": ctx.scenario.id,
            "span_id": span_id,
            "forwarded_to_server": forwarded,
            "request": {"tool": call.name, "arguments": call.arguments},
            "declared": declared,
            "schema_violations": decision["schema_violations"],
            "block_reasons": decision["block_reasons"],
            "response_excerpt": result_text[:400],
        }
    )
    ctx.recorder.permission({**decision, "span_id": span_id})
    if _should_flag(decision) or decision["block_reasons"]:
        ctx.recorder.flag(
            {
                "span_id": span_id,
                "scenario": ctx.scenario.id,
                "tool": call.name,
                "risk": decision["risk"],
                "reason": decision["verdict"],
                "activation_file": activation_file,
            },
            context_text=gen_context_text(messages),
        )
    messages.append({"role": "tool", "name": call.name, "content": result_text})


def gen_context_text(messages) -> str:
    return "\n".join((f"[{m['role']}] {m.get('content', '')}" for m in messages))
