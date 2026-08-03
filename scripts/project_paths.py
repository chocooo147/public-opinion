"""Resolve external APEX data/model roots from project configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_project_paths(project_root: Path) -> dict[str, Any]:
    path = project_root / "config/project_paths.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["_path"] = str(path)
    return payload


def configured_root(project_root: Path, key: str) -> Path:
    config = load_project_paths(project_root)
    environment_key = config.get("environment_overrides", {}).get(key)
    configured = os.environ.get(environment_key, "") if environment_key else ""
    value = configured or str(config[key])
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def resolve_project_asset(project_root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "models":
        return configured_root(project_root, "model_root").joinpath(*parts[1:])
    if parts and parts[0] == "data":
        return configured_root(project_root, "data_root").joinpath(*parts[1:])
    if parts and parts[0] == "outputs":
        return configured_root(project_root, "historical_output_root").joinpath(*parts[1:])
    return (project_root / path).resolve()
