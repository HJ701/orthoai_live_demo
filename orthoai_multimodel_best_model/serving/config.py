from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent


@dataclass(frozen=True)
class Settings:
    checkpoint_path: Path = Path(
        os.getenv("ORTHOAI_MODEL_CHECKPOINT", PACKAGE_ROOT / "weights" / "late_fusion_best.ckpt")
    )
    final_results_path: Path = Path(
        os.getenv("ORTHOAI_FINAL_RESULTS", PACKAGE_ROOT / "artifacts" / "final_results.json")
    )
    device: str = os.getenv("ORTHOAI_DEVICE", "cuda")
    require_rgb: bool = os.getenv("ORTHOAI_REQUIRE_RGB", "1") == "1"
    require_xray: bool = os.getenv("ORTHOAI_REQUIRE_XRAY", "1") == "1"


settings = Settings()

