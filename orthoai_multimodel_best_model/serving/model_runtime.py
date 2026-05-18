from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import torch
from PIL import Image

from .config import REPO_ROOT, Settings


if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from OrthoPatientFusion.ortho_patient_fusion_core import (  # noqa: E402
    MODALITY_TO_ID,
    VIEW_NAMES,
    VIEW_TO_ID,
    PatientFusionModel,
    apply_preprocess,
    build_eval_transform,
    build_preprocess_cfg_opg,
    build_preprocess_cfg_rgb,
)


@dataclass(frozen=True)
class RuntimeImage:
    image: Image.Image
    source: str
    modality: str
    view: str


def _safe_args(args: Dict[str, Any], key: str, default: Any) -> Any:
    value = args.get(key, default)
    return default if value is None else value


def normalize_modality(modality: str) -> str:
    value = modality.strip().lower()
    if value in {"opg", "x-ray", "xray", "panoramic", "panoramic_xray"}:
        return "xray"
    if value in {"rgb", "intraoral", "photo", "image"}:
        return "rgb"
    raise ValueError(f"Unsupported modality '{modality}'. Expected 'rgb' or 'xray'.")


def normalize_view(view: Optional[str], modality: str, source: str = "") -> str:
    if modality == "xray":
        return "opg"
    raw = (view or source or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return "intraoral_other"
    if raw in VIEW_TO_ID:
        return raw
    if "front" in raw or "frontal" in raw or "anterior" in raw:
        return "frontal"
    if "left" in raw and "buccal" in raw:
        return "buccal_left"
    if "right" in raw and "buccal" in raw:
        return "buccal_right"
    if "buccal" in raw or "side" in raw:
        return "buccal"
    if "maxillary" in raw or "upper" in raw:
        return "occlusal_maxillary"
    if "mandibular" in raw or "lower" in raw:
        return "occlusal_mandibular"
    if "occlusal" in raw:
        return "occlusal"
    return "intraoral_other"


class OrthoPatientFusionRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = torch.device(settings.device if settings.device != "cuda" or torch.cuda.is_available() else "cpu")
        self.checkpoint_path = settings.checkpoint_path.resolve()
        self.final_results_path = settings.final_results_path.resolve()
        self.model: Optional[PatientFusionModel] = None
        self.class_names: List[str] = []
        self.checkpoint_args: Dict[str, Any] = {}
        self.final_results: Dict[str, Any] = {}
        self.rgb_preprocess = build_preprocess_cfg_rgb()
        self.xray_preprocess = build_preprocess_cfg_opg()
        self.transform = None

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {self.checkpoint_path}")
        if self.checkpoint_path.stat().st_size == 0:
            raise RuntimeError(f"Checkpoint is empty: {self.checkpoint_path}")

        checkpoint = torch.load(self.checkpoint_path, map_location="cpu")
        self.checkpoint_args = dict(checkpoint.get("args", {}))
        self.class_names = list(checkpoint.get("class_names", ["0", "1", "2"]))
        image_size = int(_safe_args(self.checkpoint_args, "image_size", 224))
        self.transform = build_eval_transform(image_size)

        model = PatientFusionModel(
            experiment=str(_safe_args(self.checkpoint_args, "experiment", "late_fusion")),
            num_classes=len(self.class_names),
            image_size=image_size,
            opg_encoder_name=str(_safe_args(self.checkpoint_args, "opg_encoder_name", "convnext_tiny")),
            rgb_encoder_name=str(_safe_args(self.checkpoint_args, "rgb_encoder_name", "convnext_tiny")),
            # The checkpoint supplies trained weights, so random init avoids
            # network-dependent ImageNet downloads during API startup.
            encoder_init_source="random",
            token_dim=int(_safe_args(self.checkpoint_args, "token_dim", 512)),
            fusion_layers=int(_safe_args(self.checkpoint_args, "fusion_layers", 2)),
            fusion_heads=int(_safe_args(self.checkpoint_args, "fusion_heads", 8)),
            diagnosis_queries=int(_safe_args(self.checkpoint_args, "diagnosis_queries", 1)),
            dropout=float(_safe_args(self.checkpoint_args, "dropout", 0.25)),
            shared_encoder=bool(_safe_args(self.checkpoint_args, "shared_encoder", False)),
        )
        load_result = model.load_state_dict(checkpoint["model_state_dict"], strict=False)
        allowed_missing_prefixes = ("query_patient_head.",)
        disallowed_missing = [
            key for key in load_result.missing_keys
            if not key.startswith(allowed_missing_prefixes)
        ]
        if disallowed_missing or load_result.unexpected_keys:
            raise RuntimeError(
                "Checkpoint is not compatible with the serving architecture. "
                f"Missing={disallowed_missing}, unexpected={load_result.unexpected_keys}"
            )
        model.to(self.device)
        model.eval()
        self.model = model

        if self.final_results_path.exists():
            with self.final_results_path.open() as f:
                self.final_results = json.load(f)

    def model_info(self) -> Dict[str, Any]:
        return {
            "experiment_id": "1.7",
            "experiment_name": "OrthoPatientFusion",
            "fusion_experiment": self.checkpoint_args.get("experiment", "late_fusion"),
            "checkpoint_path": str(self.checkpoint_path),
            "class_names": self.class_names,
            "device": str(self.device),
            "best_val_macro_f1": self.final_results.get("best_val_macro_f1"),
            "test_metrics_best_model": self.final_results.get("test_metrics_best_model"),
        }

    def _validate_images(self, images: Sequence[RuntimeImage]) -> None:
        if not images:
            raise ValueError("At least one image is required.")
        modalities = {image.modality for image in images}
        if self.settings.require_rgb and "rgb" not in modalities:
            raise ValueError("At least one rgb intraoral image is required by this deployed model.")
        if self.settings.require_xray and "xray" not in modalities:
            raise ValueError("At least one xray/OPG image is required by this deployed model.")

    def _select_images(self, images: Sequence[RuntimeImage]) -> List[RuntimeImage]:
        max_images_per_patient = int(_safe_args(self.checkpoint_args, "max_images_per_patient", 8))
        max_images_per_view = int(_safe_args(self.checkpoint_args, "max_images_per_view", 2))

        by_view: Dict[str, List[RuntimeImage]] = {}
        for image in images:
            by_view.setdefault(image.view, []).append(image)

        selected: List[RuntimeImage] = []
        for view in VIEW_NAMES:
            view_images = sorted(by_view.get(view, []), key=lambda item: item.source)
            selected.extend(view_images[: max(1, max_images_per_view)])

        selected.sort(key=lambda item: (0 if item.modality == "xray" else 1, VIEW_TO_ID.get(item.view, 999), item.source))

        if max_images_per_patient > 0 and len(selected) > max_images_per_patient:
            opg = [item for item in selected if item.modality == "xray"]
            rest = [item for item in selected if item.modality != "xray"]
            selected = (opg[:1] + rest)[:max_images_per_patient]

        return selected

    def _tensorize(self, images: Sequence[RuntimeImage]) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, List[Dict[str, str]]]:
        if self.transform is None:
            raise RuntimeError("Runtime is not loaded.")
        tensors: List[torch.Tensor] = []
        view_ids: List[int] = []
        modality_ids: List[int] = []
        used: List[Dict[str, str]] = []

        for item in images:
            pil_image = item.image.convert("RGB")
            cfg = self.xray_preprocess if item.modality == "xray" else self.rgb_preprocess
            pil_image = apply_preprocess(pil_image, cfg, dataset_name=item.modality)
            tensors.append(self.transform(pil_image))
            view_ids.append(VIEW_TO_ID.get(item.view, VIEW_TO_ID["intraoral_other"]))
            modality_ids.append(MODALITY_TO_ID[item.modality])
            used.append({"source": item.source, "modality": item.modality, "view": item.view})

        return (
            torch.stack(tensors, dim=0),
            torch.tensor(view_ids, dtype=torch.long),
            torch.tensor(modality_ids, dtype=torch.long),
            used,
        )

    @torch.no_grad()
    def predict(self, patient_id: str, images: Sequence[RuntimeImage]) -> Dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Model is not loaded.")

        normalized: List[RuntimeImage] = []
        for item in images:
            modality = normalize_modality(item.modality)
            normalized.append(
                RuntimeImage(
                    image=item.image,
                    source=item.source,
                    modality=modality,
                    view=normalize_view(item.view, modality, item.source),
                )
            )
        self._validate_images(normalized)
        selected = self._select_images(normalized)
        image_tensor, view_ids, modality_ids, used = self._tensorize(selected)

        image_tensor = image_tensor.to(self.device, non_blocking=True)
        view_ids = view_ids.to(self.device, non_blocking=True)
        modality_ids = modality_ids.to(self.device, non_blocking=True)
        patient_index = torch.zeros((image_tensor.shape[0],), dtype=torch.long, device=self.device)

        logits, _aux = self.model(
            image_tensor,
            patient_index,
            view_ids,
            modality_ids,
            batch_size=1,
        )
        probs = torch.softmax(logits, dim=1).squeeze(0).detach().cpu()
        predicted_index = int(torch.argmax(probs).item())
        probabilities = [
            {"class_name": class_name, "probability": float(probs[idx].item())}
            for idx, class_name in enumerate(self.class_names)
        ]

        return {
            "patient_id": patient_id,
            "predicted_class": self.class_names[predicted_index],
            "predicted_index": predicted_index,
            "confidence": float(probs[predicted_index].item()),
            "probabilities": probabilities,
            "images_used": used,
            "model": self.model_info(),
        }


def load_images_from_paths(items: Iterable[Dict[str, Any]]) -> List[RuntimeImage]:
    loaded: List[RuntimeImage] = []
    for item in items:
        path = Path(str(item["image_path"])).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Image path not found: {path}")
        with Image.open(path) as image:
            image.load()
            loaded.append(
                RuntimeImage(
                    image=image.copy(),
                    source=str(path),
                    modality=normalize_modality(str(item["modality"])),
                    view=normalize_view(item.get("view"), normalize_modality(str(item["modality"])), str(path)),
                )
            )
    return loaded
