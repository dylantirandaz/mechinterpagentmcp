import pathlib

import modal

REPO = pathlib.Path(__file__).resolve().parent.parent
GPU = "A10G"
MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.4.1", "transformers==4.49.0", "accelerate>=0.30",
                 "mcp>=1.2.0", "scikit-learn>=1.3", "numpy>=1.26", "huggingface_hub>=0.23")
    .env({"HF_HOME": "/cache", "AGENT_MODEL_ID": MODEL_ID, "PYTHONUNBUFFERED": "1"})
    .add_local_dir(str(REPO), remote_path="/root/app", copy=True,
                   ignore=[".venv", ".git", "runs", "**/__pycache__", "*.log", ".pytest_cache"])
)

app = modal.App("mechinterp-contrast-acts")
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)


@app.function(image=image, gpu=GPU, timeout=1800, volumes={"/cache": hf_cache})
def capture() -> bytes:
    import io
    import json
    import sys

    import numpy as np
    sys.path.insert(0, "/root/app")
    from agent.model_runtime import AgentModel

    rows = [json.loads(l) for l in open("/root/app/probes/contrast_set.jsonl") if l.strip()]
    model = AgentModel()
    acts = np.stack([model.residual_at_decision([{"role": "user", "content": r["text"]}], None)
                     for r in rows]).astype("float16")
    labels = np.array([r["label"] for r in rows])
    texts = np.array([r["text"] for r in rows], dtype=object)
    hf_cache.commit()
    buf = io.BytesIO()
    np.savez_compressed(buf, acts=acts, labels=labels, texts=texts)
    return buf.getvalue()


@app.local_entrypoint()
def main():
    data = capture.remote()
    dest = REPO / "assets" / "_contrast_acts.npz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"[modal] wrote {dest} ({len(data)} bytes)")
