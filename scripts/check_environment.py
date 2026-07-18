from __future__ import annotations

import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models/bertopic_apex_exploratory_v1/bertopic_model.pkl"
REGISTRY = ROOT / "models/bertopic_apex_exploratory_v1/topic_registry_exploratory.json"
CORPUS = ROOT / "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv"


def version(name: str):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def main() -> int:
    checks = {}
    for module in ["bertopic", "umap", "hdbscan", "sklearn", "numpy", "pandas", "jieba"]:
        try:
            __import__(module)
            checks[module] = {"import_ok": True}
        except Exception as exc:
            checks[module] = {"import_ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        import pickle
        with MODEL.open("rb") as f:
            model = pickle.load(f)
        checks["saved_model"] = {"load_ok": True, "class": f"{type(model).__module__}.{type(model).__name__}", "calculate_probabilities": getattr(model, "calculate_probabilities", None), "embedding_model": type(getattr(model, "embedding_model", None)).__name__}
    except Exception as exc:
        checks["saved_model"] = {"load_ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result = {
        "python": sys.version,
        "platform": platform.platform(),
        "project_root": ".",
        "packages": {name: version(name) for name in ["bertopic", "umap-learn", "hdbscan", "scikit-learn", "numpy", "pandas", "jieba", "snownlp"]},
        "checks": checks,
        "paths": {"model": "models/bertopic_apex_exploratory_v1/bertopic_model.pkl", "registry": "models/bertopic_apex_exploratory_v1/topic_registry_exploratory.json", "corpus": "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv"},
        "portable_path_policy": "all runtime paths are resolved relative to the repository root; no account, token, cookie, or personal absolute path is required",
    }
    out = ROOT / "outputs/environment_check.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if checks.get("saved_model", {}).get("load_ok") and all(v.get("import_ok") for k, v in checks.items() if k != "saved_model") else 1


if __name__ == "__main__":
    raise SystemExit(main())
