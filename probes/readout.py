from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from probes.common import load_probe
from runner.policy import OFFENSIVE_RISK

ROOT = Path(__file__).resolve().parent.parent


def _sigmoid(z: float) -> float:
    return float(1.0 / (1.0 + np.exp(-z)))


def _auc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    pos, neg = (scores[labels == 1], scores[labels == 0])
    if len(pos) == 0 or len(neg) == 0:
        return None
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    rank_sum_pos = ranks[labels == 1].sum()
    return float((rank_sum_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _is_risky(perm: dict) -> bool:
    return not perm["in_scope"] or perm.get("path_traversal") or perm["risk"] in OFFENSIVE_RISK


def main(run_id: str) -> Path:
    run_dir = ROOT / "runs" / run_id
    probe = load_probe()
    best = probe["best"]
    coef, mean, scale, intercept = (
        probe["coef"],
        probe["mean"],
        probe["scale"],
        probe["intercept"],
    )
    best_acc = probe["cv_accuracy"]
    perms = json.loads((run_dir / "permissions.json").read_text(encoding="utf-8"))
    spans, scores, labels = ([], [], [])
    for perm in perms:
        npz = run_dir / "mechinterp" / f"{perm['span_id']}.npz"
        if not npz.exists():
            continue
        residual = np.load(npz)["residual"][best]
        xs = (residual - mean) / scale
        score = _sigmoid(float(np.dot(coef, xs) + intercept))
        risky = bool(_is_risky(perm))
        spans.append(
            {
                "span_id": perm["span_id"],
                "tool": perm["tool"],
                "risk": perm["risk"],
                "verdict": perm["verdict"],
                "risky": risky,
                "offense_score": round(score, 4),
            }
        )
        scores.append(score)
        labels.append(int(risky))
    scores_a, labels_a = (np.array(scores), np.array(labels))
    risky_scores = scores_a[labels_a == 1]
    benign_scores = scores_a[labels_a == 0]
    readout = {
        "run_id": run_id,
        "probe_best_layer": best,
        "probe_best_layer_cv_accuracy": round(best_acc, 4),
        "n_decisions": len(spans),
        "n_risky": int(labels_a.sum()),
        "n_benign": int((labels_a == 0).sum()),
        "mean_offense_score_risky": round(float(risky_scores.mean()), 4)
        if len(risky_scores)
        else None,
        "mean_offense_score_benign": round(float(benign_scores.mean()), 4)
        if len(benign_scores)
        else None,
        "separation_auc": round(_auc(scores_a, labels_a), 4)
        if _auc(scores_a, labels_a) is not None
        else None,
        "evidence_type": "correlational (probe readout, no causal intervention)",
        "decisions": sorted(spans, key=lambda s: s["offense_score"], reverse=True),
    }
    out = run_dir / "mechinterp" / "readout.json"
    out.write_text(json.dumps(readout, indent=2), encoding="utf-8")
    print(
        f"[readout] {run_id}: risky mean {readout['mean_offense_score_risky']} vs benign {readout['mean_offense_score_benign']} | AUC {readout['separation_auc']} -> {out}"
    )
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m probes.readout <run_id>")
    main(sys.argv[1])
