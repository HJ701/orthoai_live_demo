from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from io import BytesIO
import os
from pathlib import Path
import time
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np
from PIL import Image as PILImage
from PIL import ImageOps

from app.config import settings
from app.core.image_metadata import infer_modality
from app.models import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DENTAL_LABELS: tuple[str, ...] = (
    "Caries",
    "Crown",
    "Filling",
    "Implant",
    "Malaligned",
    "Mandibular Canal",
    "Missing teeth",
    "Periapical lesion",
    "Retained root",
    "Root Canal Treatment",
    "Root Piece",
    "impacted tooth",
    "maxillary sinus",
    "Bone Loss",
    "Fracture teeth",
    "Permanent Teeth",
    "Supra Eruption",
    "TAD",
    "abutment",
    "attrition",
    "bone defect",
    "gingival former",
    "metal band",
    "orthodontic brackets",
    "permanent retainer",
    "post - core",
    "plating",
    "wire",
    "Cyst",
    "Root resorption",
    "Primary teeth",
)

DINO_COCO_SHA256 = "dca4f546e27803b2b6670b24c4f1de7805d747ff3d55b6b09e9dda72e4bb941b"
DINO_COCO_MODEL_ID = "dino-detr-r50-4scale-coco-epoch33"


class DentalSegmentationError(RuntimeError):
    """Raised when the dental segmentation output cannot be trusted."""


_runtime: Any = None


def _checkpoint_path() -> Path:
    configured = Path(settings.dental_segmentation_checkpoint)
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


@lru_cache(maxsize=4)
def sha256_file(path_value: str) -> str:
    digest = hashlib.sha256()
    with Path(path_value).open("rb") as checkpoint:
        for chunk in iter(lambda: checkpoint.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_names(names: Any) -> tuple[str, ...]:
    if isinstance(names, Mapping):
        try:
            return tuple(str(names[index]) for index in range(len(names)))
        except (KeyError, TypeError):
            return tuple(str(value) for _, value in sorted(names.items(), key=lambda item: int(item[0])))
    if isinstance(names, Sequence) and not isinstance(names, (str, bytes)):
        return tuple(str(value) for value in names)
    return ()


def get_dental_segmentation_runtime() -> Any:
    """Load and validate the deployed dental model once per worker process."""
    global _runtime
    if _runtime is not None:
        return _runtime

    checkpoint = _checkpoint_path()
    if not checkpoint.is_file():
        raise DentalSegmentationError(f"Dental segmentation checkpoint is missing: {checkpoint}")

    actual_sha256 = sha256_file(str(checkpoint))
    expected_sha256 = settings.dental_segmentation_expected_sha256.lower().strip()
    if not expected_sha256 or actual_sha256 != expected_sha256:
        raise DentalSegmentationError(
            "Dental segmentation checkpoint checksum mismatch; refusing to run inference. "
            f"expected={expected_sha256 or 'unset'} actual={actual_sha256}"
        )

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise DentalSegmentationError(
            "Ultralytics 8.3.0 is required to load the dental segmentation checkpoint."
        ) from exc

    try:
        runtime = YOLO(str(checkpoint), task="segment", verbose=False)
    except Exception as exc:
        raise DentalSegmentationError(f"Unable to load dental segmentation checkpoint: {exc}") from exc

    task = getattr(runtime, "task", None)
    if task != "segment":
        raise DentalSegmentationError(
            f"Expected an instance-segmentation checkpoint, but runtime task is {task!r}."
        )

    runtime_names = _normalise_names(getattr(runtime, "names", None))
    if runtime_names != DENTAL_LABELS:
        raise DentalSegmentationError(
            "Dental segmentation label schema mismatch; refusing to map predictions to clinical labels."
        )

    _runtime = runtime
    return _runtime


def _allowed_modalities() -> set[str]:
    return {
        value.strip().lower()
        for value in settings.dental_segmentation_modalities.split(",")
        if value.strip()
    }


def _load_eligible_image(image_record: Image) -> tuple[Image, PILImage.Image, str]:
    from app.core.s3_storage import download_file_from_s3

    modality = infer_modality(image_record.filename, image_record.content_type)
    raw = download_file_from_s3(image_record.file_path)
    try:
        with PILImage.open(BytesIO(raw)) as source:
            source.load()
            prepared = ImageOps.exif_transpose(source).convert("RGB").copy()
    except Exception as exc:
        raise DentalSegmentationError(
            f"Image {image_record.id} ({image_record.filename}) cannot be decoded: {exc}"
        ) from exc
    return image_record, prepared, modality


def _to_numpy(value: Any) -> np.ndarray:
    if value is None:
        return np.empty((0,), dtype=float)
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _simplify_polygon(points: Any, maximum_points: int = 256) -> list[list[float]]:
    array = _to_numpy(points)
    if array.ndim != 2 or array.shape[1] != 2 or len(array) == 0:
        return []
    if len(array) > maximum_points:
        indices = np.linspace(0, len(array) - 1, maximum_points, dtype=int)
        array = array[indices]
    return [[round(float(x), 6), round(float(y), 6)] for x, y in array]


def parse_segmentation_result(
    result: Any,
    *,
    image_id: int,
    filename: str,
    modality: str,
) -> Dict[str, Any]:
    """Convert one Ultralytics result into a stable, JSON-safe clinical contract."""
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        box_xyxy = np.empty((0, 4), dtype=float)
        box_xyxyn = np.empty((0, 4), dtype=float)
        confidences = np.empty((0,), dtype=float)
        class_ids = np.empty((0,), dtype=float)
    else:
        box_xyxy = _to_numpy(getattr(boxes, "xyxy", None)).reshape(-1, 4)
        box_xyxyn = _to_numpy(getattr(boxes, "xyxyn", None)).reshape(-1, 4)
        confidences = _to_numpy(getattr(boxes, "conf", None)).reshape(-1)
        class_ids = _to_numpy(getattr(boxes, "cls", None)).reshape(-1)

    detection_count = len(confidences)
    if not (len(box_xyxy) == len(box_xyxyn) == len(class_ids) == detection_count):
        raise DentalSegmentationError("Segmentation result tensors have inconsistent instance counts.")

    masks = getattr(result, "masks", None)
    if detection_count and masks is None:
        raise DentalSegmentationError(
            "The dental model returned boxes without instance masks; refusing to publish partial output."
        )

    mask_data = _to_numpy(getattr(masks, "data", None)) if masks is not None else np.empty((0, 0, 0))
    if detection_count and (mask_data.ndim != 3 or len(mask_data) != detection_count):
        raise DentalSegmentationError("Segmentation mask count does not match the detected instances.")

    polygons = getattr(masks, "xyn", []) if masks is not None else []
    if polygons is None:
        polygons = []

    orig_shape = getattr(result, "orig_shape", None)
    if not orig_shape or len(orig_shape) < 2:
        orig_image = getattr(result, "orig_img", None)
        orig_shape = getattr(orig_image, "shape", None)
    if not orig_shape or len(orig_shape) < 2:
        raise DentalSegmentationError("Segmentation result is missing the original image dimensions.")
    height, width = int(orig_shape[0]), int(orig_shape[1])
    image_pixels = width * height

    detections: list[dict[str, Any]] = []
    for index in range(detection_count):
        class_id = int(class_ids[index])
        if class_id < 0 or class_id >= len(DENTAL_LABELS):
            raise DentalSegmentationError(f"Out-of-schema dental class id returned: {class_id}")

        x1, y1, x2, y2 = (float(value) for value in box_xyxy[index])
        nx1, ny1, nx2, ny2 = (float(value) for value in box_xyxyn[index])
        mask_fraction = float(np.count_nonzero(mask_data[index]) / mask_data[index].size)
        mask_area_pixels = int(round(mask_fraction * image_pixels))
        polygon = _simplify_polygon(polygons[index]) if index < len(polygons) else []

        detections.append(
            {
                "instance_id": index + 1,
                "class_id": class_id,
                "coco_category_id": class_id + 1,
                "label": DENTAL_LABELS[class_id],
                "confidence": round(float(confidences[index]), 6),
                "bbox_pixels": {
                    "x": round(x1, 2),
                    "y": round(y1, 2),
                    "width": round(max(0.0, x2 - x1), 2),
                    "height": round(max(0.0, y2 - y1), 2),
                },
                "bbox_normalized": {
                    "x1": round(nx1, 6),
                    "y1": round(ny1, 6),
                    "x2": round(nx2, 6),
                    "y2": round(ny2, 6),
                },
                "mask_area_pixels": mask_area_pixels,
                "mask_area_percent": round(mask_fraction * 100.0, 4),
                "polygon_normalized": polygon,
            }
        )

    return {
        "image_id": image_id,
        "filename": filename,
        "modality": modality,
        "status": "completed",
        "width_pixels": width,
        "height_pixels": height,
        "detection_count": detection_count,
        "detections": detections,
    }


def summarise_segmentations(per_image: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "confidences": [],
            "mask_area_percents": [],
            "mask_area_pixels": 0,
            "image_ids": set(),
        }
    )
    completed = 0
    skipped = 0
    total_instances = 0

    for image_result in per_image:
        if image_result.get("status") == "completed":
            completed += 1
        else:
            skipped += 1
        for detection in image_result.get("detections", []):
            class_id = int(detection["class_id"])
            bucket = grouped[class_id]
            bucket["confidences"].append(float(detection["confidence"]))
            bucket["mask_area_percents"].append(float(detection["mask_area_percent"]))
            bucket["mask_area_pixels"] += int(detection["mask_area_pixels"])
            bucket["image_ids"].add(int(image_result["image_id"]))
            total_instances += 1

    class_summaries: list[dict[str, Any]] = []
    for class_id in sorted(grouped):
        bucket = grouped[class_id]
        confidences = bucket["confidences"]
        areas = bucket["mask_area_percents"]
        class_summaries.append(
            {
                "class_id": class_id,
                "coco_category_id": class_id + 1,
                "label": DENTAL_LABELS[class_id],
                "instance_count": len(confidences),
                "image_count": len(bucket["image_ids"]),
                "mean_confidence": round(sum(confidences) / len(confidences), 6),
                "max_confidence": round(max(confidences), 6),
                "summed_mask_area_pixels": bucket["mask_area_pixels"],
                "mean_instance_area_percent": round(sum(areas) / len(areas), 4),
                "max_instance_area_percent": round(max(areas), 4),
            }
        )

    return {
        "images_completed": completed,
        "images_skipped": skipped,
        "total_instances": total_instances,
        "classes_present": len(class_summaries),
        "classes": class_summaries,
    }


def dental_model_provenance(*, model_run_id: str, created_at: str) -> Dict[str, Any]:
    checkpoint = _checkpoint_path()
    return {
        "model_run_id": model_run_id,
        "model_id": "dental-yolov8-seg-31",
        "semantic_version": settings.dental_segmentation_model_version,
        "task": "instance_segmentation",
        "framework": "ultralytics",
        "framework_version": "8.3.0",
        "artifact_sha256": sha256_file(str(checkpoint)),
        "label_schema_version": settings.dental_segmentation_label_schema_version,
        "calibration_version": None,
        "preprocessing_version": settings.dental_segmentation_preprocessing_version,
        "build_commit": settings.build_commit,
        "created_at": created_at,
    }


def dino_initialization_only_record() -> Dict[str, Any]:
    return {
        "status": "not_deployed",
        "reason": (
            "COCO initialization checkpoint only. Dental fine-tuning, calibration, and validation "
            "are required before it may enter the inference path."
        ),
        "provenance": {
            "model_id": DINO_COCO_MODEL_ID,
            "task": "object_detection",
            "architecture": "DINO-DETR ResNet-50 4-scale",
            "training_dataset": "COCO 2017",
            "class_count": 91,
            "artifact_sha256": DINO_COCO_SHA256,
            "deployment_eligible": False,
        },
    }


def predict_dental_segmentations(
    images: Iterable[Image],
    *,
    model_run_id: str,
) -> tuple[Dict[str, Any], Dict[str, float]]:
    started_at = datetime.now(timezone.utc).isoformat()
    runtime_start = time.perf_counter()
    runtime = get_dental_segmentation_runtime()
    runtime_seconds = time.perf_counter() - runtime_start

    image_records = list(images)
    allowed = _allowed_modalities()
    eligible: list[Image] = []
    per_image_by_id: dict[int, Dict[str, Any]] = {}
    for image_record in image_records:
        modality = infer_modality(image_record.filename, image_record.content_type)
        if modality in allowed:
            eligible.append(image_record)
        else:
            per_image_by_id[image_record.id] = {
                "image_id": image_record.id,
                "filename": image_record.filename,
                "modality": modality,
                "status": "skipped",
                "skip_reason": "modality_not_in_validated_scope",
                "detection_count": 0,
                "detections": [],
            }

    if not eligible:
        raise DentalSegmentationError(
            "No image is explicitly identified as an xray; dental segmentation was not run. "
            "Use an OPG/xray/panoramic/ceph filename or configure the validated modality scope."
        )

    image_start = time.perf_counter()
    worker_count = min(max(settings.model_max_download_workers, 1), len(eligible))
    if worker_count == 1:
        loaded = [_load_eligible_image(image) for image in eligible]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            loaded = list(executor.map(_load_eligible_image, eligible))
    image_seconds = time.perf_counter() - image_start

    predict_kwargs: dict[str, Any] = {
        "source": [pil_image for _, pil_image, _ in loaded],
        "imgsz": settings.dental_segmentation_imgsz,
        "conf": settings.dental_segmentation_confidence,
        "iou": settings.dental_segmentation_iou,
        "max_det": settings.dental_segmentation_max_detections,
        "verbose": False,
        "save": False,
    }
    device = settings.dental_segmentation_device.strip() or os.getenv("ORTHOAI_DEVICE", "").strip()
    if device:
        predict_kwargs["device"] = device

    predict_start = time.perf_counter()
    try:
        raw_results = list(runtime.predict(**predict_kwargs))
    except Exception as exc:
        raise DentalSegmentationError(f"Dental segmentation inference failed: {exc}") from exc
    predict_seconds = time.perf_counter() - predict_start

    if len(raw_results) != len(loaded):
        raise DentalSegmentationError(
            f"Dental segmentation returned {len(raw_results)} results for {len(loaded)} images."
        )

    for raw_result, (image_record, _, modality) in zip(raw_results, loaded):
        per_image_by_id[image_record.id] = parse_segmentation_result(
            raw_result,
            image_id=image_record.id,
            filename=image_record.filename,
            modality=modality,
        )

    per_image = [per_image_by_id[image.id] for image in image_records]
    finished_at = datetime.now(timezone.utc).isoformat()
    timings = {
        "runtime_load_seconds": round(runtime_seconds, 3),
        "image_load_seconds": round(image_seconds, 3),
        "model_predict_seconds": round(predict_seconds, 3),
        "total_inference_seconds": round(runtime_seconds + image_seconds + predict_seconds, 3),
    }
    output = {
        "status": "completed",
        "started_at": started_at,
        "completed_at": finished_at,
        "provenance": dental_model_provenance(model_run_id=model_run_id, created_at=finished_at),
        "parameters": {
            "confidence_threshold": settings.dental_segmentation_confidence,
            "iou_threshold": settings.dental_segmentation_iou,
            "image_size": settings.dental_segmentation_imgsz,
            "max_detections": settings.dental_segmentation_max_detections,
            "validated_modalities": sorted(allowed),
        },
        "quantitative_summary": summarise_segmentations(per_image),
        "per_image": per_image,
        "timings": timings,
        "interpretation": {
            "confidence": "Uncalibrated model score; not a probability of disease.",
            "mask_area_pixels": "Estimated image-plane area after scaling the binary mask fraction to original pixels.",
            "mask_area_percent": "Percentage of image plane occupied by one instance mask; not a physical area.",
            "clinical_use": "Decision support only. Every instance requires clinician review.",
        },
    }
    return output, timings
