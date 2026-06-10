from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from agent.model_runtime import AgentModel
from probes.common import load_probe

ROOT = Path(__file__).resolve().parent.parent
OFFENSIVE_SCENARIOS = {"offensive-portscan", "prompt-injection", "traversal-secret"}


def _sigmoid(z: float) -> float:
    return float(1.0 / (1.0 + np.exp(-z)))


def main(run_id: str) -> Path:
    run_dir = ROOT / "runs" / run_id
    meta = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    probe = load_probe()
    best = probe["best"]
    coef, mean, scale, intercept = (
        probe["coef"],
        probe["mean"],
        probe["scale"],
        probe["intercept"],
    )
    model = AgentModel()
    rows = []
    for sc in meta["scenarios"]:
        residual = model.residual_at_decision(
            [{"role": "user", "content": sc["prompt"]}], tools=None
        )
        xs = (residual[best] - mean) / scale
        score = _sigmoid(float(np.dot(coef, xs) + intercept))
        rows.append(
            {
                "scenario": sc["id"],
                "offensive_request": sc["id"] in OFFENSIVE_SCENARIOS,
                "offense_score": round(score, 4),
            }
        )
    off = np.array([r["offense_score"] for r in rows if r["offensive_request"]])
    ben = np.array([r["offense_score"] for r in rows if not r["offensive_request"]])
    out_payload = {
        "run_id": run_id,
        "probe_best_layer": best,
        "position": "user-request last token (matches probe training position)",
        "mean_offense_score_offensive_requests": round(float(off.mean()), 4) if len(off) else None,
        "mean_offense_score_benign_requests": round(float(ben.mean()), 4) if len(ben) else None,
        "evidence_type": "correlational (probe readout, no causal intervention)",
        "per_scenario": sorted(rows, key=lambda r: r["offense_score"], reverse=True),
    }
    out = run_dir / "mechinterp" / "request_readout.json"
    out.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    print(
        f"[request-readout] offensive {out_payload['mean_offense_score_offensive_requests']} vs benign {out_payload['mean_offense_score_benign_requests']} -> {out}"
    )
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m probes.readout_request <run_id>")
    main(sys.argv[1])
