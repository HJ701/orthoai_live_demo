#!/usr/bin/env python3
"""
Experiment 1.7 - OrthoPatientFusion.

Patient-level multimodal malocclusion classification:

    patient_id -> {OPG xray, intraoral frontal, buccal, occlusal, ...} -> diagnosis

The five experiment modes map to the concrete plan discussed for Exp 1.7:
  1. late_fusion
  2. attention_mil
  3. set_transformer
  4. cross_attention
  5. auxiliary_heads

This module is intentionally self-contained but reuses Exp 1.6 utilities for
checkpoint-compatible encoders, preprocessing, metrics, and graph generation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_pipeline import apply_preprocess  # noqa: E402
from train_exp1_6_malocclusion import (  # noqa: E402
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_class_weights,
    build_cls_encoder_from_source,
    build_eval_transform,
    build_preprocess_cfg_opg,
    build_preprocess_cfg_rgb,
    build_train_transform,
    cosine_scheduler,
    generate_graphs,
    get_autocast_context,
    infer_output_dim,
    metrics_from_predictions,
    normalize_malocclusion_label,
    safe_float,
    save_checkpoint,
    set_seed,
    soft_cross_entropy,
    soft_focal_loss,
    sort_label_names,
    to_json_compatible,
)


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
EXPERIMENTS = {
    "late_fusion",
    "attention_mil",
    "set_transformer",
    "cross_attention",
    "auxiliary_heads",
}
VIEW_NAMES = [
    "opg",
    "frontal",
    "buccal_left",
    "buccal_right",
    "buccal",
    "occlusal_maxillary",
    "occlusal_mandibular",
    "occlusal",
    "intraoral_other",
]
VIEW_TO_ID = {name: i for i, name in enumerate(VIEW_NAMES)}
MODALITY_TO_ID = {"rgb": 0, "xray": 1}


@dataclass
class ImageRecord:
    image_path: Path
    label_name: str
    label_idx: int
    patient_id: str
    modality: str
    view: str


@dataclass
class PatientRecord:
    patient_id: str
    label_name: str
    label_idx: int
    images: List[ImageRecord]
    split: str = ""


@dataclass
class IngestStats:
    source_csv: str
    modality: str
    total_rows: int = 0
    kept_rows: int = 0
    skipped_missing_label: int = 0
    skipped_missing_path: int = 0
    skipped_invalid_image: int = 0


def resolve_path(path_str: str, repo_root: Path = REPO_ROOT) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p.resolve()
    return (repo_root / p).resolve()


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(to_json_compatible(payload), f, indent=2)


def save_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(to_json_compatible(record)) + "\n")


def is_image_path(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS and not path.name.startswith(".")


def infer_view_from_path(path: Path, modality: str) -> str:
    if modality == "xray":
        return "opg"

    text = f"{path.stem} {path.parent.name}".lower()
    text = text.replace("-", " ").replace("_", " ")

    if any(tok in text for tok in ["front", "frontal", "anterior"]):
        return "frontal"
    if any(tok in text for tok in ["right side", "rightside", "right buccal"]):
        return "buccal_right"
    if any(tok in text for tok in ["left side", "leftside", "left buccal"]):
        return "buccal_left"
    if "buccal" in text or "side" in text:
        return "buccal"
    if any(tok in text for tok in ["occlusal upper", "upper occlusal", "maxillary"]):
        return "occlusal_maxillary"
    if any(tok in text for tok in ["occlusal lower", "lower occlusal", "mandibular"]):
        return "occlusal_mandibular"
    if "occlusal" in text:
        return "occlusal"
    return "intraoral_other"


def load_image_records_from_cleaned_csv(
    csv_path: Path,
    modality: str,
    class_to_idx: Optional[Dict[str, int]] = None,
    strict: bool = False,
) -> Tuple[List[ImageRecord], Dict[str, int], IngestStats]:
    if modality not in MODALITY_TO_ID:
        raise ValueError(f"Unsupported modality: {modality}")
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows: List[Tuple[Path, str, str]] = []
    labels_seen: List[str] = []
    stats = IngestStats(source_csv=str(csv_path), modality=modality)

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")

        for row_idx, row in enumerate(reader, start=2):
            stats.total_rows += 1
            img_raw = str(row.get("Image_Path", row.get("image_path", ""))).strip()
            pid_raw = str(row.get("Patient_ID", row.get("patient_id", ""))).strip()
            label_name = normalize_malocclusion_label(row.get("Malocclusion_Class", row.get("label", "")))

            if label_name is None:
                stats.skipped_missing_label += 1
                if strict:
                    raise ValueError(f"Missing Malocclusion_Class at {csv_path}:{row_idx}")
                continue
            if not img_raw:
                stats.skipped_missing_path += 1
                if strict:
                    raise ValueError(f"Missing Image_Path at {csv_path}:{row_idx}")
                continue

            image_path = resolve_path(img_raw)
            if not image_path.exists():
                stats.skipped_missing_path += 1
                if strict:
                    raise FileNotFoundError(f"Image path not found at {csv_path}:{row_idx}: {image_path}")
                continue
            if not is_image_path(image_path):
                stats.skipped_invalid_image += 1
                if strict:
                    raise ValueError(f"Invalid image path at {csv_path}:{row_idx}: {image_path}")
                continue

            patient_id = pid_raw or image_path.stem.split("_")[0]
            rows.append((image_path, label_name, patient_id))
            labels_seen.append(label_name)
            stats.kept_rows += 1

    if not rows:
        raise RuntimeError(f"No usable rows found in CSV: {csv_path}")

    if class_to_idx is None:
        class_to_idx = {name: i for i, name in enumerate(sort_label_names(labels_seen))}
    else:
        for name in sort_label_names(labels_seen):
            if name not in class_to_idx:
                class_to_idx[name] = len(class_to_idx)

    records: List[ImageRecord] = []
    for image_path, label_name, patient_id in rows:
        records.append(
            ImageRecord(
                image_path=image_path,
                label_name=label_name,
                label_idx=int(class_to_idx[label_name]),
                patient_id=str(patient_id),
                modality=modality,
                view=infer_view_from_path(image_path, modality),
            )
        )

    return records, class_to_idx, stats


def parse_required_modalities(text: str) -> List[str]:
    vals = [x.strip().lower() for x in str(text).split(",") if x.strip()]
    for v in vals:
        if v not in MODALITY_TO_ID:
            raise ValueError(f"Unsupported required modality: {v}")
    return vals


def group_patient_records(
    image_records: Sequence[ImageRecord],
    required_modalities: Sequence[str],
    min_images_per_patient: int,
) -> Tuple[List[PatientRecord], Dict[str, Any]]:
    by_patient: Dict[str, List[ImageRecord]] = defaultdict(list)
    for rec in image_records:
        by_patient[rec.patient_id].append(rec)

    patients: List[PatientRecord] = []
    skipped_missing_modality = 0
    skipped_too_few_images = 0
    label_conflicts = 0

    required = set(required_modalities)
    for pid, images in sorted(by_patient.items()):
        modalities = {x.modality for x in images}
        if required and not required.issubset(modalities):
            skipped_missing_modality += 1
            continue
        if len(images) < int(min_images_per_patient):
            skipped_too_few_images += 1
            continue

        label_counts = Counter(x.label_name for x in images)
        if len(label_counts) > 1:
            label_conflicts += 1
        label_name = label_counts.most_common(1)[0][0]
        label_idx = next(x.label_idx for x in images if x.label_name == label_name)

        patients.append(
            PatientRecord(
                patient_id=pid,
                label_name=label_name,
                label_idx=int(label_idx),
                images=sorted(images, key=lambda x: (x.modality, x.view, str(x.image_path))),
            )
        )

    stats = {
        "input_patients": len(by_patient),
        "kept_patients": len(patients),
        "skipped_missing_required_modality": skipped_missing_modality,
        "skipped_too_few_images": skipped_too_few_images,
        "label_conflict_patients_majority_vote": label_conflicts,
        "required_modalities": sorted(required),
    }
    return patients, stats


def split_patients(
    patients: Sequence[PatientRecord],
    split_ratios: Tuple[float, float, float],
    seed: int,
) -> Tuple[List[PatientRecord], List[PatientRecord], List[PatientRecord]]:
    by_label: Dict[int, List[PatientRecord]] = defaultdict(list)
    for p in patients:
        by_label[int(p.label_idx)].append(p)

    rng = random.Random(seed)
    train: List[PatientRecord] = []
    val: List[PatientRecord] = []
    test: List[PatientRecord] = []
    tr, va, _te = split_ratios

    for _label, group in sorted(by_label.items()):
        group = list(group)
        rng.shuffle(group)
        n = len(group)
        n_train = int(round(n * tr))
        n_val = int(round(n * va))
        if n >= 3:
            n_train = min(max(n_train, 1), n - 2)
            n_val = min(max(n_val, 1), n - n_train - 1)
        else:
            n_train = max(1, n - 1)
            n_val = 0
        train.extend(group[:n_train])
        val.extend(group[n_train : n_train + n_val])
        test.extend(group[n_train + n_val :])

    for split_name, records in [("train", train), ("val", val), ("test", test)]:
        for p in records:
            p.split = split_name

    return train, val, test


def parse_split_ratios(text: str) -> Tuple[float, float, float]:
    vals = [float(x.strip()) for x in str(text).split(",") if x.strip()]
    if len(vals) != 3:
        raise ValueError("--split-ratios must contain train,val,test")
    total = sum(vals)
    if total <= 0:
        raise ValueError("--split-ratios must sum to > 0")
    return vals[0] / total, vals[1] / total, vals[2] / total


def summarize_patients(split: str, patients: Sequence[PatientRecord]) -> Dict[str, Any]:
    class_counts: Dict[str, int] = {}
    modality_counts: Dict[str, int] = {"rgb": 0, "xray": 0}
    view_counts: Dict[str, int] = {}
    image_counts: List[int] = []
    for p in patients:
        class_counts[p.label_name] = class_counts.get(p.label_name, 0) + 1
        image_counts.append(len(p.images))
        for im in p.images:
            modality_counts[im.modality] = modality_counts.get(im.modality, 0) + 1
            view_counts[im.view] = view_counts.get(im.view, 0) + 1
    return {
        "split": split,
        "num_patients": len(patients),
        "num_images": int(sum(image_counts)),
        "images_per_patient": {
            "min": int(min(image_counts)) if image_counts else 0,
            "max": int(max(image_counts)) if image_counts else 0,
            "mean": float(np.mean(image_counts)) if image_counts else 0.0,
            "median": float(np.median(image_counts)) if image_counts else 0.0,
        },
        "class_counts": class_counts,
        "modality_counts": modality_counts,
        "view_counts": view_counts,
    }


def write_patient_manifest(path: Path, patients: Sequence[PatientRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for p in patients:
            payload = {
                "patient_id": p.patient_id,
                "label": p.label_name,
                "label_idx": p.label_idx,
                "split": p.split,
                "images": [
                    {
                        "image_path": str(im.image_path),
                        "modality": im.modality,
                        "view": im.view,
                    }
                    for im in p.images
                ],
            }
            f.write(json.dumps(payload) + "\n")


class PatientBagDataset(Dataset):
    def __init__(
        self,
        patients: Sequence[PatientRecord],
        train: bool,
        image_size: int,
        max_images_per_patient: int,
        max_images_per_view: int,
        require_opg_first: bool = True,
    ):
        if not patients:
            raise RuntimeError("No patient records available for dataset.")
        self.patients = list(patients)
        self.train = bool(train)
        self.image_size = int(image_size)
        self.max_images_per_patient = int(max_images_per_patient)
        self.max_images_per_view = int(max_images_per_view)
        self.require_opg_first = bool(require_opg_first)
        self.preprocess_cfg_rgb = build_preprocess_cfg_rgb()
        self.preprocess_cfg_xray = build_preprocess_cfg_opg()
        self.transform = build_train_transform(image_size) if self.train else build_eval_transform(image_size)

    def __len__(self) -> int:
        return len(self.patients)

    def _select_images(self, patient: PatientRecord) -> List[ImageRecord]:
        by_view: Dict[str, List[ImageRecord]] = defaultdict(list)
        for im in patient.images:
            by_view[im.view].append(im)

        selected: List[ImageRecord] = []
        for view in VIEW_NAMES:
            imgs = list(by_view.get(view, []))
            if not imgs:
                continue
            if self.train:
                random.shuffle(imgs)
            else:
                imgs.sort(key=lambda x: str(x.image_path))
            selected.extend(imgs[: max(1, self.max_images_per_view)])

        if self.require_opg_first:
            selected.sort(key=lambda x: (0 if x.modality == "xray" else 1, VIEW_TO_ID.get(x.view, 999), str(x.image_path)))

        if self.max_images_per_patient > 0 and len(selected) > self.max_images_per_patient:
            opg = [x for x in selected if x.modality == "xray"]
            rest = [x for x in selected if x.modality != "xray"]
            if self.train:
                random.shuffle(rest)
            keep = opg[:1] + rest
            selected = keep[: self.max_images_per_patient]

        if not selected:
            raise RuntimeError(f"Patient has no selected images: {patient.patient_id}")
        return selected

    def __getitem__(self, index: int) -> Dict[str, Any]:
        patient = self.patients[index]
        images = self._select_images(patient)

        tensors: List[torch.Tensor] = []
        view_ids: List[int] = []
        modality_ids: List[int] = []
        paths: List[str] = []

        for im_rec in images:
            with Image.open(im_rec.image_path) as im:
                im.load()
                im = im.convert("RGB")
                cfg = self.preprocess_cfg_xray if im_rec.modality == "xray" else self.preprocess_cfg_rgb
                im = apply_preprocess(im, cfg, dataset_name=im_rec.modality)
                tensors.append(self.transform(im))
            view_ids.append(VIEW_TO_ID.get(im_rec.view, VIEW_TO_ID["intraoral_other"]))
            modality_ids.append(MODALITY_TO_ID[im_rec.modality])
            paths.append(str(im_rec.image_path))

        return {
            "images": torch.stack(tensors, dim=0),
            "view_ids": torch.tensor(view_ids, dtype=torch.long),
            "modality_ids": torch.tensor(modality_ids, dtype=torch.long),
            "label": int(patient.label_idx),
            "patient_id": patient.patient_id,
            "paths": paths,
        }


def patient_collate_fn(batch: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    flat_images: List[torch.Tensor] = []
    patient_index: List[int] = []
    flat_view_ids: List[torch.Tensor] = []
    flat_modality_ids: List[torch.Tensor] = []
    labels: List[int] = []
    patient_ids: List[str] = []
    paths: List[List[str]] = []
    image_counts: List[int] = []

    for i, item in enumerate(batch):
        n = int(item["images"].shape[0])
        flat_images.append(item["images"])
        patient_index.extend([i] * n)
        flat_view_ids.append(item["view_ids"])
        flat_modality_ids.append(item["modality_ids"])
        labels.append(int(item["label"]))
        patient_ids.append(str(item["patient_id"]))
        paths.append(list(item["paths"]))
        image_counts.append(n)

    return {
        "images": torch.cat(flat_images, dim=0),
        "patient_index": torch.tensor(patient_index, dtype=torch.long),
        "view_ids": torch.cat(flat_view_ids, dim=0),
        "modality_ids": torch.cat(flat_modality_ids, dim=0),
        "labels": torch.tensor(labels, dtype=torch.long),
        "patient_ids": patient_ids,
        "paths": paths,
        "image_counts": torch.tensor(image_counts, dtype=torch.long),
    }


class MLPHead(nn.Module):
    def __init__(self, dim: int, num_classes: int, dropout: float):
        super().__init__()
        self.net = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Dropout(dropout),
            nn.Linear(dim, dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class PatientFusionModel(nn.Module):
    def __init__(
        self,
        experiment: str,
        num_classes: int,
        image_size: int,
        opg_encoder_name: str,
        rgb_encoder_name: str,
        encoder_init_source: str,
        token_dim: int,
        fusion_layers: int,
        fusion_heads: int,
        diagnosis_queries: int,
        dropout: float,
        shared_encoder: bool,
    ):
        super().__init__()
        if experiment not in EXPERIMENTS:
            raise ValueError(f"Unsupported experiment: {experiment}")
        self.experiment = experiment
        self.num_classes = int(num_classes)
        self.token_dim = int(token_dim)
        self.shared_encoder = bool(shared_encoder)

        self.rgb_encoder = build_cls_encoder_from_source(rgb_encoder_name, encoder_init_source)
        rgb_dim = infer_output_dim(self.rgb_encoder, image_size=image_size)
        if self.shared_encoder:
            self.opg_encoder = self.rgb_encoder
            opg_dim = rgb_dim
        else:
            self.opg_encoder = build_cls_encoder_from_source(opg_encoder_name, encoder_init_source)
            opg_dim = infer_output_dim(self.opg_encoder, image_size=image_size)

        self.rgb_proj = nn.Sequential(nn.LayerNorm(rgb_dim), nn.Linear(rgb_dim, token_dim), nn.GELU(), nn.LayerNorm(token_dim))
        self.opg_proj = nn.Sequential(nn.LayerNorm(opg_dim), nn.Linear(opg_dim, token_dim), nn.GELU(), nn.LayerNorm(token_dim))

        self.view_embed = nn.Embedding(len(VIEW_NAMES), token_dim)
        self.modality_embed = nn.Embedding(len(MODALITY_TO_ID), token_dim)
        self.image_dropout = nn.Dropout(dropout)

        self.image_head = MLPHead(token_dim, num_classes, dropout)
        self.patient_head = MLPHead(token_dim, num_classes, dropout)
        self.attention_score = nn.Sequential(nn.LayerNorm(token_dim), nn.Linear(token_dim, token_dim // 2), nn.GELU(), nn.Linear(token_dim // 2, 1))

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=token_dim,
            nhead=fusion_heads,
            dim_feedforward=token_dim * 4,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.set_encoder = nn.TransformerEncoder(encoder_layer, num_layers=fusion_layers)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, token_dim))

        self.diagnosis_queries = int(max(1, diagnosis_queries))
        self.query_tokens = nn.Parameter(torch.zeros(1, self.diagnosis_queries, token_dim))
        self.cross_attn = nn.MultiheadAttention(token_dim, fusion_heads, dropout=dropout, batch_first=True)
        self.cross_norm = nn.LayerNorm(token_dim)
        self.query_patient_head = MLPHead(token_dim * self.diagnosis_queries, num_classes, dropout)

        self.aux_modality_heads = nn.ModuleDict(
            {
                "rgb": MLPHead(token_dim, num_classes, dropout),
                "xray": MLPHead(token_dim, num_classes, dropout),
            }
        )

        nn.init.trunc_normal_(self.cls_token, std=0.02)
        nn.init.trunc_normal_(self.query_tokens, std=0.02)

    def encoder_parameters(self) -> Iterable[nn.Parameter]:
        seen: set[int] = set()
        for module in [self.rgb_encoder, self.opg_encoder]:
            for p in module.parameters():
                ident = id(p)
                if ident not in seen:
                    seen.add(ident)
                    yield p

    def non_encoder_parameters(self) -> Iterable[nn.Parameter]:
        encoder_param_ids = {id(p) for p in self.encoder_parameters()}
        for p in self.parameters():
            if id(p) not in encoder_param_ids:
                yield p

    def set_encoders_trainable(self, trainable: bool) -> None:
        for p in self.encoder_parameters():
            p.requires_grad = bool(trainable)

    def _encode_images(
        self,
        images: torch.Tensor,
        view_ids: torch.Tensor,
        modality_ids: torch.Tensor,
    ) -> torch.Tensor:
        tokens = torch.zeros(images.shape[0], self.token_dim, device=images.device, dtype=images.dtype)

        rgb_mask = modality_ids == MODALITY_TO_ID["rgb"]
        xray_mask = modality_ids == MODALITY_TO_ID["xray"]

        if bool(rgb_mask.any()):
            feat = self.rgb_encoder(images[rgb_mask])
            tokens[rgb_mask] = self.rgb_proj(feat)
        if bool(xray_mask.any()):
            feat = self.opg_encoder(images[xray_mask])
            tokens[xray_mask] = self.opg_proj(feat)

        tokens = tokens + self.view_embed(view_ids) + self.modality_embed(modality_ids)
        return self.image_dropout(tokens)

    @staticmethod
    def _pad_tokens(tokens: torch.Tensor, patient_index: torch.Tensor, batch_size: int) -> Tuple[torch.Tensor, torch.Tensor]:
        counts = torch.bincount(patient_index, minlength=batch_size)
        max_count = int(counts.max().item())
        padded = tokens.new_zeros((batch_size, max_count, tokens.shape[-1]))
        pad_mask = torch.ones((batch_size, max_count), dtype=torch.bool, device=tokens.device)
        cursor = torch.zeros((batch_size,), dtype=torch.long, device=tokens.device)
        for i in range(tokens.shape[0]):
            b = int(patient_index[i].item())
            j = int(cursor[b].item())
            padded[b, j] = tokens[i]
            pad_mask[b, j] = False
            cursor[b] += 1
        return padded, pad_mask

    @staticmethod
    def _scatter_mean(values: torch.Tensor, patient_index: torch.Tensor, batch_size: int) -> torch.Tensor:
        out = values.new_zeros((batch_size, values.shape[-1]))
        out.index_add_(0, patient_index, values)
        counts = torch.bincount(patient_index, minlength=batch_size).to(values.device).clamp_min(1).unsqueeze(1)
        return out / counts

    def forward(
        self,
        images: torch.Tensor,
        patient_index: torch.Tensor,
        view_ids: torch.Tensor,
        modality_ids: torch.Tensor,
        batch_size: int,
    ) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        tokens = self._encode_images(images, view_ids, modality_ids)
        aux: Dict[str, torch.Tensor] = {
            "tokens": tokens,
            "patient_index": patient_index,
            "modality_ids": modality_ids,
        }

        if self.experiment == "late_fusion":
            image_logits = self.image_head(tokens)
            aux["image_logits"] = image_logits
            logits = self._scatter_mean(image_logits, patient_index, batch_size)
            return logits, aux

        padded, pad_mask = self._pad_tokens(tokens, patient_index, batch_size)

        if self.experiment == "attention_mil":
            scores = self.attention_score(padded).squeeze(-1)
            scores = scores.masked_fill(pad_mask, -1e4)
            weights = torch.softmax(scores, dim=1)
            pooled = torch.sum(padded * weights.unsqueeze(-1), dim=1)
            aux["attention_weights"] = weights
            return self.patient_head(pooled), aux

        if self.experiment == "set_transformer":
            cls = self.cls_token.expand(batch_size, -1, -1)
            x = torch.cat([cls, padded], dim=1)
            cls_mask = torch.zeros((batch_size, 1), dtype=torch.bool, device=pad_mask.device)
            mask = torch.cat([cls_mask, pad_mask], dim=1)
            encoded = self.set_encoder(x, src_key_padding_mask=mask)
            return self.patient_head(encoded[:, 0]), aux

        # Cross-attention is also the backbone for auxiliary_heads.
        queries = self.query_tokens.expand(batch_size, -1, -1)
        attended, weights = self.cross_attn(queries, padded, padded, key_padding_mask=pad_mask, need_weights=True)
        attended = self.cross_norm(attended)
        aux["cross_attention_weights"] = weights
        logits = self.query_patient_head(attended.flatten(1))

        if self.experiment == "auxiliary_heads":
            aux_logits = tokens.new_zeros((tokens.shape[0], self.num_classes))
            for modality, idx in MODALITY_TO_ID.items():
                mask = modality_ids == idx
                if bool(mask.any()):
                    aux_logits[mask] = self.aux_modality_heads[modality](tokens[mask])
            aux["image_logits"] = aux_logits

        return logits, aux


def one_hot(labels: torch.Tensor, num_classes: int) -> torch.Tensor:
    return F.one_hot(labels, num_classes=num_classes).float()


def compute_loss(
    logits: torch.Tensor,
    labels: torch.Tensor,
    criterion: str,
    focal_gamma: float,
    class_weights: Optional[torch.Tensor],
) -> torch.Tensor:
    targets = one_hot(labels, logits.shape[-1])
    if criterion == "focal":
        return soft_focal_loss(logits, targets, gamma=focal_gamma, class_weights=class_weights)
    return soft_cross_entropy(logits, targets, class_weights=class_weights)


def expand_patient_labels(labels: torch.Tensor, patient_index: torch.Tensor) -> torch.Tensor:
    return labels[patient_index]


@torch.no_grad()
def evaluate_patient_model(
    model: PatientFusionModel,
    loader: DataLoader,
    device: torch.device,
    amp: bool,
    criterion: str,
    focal_gamma: float,
    class_weights: Optional[torch.Tensor],
    class_names: Sequence[str],
    aux_loss_weight: float,
) -> Dict[str, Any]:
    model.eval()
    losses: List[float] = []
    true_all: List[np.ndarray] = []
    prob_all: List[np.ndarray] = []

    cw = class_weights.to(device) if class_weights is not None else None

    for batch in loader:
        images = batch["images"].to(device, non_blocking=True)
        patient_index = batch["patient_index"].to(device, non_blocking=True)
        view_ids = batch["view_ids"].to(device, non_blocking=True)
        modality_ids = batch["modality_ids"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)

        with get_autocast_context(device, amp):
            logits, aux = model(images, patient_index, view_ids, modality_ids, batch_size=labels.shape[0])
            loss = compute_loss(logits, labels, criterion, focal_gamma, cw)
            if aux_loss_weight > 0 and "image_logits" in aux:
                image_labels = expand_patient_labels(labels, patient_index)
                loss = loss + aux_loss_weight * compute_loss(aux["image_logits"], image_labels, criterion, focal_gamma, cw)

        losses.append(float(loss.item()))
        true_all.append(labels.detach().cpu().numpy())
        prob_all.append(torch.softmax(logits, dim=1).detach().cpu().numpy())

    y_true = np.concatenate(true_all, axis=0) if true_all else np.zeros((0,), dtype=np.int64)
    y_prob = np.concatenate(prob_all, axis=0) if prob_all else np.zeros((0, len(class_names)), dtype=np.float32)
    metrics = metrics_from_predictions(y_true, y_prob, class_names)
    metrics["loss"] = float(np.mean(losses)) if losses else float("nan")
    metrics["y_true"] = y_true
    metrics["y_prob"] = y_prob
    return metrics


def strip_metric_arrays(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in metrics.items() if k not in {"y_true", "y_prob"}}


def write_epoch_record(path: Path, record: Dict[str, Any]) -> None:
    save_jsonl(path, record)


def build_arg_parser(default_experiment: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Exp 1.7 OrthoPatientFusion patient-level multimodal training")

    p.add_argument("--experiment", choices=sorted(EXPERIMENTS), default=default_experiment)
    p.add_argument("--rgb-csv", type=str, default="data/Orthoai-cleaned-dataset-dr-Mohammed/rgb_intraoral_labels_matched_from_rgb_intraoral_cleaned.csv")
    p.add_argument("--opg-csv", type=str, default="data/Orthoai-cleaned-dataset-dr-Mohammed/opg_cleaned.csv")
    p.add_argument("--strict-cleaned-csv", action="store_true")
    p.add_argument("--required-modalities", type=str, default="rgb,xray", help="Comma-separated modalities required per patient. Use empty string to allow incomplete bags.")
    p.add_argument("--min-images-per-patient", type=int, default=2)
    p.add_argument("--max-images-per-patient", type=int, default=8)
    p.add_argument("--max-images-per-view", type=int, default=2)
    p.add_argument("--split-ratios", type=str, default="0.70,0.15,0.15")
    p.add_argument("--seed", type=int, default=42)

    p.add_argument("--opg-encoder-name", choices=["convnext_tiny", "resnet50", "resnet101", "efficientnet_b3", "vit_b16"], default="convnext_tiny")
    p.add_argument("--rgb-encoder-name", choices=["convnext_tiny", "resnet50", "resnet101", "efficientnet_b3", "vit_b16"], default="convnext_tiny")
    p.add_argument("--encoder-init-source", choices=["imagenet", "random"], default="imagenet")
    p.add_argument("--shared-encoder", action="store_true")
    p.add_argument("--freeze-encoders", action="store_true")
    p.add_argument("--token-dim", type=int, default=512)
    p.add_argument("--fusion-layers", type=int, default=2)
    p.add_argument("--fusion-heads", type=int, default=8)
    p.add_argument("--diagnosis-queries", type=int, default=1)
    p.add_argument("--dropout", type=float, default=0.25)

    p.add_argument("--image-size", type=int, default=224)
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--min-epochs", type=int, default=15)
    p.add_argument("--early-stopping-patience", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--accum-steps", type=int, default=1)
    p.add_argument("--num-workers", type=int, default=8)
    p.add_argument("--encoder-lr", type=float, default=1e-5)
    p.add_argument("--fusion-lr", type=float, default=5e-4)
    p.add_argument("--min-lr-scale", type=float, default=0.10)
    p.add_argument("--warmup-epochs", type=int, default=5)
    p.add_argument("--weight-decay", type=float, default=0.05)
    p.add_argument("--criterion", choices=["ce", "focal"], default="focal")
    p.add_argument("--focal-gamma", type=float, default=2.0)
    p.add_argument("--class-weight-mode", choices=["none", "balanced", "sqrt_balanced"], default="sqrt_balanced")
    p.add_argument("--aux-loss-weight", type=float, default=0.25)

    p.add_argument("--device", type=str, default="cuda")
    p.add_argument("--amp", action="store_true")
    p.add_argument("--save-every", type=int, default=5)
    p.add_argument("--out-dir", type=str, default="")
    p.add_argument("--checkpoint-name", type=str, default="exp1_7_orthopatientfusion.ckpt")
    p.add_argument("--resume", type=str, default="")

    return p


def prepare_data(args: argparse.Namespace) -> Tuple[List[PatientRecord], List[PatientRecord], List[PatientRecord], Dict[str, Any], List[str]]:
    class_to_idx: Optional[Dict[str, int]] = None
    all_images: List[ImageRecord] = []
    ingest_stats: List[Dict[str, Any]] = []

    if args.rgb_csv:
        records, class_to_idx, stats = load_image_records_from_cleaned_csv(
            resolve_path(args.rgb_csv),
            modality="rgb",
            class_to_idx=class_to_idx,
            strict=bool(args.strict_cleaned_csv),
        )
        all_images.extend(records)
        ingest_stats.append(asdict(stats))

    if args.opg_csv:
        records, class_to_idx, stats = load_image_records_from_cleaned_csv(
            resolve_path(args.opg_csv),
            modality="xray",
            class_to_idx=class_to_idx,
            strict=bool(args.strict_cleaned_csv),
        )
        all_images.extend(records)
        ingest_stats.append(asdict(stats))

    if not all_images or class_to_idx is None:
        raise RuntimeError("No image records loaded. Provide --rgb-csv and/or --opg-csv.")

    required_modalities = parse_required_modalities(args.required_modalities)
    patients, group_stats = group_patient_records(
        all_images,
        required_modalities=required_modalities,
        min_images_per_patient=args.min_images_per_patient,
    )
    if len(patients) < 10:
        raise RuntimeError(f"Too few patients for Exp 1.7 after filtering: {len(patients)}")

    train, val, test = split_patients(patients, parse_split_ratios(args.split_ratios), seed=args.seed)
    class_names = [name for name, _idx in sorted(class_to_idx.items(), key=lambda kv: kv[1])]
    stats = {
        "ingest": ingest_stats,
        "grouping": group_stats,
        "split_summary": {
            "train": summarize_patients("train", train),
            "val": summarize_patients("val", val),
            "test": summarize_patients("test", test),
        },
    }
    return train, val, test, stats, class_names


def checkpoint_payload(
    args: argparse.Namespace,
    model: PatientFusionModel,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    best_val_macro_f1: float,
    class_names: Sequence[str],
    data_stats: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "experiment_id": "1.7",
        "experiment_name": "OrthoPatientFusion",
        "fusion_experiment": args.experiment,
        "epoch": int(epoch),
        "best_val_macro_f1": float(best_val_macro_f1),
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "class_names": list(class_names),
        "args": vars(args),
        "data_stats": data_stats,
    }


def main(default_experiment: str = "cross_attention") -> None:
    parser = build_arg_parser(default_experiment=default_experiment)
    args = parser.parse_args()
    set_seed(args.seed)

    if args.experiment not in EXPERIMENTS:
        raise ValueError(f"Unsupported experiment: {args.experiment}")
    if args.accum_steps <= 0:
        raise ValueError("--accum-steps must be > 0")

    run_name = args.experiment
    out_dir = resolve_path(args.out_dir) if args.out_dir else REPO_ROOT / "models" / "exp1_7_orthopatientfusion_runs" / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "train_log.jsonl"
    final_results_path = out_dir / "final_results.json"

    print(f"[info] Exp 1.7 OrthoPatientFusion mode: {args.experiment}", flush=True)
    print(f"[info] Output dir: {out_dir}", flush=True)

    train_patients, val_patients, test_patients, data_stats, class_names = prepare_data(args)
    num_classes = len(class_names)
    write_patient_manifest(out_dir / "train_patients.jsonl", train_patients)
    write_patient_manifest(out_dir / "val_patients.jsonl", val_patients)
    write_patient_manifest(out_dir / "test_patients.jsonl", test_patients)
    save_json(out_dir / "metadata.json", {"args": vars(args), "class_names": class_names, "data_stats": data_stats})

    train_ds = PatientBagDataset(train_patients, train=True, image_size=args.image_size, max_images_per_patient=args.max_images_per_patient, max_images_per_view=args.max_images_per_view)
    val_ds = PatientBagDataset(val_patients, train=False, image_size=args.image_size, max_images_per_patient=args.max_images_per_patient, max_images_per_view=args.max_images_per_view)
    test_ds = PatientBagDataset(test_patients, train=False, image_size=args.image_size, max_images_per_patient=args.max_images_per_patient, max_images_per_view=args.max_images_per_view)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, pin_memory=True, collate_fn=patient_collate_fn)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=True, collate_fn=patient_collate_fn)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=True, collate_fn=patient_collate_fn)

    device = torch.device(args.device if (args.device != "cuda" or torch.cuda.is_available()) else "cpu")
    model = PatientFusionModel(
        experiment=args.experiment,
        num_classes=num_classes,
        image_size=args.image_size,
        opg_encoder_name=args.opg_encoder_name,
        rgb_encoder_name=args.rgb_encoder_name,
        encoder_init_source=args.encoder_init_source,
        token_dim=args.token_dim,
        fusion_layers=args.fusion_layers,
        fusion_heads=args.fusion_heads,
        diagnosis_queries=args.diagnosis_queries,
        dropout=args.dropout,
        shared_encoder=args.shared_encoder,
    )
    model.set_encoders_trainable(not args.freeze_encoders)
    model.to(device)

    encoder_params = [p for p in model.encoder_parameters() if p.requires_grad]
    fusion_params = [p for p in model.non_encoder_parameters() if p.requires_grad]
    param_groups = []
    if encoder_params:
        param_groups.append({"params": encoder_params, "lr": args.encoder_lr, "name": "encoder"})
    if fusion_params:
        param_groups.append({"params": fusion_params, "lr": args.fusion_lr, "name": "fusion"})
    optimizer = torch.optim.AdamW(param_groups, weight_decay=args.weight_decay)

    start_epoch = 1
    best_val_macro_f1 = -1.0
    if args.resume:
        ckpt = torch.load(resolve_path(args.resume), map_location="cpu")
        model.load_state_dict(ckpt["model_state_dict"], strict=True)
        if "optimizer_state_dict" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_epoch = int(ckpt.get("epoch", 0)) + 1
        best_val_macro_f1 = float(ckpt.get("best_val_macro_f1", -1.0))
        print(f"[info] Resumed from {args.resume} at epoch {start_epoch}", flush=True)

    class_weights = build_class_weights(
        [
            type("PatientClassProxy", (), {"label_idx": int(p.label_idx)})()
            for p in train_patients
        ],
        num_classes=num_classes,
        mode=args.class_weight_mode,
    )
    class_weights_device = class_weights.to(device) if class_weights is not None else None

    total_steps = max(1, args.epochs)
    encoder_schedule = cosine_scheduler(args.encoder_lr, args.encoder_lr * args.min_lr_scale, total_steps, args.warmup_epochs, args.encoder_lr * 0.1)
    fusion_schedule = cosine_scheduler(args.fusion_lr, args.fusion_lr * args.min_lr_scale, total_steps, args.warmup_epochs, args.fusion_lr * 0.1)

    scaler = torch.cuda.amp.GradScaler(enabled=bool(args.amp and device.type == "cuda"))
    epochs_without_improvement = 0

    for epoch in range(start_epoch, args.epochs + 1):
        model.train()
        t0 = time.time()
        for group in optimizer.param_groups:
            if group.get("name") == "encoder":
                group["lr"] = float(encoder_schedule[epoch - 1])
            else:
                group["lr"] = float(fusion_schedule[epoch - 1])

        optimizer.zero_grad(set_to_none=True)
        train_losses: List[float] = []

        for step, batch in enumerate(train_loader, start=1):
            images = batch["images"].to(device, non_blocking=True)
            patient_index = batch["patient_index"].to(device, non_blocking=True)
            view_ids = batch["view_ids"].to(device, non_blocking=True)
            modality_ids = batch["modality_ids"].to(device, non_blocking=True)
            labels = batch["labels"].to(device, non_blocking=True)

            with get_autocast_context(device, args.amp):
                logits, aux = model(images, patient_index, view_ids, modality_ids, batch_size=labels.shape[0])
                loss = compute_loss(logits, labels, args.criterion, args.focal_gamma, class_weights_device)
                if args.aux_loss_weight > 0 and "image_logits" in aux:
                    image_labels = expand_patient_labels(labels, patient_index)
                    loss = loss + args.aux_loss_weight * compute_loss(aux["image_logits"], image_labels, args.criterion, args.focal_gamma, class_weights_device)
                loss = loss / args.accum_steps

            scaler.scale(loss).backward()
            if step % args.accum_steps == 0 or step == len(train_loader):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)

            train_losses.append(float(loss.item() * args.accum_steps))

        val_metrics = evaluate_patient_model(
            model,
            val_loader,
            device=device,
            amp=args.amp,
            criterion=args.criterion,
            focal_gamma=args.focal_gamma,
            class_weights=class_weights,
            class_names=class_names,
            aux_loss_weight=args.aux_loss_weight if args.experiment == "auxiliary_heads" else 0.0,
        )
        val_macro_f1 = safe_float(val_metrics.get("macro_f1")) or -1.0
        improved = val_macro_f1 > best_val_macro_f1
        if improved:
            best_val_macro_f1 = val_macro_f1
            epochs_without_improvement = 0
            save_checkpoint(out_dir / "best.ckpt", checkpoint_payload(args, model, optimizer, epoch, best_val_macro_f1, class_names, data_stats))
        else:
            epochs_without_improvement += 1

        if args.save_every > 0 and epoch % args.save_every == 0:
            save_checkpoint(out_dir / f"epoch_{epoch:04d}.ckpt", checkpoint_payload(args, model, optimizer, epoch, best_val_macro_f1, class_names, data_stats))
        save_checkpoint(out_dir / "last.ckpt", checkpoint_payload(args, model, optimizer, epoch, best_val_macro_f1, class_names, data_stats))

        record = {
            "epoch": epoch,
            "train_loss": float(np.mean(train_losses)) if train_losses else float("nan"),
            "val_loss": val_metrics.get("loss"),
            "val_accuracy": val_metrics.get("accuracy"),
            "val_macro_f1": val_metrics.get("macro_f1"),
            "val_macro_auc": val_metrics.get("macro_auc"),
            "val_kappa": val_metrics.get("kappa"),
            "lr_encoder": float(encoder_schedule[epoch - 1]),
            "lr_head": float(fusion_schedule[epoch - 1]),
            "epoch_seconds": time.time() - t0,
            "best_val_macro_f1": best_val_macro_f1,
        }
        write_epoch_record(log_path, record)
        print(json.dumps(to_json_compatible(record)), flush=True)

        if epoch >= args.min_epochs and epochs_without_improvement >= args.early_stopping_patience:
            print(f"[info] Early stopping at epoch {epoch}", flush=True)
            break

    best_path = out_dir / "best.ckpt"
    if best_path.exists():
        ckpt = torch.load(best_path, map_location="cpu")
        model.load_state_dict(ckpt["model_state_dict"], strict=True)
        model.to(device)

    val_best = evaluate_patient_model(
        model,
        val_loader,
        device=device,
        amp=args.amp,
        criterion=args.criterion,
        focal_gamma=args.focal_gamma,
        class_weights=class_weights,
        class_names=class_names,
        aux_loss_weight=args.aux_loss_weight if args.experiment == "auxiliary_heads" else 0.0,
    )
    test_best = evaluate_patient_model(
        model,
        test_loader,
        device=device,
        amp=args.amp,
        criterion=args.criterion,
        focal_gamma=args.focal_gamma,
        class_weights=class_weights,
        class_names=class_names,
        aux_loss_weight=args.aux_loss_weight if args.experiment == "auxiliary_heads" else 0.0,
    )
    graphs, graph_error = generate_graphs(log_path, out_dir / "graphs")

    deliverable = out_dir / args.checkpoint_name
    if best_path.exists():
        ckpt = torch.load(best_path, map_location="cpu")
        save_checkpoint(deliverable, ckpt)

    final_payload = {
        "experiment_id": "1.7",
        "experiment_name": "OrthoPatientFusion",
        "fusion_experiment": args.experiment,
        "best_checkpoint": str(best_path),
        "deliverable_checkpoint": str(deliverable),
        "best_val_macro_f1": strip_metric_arrays(val_best).get("macro_f1"),
        "val_metrics_best_model": strip_metric_arrays(val_best),
        "test_metrics_best_model": strip_metric_arrays(test_best),
        "class_names": class_names,
        "data_stats": data_stats,
        "graphs": graphs,
        "graph_error": graph_error,
        "metadata_file": str(out_dir / "metadata.json"),
        "train_log": str(log_path),
    }
    save_json(final_results_path, final_payload)
    print(f"[done] Final results: {final_results_path}", flush=True)
    print(f"[done] Best checkpoint: {best_path}", flush=True)


if __name__ == "__main__":
    main()
