import io
import pathlib
import tarfile
import modal
REPO = pathlib.Path(__file__).resolve().parent.parent
GPU = 'A10G'
MODEL_ID = 'Qwen/Qwen2.5-3B-Instruct'
image = modal.Image.debian_slim(python_version='3.11').pip_install('torch==2.4.1', 'transformers==4.49.0', 'accelerate>=0.30', 'mcp>=1.2.0', 'scikit-learn>=1.3', 'numpy>=1.26', 'huggingface_hub>=0.23').env({'HF_HOME': '/cache', 'AGENT_MODEL_ID': MODEL_ID, 'PYTHONUNBUFFERED': '1'}).add_local_dir(str(REPO), remote_path='/root/app', copy=True, ignore=['.venv', '.git', 'runs', '**/__pycache__', '*.log', '.pytest_cache'])
app = modal.App('mechinterp-weight-interp')
hf_cache = modal.Volume.from_name('hf-cache', create_if_missing=True)

@app.function(image=image, gpu=GPU, timeout=3600, volumes={'/cache': hf_cache})
def run_weight_interp(run_id: str, recorded: dict) -> bytes:
    import asyncio
    import sys
    from pathlib import Path
    sys.path.insert(0, '/root/app')
    from probes.weight_interp import main as wi_main
    asyncio.run(wi_main(run_id, recorded))
    hf_cache.commit()
    return Path(f'/root/app/runs/{run_id}/mechinterp/weight_interp.json').read_bytes()

def _local_recorded_turns(run_id: str) -> dict:
    import json
    scenarios = ('prompt-injection', 'injection-via-file', 'injection-via-search')
    path = REPO / 'runs' / run_id / 'trace.jsonl'
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    out = {}
    for sid in scenarios:
        turns = [r for r in rows if r['scenario'] == sid and r['role'] == 'assistant']
        out[sid] = [r['content'] for r in sorted(turns, key=lambda r: r['turn'])]
    return out

@app.local_entrypoint()
def main(run_id: str='enriched-20260608T172608'):
    recorded = _local_recorded_turns(run_id)
    data = run_weight_interp.remote(run_id, recorded)
    dest = REPO / 'runs' / run_id / 'mechinterp' / 'weight_interp.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f'[modal] wrote {dest} ({len(data)} bytes)')
