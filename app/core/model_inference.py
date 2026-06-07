from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional

from PIL import Image as PILImage

from app.core.s3_storage import download_file_from_s3
from app.models import Image


_runtime = None


def _infer_modality(filename: str, content_type: Optional[str]) -> str:
    value = (filename or "").lower()
    if any(token in value for token in ("opg", "xray", "x-ray", "panoramic", "ceph")):
        return "xray"
    return "rgb"


def _infer_view(filename: str, modality: str) -> Optional[str]:
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


def get_model_runtime():
    global _runtime
    if _runtime is not None:
        return _runtime

    try:
        from orthoai_multimodel_best_model.serving.config import settings as model_settings
        from orthoai_multimodel_best_model.serving.model_runtime import (
            OrthoPatientFusionRuntime,
        )
    except ImportError as exc:
        raise RuntimeError(
            "OrthoAI multimodal runtime dependencies are incomplete. "
            "Install torch/torchvision and make sure the serving-time model source is present. "
            "The current runtime requires OrthoPatientFusion/ortho_patient_fusion_core.py plus "
            "the src modules it imports, including data_pipeline.py and train_exp1_6_malocclusion.py. "
            f"Import error: {exc!r}"
        ) from exc

    runtime = OrthoPatientFusionRuntime(model_settings)
    runtime.load()
    _runtime = runtime
    return _runtime


def load_runtime_images(images: Iterable[Image]) -> List[Any]:
    try:
        from orthoai_multimodel_best_model.serving.model_runtime import RuntimeImage
    except ImportError as exc:
        raise RuntimeError(
            "OrthoAI multimodal runtime source is unavailable; cannot construct runtime images."
        ) from exc

    runtime_images: List[Any] = []
    for image_record in images:
        raw = download_file_from_s3(image_record.file_path)
        with PILImage.open(BytesIO(raw)) as pil_image:
            pil_image.load()
            modality = _infer_modality(image_record.filename, image_record.content_type)
            runtime_images.append(
                RuntimeImage(
                    image=pil_image.copy(),
                    source=image_record.filename,
                    modality=modality,
                    view=_infer_view(image_record.filename, modality) or "",
                )
            )
    return runtime_images


def predict_case(patient_id: str, images: Iterable[Image]) -> Dict[str, Any]:
    runtime = get_model_runtime()
    runtime_images = load_runtime_images(images)
    return runtime.predict(patient_id, runtime_images)
