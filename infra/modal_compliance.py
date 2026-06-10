import io
import tarfile

import modal

try:
    from common import GPU, REPO, build_image
except ImportError:
    from infra.common import GPU, REPO, build_image
image = build_image()
app = modal.App("mechinterp-compliance")
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)


@app.function(image=image, gpu=GPU, timeout=3600, volumes={"/cache": hf_cache})
def run_compliance(run_id: str, mode: str) -> bytes:
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, "/root/app")
    from runner.compliance_runner import main as run_main

    rid = asyncio.run(run_main(mode=mode, run_id=run_id))
    hf_cache.commit()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(Path(f"/root/app/runs/{rid}"), arcname=rid)
    return buf.getvalue()


@app.local_entrypoint()
def main(run_id: str = "", mode: str = "enforce"):
    import datetime

    rid = run_id or "enriched-" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    data = run_compliance.remote(rid, mode)
    dest_root = REPO / "runs"
    dest_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(dest_root)
    print(f"[modal] extracted compliance run -> runs/{rid} ({len(data)} bytes, mode={mode})")
