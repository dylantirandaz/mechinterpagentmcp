import pathlib
import modal
REPO = pathlib.Path(__file__).resolve().parent.parent
GPU = 'A10G'
MODEL_ID = 'Qwen/Qwen2.5-3B-Instruct'
image = modal.Image.debian_slim(python_version='3.11').pip_install('torch==2.4.1', 'transformers==4.49.0', 'accelerate>=0.30', 'mcp>=1.2.0', 'scikit-learn>=1.3', 'numpy>=1.26', 'huggingface_hub>=0.23').env({'HF_HOME': '/cache', 'AGENT_MODEL_ID': MODEL_ID, 'PYTHONUNBUFFERED': '1'}).add_local_dir(str(REPO), remote_path='/root/app', copy=True, ignore=['.venv', '.git', 'runs', '**/__pycache__', '*.log', '.pytest_cache'])
app = modal.App('mechinterp-sweep')
hf_cache = modal.Volume.from_name('hf-cache', create_if_missing=True)

@app.function(image=image, gpu=GPU, timeout=3600, volumes={'/cache': hf_cache})
def run_sweep(run_id: str) -> bytes:
    import subprocess
    import sys
    from pathlib import Path
    out_dir = Path(f'/root/app/runs/{run_id}/mechinterp')
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'probes.intervene_sweep', run_id], cwd='/root/app', check=True)
    hf_cache.commit()
    return (out_dir / 'intervention_sweep.json').read_bytes()

@app.function(image=image, gpu=GPU, timeout=1800, volumes={'/cache': hf_cache})
def smoke() -> str:
    import subprocess
    import sys
    code = "from agent.model_runtime import AgentModel\nm = AgentModel()\ng = m.generate([{'role':'user','content':'Read README.md in your workspace and summarize it.'}], None)\nh = m.residual_at_decision([{'role':'user','content':'hello'}], None)\nprint('DEVICE', m.device, 'LAYERS', m.num_layers, 'DMODEL', m.hidden_size)\nprint('GEN', repr(g.text[:160]))\nprint('RESID', h.shape)\n"
    r = subprocess.run([sys.executable, '-c', code], cwd='/root/app', capture_output=True, text=True)
    hf_cache.commit()
    return f'returncode={r.returncode}\n{r.stdout}\n--- stderr tail ---\n{r.stderr[-800:]}'

@app.local_entrypoint()
def smoke_entry():
    print(smoke.remote())

@app.local_entrypoint()
def main(run_id: str='20260607T164400'):
    data = run_sweep.remote(run_id)
    dest = REPO / 'runs' / run_id / 'mechinterp' / 'intervention_sweep.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f'[modal] wrote {dest} ({len(data)} bytes)')
