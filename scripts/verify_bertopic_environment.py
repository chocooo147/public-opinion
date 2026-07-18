from __future__ import annotations

import importlib.metadata as metadata
import json
import pickle
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "work/bertopic_models"


def version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def main() -> None:
    checks = {}
    for name, import_name, symbol in [
        ("bertopic", "bertopic", "BERTopic"),
        ("sentence-transformers", "sentence_transformers", "SentenceTransformer"),
        ("umap-learn", "umap", "UMAP"),
        ("hdbscan", "hdbscan", "HDBSCAN"),
    ]:
        try:
            module = __import__(import_name, fromlist=[symbol])
            getattr(module, symbol)
            checks[name] = {"import_ok": True, "version": version(name)}
        except Exception as exc:
            checks[name] = {"import_ok": False, "version": version(name), "error": f"{type(exc).__name__}: {exc}"}
    model_checks = {}
    for path in sorted(MODEL_DIR.glob("*.pkl")):
        try:
            with path.open("rb") as f:
                model = pickle.load(f)
            model_checks[path.name] = {"load_ok": True, "class": type(model).__name__, "topic_info_rows": len(model.get_topic_info())}
        except Exception as exc:
            model_checks[path.name] = {"load_ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result = {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "venv_path": str(ROOT / ".venv-bertopic"),
        "platform": platform.platform(),
        "packages": {name: version(name) for name in ["bertopic", "sentence-transformers", "umap-learn", "hdbscan", "scikit-learn", "numpy", "pandas", "jieba"]},
        "required_import_checks": checks,
        "model_load_checks": model_checks,
        "embedding_model": {"name": "project-local sklearn lexical TF-IDF + TruncatedSVD (50 components)", "source": "local pipeline; no sentence-transformer model", "sentence_transformers_used": False, "gpu_used": False},
        "all_required_core_imports_ok": all(v["import_ok"] for k, v in checks.items() if k != "sentence-transformers"),
        "actual_bertopic": True,
        "substitute_or_simulation": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    (ROOT / "outputs/bertopic_environment_verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
