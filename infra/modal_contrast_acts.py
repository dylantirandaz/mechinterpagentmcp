import modal

try:
    from common import GPU, REPO, build_image
except ImportError:
    from infra.common import GPU, REPO, build_image

image = build_image()

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

    rows = [
        json.loads(line) for line in open("/root/app/probes/contrast_set.jsonl") if line.strip()
    ]
    model = AgentModel()
    acts = np.stack(
        [model.residual_at_decision([{"role": "user", "content": r["text"]}], None) for r in rows]
    ).astype("float16")
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
