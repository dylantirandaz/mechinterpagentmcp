import io
import pathlib
import tarfile
import modal
REPO = pathlib.Path(__file__).resolve().parent.parent
GPU = 'A10G'
MODEL_ID = 'Qwen/Qwen2.5-3B-Instruct'
image = modal.Image.debian_slim(python_version='3.11').pip_install('torch==2.4.1', 'transformers==4.49.0', 'accelerate>=0.30', 'mcp>=1.2.0', 'scikit-learn>=1.3', 'numpy>=1.26', 'huggingface_hub>=0.23').env({'HF_HOME': '/cache', 'AGENT_MODEL_ID': MODEL_ID, 'PYTHONUNBUFFERED': '1'}).add_local_dir(str(REPO), remote_path='/root/app', copy=True, ignore=['.venv', '.git', 'runs', '**/__pycache__', '*.log', '.pytest_cache'])
app = modal.App('mechinterp-compliance')
hf_cache = modal.Volume.from_name('hf-cache', create_if_missing=True)

@app.function(image=image, gpu=GPU, timeout=3600, volumes={'/cache': hf_cache})
def run_compliance(run_id: str, mode: str) -> bytes:
    import asyncio
    import sys
    from pathlib import Path
    sys.path.insert(0, '/root/app')
    from runner.compliance_runner import main as run_main
    rid = asyncio.run(run_main(mode=mode, run_id=run_id))
    hf_cache.commit()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        tar.add(Path(f'/root/app/runs/{rid}'), arcname=rid)
    return buf.getvalue()

@app.local_entrypoint()
def main(run_id: str='', mode: str='enforce'):
    import datetime
    rid = run_id or 'enriched-' + datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
    data = run_compliance.remote(rid, mode)
    dest_root = REPO / 'runs'
    dest_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        tar.extractall(dest_root)
    print(f'[modal] extracted compliance run -> runs/{rid} ({len(data)} bytes, mode={mode})')
