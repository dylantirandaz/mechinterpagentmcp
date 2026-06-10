from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

from agent.model_runtime import AgentModel
from probes.common import CONTRAST, contrast_texts_labels

PROBE_DIR = Path(__file__).resolve().parent
CV_FOLDS = 5


def _capture_all(model: AgentModel, texts: list[str]) -> np.ndarray:
    acts = []
    for i, text in enumerate(texts):
        messages = [{"role": "user", "content": text}]
        acts.append(model.residual_at_decision(messages, tools=None))
        if (i + 1) % 10 == 0:
            print(f"  captured {i + 1}/{len(texts)}", flush=True)
    return np.stack(acts)


def _fit_layer(x: np.ndarray, y: np.ndarray) -> tuple[dict, float]:
    scaler = StandardScaler().fit(x)
    xs = scaler.transform(x)
    clf = LogisticRegression(max_iter=2000, C=1.0)
    cv = float(np.mean(cross_val_score(clf, xs, y, cv=CV_FOLDS, scoring="accuracy")))
    clf.fit(xs, y)
    layer = {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
    }
    return (layer, cv)


def main() -> None:
    if not CONTRAST.exists():
        raise SystemExit("contrast_set.jsonl missing — run probes.make_contrast_set first")
    texts, labels = contrast_texts_labels()
    print(f"[probe] loading model and capturing {len(texts)} activations...", flush=True)
    model = AgentModel()
    acts = _capture_all(model, texts)
    num_layers = acts.shape[1]
    layers, accuracies = ([], [])
    for layer_idx in range(num_layers):
        layer, cv = _fit_layer(acts[:, layer_idx, :], labels)
        layers.append(layer)
        accuracies.append(cv)
        print(f"  layer {layer_idx:2d} CV-acc {cv:.3f}", flush=True)
    best_layer = int(np.argmax(accuracies))
    np.savez_compressed(
        PROBE_DIR / "cyber_probe.npz",
        **{f"coef_{i}": np.array(L["coef"]) for i, L in enumerate(layers)},
        **{f"mean_{i}": np.array(L["mean"]) for i, L in enumerate(layers)},
        **{f"scale_{i}": np.array(L["scale"]) for i, L in enumerate(layers)},
        intercepts=np.array([L["intercept"] for L in layers]),
        accuracies=np.array(accuracies),
        best_layer=np.array(best_layer),
    )
    report = {
        "model": model.model_id,
        "n_examples": len(texts),
        "n_offensive": int(labels.sum()),
        "n_benign": int((labels == 0).sum()),
        "cv_folds": CV_FOLDS,
        "per_layer_cv_accuracy": {str(i): round(a, 4) for i, a in enumerate(accuracies)},
        "best_layer": best_layer,
        "best_layer_cv_accuracy": round(accuracies[best_layer], 4),
    }
    (PROBE_DIR / "cyber_probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"[probe] best layer {best_layer} acc {accuracies[best_layer]:.3f} -> cyber_probe.npz/json",
        flush=True,
    )


if __name__ == "__main__":
    main()
