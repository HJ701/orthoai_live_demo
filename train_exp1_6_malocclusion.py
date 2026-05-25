#!/usr/bin/env python3
"""
Experiment 1.6 - Multi-encoder fusion for malocclusion classification.

Implements the architecture and training plan described in experiment_1_6_architecture (1).jsx:
  - Load elected checkpoints from Exp 1.2/1.3/1.4/1.5
  - Extract per-encoder features and project to 768-dim
  - Fuse with attention/concat/gating
  - End-to-end training with differential learning rates
  - Patient-disjoint split and ablation-ready controls

Primary outputs:
  - train_log.jsonl (epoch progress)
  - final_results.json (best-val + test metrics + CI)
  - graphs/*.png (if matplotlib is available)
  - exp1_6_fusion.ckpt (deliverable)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import random
import time
from collections import Counter
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models
from torchvision import transforms as T
from torchvision.transforms import InterpolationMode

from data_pipeline import apply_preprocess, build_preprocess_config

try:
    from tqdm import tqdm as _tqdm
except Exception:
    _tqdm = None


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def _progress(iterable: Iterable, total: Optional[int] = None, desc: str = "") -> Iterable:
    if _tqdm is None:
        return iterable
    return _tqdm(iterable, total=total, desc=desc, leave=False)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def resolve_path(path_str: str, repo_root: Path) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p.resolve()
    return (repo_root / p).resolve()


def safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def to_json_compatible(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_json_compatible(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json_compatible(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if torch.is_tensor(obj):
        return obj.detach().cpu().tolist()
    if hasattr(obj, "name") and isinstance(getattr(obj, "name"), str):
        return str(obj.name)
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def save_jsonl(path: Path, record: Dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(to_json_compatible(record)) + "\n")


def save_checkpoint(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, path)


class _TorchCompatWeightsEnumProxy:
    def __new__(cls, value):
        # Older checkpoints may serialize torchvision enum instances whose concrete enum
        # members do not exist in the currently installed torchvision build. For inference
        # we only need the tensor state dicts, so preserving the raw value is sufficient.
        return value


class _TorchCompatUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if module.startswith("torchvision.models.") and name.endswith("_Weights"):
            return _TorchCompatWeightsEnumProxy
        return super().find_class(module, name)


class _TorchCompatPickleModule:
    Unpickler = _TorchCompatUnpickler
    Pickler = pickle.Pickler
    HIGHEST_PROTOCOL = pickle.HIGHEST_PROTOCOL
    DEFAULT_PROTOCOL = pickle.DEFAULT_PROTOCOL
    load = staticmethod(pickle.load)
    loads = staticmethod(pickle.loads)
    dump = staticmethod(pickle.dump)
    dumps = staticmethod(pickle.dumps)


_TORCHVISION_ENUM_PATCHED = False


def _patch_torchvision_weight_enums() -> None:
    global _TORCHVISION_ENUM_PATCHED
    if _TORCHVISION_ENUM_PATCHED:
        return

    candidates = []
    try:
        from torchvision.models.detection.faster_rcnn import FasterRCNN_ResNet50_FPN_V2_Weights
        from torchvision.models.detection.faster_rcnn import FasterRCNN_ResNet50_FPN_Weights

        candidates.extend([FasterRCNN_ResNet50_FPN_Weights, FasterRCNN_ResNet50_FPN_V2_Weights])
    except Exception:
        pass

    for enum_cls in candidates:
        if getattr(enum_cls, "_orthoai_missing_patch", False):
            continue
        original_missing = getattr(enum_cls, "_missing_", None)

        @classmethod
        def _patched_missing(cls, value, _original=original_missing):
            if hasattr(value, "url"):
                default = getattr(cls, "DEFAULT", None)
                if default is not None:
                    return default
                members = list(cls)
                if members:
                    return members[0]
            if _original is not None:
                return _original(value)
            return None

        enum_cls._missing_ = _patched_missing
        enum_cls._orthoai_missing_patch = True

    _TORCHVISION_ENUM_PATCHED = True


def load_checkpoint(path: Path, map_location: str = "cpu") -> Dict[str, Any]:
    _patch_torchvision_weight_enums()
    return torch.load(path, map_location=map_location, pickle_module=_TorchCompatPickleModule)


def write_samples_jsonl(path: Path, samples: Sequence["Sample"], root_anchor: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for s in samples:
            rec = {
                "image_path": str(s.image_path),
                "label": s.label_name,
                "label_idx": s.label_idx,
                "patient_id": s.patient_id,
                "modality": s.modality,
                "split": s.split,
            }
            try:
                rec["image_path"] = str(s.image_path.relative_to(root_anchor))
            except Exception:
                pass
            f.write(json.dumps(rec) + "\n")


def _is_image_path(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS and not path.name.startswith(".")


def parse_float_csv(text: str, n_expected: int) -> List[float]:
    vals: List[float] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        vals.append(float(tok))
    if len(vals) != n_expected:
        raise ValueError(f"Expected {n_expected} comma-separated values, got {len(vals)}: {text}")
    return vals


def split_ratios_from_text(text: str) -> Tuple[float, float, float]:
    a, b, c = parse_float_csv(text, 3)
    total = a + b + c
    if total <= 0.0:
        raise ValueError("Split ratios must sum to > 0")
    return a / total, b / total, c / total


def discover_latest_checkpoint(patterns: Sequence[str], repo_root: Path) -> Optional[Path]:
    candidates: List[Path] = []
    for pat in patterns:
        candidates.extend(repo_root.glob(pat))
    candidates = [p.resolve() for p in candidates if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def infer_modality_from_path(path: Path) -> str:
    low = str(path).lower()
    hints_xray = ["xray", "x-ray", "opg", "pan", "pano", "radiograph"]
    if any(h in low for h in hints_xray):
        return "xray"
    return "rgb"


def infer_patient_id_from_path(path: Path) -> str:
    stem = path.stem
    for sep in ["_", "-", " "]:
        if sep in stem:
            token = stem.split(sep)[0].strip()
            if token:
                return token
    return stem


def get_autocast_context(device: torch.device, enabled: bool):
    if not enabled:
        return nullcontext()
    if device.type == "cuda":
        return torch.autocast(device_type="cuda", dtype=torch.float16)
    if device.type == "cpu":
        return torch.autocast(device_type="cpu", dtype=torch.bfloat16)
    return nullcontext()


def cosine_scheduler(
    base_value: float,
    final_value: float,
    total_iters: int,
    warmup_iters: int = 0,
    start_warmup_value: float = 0.0,
) -> np.ndarray:
    if total_iters <= 0:
        return np.array([], dtype=np.float32)
    schedule = np.empty(total_iters, dtype=np.float32)
    warmup_iters = max(0, min(warmup_iters, total_iters))
    if warmup_iters > 0:
        schedule[:warmup_iters] = np.linspace(start_warmup_value, base_value, warmup_iters, dtype=np.float32)
    iters = np.arange(total_iters - warmup_iters, dtype=np.float32)
    if len(iters) > 0:
        cosine = 0.5 * (1.0 + np.cos(np.pi * iters / max(1, len(iters) - 1)))
        schedule[warmup_iters:] = final_value + (base_value - final_value) * cosine
    return schedule


@dataclass
class Sample:
    image_path: Path
    label_name: str
    label_idx: int
    patient_id: str
    modality: str  # rgb|xray
    split: str  # train|val|test


@dataclass
class SplitSummary:
    split: str
    num_samples: int
    num_patients: int
    class_counts: Dict[str, int]
    modality_counts: Dict[str, int]


@dataclass
class CleanedCSVIngestStats:
    source_csv: str
    modality: str
    total_rows: int
    kept_rows: int
    skipped_missing_label: int
    skipped_missing_path: int
    skipped_invalid_image: int


def load_manifest_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open() as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = [dict(r) for r in reader]
        return rows

    if suffix in {".jsonl"}:
        rows: List[Dict[str, Any]] = []
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    if suffix in {".json"}:
        obj = json.loads(path.read_text())
        if isinstance(obj, list):
            return [dict(x) for x in obj]
        raise ValueError(f"JSON manifest must contain a list of records: {path}")

    raise ValueError(f"Unsupported manifest format: {path}")


def build_samples_from_records(
    records: Sequence[Dict[str, Any]],
    repo_root: Path,
    dataset_root: Optional[Path],
    class_to_idx: Optional[Dict[str, int]] = None,
    require_split: bool = False,
) -> Tuple[List[Sample], Dict[str, int]]:
    rows = list(records)
    if not rows:
        return [], class_to_idx or {}

    labels_seen: set[str] = set()
    for r in rows:
        lbl = str(r.get("label", "")).strip()
        if not lbl:
            raise ValueError("Each record must have a non-empty 'label' field.")
        labels_seen.add(lbl)

    if class_to_idx is None:
        class_to_idx = {name: i for i, name in enumerate(sorted(labels_seen))}

    samples: List[Sample] = []
    for r in rows:
        p_raw = str(r.get("image_path", "")).strip()
        if not p_raw:
            raise ValueError("Each record must have an 'image_path' field.")
        p = Path(p_raw)
        if not p.is_absolute():
            if dataset_root is not None:
                p = (dataset_root / p).resolve()
            else:
                p = (repo_root / p).resolve()
        else:
            p = p.resolve()

        if not p.exists() or not _is_image_path(p):
            raise FileNotFoundError(f"Image path is missing or invalid: {p}")

        label_name = str(r.get("label", "")).strip()
        if label_name not in class_to_idx:
            raise ValueError(f"Unknown label '{label_name}' not in class mapping.")

        patient_id = str(r.get("patient_id", "")).strip() or infer_patient_id_from_path(p)

        modality = str(r.get("modality", "")).strip().lower()
        if modality not in {"rgb", "xray"}:
            modality = infer_modality_from_path(p)

        split = str(r.get("split", "")).strip().lower()
        if split not in {"train", "val", "test"}:
            split = ""
        if require_split and not split:
            raise ValueError("Manifest must include split=train|val|test when require_split=True")

        samples.append(
            Sample(
                image_path=p,
                label_name=label_name,
                label_idx=int(class_to_idx[label_name]),
                patient_id=patient_id,
                modality=modality,
                split=split,
            )
        )

    return samples, class_to_idx


def build_samples_from_folder(dataset_root: Path) -> Tuple[List[Sample], Dict[str, int]]:
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")

    class_names = sorted([d.name for d in dataset_root.iterdir() if d.is_dir() and not d.name.startswith(".")])
    if not class_names:
        raise RuntimeError(f"No class subdirectories found under dataset root: {dataset_root}")

    class_to_idx = {c: i for i, c in enumerate(class_names)}
    samples: List[Sample] = []

    for cls in class_names:
        cls_dir = dataset_root / cls
        for p in cls_dir.rglob("*"):
            if not _is_image_path(p):
                continue
            modality = infer_modality_from_path(p)
            patient_id = infer_patient_id_from_path(p)
            samples.append(
                Sample(
                    image_path=p.resolve(),
                    label_name=cls,
                    label_idx=int(class_to_idx[cls]),
                    patient_id=patient_id,
                    modality=modality,
                    split="",
                )
            )

    return samples, class_to_idx


def normalize_malocclusion_label(raw_label: Any) -> Optional[str]:
    text = str(raw_label).strip()
    if not text:
        return None

    low = text.lower()
    if low in {"nan", "none", "null"}:
        return None

    try:
        val = float(text)
        if math.isnan(val) or math.isinf(val):
            return None
        rounded = round(val)
        if abs(val - rounded) < 1e-8:
            return str(int(rounded))
        return str(val)
    except Exception:
        return text


def sort_label_names(labels: Sequence[str]) -> List[str]:
    uniq = list(set([str(x).strip() for x in labels if str(x).strip()]))

    def _key(lbl: str):
        try:
            return (0, int(lbl))
        except Exception:
            try:
                return (1, float(lbl))
            except Exception:
                return (2, lbl)

    return sorted(uniq, key=_key)


def build_samples_from_cleaned_csv(
    csv_path: Path,
    modality: str,
    repo_root: Path,
    class_to_idx: Optional[Dict[str, int]] = None,
    strict: bool = False,
) -> Tuple[List[Sample], Dict[str, int], CleanedCSVIngestStats]:
    if modality not in {"rgb", "xray"}:
        raise ValueError(f"Unsupported modality for cleaned CSV: {modality}")
    if not csv_path.exists():
        raise FileNotFoundError(f"Cleaned CSV not found: {csv_path}")

    kept_rows: List[Tuple[Path, str, str]] = []
    labels_seen: List[str] = []
    stats = CleanedCSVIngestStats(
        source_csv=str(csv_path),
        modality=modality,
        total_rows=0,
        kept_rows=0,
        skipped_missing_label=0,
        skipped_missing_path=0,
        skipped_invalid_image=0,
    )

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")

        for row_idx, row in enumerate(reader, start=2):
            stats.total_rows += 1

            img_raw = str(row.get("Image_Path", row.get("image_path", ""))).strip()
            lbl_raw = row.get("Malocclusion_Class", row.get("label", ""))
            pid_raw = str(row.get("Patient_ID", row.get("patient_id", ""))).strip()

            label_name = normalize_malocclusion_label(lbl_raw)
            if label_name is None:
                stats.skipped_missing_label += 1
                if strict:
                    raise ValueError(f"Missing/invalid Malocclusion_Class at {csv_path}:{row_idx}")
                continue

            if not img_raw:
                stats.skipped_missing_path += 1
                if strict:
                    raise ValueError(f"Missing Image_Path at {csv_path}:{row_idx}")
                continue

            image_path = Path(img_raw)
            if not image_path.is_absolute():
                image_path = (repo_root / image_path).resolve()
            else:
                image_path = image_path.resolve()

            if not image_path.exists():
                stats.skipped_missing_path += 1
                if strict:
                    raise FileNotFoundError(f"Image path not found at {csv_path}:{row_idx}: {image_path}")
                continue

            if not _is_image_path(image_path):
                stats.skipped_invalid_image += 1
                if strict:
                    raise ValueError(f"Invalid image path/extension at {csv_path}:{row_idx}: {image_path}")
                continue

            patient_id = pid_raw or infer_patient_id_from_path(image_path)

            kept_rows.append((image_path, label_name, patient_id))
            labels_seen.append(label_name)
            stats.kept_rows += 1

    if not kept_rows:
        raise RuntimeError(f"No usable rows found in cleaned CSV: {csv_path}")

    if class_to_idx is None:
        class_to_idx = {name: i for i, name in enumerate(sort_label_names(labels_seen))}
    else:
        for name in sort_label_names(labels_seen):
            if name not in class_to_idx:
                class_to_idx[name] = len(class_to_idx)

    samples: List[Sample] = []
    for image_path, label_name, patient_id in kept_rows:
        samples.append(
            Sample(
                image_path=image_path,
                label_name=label_name,
                label_idx=int(class_to_idx[label_name]),
                patient_id=patient_id,
                modality=modality,
                split="",
            )
        )

    return samples, class_to_idx, stats


def stratified_patient_split(
    samples: Sequence[Sample],
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    seed: int,
) -> Tuple[List[Sample], List[Sample], List[Sample]]:
    if not samples:
        return [], [], []

    by_patient: Dict[str, List[Sample]] = {}
    for s in samples:
        by_patient.setdefault(s.patient_id, []).append(s)

    patient_mode_label: Dict[str, int] = {}
    for pid, group in by_patient.items():
        cnt = Counter([g.label_idx for g in group])
        patient_mode_label[pid] = int(cnt.most_common(1)[0][0])

    by_label_patients: Dict[int, List[str]] = {}
    for pid, lbl in patient_mode_label.items():
        by_label_patients.setdefault(lbl, []).append(pid)

    rng = random.Random(seed)
    train_patients: set[str] = set()
    val_patients: set[str] = set()
    test_patients: set[str] = set()

    for lbl, pids in by_label_patients.items():
        pids = list(pids)
        rng.shuffle(pids)
        n = len(pids)
        n_train = max(1, int(round(n * train_ratio))) if n >= 3 else max(1, n - 2)
        n_val = max(1, int(round(n * val_ratio))) if n >= 3 else 1
        if n_train + n_val >= n:
            n_train = max(1, n - 2)
            n_val = 1
        n_test = n - n_train - n_val
        if n_test <= 0:
            n_test = 1
            if n_train > 1:
                n_train -= 1
            else:
                n_val = max(1, n_val - 1)

        train_patients.update(pids[:n_train])
        val_patients.update(pids[n_train : n_train + n_val])
        test_patients.update(pids[n_train + n_val :])

    # Ensure disjointness by priority assignment.
    val_patients -= train_patients
    test_patients -= train_patients
    test_patients -= val_patients

    train: List[Sample] = []
    val: List[Sample] = []
    test: List[Sample] = []

    for s in samples:
        if s.patient_id in train_patients:
            s.split = "train"
            train.append(s)
        elif s.patient_id in val_patients:
            s.split = "val"
            val.append(s)
        elif s.patient_id in test_patients:
            s.split = "test"
            test.append(s)
        else:
            # fallback (should be rare)
            s.split = "train"
            train.append(s)

    return train, val, test


def summarize_split(split: str, samples: Sequence[Sample], class_names: Sequence[str]) -> SplitSummary:
    class_counts = {c: 0 for c in class_names}
    modality_counts = {"rgb": 0, "xray": 0}
    patients: set[str] = set()
    for s in samples:
        class_counts[s.label_name] = class_counts.get(s.label_name, 0) + 1
        modality_counts[s.modality] = modality_counts.get(s.modality, 0) + 1
        patients.add(s.patient_id)

    return SplitSummary(
        split=split,
        num_samples=len(samples),
        num_patients=len(patients),
        class_counts=class_counts,
        modality_counts=modality_counts,
    )


def build_preprocess_cfg_opg() -> Any:
    return build_preprocess_config(
        pipeline="opg",
        normalize=True,
        clahe=True,
        clahe_tiles=8,
        clahe_clip=0.01,
        denoise=0,
        gamma=1.0,
        white_balance=False,
        xray_to_rgb=True,
    )


def build_preprocess_cfg_rgb() -> Any:
    return build_preprocess_config(
        pipeline="rgb",
        normalize=True,
        clahe=True,
        clahe_tiles=8,
        clahe_clip=0.01,
        denoise=0,
        gamma=1.0,
        white_balance=True,
        xray_to_rgb=False,
    )


def build_train_transform(image_size: int, randaugment_magnitude: int = 7) -> T.Compose:
    ops: List[Any] = [
        T.RandomResizedCrop(image_size, scale=(0.7, 1.0), interpolation=InterpolationMode.BICUBIC),
        T.RandomHorizontalFlip(p=0.5),
        T.RandomRotation(degrees=10),
        T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1, hue=0.03),
    ]
    if hasattr(T, "RandAugment"):
        ops.append(T.RandAugment(num_ops=2, magnitude=max(1, int(randaugment_magnitude))))
    ops.extend(
        [
            T.ToTensor(),
            T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    return T.Compose(ops)


def build_eval_transform(image_size: int) -> T.Compose:
    return T.Compose(
        [
            T.Resize(image_size + 32, interpolation=InterpolationMode.BICUBIC),
            T.CenterCrop(image_size),
            T.ToTensor(),
            T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )


class MalocclusionDataset(Dataset):
    def __init__(
        self,
        samples: Sequence[Sample],
        train: bool,
        image_size: int,
        include_rgb: bool,
        include_xray: bool,
    ):
        filtered: List[Sample] = []
        for s in samples:
            if s.modality == "rgb" and not include_rgb:
                continue
            if s.modality == "xray" and not include_xray:
                continue
            filtered.append(s)

        if not filtered:
            raise RuntimeError("No samples available after modality filtering.")

        self.samples = list(filtered)
        self.train = bool(train)
        self.image_size = int(image_size)
        self.preprocess_cfg_rgb = build_preprocess_cfg_rgb()
        self.preprocess_cfg_xray = build_preprocess_cfg_opg()
        self.transform = build_train_transform(image_size) if self.train else build_eval_transform(image_size)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        s = self.samples[index]
        with Image.open(s.image_path) as im:
            im.load()
            im = im.convert("RGB")
            cfg = self.preprocess_cfg_xray if s.modality == "xray" else self.preprocess_cfg_rgb
            im = apply_preprocess(im, cfg, dataset_name=s.modality)
            x = self.transform(im)

        y = int(s.label_idx)
        return x, y, s.patient_id, s.modality, str(s.image_path)


def collate_fn(batch):
    images, labels, patient_ids, modalities, paths = zip(*batch)
    return torch.stack(images, dim=0), torch.tensor(labels, dtype=torch.long), list(patient_ids), list(modalities), list(paths)


# -----------------------------
# SSL MAE encoder definitions
# -----------------------------

def trunc_normal_(tensor: torch.Tensor, std: float = 0.02) -> torch.Tensor:
    if hasattr(nn.init, "trunc_normal_"):
        nn.init.trunc_normal_(tensor, std=std)
    else:
        nn.init.normal_(tensor, std=std)
    return tensor


class PatchEmbed(nn.Module):
    def __init__(self, img_size: int = 224, patch_size: int = 16, in_chans: int = 3, embed_dim: int = 768):
        super().__init__()
        if img_size % patch_size != 0:
            raise ValueError("img_size must be divisible by patch_size")
        self.img_size = img_size
        self.patch_size = patch_size
        self.grid_size = img_size // patch_size
        self.num_patches = self.grid_size * self.grid_size
        self.proj = nn.Conv2d(in_chans, embed_dim, kernel_size=patch_size, stride=patch_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.proj(x)
        x = x.flatten(2).transpose(1, 2)
        return x


class MLP(nn.Module):
    def __init__(self, dim: int, hidden_dim: int, out_dim: Optional[int] = None, drop: float = 0.0):
        super().__init__()
        out_dim = out_dim if out_dim is not None else dim
        self.fc1 = nn.Linear(dim, hidden_dim)
        self.act = nn.GELU()
        self.drop1 = nn.Dropout(drop)
        self.fc2 = nn.Linear(hidden_dim, out_dim)
        self.drop2 = nn.Dropout(drop)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.fc1(x)
        x = self.act(x)
        x = self.drop1(x)
        x = self.fc2(x)
        x = self.drop2(x)
        return x


class TransformerBlock(nn.Module):
    def __init__(self, dim: int, num_heads: int, mlp_ratio: float = 4.0, drop: float = 0.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = nn.MultiheadAttention(dim, num_heads, dropout=drop, batch_first=True)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = MLP(dim, int(dim * mlp_ratio), drop=drop)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x_norm = self.norm1(x)
        attn_out, _ = self.attn(x_norm, x_norm, x_norm, need_weights=False)
        x = x + attn_out
        x = x + self.mlp(self.norm2(x))
        return x


class VisionTransformer(nn.Module):
    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 16,
        in_chans: int = 3,
        embed_dim: int = 768,
        depth: int = 12,
        num_heads: int = 12,
        mlp_ratio: float = 4.0,
        drop_rate: float = 0.0,
    ):
        super().__init__()
        self.patch_embed = PatchEmbed(img_size, patch_size, in_chans, embed_dim)
        num_patches = self.patch_embed.num_patches
        self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.pos_embed = nn.Parameter(torch.zeros(1, num_patches + 1, embed_dim))
        self.blocks = nn.ModuleList(
            [TransformerBlock(embed_dim, num_heads, mlp_ratio=mlp_ratio, drop=drop_rate) for _ in range(depth)]
        )
        self.norm = nn.LayerNorm(embed_dim)
        self.embed_dim = embed_dim
        self.num_patches = num_patches
        self._init_weights()

    def _init_weights(self) -> None:
        trunc_normal_(self.cls_token, std=0.02)
        trunc_normal_(self.pos_embed, std=0.02)
        for m in self.modules():
            if isinstance(m, nn.Linear):
                trunc_normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.LayerNorm):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward_tokens(self, x: torch.Tensor) -> torch.Tensor:
        x = self.patch_embed(x)
        b, n, _ = x.shape
        cls = self.cls_token.expand(b, -1, -1)
        x = torch.cat([cls, x], dim=1)
        x = x + self.pos_embed[:, : n + 1]
        for blk in self.blocks:
            x = blk(x)
        x = self.norm(x)
        return x

    def forward_features(self, x: torch.Tensor) -> torch.Tensor:
        x = self.forward_tokens(x)
        return x[:, 0]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.forward_features(x)


# -----------------------------
# Encoder wrappers
# -----------------------------


def _build_torchvision_model(factory: Any, weight_enum_name: str, use_pretrained: bool) -> nn.Module:
    if use_pretrained:
        weights_enum = getattr(models, weight_enum_name, None)
        if weights_enum is not None:
            try:
                return factory(weights=weights_enum.DEFAULT)
            except Exception:
                pass
        try:
            return factory(pretrained=True)
        except Exception:
            pass
    try:
        return factory(weights=None)
    except TypeError:
        return factory(pretrained=False)


def build_cls_encoder(encoder_name: str, use_pretrained: bool) -> Tuple[nn.Module, int]:
    name = encoder_name.lower()

    if name == "resnet50":
        net = _build_torchvision_model(models.resnet50, "ResNet50_Weights", use_pretrained)
        feat_dim = int(net.fc.in_features)
        net.fc = nn.Identity()
        return net, feat_dim

    if name == "resnet101":
        net = _build_torchvision_model(models.resnet101, "ResNet101_Weights", use_pretrained)
        feat_dim = int(net.fc.in_features)
        net.fc = nn.Identity()
        return net, feat_dim


    if name == "efficientnet_b3":
        net = _build_torchvision_model(models.efficientnet_b3, "EfficientNet_B3_Weights", use_pretrained)
        feat_dim = int(net.classifier[-1].in_features)
        net.classifier = nn.Identity()
        return net, feat_dim

    if name == "convnext_tiny":
        net = _build_torchvision_model(models.convnext_tiny, "ConvNeXt_Tiny_Weights", use_pretrained)
        feat_dim = int(net.classifier[-1].in_features)
        net.classifier = nn.Identity()
        return net, feat_dim

    if name == "vit_b16":
        net = _build_torchvision_model(models.vit_b_16, "ViT_B_16_Weights", use_pretrained)
        feat_dim = int(net.heads.head.in_features)
        net.heads = nn.Identity()
        return net, feat_dim

    raise ValueError(f"Unsupported classification encoder: {encoder_name}")


class ResNetEncoder(nn.Module):
    """Minimal wrapper for segmentation upernet backbones."""

    def __init__(self, net: nn.Module):
        super().__init__()
        self.layer0 = nn.Sequential(net.conv1, net.bn1, net.relu)
        self.maxpool = net.maxpool
        self.layer1 = net.layer1
        self.layer2 = net.layer2
        self.layer3 = net.layer3
        self.layer4 = net.layer4

    def forward(self, x: torch.Tensor):
        x = self.layer0(x)
        x = self.maxpool(x)
        c2 = self.layer1(x)
        c3 = self.layer2(c2)
        c4 = self.layer3(c3)
        c5 = self.layer4(c4)
        return c2, c3, c4, c5


class SSLFeatureExtractor(nn.Module):
    def __init__(self, vit: VisionTransformer):
        super().__init__()
        self.vit = vit

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.vit.forward_features(x)


class GenericFeatureExtractor(nn.Module):
    def __init__(self, encoder: nn.Module):
        super().__init__()
        self.encoder = encoder

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.encoder(x)
        if isinstance(feat, (list, tuple)):
            feat = feat[0]
        if isinstance(feat, dict):
            if "out" in feat:
                feat = feat["out"]
            else:
                feat = feat[sorted(feat.keys())[-1]]
        if feat.ndim > 2:
            feat = torch.flatten(feat, start_dim=1)
        return feat


class SegFeatureExtractor(nn.Module):
    def __init__(self, backbone: nn.Module, arch: str):
        super().__init__()
        self.backbone = backbone
        self.arch = arch.lower()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.backbone(x)
        if isinstance(feat, dict):
            if "out" in feat:
                y = feat["out"]
            else:
                y = feat[sorted(feat.keys())[-1]]
        elif isinstance(feat, (list, tuple)):
            y = feat[-1]
        else:
            y = feat
        if y.ndim == 4:
            y = F.adaptive_avg_pool2d(y, output_size=1).flatten(1)
        elif y.ndim > 2:
            y = torch.flatten(y, start_dim=1)
        return y


class DetFeatureExtractor(nn.Module):
    def __init__(self, backbone: nn.Module):
        super().__init__()
        self.backbone = backbone

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.backbone(x)
        if isinstance(feat, torch.Tensor):
            feat = {"0": feat}
        if not isinstance(feat, dict):
            raise RuntimeError("Unexpected detection backbone output type.")

        pooled: List[torch.Tensor] = []
        for k in sorted(feat.keys()):
            y = feat[k]
            if y.ndim != 4:
                y = torch.flatten(y, start_dim=1)
                pooled.append(y)
            else:
                pooled.append(F.adaptive_avg_pool2d(y, output_size=1).flatten(1))

        if not pooled:
            raise RuntimeError("Detection backbone produced no usable features.")
        return torch.cat(pooled, dim=1)


def infer_output_dim(module: nn.Module, image_size: int) -> int:
    module.eval()
    with torch.no_grad():
        x = torch.zeros(1, 3, image_size, image_size)
        y = module(x)
        if y.ndim != 2:
            y = y.view(y.shape[0], -1)
        return int(y.shape[1])


def _strip_prefix_if_all(state: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    if not state:
        return state
    if all(str(k).startswith(prefix) for k in state.keys()):
        plen = len(prefix)
        return {str(k)[plen:]: v for k, v in state.items()}
    return state


def _load_convnext_encoder_from_state(enc_state: Dict[str, Any]) -> nn.Module:
    enc, _ = build_cls_encoder("convnext_tiny", use_pretrained=False)
    state = dict(enc_state)
    state = _strip_prefix_if_all(state, "encoder.")
    state = _strip_prefix_if_all(state, "features.")
    if all(str(k).isdigit() or str(k).split(".", 1)[0].isdigit() for k in state.keys()):
        state = {f"features.{k}": v for k, v in state.items()}
    missing, unexpected = enc.load_state_dict(state, strict=True)
    if missing or unexpected:
        raise RuntimeError(f"ConvNeXt encoder state mismatch: missing={missing}, unexpected={unexpected}")
    return enc


def load_ssl_encoder(ckpt_path: Path) -> nn.Module:
    ckpt = load_checkpoint(ckpt_path, map_location="cpu")
    method = str(ckpt.get("method", "")).lower()
    if method != "mae":
        raise RuntimeError(f"Expected MAE checkpoint for SSL encoder, got method={ckpt.get('method')}")

    enc_name = str(ckpt.get("encoder_name", "")).strip().lower()
    if not enc_name:
        enc_name = str((ckpt.get("args") or {}).get("ssl_encoder_backbone", "")).strip().lower()
    if enc_name == "convnext_tiny":
        enc_state = ckpt.get("encoder_state_dict")
        if not isinstance(enc_state, dict):
            raise RuntimeError(f"SSL checkpoint missing encoder_state_dict: {ckpt_path}")
        enc = _load_convnext_encoder_from_state(enc_state)
        return GenericFeatureExtractor(enc)

    a = ckpt.get("args", {})
    vit = VisionTransformer(
        img_size=int(a.get("image_size", 224)),
        patch_size=int(a.get("patch_size", 16)),
        in_chans=3,
        embed_dim=int(a.get("embed_dim", 768)),
        depth=int(a.get("depth", 12)),
        num_heads=int(a.get("num_heads", 12)),
        mlp_ratio=float(a.get("mlp_ratio", 4.0)),
        drop_rate=0.0,
    )
    vit.load_state_dict(ckpt["encoder_state_dict"], strict=True)
    return SSLFeatureExtractor(vit)


def load_cls_encoder(ckpt_path: Path) -> nn.Module:
    ckpt = load_checkpoint(ckpt_path, map_location="cpu")
    enc_name = str(ckpt.get("encoder_name", "")).strip()
    if not enc_name:
        raise RuntimeError(f"Invalid classification checkpoint missing encoder_name: {ckpt_path}")

    enc, _ = build_cls_encoder(enc_name, use_pretrained=False)
    enc.load_state_dict(ckpt["encoder_state_dict"], strict=True)
    return GenericFeatureExtractor(enc)


def build_cls_encoder_from_source(encoder_name: str, init_source: str) -> nn.Module:
    src = str(init_source).lower().strip()
    if src == "imagenet":
        enc, _ = build_cls_encoder(encoder_name, use_pretrained=True)
    elif src in {"random", "scratch", "none", "no_pretraining"}:
        enc, _ = build_cls_encoder(encoder_name, use_pretrained=False)
    else:
        raise ValueError(f"Unsupported cls init source: {init_source}")
    return GenericFeatureExtractor(enc)


def load_seg_encoder(ckpt_path: Path) -> nn.Module:
    ckpt = load_checkpoint(ckpt_path, map_location="cpu")
    arch = str(ckpt.get("arch", "")).lower()
    encoder = str(ckpt.get("encoder", ckpt.get("encoder_name", ""))).lower()

    if arch == "deeplabv3plus":
        if encoder == "convnext_tiny":
            enc_state = ckpt.get("encoder_state_dict")
            if not isinstance(enc_state, dict):
                raise RuntimeError(f"Invalid segmentation checkpoint missing encoder_state_dict: {ckpt_path}")
            enc = _load_convnext_encoder_from_state(enc_state)
            return GenericFeatureExtractor(enc)
        if encoder == "resnet50":
            # Explicitly disable backbone weights to avoid any download attempt at inference time.
            net = models.segmentation.deeplabv3_resnet50(weights=None, weights_backbone=None)
        elif encoder == "resnet101":
            net = models.segmentation.deeplabv3_resnet101(weights=None, weights_backbone=None)
        else:
            raise RuntimeError(f"Unsupported segmentation encoder: {encoder}")

        if not hasattr(net, "backbone"):
            raise RuntimeError("DeepLab net missing backbone")
        net.backbone.load_state_dict(ckpt["encoder_state_dict"], strict=True)
        return SegFeatureExtractor(net.backbone, arch=arch)

    if arch == "upernet":
        if encoder == "resnet50":
            res = models.resnet50(weights=None)
        elif encoder == "resnet101":
            res = models.resnet101(weights=None)
        else:
            raise RuntimeError(f"Unsupported UPerNet encoder: {encoder}")
        back = ResNetEncoder(res)
        back.load_state_dict(ckpt["encoder_state_dict"], strict=True)
        return SegFeatureExtractor(back, arch=arch)

    raise RuntimeError(f"Unsupported segmentation checkpoint arch: {arch}")


def load_det_encoder(ckpt_path: Path) -> nn.Module:
    ckpt = load_checkpoint(ckpt_path, map_location="cpu")
    model_name = str(ckpt.get("model", "")).lower()
    if model_name != "fasterrcnn":
        raise RuntimeError(
            f"Experiment 1.6 currently supports Faster R-CNN detection checkpoint for fusion, got: {model_name}"
        )

    enc_name = str(ckpt.get("encoder_name", "")).strip().lower()
    enc_state = ckpt.get("encoder_state_dict", {})
    if enc_name == "convnext_tiny":
        if not isinstance(enc_state, dict):
            raise RuntimeError(f"Invalid detection checkpoint missing encoder_state_dict: {ckpt_path}")
        source = None
        if isinstance(enc_state.get("encoder"), dict):
            source = dict(enc_state["encoder"])
        elif isinstance(enc_state.get("backbone"), dict):
            back = dict(enc_state["backbone"])
            body_only = {str(k)[5:]: v for k, v in back.items() if str(k).startswith("body.")}
            source = body_only if body_only else back
        else:
            source = dict(enc_state)
        source = _strip_prefix_if_all(source, "features.")
        source = _strip_prefix_if_all(source, "encoder.features.")
        if all(str(k).isdigit() or str(k).split(".", 1)[0].isdigit() for k in source.keys()):
            source = {f"features.{k}": v for k, v in source.items()}
        enc = _load_convnext_encoder_from_state(source)
        return GenericFeatureExtractor(enc)

    net = models.detection.fasterrcnn_resnet50_fpn(weights=None, weights_backbone=None)
    if isinstance(enc_state, dict) and "backbone" in enc_state:
        state = enc_state["backbone"]
    else:
        state = enc_state
    net.backbone.load_state_dict(state, strict=True)
    return DetFeatureExtractor(net.backbone)


def load_elected_encoders(
    active_encoders: Sequence[str],
    image_size_for_dim: int,
    ssl_ckpt: Optional[Path] = None,
    cls_ckpt: Optional[Path] = None,
    seg_ckpt: Optional[Path] = None,
    det_ckpt: Optional[Path] = None,
    cls_init_source: str = "ckpt",
    cls_encoder_name: str = "convnext_tiny",
) -> Tuple[Dict[str, nn.Module], Dict[str, int], Dict[str, str]]:
    active = [x.strip().lower() for x in active_encoders if x.strip()]
    active = [x for x in active if x in {"ssl", "cls", "seg", "det"}]
    if not active:
        raise RuntimeError("No valid active encoders selected in --use-encoders")

    encoders: Dict[str, nn.Module] = {}
    ckpt_paths: Dict[str, str] = {}

    if "ssl" in active:
        if ssl_ckpt is None:
            raise FileNotFoundError("SSL encoder requested but no --ssl-ckpt was resolved.")
        encoders["ssl"] = load_ssl_encoder(ssl_ckpt)
        ckpt_paths["ssl"] = str(ssl_ckpt)

    if "cls" in active:
        src = str(cls_init_source).lower().strip()
        if src == "ckpt":
            if cls_ckpt is None:
                raise FileNotFoundError("CLS encoder requested with --cls-init-source=ckpt but no --cls-ckpt was resolved.")
            encoders["cls"] = load_cls_encoder(cls_ckpt)
            ckpt_paths["cls"] = str(cls_ckpt)
        elif src in {"imagenet", "random", "scratch", "none", "no_pretraining"}:
            encoders["cls"] = build_cls_encoder_from_source(cls_encoder_name, init_source=src)
            ckpt_paths["cls"] = f"{src}::{cls_encoder_name}"
        else:
            raise ValueError(f"Unsupported --cls-init-source: {cls_init_source}")

    if "seg" in active:
        if seg_ckpt is None:
            raise FileNotFoundError("SEG encoder requested but no --seg-ckpt was resolved.")
        encoders["seg"] = load_seg_encoder(seg_ckpt)
        ckpt_paths["seg"] = str(seg_ckpt)

    if "det" in active:
        if det_ckpt is None:
            raise FileNotFoundError("DET encoder requested but no --det-ckpt was resolved.")
        encoders["det"] = load_det_encoder(det_ckpt)
        ckpt_paths["det"] = str(det_ckpt)

    feat_dims: Dict[str, int] = {}
    for k, m in encoders.items():
        feat_dims[k] = infer_output_dim(m, image_size=image_size_for_dim)
    return encoders, feat_dims, ckpt_paths


# -----------------------------
# Fusion model
# -----------------------------


class AttentionFusion(nn.Module):
    def __init__(self, dim: int, num_heads: int, dropout: float):
        super().__init__()
        self.query = nn.Parameter(torch.zeros(1, 1, dim))
        self.attn = nn.MultiheadAttention(dim, num_heads=num_heads, dropout=dropout, batch_first=True)
        self.norm = nn.LayerNorm(dim)
        trunc_normal_(self.query, std=0.02)

    def forward(self, tokens: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        b = tokens.shape[0]
        q = self.query.expand(b, -1, -1)
        out, weights = self.attn(q, tokens, tokens, need_weights=True)
        out = self.norm(out[:, 0, :])
        return out, {"attn_weights": weights.squeeze(1)}


class ConcatFusion(nn.Module):
    def __init__(self, dim: int, n_tokens: int, dropout: float):
        super().__init__()
        self.fc = nn.Sequential(
            nn.LayerNorm(dim * n_tokens),
            nn.Linear(dim * n_tokens, dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.LayerNorm(dim),
        )

    def forward(self, tokens: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        x = tokens.flatten(1)
        return self.fc(x), {}


class GatingFusion(nn.Module):
    def __init__(self, dim: int, dropout: float):
        super().__init__()
        self.score = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Linear(dim, dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim // 2, 1),
        )
        self.out_norm = nn.LayerNorm(dim)

    def forward(self, tokens: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        logits = self.score(tokens).squeeze(-1)
        w = torch.softmax(logits, dim=1)
        fused = torch.sum(tokens * w.unsqueeze(-1), dim=1)
        return self.out_norm(fused), {"gate_weights": w}


class MultiEncoderFusionClassifier(nn.Module):
    def __init__(
        self,
        encoders: Dict[str, nn.Module],
        feature_dims: Dict[str, int],
        active_encoders: Sequence[str],
        proj_dim: int,
        fusion: str,
        num_heads: int,
        num_classes: int,
        dropout: float,
    ):
        super().__init__()
        self.active_encoders = [e for e in active_encoders if e in encoders]
        if not self.active_encoders:
            raise RuntimeError("No active encoders selected.")

        self.encoders = nn.ModuleDict({k: encoders[k] for k in self.active_encoders})
        self.projections = nn.ModuleDict()
        for k in self.active_encoders:
            in_dim = int(feature_dims[k])
            self.projections[k] = nn.Sequential(
                nn.LayerNorm(in_dim),
                nn.Linear(in_dim, proj_dim),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.LayerNorm(proj_dim),
            )

        f = fusion.lower()
        if f == "attention":
            self.fusion = AttentionFusion(dim=proj_dim, num_heads=num_heads, dropout=dropout)
        elif f == "concat":
            self.fusion = ConcatFusion(dim=proj_dim, n_tokens=len(self.active_encoders), dropout=dropout)
        elif f == "gating":
            self.fusion = GatingFusion(dim=proj_dim, dropout=dropout)
        else:
            raise ValueError(f"Unsupported fusion: {fusion}")
        self.fusion_name = f

        self.head = nn.Sequential(
            nn.LayerNorm(proj_dim),
            nn.Dropout(dropout),
            nn.Linear(proj_dim, 256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes),
        )

    def set_encoders_trainable(self, trainable: bool) -> None:
        for m in self.encoders.values():
            for p in m.parameters():
                p.requires_grad = bool(trainable)

    def encoder_grad_norms(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for name, module in self.encoders.items():
            total = 0.0
            for p in module.parameters():
                if p.grad is None:
                    continue
                v = float(p.grad.detach().norm(2).item())
                total += v * v
            out[name] = math.sqrt(total) if total > 0 else 0.0
        return out

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        tokens: List[torch.Tensor] = []
        for name in self.active_encoders:
            feat = self.encoders[name](x)
            tok = self.projections[name](feat)
            tokens.append(tok)

        z = torch.stack(tokens, dim=1)  # [B, N_enc, D]
        fused, aux = self.fusion(z)
        logits = self.head(fused)
        return logits, aux


# -----------------------------
# Loss + augmentation
# -----------------------------


def one_hot(labels: torch.Tensor, num_classes: int) -> torch.Tensor:
    return F.one_hot(labels, num_classes=num_classes).float()


def mixup(images: torch.Tensor, labels: torch.Tensor, num_classes: int, alpha: float) -> Tuple[torch.Tensor, torch.Tensor]:
    if alpha <= 0.0:
        return images, one_hot(labels, num_classes)
    lam = float(np.random.beta(alpha, alpha))
    idx = torch.randperm(images.size(0), device=images.device)
    mixed = lam * images + (1.0 - lam) * images[idx]
    y = lam * one_hot(labels, num_classes) + (1.0 - lam) * one_hot(labels[idx], num_classes)
    return mixed, y


def cutmix(images: torch.Tensor, labels: torch.Tensor, num_classes: int, alpha: float) -> Tuple[torch.Tensor, torch.Tensor]:
    if alpha <= 0.0:
        return images, one_hot(labels, num_classes)

    lam = float(np.random.beta(alpha, alpha))
    idx = torch.randperm(images.size(0), device=images.device)

    b, _c, h, w = images.shape
    cut_ratio = math.sqrt(max(0.0, 1.0 - lam))
    cut_w = int(w * cut_ratio)
    cut_h = int(h * cut_ratio)

    cx = random.randint(0, max(w - 1, 0))
    cy = random.randint(0, max(h - 1, 0))

    x1 = max(cx - cut_w // 2, 0)
    y1 = max(cy - cut_h // 2, 0)
    x2 = min(cx + cut_w // 2, w)
    y2 = min(cy + cut_h // 2, h)

    mixed = images.clone()
    mixed[:, :, y1:y2, x1:x2] = images[idx, :, y1:y2, x1:x2]

    area = float(max(0, x2 - x1) * max(0, y2 - y1))
    lam_adj = 1.0 - (area / max(float(h * w), 1.0))

    y = lam_adj * one_hot(labels, num_classes) + (1.0 - lam_adj) * one_hot(labels[idx], num_classes)
    return mixed, y


def soft_cross_entropy(logits: torch.Tensor, target_probs: torch.Tensor, class_weights: Optional[torch.Tensor]) -> torch.Tensor:
    log_probs = F.log_softmax(logits, dim=1)
    if class_weights is not None:
        target_probs = target_probs * class_weights.view(1, -1)
        target_probs = target_probs / target_probs.sum(dim=1, keepdim=True).clamp_min(1e-8)
    loss = -(target_probs * log_probs).sum(dim=1)
    return loss.mean()


def soft_focal_loss(
    logits: torch.Tensor,
    target_probs: torch.Tensor,
    gamma: float,
    class_weights: Optional[torch.Tensor],
) -> torch.Tensor:
    probs = F.softmax(logits, dim=1)
    log_probs = torch.log(probs.clamp_min(1e-8))
    ce = -(target_probs * log_probs).sum(dim=1)
    pt = (target_probs * probs).sum(dim=1).clamp_min(1e-8)
    focal = ((1.0 - pt) ** gamma) * ce

    if class_weights is not None:
        sample_w = (target_probs * class_weights.view(1, -1)).sum(dim=1)
        focal = focal * sample_w

    return focal.mean()


def build_class_weights(train_samples: Sequence[Sample], num_classes: int, mode: str) -> Optional[torch.Tensor]:
    m = mode.lower()
    if m == "none":
        return None

    counts = np.zeros((num_classes,), dtype=np.float64)
    for s in train_samples:
        counts[s.label_idx] += 1.0

    counts = np.clip(counts, 1.0, None)
    if m == "balanced":
        w = counts.sum() / (len(counts) * counts)
    elif m == "sqrt_balanced":
        w = np.sqrt(counts.sum() / (len(counts) * counts))
    else:
        raise ValueError(f"Unsupported class-weight mode: {mode}")

    w = w / np.mean(w)
    return torch.tensor(w, dtype=torch.float32)


# -----------------------------
# Metrics
# -----------------------------


def _roc_auc_binary(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = y_true.astype(np.int64)
    y_score = y_score.astype(np.float64)
    pos_mask = y_true == 1
    neg_mask = y_true == 0
    n_pos = int(pos_mask.sum())
    n_neg = int(neg_mask.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    order = np.argsort(y_score)
    sorted_scores = y_score[order]
    ranks = np.arange(1, len(y_score) + 1, dtype=np.float64)

    i = 0
    while i < len(sorted_scores):
        j = i + 1
        while j < len(sorted_scores) and sorted_scores[j] == sorted_scores[i]:
            j += 1
        if j - i > 1:
            avg_rank = 0.5 * (ranks[i] + ranks[j - 1])
            ranks[i:j] = avg_rank
        i = j

    unsorted_ranks = np.empty_like(ranks)
    unsorted_ranks[order] = ranks
    sum_ranks_pos = float(unsorted_ranks[pos_mask].sum())
    auc = (sum_ranks_pos - (n_pos * (n_pos + 1) / 2.0)) / (n_pos * n_neg)
    return float(auc)


def _nanmean(values: Sequence[float]) -> float:
    arr = np.asarray(values, dtype=np.float64)
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return float("nan")
    return float(valid.mean())


def confusion_matrix_np(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> np.ndarray:
    conf = np.zeros((num_classes, num_classes), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        if 0 <= int(t) < num_classes and 0 <= int(p) < num_classes:
            conf[int(t), int(p)] += 1
    return conf


def metrics_from_predictions(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    class_names: Sequence[str],
) -> Dict[str, Any]:
    num_classes = len(class_names)
    y_true = y_true.astype(np.int64)
    y_pred = np.argmax(y_prob, axis=1).astype(np.int64)

    conf = confusion_matrix_np(y_true, y_pred, num_classes=num_classes)

    eps = 1e-9
    per_class: Dict[str, Any] = {}
    f1s: List[float] = []
    aucs: List[float] = []

    for i, name in enumerate(class_names):
        tp = float(conf[i, i])
        fp = float(conf[:, i].sum() - conf[i, i])
        fn = float(conf[i, :].sum() - conf[i, i])

        precision = tp / (tp + fp + eps)
        recall = tp / (tp + fn + eps)
        if (tp + fp + fn) <= 0:
            f1 = float("nan")
        else:
            f1 = 2.0 * precision * recall / (precision + recall + eps)
        auc = _roc_auc_binary((y_true == i).astype(np.int64), y_prob[:, i])

        per_class[name] = {
            "support": int((y_true == i).sum()),
            "precision": safe_float(precision),
            "recall": safe_float(recall),
            "f1": safe_float(f1),
            "auc": safe_float(auc),
        }
        f1s.append(float(f1))
        aucs.append(float(auc))

    macro_f1 = _nanmean(f1s)
    macro_auc = _nanmean(aucs)
    acc = float((y_true == y_pred).mean()) if y_true.size > 0 else float("nan")

    n = float(conf.sum())
    po = float(np.trace(conf)) / max(n, 1.0)
    row_marg = conf.sum(axis=1).astype(np.float64)
    col_marg = conf.sum(axis=0).astype(np.float64)
    pe = float((row_marg * col_marg).sum()) / max(n * n, 1.0)
    if abs(1.0 - pe) < 1e-9:
        kappa = float("nan")
    else:
        kappa = (po - pe) / (1.0 - pe)

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "macro_auc": macro_auc,
        "kappa": float(kappa),
        "per_class": per_class,
        "confusion_matrix": conf.tolist(),
    }


def bootstrap_ci(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    class_names: Sequence[str],
    metric_key: str,
    num_bootstrap: int,
    seed: int,
) -> Dict[str, Optional[float]]:
    if num_bootstrap <= 0 or y_true.size == 0:
        return {"mean": None, "ci95_low": None, "ci95_high": None}

    rng = np.random.default_rng(seed)
    n = len(y_true)
    vals: List[float] = []
    for _ in range(num_bootstrap):
        idx = rng.integers(0, n, size=n)
        yt = y_true[idx]
        yp = y_prob[idx]
        m = metrics_from_predictions(yt, yp, class_names=class_names)
        v = safe_float(m.get(metric_key))
        if v is not None:
            vals.append(float(v))

    if not vals:
        return {"mean": None, "ci95_low": None, "ci95_high": None}

    arr = np.asarray(vals, dtype=np.float64)
    return {
        "mean": float(np.mean(arr)),
        "ci95_low": float(np.percentile(arr, 2.5)),
        "ci95_high": float(np.percentile(arr, 97.5)),
    }


@torch.no_grad()
def evaluate(
    model: MultiEncoderFusionClassifier,
    loader: Optional[DataLoader],
    criterion_type: str,
    focal_gamma: float,
    class_weights: Optional[torch.Tensor],
    device: torch.device,
    amp: bool,
    class_names: Sequence[str],
    return_outputs: bool = False,
) -> Dict[str, Any]:
    if loader is None or len(loader) == 0:
        out = {
            "loss": float("nan"),
            "accuracy": float("nan"),
            "macro_f1": float("nan"),
            "macro_auc": float("nan"),
            "kappa": float("nan"),
            "per_class": {},
            "confusion_matrix": [],
        }
        if return_outputs:
            out["y_true"] = np.zeros((0,), dtype=np.int64)
            out["y_prob"] = np.zeros((0, len(class_names)), dtype=np.float32)
        return out

    model.eval()
    losses: List[float] = []
    all_true: List[np.ndarray] = []
    all_prob: List[np.ndarray] = []

    cw = class_weights.to(device) if class_weights is not None else None

    for images, labels, _pids, _mods, _paths in _progress(loader, total=len(loader), desc="Eval"):
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        with get_autocast_context(device, amp):
            logits, _aux = model(images)
            target_probs = one_hot(labels, num_classes=len(class_names))
            if criterion_type == "focal":
                loss = soft_focal_loss(logits, target_probs, gamma=focal_gamma, class_weights=cw)
            else:
                loss = soft_cross_entropy(logits, target_probs, class_weights=cw)

        probs = torch.softmax(logits, dim=1)
        losses.append(float(loss.item()))
        all_true.append(labels.detach().cpu().numpy())
        all_prob.append(probs.detach().cpu().numpy())

    y_true = np.concatenate(all_true, axis=0) if all_true else np.zeros((0,), dtype=np.int64)
    y_prob = np.concatenate(all_prob, axis=0) if all_prob else np.zeros((0, len(class_names)), dtype=np.float32)

    metrics = metrics_from_predictions(y_true, y_prob, class_names=class_names)
    metrics["loss"] = float(np.mean(losses)) if losses else float("nan")

    if return_outputs:
        metrics["y_true"] = y_true
        metrics["y_prob"] = y_prob

    return metrics


# -----------------------------
# Graphs
# -----------------------------

def generate_graphs(log_path: Path, graph_dir: Path) -> Tuple[List[str], Optional[str]]:
    if not log_path.exists():
        return [], "train_log.jsonl not found"

    records: List[Dict[str, Any]] = []
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        return [], "No records in train_log.jsonl"

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        return [], str(exc)

    def _series(key: str) -> List[float]:
        out: List[float] = []
        for r in records:
            v = safe_float(r.get(key))
            out.append(float(v) if v is not None else float("nan"))
        return out

    graph_dir.mkdir(parents=True, exist_ok=True)
    epochs = [int(r.get("epoch", i + 1)) for i, r in enumerate(records)]
    generated: List[str] = []

    fig = plt.figure(figsize=(8, 5))
    plt.plot(epochs, _series("train_loss"), label="train_loss", linewidth=2)
    plt.plot(epochs, _series("val_loss"), label="val_loss", linewidth=2)
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title("Experiment 1.6 Loss")
    plt.grid(True, alpha=0.3)
    plt.legend()
    p = graph_dir / "loss_curve.png"
    fig.tight_layout()
    fig.savefig(p, dpi=180)
    plt.close(fig)
    generated.append(str(p))

    fig = plt.figure(figsize=(8, 5))
    plt.plot(epochs, _series("val_macro_f1"), label="val_macro_f1", linewidth=2)
    plt.plot(epochs, _series("val_macro_auc"), label="val_macro_auc", linewidth=2)
    plt.plot(epochs, _series("val_kappa"), label="val_kappa", linewidth=2)
    plt.xlabel("Epoch")
    plt.ylabel("Score")
    plt.title("Validation Metrics")
    plt.ylim(0.0, 1.0)
    plt.grid(True, alpha=0.3)
    plt.legend()
    p = graph_dir / "val_metrics_curve.png"
    fig.tight_layout()
    fig.savefig(p, dpi=180)
    plt.close(fig)
    generated.append(str(p))

    fig = plt.figure(figsize=(8, 5))
    plt.plot(epochs, _series("lr_encoder"), label="lr_encoder", linewidth=2)
    plt.plot(epochs, _series("lr_head"), label="lr_head", linewidth=2)
    plt.xlabel("Epoch")
    plt.ylabel("Learning Rate")
    plt.title("Differential LR Schedules")
    plt.grid(True, alpha=0.3)
    plt.legend()
    p = graph_dir / "lr_curve.png"
    fig.tight_layout()
    fig.savefig(p, dpi=180)
    plt.close(fig)
    generated.append(str(p))

    grad_keys = [k for k in records[0].keys() if k.startswith("grad_norm_")]
    if grad_keys:
        fig = plt.figure(figsize=(8, 5))
        for k in sorted(grad_keys):
            plt.plot(epochs, _series(k), label=k, linewidth=2)
        plt.xlabel("Epoch")
        plt.ylabel("L2 Grad Norm")
        plt.title("Per-Encoder Gradient Norms")
        plt.grid(True, alpha=0.3)
        plt.legend()
        p = graph_dir / "grad_norms_curve.png"
        fig.tight_layout()
        fig.savefig(p, dpi=180)
        plt.close(fig)
        generated.append(str(p))

    return generated, None


# -----------------------------
# Ablation profiles
# -----------------------------

def apply_ablation_profile(args: argparse.Namespace) -> None:
    a = str(args.ablation).lower().strip()
    if a in {"", "none"}:
        return

    if a == "a1_single_frozen":
        args.use_encoders = "cls"
        args.freeze_encoders = True
        args.fusion = "attention"
    elif a == "a2_single_finetune":
        args.use_encoders = "cls"
        args.freeze_encoders = False
        args.fusion = "attention"
    elif a == "a3_all_frozen":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = True
        args.fusion = "attention"
    elif a == "a4_target":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.fusion = "attention"
    elif a == "a5_concat":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.fusion = "concat"
    elif a == "a5_gating":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.fusion = "gating"
    elif a == "a6_no_xray":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.include_xray = False
    elif a == "a6_with_xray":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.include_xray = True
    elif a == "a7_lr_1e4":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.encoder_lr = 1e-4
    elif a == "a7_lr_1e5":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.encoder_lr = 1e-5
    elif a == "a7_lr_1e6":
        args.use_encoders = "ssl,cls,seg,det"
        args.freeze_encoders = False
        args.encoder_lr = 1e-6
    else:
        raise ValueError(f"Unsupported ablation profile: {args.ablation}")


# -----------------------------
# Args
# -----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Experiment 1.6 - multi-encoder fusion for malocclusion")

    p.add_argument("--rgb-csv", type=str, default="", help="Cleaned RGB intraoral CSV with Patient_ID/Image_Path/Malocclusion_Class")
    p.add_argument("--opg-csv", type=str, default="", help="Cleaned OPG CSV with Patient_ID/Image_Path/Malocclusion_Class")
    p.add_argument("--strict-cleaned-csv", action="store_true", help="Fail on invalid/missing labels or paths in cleaned CSV ingestion")

    p.add_argument("--manifest", type=str, default="", help="Single manifest (csv/json/jsonl). Optional split column.")
    p.add_argument("--train-manifest", type=str, default="")
    p.add_argument("--val-manifest", type=str, default="")
    p.add_argument("--test-manifest", type=str, default="")
    p.add_argument("--dataset-root", type=str, default="", help="Fallback: class-subfolder dataset root")

    p.add_argument("--split-ratios", type=str, default="0.70,0.15,0.15")
    p.add_argument("--seed", type=int, default=42)

    p.add_argument("--include-rgb", dest="include_rgb", action="store_true")
    p.add_argument("--no-include-rgb", dest="include_rgb", action="store_false")
    p.set_defaults(include_rgb=True)

    p.add_argument("--include-xray", dest="include_xray", action="store_true")
    p.add_argument("--no-include-xray", dest="include_xray", action="store_false")
    p.set_defaults(include_xray=True)

    p.add_argument("--ablation", type=str, default="a4_target")
    p.add_argument("--use-encoders", type=str, default="ssl,cls,seg,det", help="Comma-separated subset of ssl,cls,seg,det")
    p.add_argument(
        "--cls-init-source",
        choices=["ckpt", "imagenet", "random"],
        default="ckpt",
        help="Initialization source for cls encoder when cls is active.",
    )
    p.add_argument(
        "--cls-encoder-name",
        choices=["convnext_tiny", "resnet50", "resnet101", "efficientnet_b3", "vit_b16"],
        default="convnext_tiny",
        help="Classifier backbone used when --cls-init-source is imagenet/random.",
    )
    p.add_argument("--fusion", choices=["attention", "concat", "gating"], default="attention")
    p.add_argument("--proj-dim", type=int, default=768)
    p.add_argument("--fusion-heads", type=int, default=8)
    p.add_argument("--dropout", type=float, default=0.30)
    p.add_argument("--freeze-encoders", action="store_true")

    p.add_argument("--ssl-ckpt", type=str, default="")
    p.add_argument("--cls-ckpt", type=str, default="")
    p.add_argument("--seg-ckpt", type=str, default="")
    p.add_argument("--det-ckpt", type=str, default="")

    p.add_argument("--image-size", type=int, default=224)
    p.add_argument("--randaugment-magnitude", type=int, default=7)

    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--min-epochs", type=int, default=20)
    p.add_argument("--early-stopping-patience", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--accum-steps", type=int, default=1)
    p.add_argument("--num-workers", type=int, default=8)

    p.add_argument("--encoder-lr", type=float, default=1e-5)
    p.add_argument("--head-lr", type=float, default=1e-3)
    p.add_argument("--min-lr-scale", type=float, default=0.1, help="Final LR as scale * base LR")
    p.add_argument("--warmup-epochs", type=int, default=5)
    p.add_argument("--weight-decay", type=float, default=0.05)

    p.add_argument("--criterion", choices=["ce", "focal"], default="focal")
    p.add_argument("--focal-gamma", type=float, default=2.0)
    p.add_argument("--class-weight-mode", choices=["none", "balanced", "sqrt_balanced"], default="sqrt_balanced")

    p.add_argument("--mixup-alpha", type=float, default=0.2)
    p.add_argument("--cutmix-alpha", type=float, default=0.2)
    p.add_argument("--mix-prob", type=float, default=0.5)

    p.add_argument("--amp", action="store_true")
    p.add_argument("--device", type=str, default="cuda")
    p.add_argument("--save-every", type=int, default=5)

    p.add_argument("--bootstrap-samples", type=int, default=1000)
    p.add_argument("--bootstrap-seed", type=int, default=123)

    p.add_argument("--out-dir", type=str, default="models/exp1_6_malocclusion")
    p.add_argument("--checkpoint-name", type=str, default="exp1_6_fusion.ckpt")
    p.add_argument("--resume", type=str, default="")

    return p.parse_args()


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    args = parse_args()
    apply_ablation_profile(args)
    set_seed(args.seed)

    if args.epochs <= 0:
        raise ValueError("--epochs must be > 0")
    if args.batch_size <= 0 or args.accum_steps <= 0:
        raise ValueError("--batch-size and --accum-steps must be > 0")

    repo_root = Path.cwd()
    out_dir = resolve_path(args.out_dir, repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    active_encoders = [x.strip().lower() for x in args.use_encoders.split(",") if x.strip()]
    active_encoders = [x for x in active_encoders if x in {"ssl", "cls", "seg", "det"}]
    if not active_encoders:
        raise RuntimeError("No valid active encoders selected in --use-encoders")

    cls_init_source = str(args.cls_init_source).lower().strip()
    if cls_init_source not in {"ckpt", "imagenet", "random"}:
        raise ValueError(f"Unsupported --cls-init-source: {args.cls_init_source}")

    need_ssl_ckpt = "ssl" in active_encoders
    need_cls_ckpt = ("cls" in active_encoders) and (cls_init_source == "ckpt")
    need_seg_ckpt = "seg" in active_encoders
    need_det_ckpt = "det" in active_encoders

    # Resolve selected checkpoint paths (overrideable by user args).
    ssl_ckpt: Optional[Path] = None
    cls_ckpt: Optional[Path] = None
    seg_ckpt: Optional[Path] = None
    det_ckpt: Optional[Path] = None

    if need_ssl_ckpt:
        ssl_ckpt = resolve_path(args.ssl_ckpt, repo_root) if args.ssl_ckpt else discover_latest_checkpoint(
            ["models/ssl_intraoral_runs/**/ssl_intraoral.ckpt"], repo_root
        )
    if need_cls_ckpt:
        cls_ckpt = resolve_path(args.cls_ckpt, repo_root) if args.cls_ckpt else discover_latest_checkpoint(
            ["models/cls_xray_runs/**/convnext_tiny/cls_xray.ckpt"], repo_root
        )
    elif "cls" in active_encoders and args.cls_ckpt:
        print(
            f"[warn] Ignoring --cls-ckpt because --cls-init-source={cls_init_source}. "
            f"Using torchvision {cls_init_source} init for cls encoder.",
            flush=True,
        )
    if need_seg_ckpt:
        seg_ckpt = resolve_path(args.seg_ckpt, repo_root) if args.seg_ckpt else discover_latest_checkpoint(
            [
                "models/seg_pretrain_runs/**/deeplabv3plus_convnext_tiny/seg_encoder.ckpt",
                "models/seg_pretrain_runs/**/deeplabv3plus_resnet50/seg_encoder.ckpt",
            ],
            repo_root,
        )
    if need_det_ckpt:
        det_ckpt = resolve_path(args.det_ckpt, repo_root) if args.det_ckpt else discover_latest_checkpoint(
            [
                "models/det_pretrain_runs/**/fasterrcnn_convnext_tiny/det_encoder.ckpt",
                "models/det_pretrain_runs/**/fasterrcnn/det_encoder.ckpt",
            ],
            repo_root,
        )

    required = []
    if need_ssl_ckpt:
        required.append(("ssl", ssl_ckpt))
    if need_cls_ckpt:
        required.append(("cls", cls_ckpt))
    if need_seg_ckpt:
        required.append(("seg", seg_ckpt))
    if need_det_ckpt:
        required.append(("det", det_ckpt))
    for name, pth in required:
        if pth is None or not Path(pth).exists():
            raise FileNotFoundError(f"Could not resolve elected {name} checkpoint. Provide --{name}-ckpt explicitly.")

    # Build samples.
    class_to_idx: Optional[Dict[str, int]] = None
    train_samples: List[Sample] = []
    val_samples: List[Sample] = []
    test_samples: List[Sample] = []

    train_manifest = args.train_manifest.strip()
    val_manifest = args.val_manifest.strip()
    test_manifest = args.test_manifest.strip()
    manifest = args.manifest.strip()
    rgb_csv = args.rgb_csv.strip()
    opg_csv = args.opg_csv.strip()
    dataset_root = resolve_path(args.dataset_root, repo_root) if args.dataset_root.strip() else None
    data_source_info: Dict[str, Any] = {}

    if rgb_csv or opg_csv:
        all_samples: List[Sample] = []
        cleaned_stats: Dict[str, Any] = {}

        if rgb_csv:
            rgb_samples, class_to_idx, rgb_stats = build_samples_from_cleaned_csv(
                csv_path=resolve_path(rgb_csv, repo_root),
                modality="rgb",
                repo_root=repo_root,
                class_to_idx=class_to_idx,
                strict=bool(args.strict_cleaned_csv),
            )
            all_samples.extend(rgb_samples)
            cleaned_stats["rgb"] = asdict(rgb_stats)

        if opg_csv:
            opg_samples, class_to_idx, opg_stats = build_samples_from_cleaned_csv(
                csv_path=resolve_path(opg_csv, repo_root),
                modality="xray",
                repo_root=repo_root,
                class_to_idx=class_to_idx,
                strict=bool(args.strict_cleaned_csv),
            )
            all_samples.extend(opg_samples)
            cleaned_stats["opg"] = asdict(opg_stats)

        if not all_samples:
            raise RuntimeError("No usable samples after cleaned CSV ingestion.")

        tr, va, te = split_ratios_from_text(args.split_ratios)
        train_samples, val_samples, test_samples = stratified_patient_split(
            all_samples,
            train_ratio=tr,
            val_ratio=va,
            test_ratio=te,
            seed=args.seed,
        )
        data_source_info = {
            "mode": "cleaned_csv_pair",
            "rgb_csv": str(resolve_path(rgb_csv, repo_root)) if rgb_csv else "",
            "opg_csv": str(resolve_path(opg_csv, repo_root)) if opg_csv else "",
            "strict_cleaned_csv": bool(args.strict_cleaned_csv),
            "ingest_stats": cleaned_stats,
        }

    elif train_manifest and val_manifest and test_manifest:
        train_records = load_manifest_records(resolve_path(train_manifest, repo_root))
        val_records = load_manifest_records(resolve_path(val_manifest, repo_root))
        test_records = load_manifest_records(resolve_path(test_manifest, repo_root))

        train_samples, class_to_idx = build_samples_from_records(
            train_records, repo_root=repo_root, dataset_root=dataset_root, class_to_idx=None, require_split=False
        )
        val_samples, class_to_idx = build_samples_from_records(
            val_records, repo_root=repo_root, dataset_root=dataset_root, class_to_idx=class_to_idx, require_split=False
        )
        test_samples, class_to_idx = build_samples_from_records(
            test_records, repo_root=repo_root, dataset_root=dataset_root, class_to_idx=class_to_idx, require_split=False
        )

        for s in train_samples:
            s.split = "train"
        for s in val_samples:
            s.split = "val"
        for s in test_samples:
            s.split = "test"
        data_source_info = {
            "mode": "explicit_split_manifests",
            "train_manifest": str(resolve_path(train_manifest, repo_root)),
            "val_manifest": str(resolve_path(val_manifest, repo_root)),
            "test_manifest": str(resolve_path(test_manifest, repo_root)),
            "dataset_root": str(dataset_root) if dataset_root is not None else "",
        }

    elif manifest:
        records = load_manifest_records(resolve_path(manifest, repo_root))
        all_samples, class_to_idx = build_samples_from_records(
            records, repo_root=repo_root, dataset_root=dataset_root, class_to_idx=None, require_split=False
        )

        has_split = any(s.split in {"train", "val", "test"} for s in all_samples)
        if has_split:
            train_samples = [s for s in all_samples if s.split == "train"]
            val_samples = [s for s in all_samples if s.split == "val"]
            test_samples = [s for s in all_samples if s.split == "test"]
        else:
            tr, va, te = split_ratios_from_text(args.split_ratios)
            train_samples, val_samples, test_samples = stratified_patient_split(
                all_samples,
                train_ratio=tr,
                val_ratio=va,
                test_ratio=te,
                seed=args.seed,
            )
        data_source_info = {
            "mode": "single_manifest",
            "manifest": str(resolve_path(manifest, repo_root)),
            "dataset_root": str(dataset_root) if dataset_root is not None else "",
        }

    elif dataset_root is not None:
        all_samples, class_to_idx = build_samples_from_folder(dataset_root)
        tr, va, te = split_ratios_from_text(args.split_ratios)
        train_samples, val_samples, test_samples = stratified_patient_split(
            all_samples,
            train_ratio=tr,
            val_ratio=va,
            test_ratio=te,
            seed=args.seed,
        )
        data_source_info = {
            "mode": "folder_dataset_root",
            "dataset_root": str(dataset_root),
        }

    else:
        raise ValueError(
            "Provide one data mode: --rgb-csv/--opg-csv, or --manifest, "
            "or --train-manifest/--val-manifest/--test-manifest, or --dataset-root"
        )

    if data_source_info.get("mode") == "cleaned_csv_pair":
        ingest_stats = data_source_info.get("ingest_stats", {})
        for name in ["rgb", "opg"]:
            st = ingest_stats.get(name)
            if not isinstance(st, dict):
                continue
            print(
                f"[info] cleaned_csv[{name}] kept={st.get('kept_rows')} total={st.get('total_rows')} "
                f"skip_label={st.get('skipped_missing_label')} skip_path={st.get('skipped_missing_path')} "
                f"skip_invalid={st.get('skipped_invalid_image')}",
                flush=True,
            )

    if class_to_idx is None:
        raise RuntimeError("Class mapping could not be built.")

    idx_to_class = {i: c for c, i in class_to_idx.items()}
    class_names = [idx_to_class[i] for i in sorted(idx_to_class.keys())]
    num_classes = len(class_names)

    if not train_samples:
        raise RuntimeError("Train split is empty.")
    if not val_samples:
        raise RuntimeError("Validation split is empty.")
    if not test_samples:
        raise RuntimeError("Test split is empty.")

    # Ensure patient disjointness across splits.
    train_p = {s.patient_id for s in train_samples}
    val_p = {s.patient_id for s in val_samples}
    test_p = {s.patient_id for s in test_samples}
    if (train_p & val_p) or (train_p & test_p) or (val_p & test_p):
        raise RuntimeError("Patient overlap detected across train/val/test splits.")

    # Persist split manifests.
    write_samples_jsonl(out_dir / "train_samples.jsonl", train_samples, root_anchor=repo_root)
    write_samples_jsonl(out_dir / "val_samples.jsonl", val_samples, root_anchor=repo_root)
    write_samples_jsonl(out_dir / "test_samples.jsonl", test_samples, root_anchor=repo_root)

    # Build datasets/loaders.
    train_ds = MalocclusionDataset(
        samples=train_samples,
        train=True,
        image_size=args.image_size,
        include_rgb=args.include_rgb,
        include_xray=args.include_xray,
    )
    val_ds = MalocclusionDataset(
        samples=val_samples,
        train=False,
        image_size=args.image_size,
        include_rgb=args.include_rgb,
        include_xray=args.include_xray,
    )
    test_ds = MalocclusionDataset(
        samples=test_samples,
        train=False,
        image_size=args.image_size,
        include_rgb=args.include_rgb,
        include_xray=args.include_xray,
    )

    device = torch.device(args.device if (args.device == "cuda" and torch.cuda.is_available()) else "cpu")
    pin = device.type == "cuda"

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=pin,
        drop_last=False,
        collate_fn=collate_fn,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=max(1, args.batch_size // 2),
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=pin,
        drop_last=False,
        collate_fn=collate_fn,
    )
    test_loader = DataLoader(
        test_ds,
        batch_size=max(1, args.batch_size // 2),
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=pin,
        drop_last=False,
        collate_fn=collate_fn,
    )

    if len(train_loader) == 0:
        raise RuntimeError("Train dataloader is empty.")

    encoders, feature_dims, ckpt_paths = load_elected_encoders(
        active_encoders=active_encoders,
        image_size_for_dim=args.image_size,
        ssl_ckpt=Path(ssl_ckpt) if ssl_ckpt is not None else None,
        cls_ckpt=Path(cls_ckpt) if cls_ckpt is not None else None,
        seg_ckpt=Path(seg_ckpt) if seg_ckpt is not None else None,
        det_ckpt=Path(det_ckpt) if det_ckpt is not None else None,
        cls_init_source=cls_init_source,
        cls_encoder_name=args.cls_encoder_name,
    )

    model = MultiEncoderFusionClassifier(
        encoders=encoders,
        feature_dims=feature_dims,
        active_encoders=active_encoders,
        proj_dim=args.proj_dim,
        fusion=args.fusion,
        num_heads=args.fusion_heads,
        num_classes=num_classes,
        dropout=args.dropout,
    ).to(device)

    model.set_encoders_trainable(trainable=(not args.freeze_encoders))

    class_weights = build_class_weights(train_samples, num_classes=num_classes, mode=args.class_weight_mode)

    encoder_params: List[nn.Parameter] = []
    head_params: List[nn.Parameter] = []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        if name.startswith("encoders."):
            encoder_params.append(p)
        else:
            head_params.append(p)

    param_groups = []
    if encoder_params:
        param_groups.append({"params": encoder_params, "lr": args.encoder_lr, "group_name": "encoder"})
    if head_params:
        param_groups.append({"params": head_params, "lr": args.head_lr, "group_name": "head"})

    if not param_groups:
        raise RuntimeError("No trainable parameters found.")

    optimizer = torch.optim.AdamW(param_groups, betas=(0.9, 0.999), weight_decay=args.weight_decay)

    amp_enabled = bool(args.amp and device.type == "cuda")
    scaler = torch.cuda.amp.GradScaler(enabled=amp_enabled)

    steps_per_epoch = len(train_loader)
    total_iters = max(1, steps_per_epoch * args.epochs)
    warmup_iters = int(args.warmup_epochs * steps_per_epoch)

    enc_final = args.encoder_lr * max(args.min_lr_scale, 1e-6)
    head_final = args.head_lr * max(args.min_lr_scale, 1e-6)

    lr_enc_schedule = cosine_scheduler(
        base_value=args.encoder_lr,
        final_value=enc_final,
        total_iters=total_iters,
        warmup_iters=warmup_iters,
        start_warmup_value=args.encoder_lr * 0.1,
    )
    lr_head_schedule = cosine_scheduler(
        base_value=args.head_lr,
        final_value=head_final,
        total_iters=total_iters,
        warmup_iters=warmup_iters,
        start_warmup_value=args.head_lr * 0.1,
    )

    start_epoch = 0
    global_step = 0
    best_metric = -float("inf")
    best_epoch = 0
    bad_epochs = 0

    if args.resume:
        resume_path = resolve_path(args.resume, repo_root)
        if not resume_path.exists():
            raise FileNotFoundError(f"--resume checkpoint not found: {resume_path}")
        ckpt = load_checkpoint(resume_path, map_location="cpu")
        model.load_state_dict(ckpt["model"], strict=True)
        if "optimizer" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer"])
        if "scaler" in ckpt:
            scaler.load_state_dict(ckpt["scaler"])
        start_epoch = int(ckpt.get("epoch", 0))
        global_step = int(ckpt.get("global_step", 0))
        best_metric = float(ckpt.get("best_metric", best_metric))
        best_epoch = int(ckpt.get("best_epoch", best_epoch))
        bad_epochs = int(ckpt.get("bad_epochs", bad_epochs))
        print(f"[info] Resumed from {resume_path} at epoch {start_epoch}", flush=True)

    train_summary = summarize_split("train", train_ds.samples, class_names)
    val_summary = summarize_split("val", val_ds.samples, class_names)
    test_summary = summarize_split("test", test_ds.samples, class_names)

    metadata = {
        "experiment_id": "1.6",
        "experiment_name": "Multi-Encoder Fusion for Malocclusion Classification",
        "ablation": args.ablation,
        "active_encoders": active_encoders,
        "encoder_init": {
            "cls_init_source": cls_init_source if "cls" in active_encoders else None,
            "cls_encoder_name": args.cls_encoder_name if "cls" in active_encoders else None,
        },
        "fusion": args.fusion,
        "freeze_encoders": bool(args.freeze_encoders),
        "checkpoints": ckpt_paths,
        "feature_dims": feature_dims,
        "num_classes": num_classes,
        "class_names": class_names,
        "split_summary": {
            "train": asdict(train_summary),
            "val": asdict(val_summary),
            "test": asdict(test_summary),
        },
        "patient_disjoint_verified": True,
        "data_source": data_source_info,
        "modality_filter": {"include_rgb": args.include_rgb, "include_xray": args.include_xray},
        "hyperparams": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "accum_steps": args.accum_steps,
            "encoder_lr": args.encoder_lr,
            "head_lr": args.head_lr,
            "criterion": args.criterion,
            "focal_gamma": args.focal_gamma,
            "class_weight_mode": args.class_weight_mode,
            "mixup_alpha": args.mixup_alpha,
            "cutmix_alpha": args.cutmix_alpha,
            "mix_prob": args.mix_prob,
            "weight_decay": args.weight_decay,
            "early_stopping_patience": args.early_stopping_patience,
        },
        "architecture_reference": "experiment_1_6_architecture (1).jsx",
    }
    (out_dir / "metadata.json").write_text(json.dumps(to_json_compatible(metadata), indent=2))

    log_path = out_dir / "train_log.jsonl"
    if start_epoch == 0 and log_path.exists():
        log_path.unlink()

    print(f"[info] Device: {device}", flush=True)
    print(
        f"[info] ablation={args.ablation}, fusion={args.fusion}, active_encoders={active_encoders}, "
        f"cls_init={cls_init_source}, cls_backbone={args.cls_encoder_name}, "
        f"train={len(train_ds)}, val={len(val_ds)}, test={len(test_ds)}",
        flush=True,
    )

    for epoch in range(start_epoch, args.epochs):
        t0 = time.time()
        model.train()
        if args.freeze_encoders:
            for m in model.encoders.values():
                m.eval()

        optimizer.zero_grad(set_to_none=True)
        losses: List[float] = []
        grad_acc: Dict[str, List[float]] = {k: [] for k in model.active_encoders}

        pbar = _progress(train_loader, total=len(train_loader), desc=f"exp1.6 epoch {epoch+1}/{args.epochs}")
        for it, (images, labels, _pids, _mods, _paths) in enumerate(pbar):
            iter_idx = epoch * steps_per_epoch + it

            lr_enc = float(lr_enc_schedule[min(iter_idx, len(lr_enc_schedule) - 1)])
            lr_head = float(lr_head_schedule[min(iter_idx, len(lr_head_schedule) - 1)])
            for g in optimizer.param_groups:
                if g.get("group_name") == "encoder":
                    g["lr"] = lr_enc
                else:
                    g["lr"] = lr_head

            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            target_probs: Optional[torch.Tensor] = None
            if random.random() < args.mix_prob and args.mixup_alpha > 0.0:
                images, target_probs = mixup(images, labels, num_classes=num_classes, alpha=args.mixup_alpha)
            elif random.random() < args.mix_prob and args.cutmix_alpha > 0.0:
                images, target_probs = cutmix(images, labels, num_classes=num_classes, alpha=args.cutmix_alpha)
            else:
                target_probs = one_hot(labels, num_classes=num_classes)

            cw = class_weights.to(device) if class_weights is not None else None
            with get_autocast_context(device, amp_enabled):
                logits, _aux = model(images)
                if args.criterion == "focal":
                    loss = soft_focal_loss(logits, target_probs, gamma=args.focal_gamma, class_weights=cw)
                else:
                    loss = soft_cross_entropy(logits, target_probs, class_weights=cw)

            if not torch.isfinite(loss):
                raise RuntimeError(f"Non-finite loss at step {iter_idx}: {float(loss.item())}")

            losses.append(float(loss.item()))

            scaler.scale(loss / args.accum_steps).backward()

            should_step = ((it + 1) % args.accum_steps == 0) or ((it + 1) == steps_per_epoch)
            if should_step:
                for k, v in model.encoder_grad_norms().items():
                    grad_acc[k].append(float(v))
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1

        train_loss = float(np.mean(losses)) if losses else float("nan")

        val_metrics = evaluate(
            model=model,
            loader=val_loader,
            criterion_type=args.criterion,
            focal_gamma=args.focal_gamma,
            class_weights=class_weights,
            device=device,
            amp=amp_enabled,
            class_names=class_names,
            return_outputs=False,
        )

        elapsed = time.time() - t0
        grad_epoch = {f"grad_norm_{k}": (float(np.mean(v)) if v else 0.0) for k, v in grad_acc.items()}

        record: Dict[str, Any] = {
            "epoch": epoch + 1,
            "global_step": global_step,
            "train_loss": train_loss,
            "val_loss": safe_float(val_metrics.get("loss")),
            "val_accuracy": safe_float(val_metrics.get("accuracy")),
            "val_macro_f1": safe_float(val_metrics.get("macro_f1")),
            "val_macro_auc": safe_float(val_metrics.get("macro_auc")),
            "val_kappa": safe_float(val_metrics.get("kappa")),
            "lr_encoder": lr_enc if any(g.get("group_name") == "encoder" for g in optimizer.param_groups) else 0.0,
            "lr_head": lr_head,
            "time_sec": round(elapsed, 2),
        }
        record.update({k: safe_float(v) for k, v in grad_epoch.items()})
        save_jsonl(log_path, record)

        state = {
            "epoch": epoch + 1,
            "global_step": global_step,
            "best_metric": best_metric,
            "best_epoch": best_epoch,
            "bad_epochs": bad_epochs,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scaler": scaler.state_dict(),
            "args": vars(args),
            "metadata": metadata,
            "class_names": class_names,
            "feature_dims": feature_dims,
            "active_encoders": active_encoders,
        }
        save_checkpoint(out_dir / "last.ckpt", state)

        metric = safe_float(val_metrics.get("macro_f1"))
        score = float(metric) if metric is not None else -float("inf")
        improved = score > best_metric

        if improved:
            best_metric = score
            best_epoch = epoch + 1
            bad_epochs = 0
            state["best_metric"] = best_metric
            state["best_epoch"] = best_epoch
            state["bad_epochs"] = bad_epochs
            save_checkpoint(out_dir / "best.ckpt", state)
        else:
            bad_epochs += 1

        if args.save_every > 0 and ((epoch + 1) % args.save_every == 0):
            save_checkpoint(out_dir / f"epoch_{epoch+1:04d}.ckpt", state)

        if (epoch + 1) >= args.min_epochs and bad_epochs >= args.early_stopping_patience:
            print(
                f"[info] Early stopping at epoch={epoch+1}. No val macro-F1 improvement for {bad_epochs} epochs.",
                flush=True,
            )
            break

    # Restore best model
    best_ckpt_path = out_dir / "best.ckpt"
    if best_ckpt_path.exists():
        best_ckpt = load_checkpoint(best_ckpt_path, map_location="cpu")
        model.load_state_dict(best_ckpt["model"], strict=True)
        best_metric = float(best_ckpt.get("best_metric", best_metric))
        best_epoch = int(best_ckpt.get("best_epoch", best_epoch))

    best_val = evaluate(
        model=model,
        loader=val_loader,
        criterion_type=args.criterion,
        focal_gamma=args.focal_gamma,
        class_weights=class_weights,
        device=device,
        amp=amp_enabled,
        class_names=class_names,
        return_outputs=True,
    )
    test_metrics = evaluate(
        model=model,
        loader=test_loader,
        criterion_type=args.criterion,
        focal_gamma=args.focal_gamma,
        class_weights=class_weights,
        device=device,
        amp=amp_enabled,
        class_names=class_names,
        return_outputs=True,
    )

    # Bootstrap CIs on test metrics.
    y_true_test = test_metrics.pop("y_true")
    y_prob_test = test_metrics.pop("y_prob")
    test_ci = {
        "macro_f1": bootstrap_ci(
            y_true=y_true_test,
            y_prob=y_prob_test,
            class_names=class_names,
            metric_key="macro_f1",
            num_bootstrap=args.bootstrap_samples,
            seed=args.bootstrap_seed,
        ),
        "macro_auc": bootstrap_ci(
            y_true=y_true_test,
            y_prob=y_prob_test,
            class_names=class_names,
            metric_key="macro_auc",
            num_bootstrap=args.bootstrap_samples,
            seed=args.bootstrap_seed + 1,
        ),
        "kappa": bootstrap_ci(
            y_true=y_true_test,
            y_prob=y_prob_test,
            class_names=class_names,
            metric_key="kappa",
            num_bootstrap=args.bootstrap_samples,
            seed=args.bootstrap_seed + 2,
        ),
    }

    # Drop arrays from val bundle as well.
    best_val.pop("y_true", None)
    best_val.pop("y_prob", None)

    deliverable = {
        "experiment_id": "1.6",
        "model_state_dict": model.state_dict(),
        "class_names": class_names,
        "active_encoders": active_encoders,
        "feature_dims": feature_dims,
        "args": vars(args),
        "metadata": metadata,
        "selected_checkpoints": ckpt_paths,
    }
    save_checkpoint(out_dir / args.checkpoint_name, deliverable)

    graph_dir = out_dir / "graphs"
    graphs, graph_error = generate_graphs(log_path=log_path, graph_dir=graph_dir)

    final_results = {
        "experiment_id": "1.6",
        "experiment_name": "Multi-Encoder Fusion for Malocclusion Classification",
        "ablation": args.ablation,
        "fusion": args.fusion,
        "active_encoders": active_encoders,
        "encoder_init": {
            "cls_init_source": cls_init_source if "cls" in active_encoders else None,
            "cls_encoder_name": args.cls_encoder_name if "cls" in active_encoders else None,
        },
        "best_epoch": best_epoch,
        "best_val_macro_f1": safe_float(best_metric),
        "val_metrics_best_model": to_json_compatible(best_val),
        "test_metrics_best_model": to_json_compatible(test_metrics),
        "test_bootstrap_ci": to_json_compatible(test_ci),
        "selected_checkpoints": ckpt_paths,
        "artifacts": {
            "train_log_jsonl": str(log_path),
            "metadata_json": str(out_dir / "metadata.json"),
            "train_samples": str(out_dir / "train_samples.jsonl"),
            "val_samples": str(out_dir / "val_samples.jsonl"),
            "test_samples": str(out_dir / "test_samples.jsonl"),
            "final_results_json": str(out_dir / "final_results.json"),
            "last_checkpoint": str(out_dir / "last.ckpt"),
            "best_checkpoint": str(out_dir / "best.ckpt"),
            "deliverable_checkpoint": str(out_dir / args.checkpoint_name),
        },
        "graphs": graphs,
        "graph_generation_error": graph_error,
    }

    (out_dir / "final_results.json").write_text(json.dumps(to_json_compatible(final_results), indent=2))

    print(
        f"[done] Finished Exp 1.6. Best val macro-F1={safe_float(best_metric)} at epoch={best_epoch}. "
        f"Deliverable checkpoint: {out_dir / args.checkpoint_name}",
        flush=True,
    )


if __name__ == "__main__":
    main()
