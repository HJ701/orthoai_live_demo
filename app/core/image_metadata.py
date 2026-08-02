from __future__ import annotations

from typing import Optional


def infer_modality(filename: str, content_type: Optional[str]) -> str:
    value = (filename or "").lower()
    if any(token in value for token in ("opg", "xray", "x-ray", "panoramic", "ceph")):
        return "xray"
    return "rgb"


def infer_view(filename: str, modality: str) -> Optional[str]:
    if modality == "xray":
        return "opg"
    value = (filename or "").lower().replace("-", "_").replace(" ", "_")
    if "front" in value or "frontal" in value:
        return "frontal"
    if "left" in value and "buccal" in value:
        return "buccal_left"
    if "right" in value and "buccal" in value:
        return "buccal_right"
    if "upper" in value or "maxillary" in value:
        return "occlusal_maxillary"
    if "lower" in value or "mandibular" in value:
        return "occlusal_mandibular"
    if "occlusal" in value:
        return "occlusal"
    if "buccal" in value:
        return "buccal"
    return None
