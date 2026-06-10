from __future__ import annotations

import asyncio
import datetime
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.mcp_agent import run_scenario
from agent.model_runtime import AgentModel
from runner.policy import ENFORCE
from runner.recorder import Recorder
from runner.scenarios import GRANTED_TOOLS, SCENARIOS, TOOL_RISK

SERVER_PATH = Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"
KNOWN_MCP_REVISIONS = {"2024-11-05", "2025-03-26", "2025-06-18"}


def _build_metadata(
    run_id: str, model: AgentModel, offered: list[str], handshake: dict, mode: str
) -> dict:
    return {
        "run_id": run_id,
        "model": model.model_id,
        "device": model.device,
        "num_layers": model.num_layers,
        "hidden_size": model.hidden_size,
        "enforcement_mode": mode,
        "granted_tools": list(GRANTED_TOOLS),
        "offered_tools": offered,
        "out_of_scope_tools": [t for t in offered if t not in GRANTED_TOOLS],
        "mcp_handshake": handshake,
        "scenarios": [
            {"id": s.id, "prompt": s.prompt, "expectation": s.expectation, "tempts": s.tempts}
            for s in SCENARIOS
        ],
    }


async def main(mode: str = ENFORCE, run_id: str | None = None) -> str:
    run_id = run_id or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    recorder = Recorder(run_id)
    print(f"[runner] run_id={run_id} mode={mode}; loading model...", flush=True)
    model = AgentModel()
    server = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            protocol_version = str(getattr(init, "protocolVersion", ""))
            handshake = {
                "protocol_version": protocol_version,
                "protocol_recognized": protocol_version in KNOWN_MCP_REVISIONS,
                "known_revisions": sorted(KNOWN_MCP_REVISIONS),
                "server_name": init.serverInfo.name,
                "server_version": init.serverInfo.version,
                "capabilities": str(init.capabilities),
            }
            tools_result = await session.list_tools()
            schemas = {t.name: t.inputSchema for t in tools_result.tools}
            offered = list(schemas.keys())
            recorder.write_json("mcp_handshake.json", handshake)
            recorder.write_json("mcp_offered_schemas.json", schemas)
            for scenario in SCENARIOS:
                print(f"[runner] scenario={scenario.id}", flush=True)
                await run_scenario(
                    model, session, scenario, GRANTED_TOOLS, TOOL_RISK, recorder, schemas, mode
                )
    recorder.finalize(_build_metadata(run_id, model, offered, handshake, mode))
    print(f"[runner] DONE run_id={run_id} -> runs/{run_id}", flush=True)
    return run_id


if __name__ == "__main__":
    asyncio.run(main())
