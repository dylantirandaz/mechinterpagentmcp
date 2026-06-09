from __future__ import annotations
import json
from pathlib import Path
RUNS_DIR = Path(__file__).resolve().parent.parent / 'runs'

class Recorder:

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.root = RUNS_DIR / run_id
        (self.root / 'decision_contexts').mkdir(parents=True, exist_ok=True)
        (self.root / 'mechinterp').mkdir(parents=True, exist_ok=True)
        self._trace = (self.root / 'trace.jsonl').open('w', encoding='utf-8')
        self._mcp = (self.root / 'mcp_trace.jsonl').open('w', encoding='utf-8')
        self.permissions: list[dict] = []
        self.flagged: list[dict] = []

    def _append(self, handle, record: dict) -> None:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        handle.flush()

    def trace(self, record: dict) -> None:
        self._append(self._trace, record)

    def mcp(self, record: dict) -> None:
        self._append(self._mcp, record)

    def permission(self, record: dict) -> None:
        self.permissions.append(record)

    def flag(self, span: dict, context_text: str) -> None:
        span_id = span['span_id']
        ctx_path = self.root / 'decision_contexts' / f'{span_id}.txt'
        ctx_path.write_text(context_text, encoding='utf-8')
        span['context_file'] = str(ctx_path.relative_to(self.root)).replace('\\', '/')
        self.flagged.append(span)

    def write_json(self, name: str, payload: dict | list) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        return path

    def finalize(self, metadata: dict) -> None:
        self.write_json('metadata.json', metadata)
        self.write_json('permissions.json', self.permissions)
        self.write_json('flagged_spans.json', self.flagged)
        self._trace.close()
        self._mcp.close()
