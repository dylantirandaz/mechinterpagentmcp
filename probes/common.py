from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from agent.tool_calls import parse_tool_calls
from runner.policy import _should_flag, classify_call
from runner.scenarios import GRANTED_TOOLS, TOOL_RISK

PROBE_DIR = Path(__file__).resolve().parent
CONTRAST = PROBE_DIR / "contrast_set.jsonl"
PROBE_NPZ = PROBE_DIR / "cyber_probe.npz"


def load_contrast_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in CONTRAST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def contrast_texts_labels() -> tuple[list[str], np.ndarray]:
    rows = load_contrast_rows()
    return ([r["text"] for r in rows], np.array([int(r["label"]) for r in rows]))


def benign_offensive_texts() -> tuple[list[str], list[str]]:
    rows = load_contrast_rows()
    return (
        [r["text"] for r in rows if r["label"] == 0],
        [r["text"] for r in rows if r["label"] == 1],
    )


def emits(text: str, tool: str) -> bool:
    return re.search('"name"\\s*:\\s*"%s"' % re.escape(tool), text) is not None


def offensive_tool_names(text: str) -> list[str]:
    names = []
    for call in parse_tool_calls(text):
        if _should_flag(classify_call(call.name, call.arguments, GRANTED_TOOLS, TOOL_RISK)):
            names.append(call.name)
    return names


def load_probe() -> dict:
    p = np.load(PROBE_NPZ)
    best = int(p["best_layer"])
    return {
        "best": best,
        "coef": p[f"coef_{best}"],
        "mean": p[f"mean_{best}"],
        "scale": p[f"scale_{best}"],
        "intercept": float(p["intercepts"][best]),
        "cv_accuracy": float(p["accuracies"][best]),
    }
