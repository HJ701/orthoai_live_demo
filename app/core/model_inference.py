from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import sys
import time
from typing import Any, Dict, Iterable, List, Optional

from PIL import Image as PILImage

from app.config import settings as app_settings
from app.core.s3_storage import download_file_from_s3
from app.models import Image


_runtime = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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

    image_records = list(images)

    def load_one(image_record: Image) -> Any:
        raw = download_file_from_s3(image_record.file_path)
        with PILImage.open(BytesIO(raw)) as pil_image:
            pil_image.load()
            modality = _infer_modality(image_record.filename, image_record.content_type)
            return RuntimeImage(
                image=pil_image.copy(),
                source=image_record.filename,
                modality=modality,
                view=_infer_view(image_record.filename, modality) or "",
            )

    worker_count = min(
        max(app_settings.model_max_download_workers, 1),
        max(len(image_records), 1),
    )
    if worker_count == 1:
        return [load_one(image_record) for image_record in image_records]

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(load_one, image_records))


def predict_case_with_timings(patient_id: str, images: Iterable[Image]) -> tuple[Dict[str, Any], Dict[str, float]]:
    runtime_start = time.perf_counter()
    runtime = get_model_runtime()
    runtime_seconds = time.perf_counter() - runtime_start

    image_start = time.perf_counter()
    runtime_images = load_runtime_images(images)
    image_seconds = time.perf_counter() - image_start

    predict_start = time.perf_counter()
    prediction = runtime.predict(patient_id, runtime_images)
    predict_seconds = time.perf_counter() - predict_start

    return prediction, {
        "runtime_load_seconds": round(runtime_seconds, 3),
        "image_load_seconds": round(image_seconds, 3),
        "model_predict_seconds": round(predict_seconds, 3),
        "total_inference_seconds": round(
            runtime_seconds + image_seconds + predict_seconds,
            3,
        ),
    }


def predict_case(patient_id: str, images: Iterable[Image]) -> Dict[str, Any]:
    prediction, _timings = predict_case_with_timings(patient_id, images)
    return prediction
