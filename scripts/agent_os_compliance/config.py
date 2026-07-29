from __future__ import annotations

import tomllib
from pathlib import Path

from .models import ComplianceConfig


DEFAULT_CONFIG = ".agent-os-compliance.toml"


def load_config(root: Path, path: str = DEFAULT_CONFIG) -> ComplianceConfig:
    config_path = root / path
    if not config_path.is_file():
        raise FileNotFoundError(f"Compliance configuration not found: {config_path}")
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise ValueError("Unsupported compliance configuration version")
    return ComplianceConfig(root=root, raw=raw, path=path)
