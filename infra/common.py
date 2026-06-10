import pathlib

import modal

REPO = pathlib.Path(__file__).resolve().parent.parent
GPU = "A10G"
MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"


def build_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "torch==2.4.1",
            "transformers==4.49.0",
            "accelerate>=0.30",
            "mcp>=1.2.0",
            "scikit-learn>=1.3",
            "numpy>=1.26",
            "huggingface_hub>=0.23",
        )
        .env({"HF_HOME": "/cache", "AGENT_MODEL_ID": MODEL_ID, "PYTHONUNBUFFERED": "1"})
        .add_local_dir(
            str(REPO),
            remote_path="/root/app",
            copy=True,
            ignore=[".venv", ".git", "runs", "**/__pycache__", "*.log", ".pytest_cache"],
        )
    )
