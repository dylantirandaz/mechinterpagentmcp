from __future__ import annotations


def mcp_tools_to_chat(tools) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in tools
    ]


async def call_tool(session, name: str, arguments: dict) -> str:
    result = await session.call_tool(name, arguments=arguments)
    parts = [getattr(item, "text", str(item)) for item in result.content]
    return "\n".join(parts) if parts else "(no content)"
