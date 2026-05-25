#!/usr/bin/env python3
"""
Data preprocessing pipeline for medical imaging datasets.

Usage:
  python3 src/data_pipeline.py --data data --out processed
  python3 src/data_pipeline.py --data data --out processed --resize 512x512 --normalize
  python3 src/data_pipeline.py --data data --out processed --pipeline auto --normalize --xray-to-rgb
"""

from __future__ import annotations

import argparse
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

try:
    from PIL import Image, ImageFilter
except Exception:
    Image = None
    ImageFilter = None

try:
    import numpy as np
except Exception:
    np = None

try:
    from tqdm import tqdm as _tqdm
except Exception:
    _tqdm = None


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
LABEL_IMAGE_HINTS = {"label", "labels", "mask", "masks", "seg", "segmentation"}
LABEL_DIR_HINTS = {"labels", "label", "annotations", "annotation", "masks", "mask"}


class _SimpleProgress:
    def __init__(self, iterable, total=None, desc=""):
        self.iterable = iterable
        self.total = total
        self.desc = desc
        self.count = 0
        self.last_print = 0
        self.start = time.perf_counter()

    def __iter__(self):
        for item in self.iterable:
            self.count += 1
            self._maybe_print()
            yield item
        self._print(final=True)

    def _maybe_print(self):
        if self.total:
            step = max(1, self.total // 50)
            if self.count == 1 or self.count == self.total or (self.count - self.last_print) >= step:
                self._print()
        else:
            if (self.count - self.last_print) >= 200:
                self._print()

    def _print(self, final=False):
        elapsed = time.perf_counter() - self.start
        if self.total:
            pct = self.count / self.total
            bar_len = 24
            filled = int(bar_len * pct)
            bar = "#" * filled + "-" * (bar_len - filled)
            msg = f"{self.desc} [{bar}] {self.count}/{self.total} {pct*100:5.1f}% {elapsed:0.1f}s"
        else:
            msg = f"{self.desc} {self.count} {elapsed:0.1f}s"
        end = "\n" if final else "\r"
        print(msg, end=end, flush=True)
        self.last_print = self.count


def _progress(iterable, total=None, desc=""):
    if _tqdm is not None:
        return _tqdm(iterable, total=total, desc=desc, leave=False)
    return _SimpleProgress(iterable, total=total, desc=desc)


def _ensure_pillow():
    if Image is None:
        raise RuntimeError("Pillow is required. Install with: pip install pillow")


def _ensure_numpy():
    if np is None:
        raise RuntimeError("NumPy is required. Install with: pip install numpy")


def _is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _safe_mkdir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def _is_label_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return any(hint in parts for hint in LABEL_DIR_HINTS)


def _is_mask_like_dir(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return any(hint in parts for hint in LABEL_IMAGE_HINTS)


@dataclass
class PreprocessConfig:
    pipeline: str  # auto|opg|rgb|none
    normalize: bool
    clahe: bool
    clahe_tiles: int
    clahe_clip: float
    denoise: int
    gamma: float
    white_balance: bool
    xray_to_rgb: bool


def _is_grayscale_like_array(arr: "np.ndarray") -> bool:
    if arr.ndim == 2:
        return True
    if arr.ndim == 3 and arr.shape[2] == 1:
        return True
    if arr.ndim == 3 and arr.shape[2] >= 3:
        h, w = arr.shape[:2]
        stride = max(1, int(max(h, w) / 512))
        sample = arr[::stride, ::stride, :3].astype(np.int16)
        diff = np.abs(sample[..., 0] - sample[..., 1]) + np.abs(sample[..., 0] - sample[..., 2])
        return int(np.max(diff)) <= 2
    return False


def _percentile_normalize(arr: "np.ndarray", p1: float = 1.0, p99: float = 99.0) -> "np.ndarray":
    arr_f = arr.astype(np.float32)
    lo = float(np.percentile(arr_f, p1))
    hi = float(np.percentile(arr_f, p99))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    arr_f = (arr_f - lo) / (hi - lo)
    arr_f = np.clip(arr_f * 255.0, 0, 255)
    return arr_f.astype(np.uint8)


def _minmax_to_uint8(arr: "np.ndarray") -> "np.ndarray":
    arr_f = arr.astype(np.float32)
    lo = float(np.min(arr_f))
    hi = float(np.max(arr_f))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    arr_f = (arr_f - lo) / (hi - lo)
    arr_f = np.clip(arr_f * 255.0, 0, 255)
    return arr_f.astype(np.uint8)


def _as_uint8(arr: "np.ndarray", normalize: bool) -> "np.ndarray":
    arr_f = arr.astype(np.float32)
    if normalize:
        return _percentile_normalize(arr_f)
    if float(arr_f.min()) >= 0.0 and float(arr_f.max()) <= 1.5:
        return np.clip(arr_f * 255.0, 0, 255).astype(np.uint8)
    if float(arr_f.min()) >= 0.0 and float(arr_f.max()) <= 255.0:
        return np.clip(arr_f, 0, 255).astype(np.uint8)
    return _minmax_to_uint8(arr_f)


def _gamma_correction(arr: "np.ndarray", gamma: float) -> "np.ndarray":
    if gamma <= 0 or math.isclose(gamma, 1.0):
        return arr
    arr_f = arr.astype(np.float32) / 255.0
    arr_f = np.clip(arr_f, 0.0, 1.0) ** (1.0 / gamma)
    return np.clip(arr_f * 255.0, 0, 255).astype(np.uint8)


def _gray_world_white_balance(arr: "np.ndarray") -> "np.ndarray":
    if arr.ndim != 3 or arr.shape[2] < 3:
        return arr
    arr_f = arr.astype(np.float32)
    means = arr_f.reshape(-1, arr_f.shape[2]).mean(axis=0)
    gray = float(np.mean(means[:3]))
    scale = gray / (means[:3] + 1e-6)
    arr_f[..., 0] *= scale[0]
    arr_f[..., 1] *= scale[1]
    arr_f[..., 2] *= scale[2]
    return np.clip(arr_f, 0, 255).astype(np.uint8)


def _clahe_gray(img: "np.ndarray", tiles: int = 8, clip_limit: float = 0.01) -> "np.ndarray":
    if img.ndim != 2:
        raise ValueError("CLAHE expects a 2D grayscale image.")
    tiles = max(1, int(tiles))
    if tiles == 1:
        return img
    h, w = img.shape
    tile_h = max(1, math.ceil(h / tiles))
    tile_w = max(1, math.ceil(w / tiles))

    luts = np.zeros((tiles, tiles, 256), dtype=np.uint8)
    for ty in range(tiles):
        for tx in range(tiles):
            y0, y1 = ty * tile_h, min((ty + 1) * tile_h, h)
            x0, x1 = tx * tile_w, min((tx + 1) * tile_w, w)
            tile = img[y0:y1, x0:x1]
            hist = np.bincount(tile.ravel(), minlength=256)
            if clip_limit > 0:
                clip_count = max(1, int(clip_limit * tile.size))
                excess = np.maximum(hist - clip_count, 0)
                hist = np.minimum(hist, clip_count)
                excess_total = int(excess.sum())
                if excess_total > 0:
                    incr = excess_total // 256
                    hist += incr
                    residual = excess_total - incr * 256
                    if residual > 0:
                        hist[:residual] += 1
            cdf = hist.cumsum().astype(np.float32)
            cdf_min = float(cdf.min())
            cdf_max = float(cdf.max())
            if cdf_max > cdf_min:
                cdf = (cdf - cdf_min) / (cdf_max - cdf_min)
            else:
                cdf = cdf * 0.0
            luts[ty, tx] = np.clip(cdf * 255.0, 0, 255).astype(np.uint8)

    out = np.empty_like(img)
    for ty in range(tiles):
        for tx in range(tiles):
            y0, y1 = ty * tile_h, min((ty + 1) * tile_h, h)
            x0, x1 = tx * tile_w, min((tx + 1) * tile_w, w)
            block = img[y0:y1, x0:x1]
            ty1 = min(ty + 1, tiles - 1)
            tx1 = min(tx + 1, tiles - 1)

            lut00 = luts[ty, tx]
            lut10 = luts[ty, tx1]
            lut01 = luts[ty1, tx]
            lut11 = luts[ty1, tx1]

            yy = (np.arange(y0, y1) - y0 + 0.5) / tile_h
            xx = (np.arange(x0, x1) - x0 + 0.5) / tile_w
            wy = yy[:, None]
            wx = xx[None, :]

            mapped00 = lut00[block]
            mapped10 = lut10[block]
            mapped01 = lut01[block]
            mapped11 = lut11[block]

            out_block = (
                mapped00 * (1 - wx) * (1 - wy)
                + mapped10 * wx * (1 - wy)
                + mapped01 * (1 - wx) * wy
                + mapped11 * wx * wy
            )
            out[y0:y1, x0:x1] = np.clip(out_block, 0, 255).astype(np.uint8)
    return out


def _apply_opg_pipeline(im: "Image.Image", cfg: PreprocessConfig) -> "Image.Image":
    _ensure_numpy()
    im = im.convert("L")
    arr = np.array(im)
    arr = _as_uint8(arr, normalize=cfg.normalize)
    if cfg.denoise and cfg.denoise >= 3:
        if ImageFilter is None:
            raise RuntimeError("Pillow ImageFilter is required for denoising.")
        denoise_size = cfg.denoise if cfg.denoise % 2 == 1 else cfg.denoise + 1
        arr = np.array(Image.fromarray(arr, mode="L").filter(ImageFilter.MedianFilter(size=denoise_size)))
    if cfg.clahe:
        arr = _clahe_gray(arr, tiles=cfg.clahe_tiles, clip_limit=cfg.clahe_clip)
    if cfg.gamma and not math.isclose(cfg.gamma, 1.0):
        arr = _gamma_correction(arr, cfg.gamma)
    out = Image.fromarray(arr, mode="L")
    if cfg.xray_to_rgb:
        out = out.convert("RGB")
    return out


def _apply_rgb_pipeline(im: "Image.Image", cfg: PreprocessConfig) -> "Image.Image":
    _ensure_numpy()
    im = im.convert("RGB")
    arr = np.array(im)
    if cfg.white_balance:
        arr = _gray_world_white_balance(arr)
    lab = Image.fromarray(arr, mode="RGB").convert("LAB")
    lab_arr = np.array(lab)
    l_chan = _as_uint8(lab_arr[..., 0], normalize=cfg.normalize)
    if cfg.clahe:
        l_chan = _clahe_gray(l_chan, tiles=cfg.clahe_tiles, clip_limit=cfg.clahe_clip)
    if cfg.gamma and not math.isclose(cfg.gamma, 1.0):
        l_chan = _gamma_correction(l_chan, cfg.gamma)
    lab_arr[..., 0] = l_chan
    return Image.fromarray(lab_arr, mode="LAB").convert("RGB")


def _infer_pipeline(pipeline: str, dataset_name: str, arr: "np.ndarray") -> str:
    if pipeline != "auto":
        return pipeline
    name = dataset_name.lower()
    if any(k in name for k in ("opg", "pan", "xray", "x-ray")):
        return "opg"
    if any(k in name for k in ("intraoral", "rgb")):
        return "rgb"
    return "opg" if _is_grayscale_like_array(arr) else "rgb"


def _apply_preprocess(im: "Image.Image", cfg: PreprocessConfig, dataset_name: str) -> "Image.Image":
    _ensure_numpy()
    arr = np.array(im)
    pipeline = _infer_pipeline(cfg.pipeline, dataset_name, arr)
    if pipeline == "none":
        if cfg.normalize:
            arr = _percentile_normalize(arr)
            return Image.fromarray(arr)
        return im
    if pipeline == "opg":
        return _apply_opg_pipeline(im, cfg)
    if pipeline == "rgb":
        return _apply_rgb_pipeline(im, cfg)
    return im


def build_preprocess_config(
    *,
    pipeline: str = "auto",
    normalize: bool = False,
    clahe: bool = True,
    clahe_tiles: int = 8,
    clahe_clip: float = 0.01,
    denoise: int = 3,
    gamma: float = 1.0,
    white_balance: bool = True,
    xray_to_rgb: bool = False,
) -> PreprocessConfig:
    """Public helper to build a PreprocessConfig for reuse in training scripts."""
    return PreprocessConfig(
        pipeline=pipeline,
        normalize=normalize,
        clahe=clahe,
        clahe_tiles=clahe_tiles,
        clahe_clip=clahe_clip,
        denoise=denoise,
        gamma=gamma,
        white_balance=white_balance,
        xray_to_rgb=xray_to_rgb,
    )


def apply_preprocess(
    im: "Image.Image",
    cfg: PreprocessConfig,
    dataset_name: str = "",
) -> "Image.Image":
    """Public wrapper around the preprocessing pipeline."""
    return _apply_preprocess(im, cfg, dataset_name)


def _detect_label_types(dataset_root: Path) -> set[str]:
    label_types: set[str] = set()
    for path in dataset_root.rglob("*"):
        if path.is_dir() or _is_hidden(path):
            continue
        suffix = path.suffix.lower()
        if suffix == ".txt":
            if path.name.lower().startswith("readme"):
                continue
            label_types.add("yolo")
        elif suffix == ".xml":
            label_types.add("pascal_voc")
        elif suffix == ".csv":
            label_types.add("csv_bbox")
        elif suffix == ".json":
            label_types.add("json_label")
    return label_types


def _discover_datasets(data_root: Path) -> list[Path]:
    datasets = []
    for path in data_root.iterdir():
        if path.is_dir() and not _is_hidden(path):
            datasets.append(path)
    return sorted(datasets)


def _preprocess_copy(
    dataset_root: Path,
    out_root: Path,
    resize: Optional[Tuple[int, int]],
    dry_run: bool,
    preprocess_cfg: PreprocessConfig,
):
    """Copy images/labels and optionally resize and preprocess.

    Note: label files are kept unchanged. Resizing is skipped if detection labels exist.
    """
    _ensure_pillow()
    _ensure_numpy()

    dataset_name = dataset_root.name
    dst_root = out_root / dataset_name
    images_out = dst_root / "images"
    labels_out = dst_root / "labels"
    _safe_mkdir(images_out)
    _safe_mkdir(labels_out)

    detection_label_types = {"yolo", "coco", "pascal_voc", "labelme", "csv_bbox", "json_label"}
    label_types = _detect_label_types(dataset_root)
    has_detection_labels = any(t in detection_label_types for t in label_types)
    resize_effective = resize if not has_detection_labels else None
    if resize and has_detection_labels:
        print(f"[warn] Skipping resize for {dataset_name} due to detection labels.")

    file_list = [p for p in dataset_root.rglob("*") if p.is_file() and not _is_hidden(p)]
    for path in _progress(file_list, total=len(file_list), desc=f"{dataset_name} preprocess"):
        if path.is_dir() or _is_hidden(path):
            continue
        rel = path.relative_to(dataset_root)
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTS:
            is_mask = _is_label_path(path) or _is_mask_like_dir(path)
            out_base = labels_out if is_mask else images_out
            out_path = out_base / rel
            _safe_mkdir(out_path.parent)
            if dry_run:
                continue
            with Image.open(path) as im:
                im.load()
                if resize_effective:
                    resample = Image.NEAREST if is_mask else Image.BILINEAR
                    im = im.resize(resize_effective, resample)
                if not is_mask:
                    im = _apply_preprocess(im, preprocess_cfg, dataset_name)
                im.save(out_path)
        elif suffix in {".json", ".xml", ".txt", ".csv"}:
            if suffix == ".txt" and path.name.lower().startswith("readme"):
                continue
            out_path = labels_out / rel
            _safe_mkdir(out_path.parent)
            if dry_run:
                continue
            out_path.write_bytes(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description="Dataset preprocessing pipeline")
    parser.add_argument("--data", required=True, help="Path to data root")
    parser.add_argument("--out", default=None, help="Output directory for preprocessed data")
    parser.add_argument("--prepare", default=None, help="Deprecated alias for --out")
    parser.add_argument("--resize", default=None, help="Resize images, e.g. 512x512")
    parser.add_argument("--normalize", action="store_true", help="Percentile normalize images to 8-bit")
    parser.add_argument(
        "--pipeline",
        default="auto",
        choices=["auto", "opg", "rgb", "none"],
        help="Preprocess pipeline: auto (by modality), opg, rgb, or none",
    )
    parser.add_argument(
        "--no-clahe",
        dest="clahe",
        action="store_false",
        help="Disable CLAHE contrast enhancement",
    )
    parser.add_argument(
        "--clahe-tiles",
        type=int,
        default=8,
        help="CLAHE tile grid size (NxN)",
    )
    parser.add_argument(
        "--clahe-clip",
        type=float,
        default=0.01,
        help="CLAHE clip limit as fraction of tile pixels",
    )
    parser.add_argument(
        "--denoise",
        type=int,
        default=3,
        help="Median filter size for OPG denoising (odd, 0 disables)",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=1.0,
        help="Gamma correction (1.0 = no change)",
    )
    parser.add_argument(
        "--no-white-balance",
        dest="white_balance",
        action="store_false",
        help="Disable gray-world white balance for RGB",
    )
    parser.add_argument(
        "--xray-to-rgb",
        action="store_true",
        help="Convert OPG outputs to 3-channel RGB",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write preprocessed outputs")

    parser.set_defaults(clahe=True, white_balance=True)

    args = parser.parse_args()
    out_arg = args.out or args.prepare
    if out_arg is None:
        parser.error("--out is required (or use deprecated --prepare)")

    data_root = Path(args.data)
    out_root = Path(out_arg)
    _safe_mkdir(out_root)

    if args.resize:
        m = re.match(r"^(\d+)x(\d+)$", args.resize)
        if not m:
            raise ValueError("--resize should be like 512x512")
        resize = (int(m.group(1)), int(m.group(2)))
    else:
        resize = None

    preprocess_cfg = PreprocessConfig(
        pipeline=args.pipeline,
        normalize=args.normalize,
        clahe=args.clahe,
        clahe_tiles=args.clahe_tiles,
        clahe_clip=args.clahe_clip,
        denoise=args.denoise,
        gamma=args.gamma,
        white_balance=args.white_balance,
        xray_to_rgb=args.xray_to_rgb,
    )

    dataset_roots = _discover_datasets(data_root)
    for dataset_root in _progress(dataset_roots, total=len(dataset_roots), desc="Datasets"):
        print(f"\n[info] Preprocessing {dataset_root.name}...", flush=True)
        _preprocess_copy(dataset_root, out_root, resize, args.dry_run, preprocess_cfg)

    if args.dry_run:
        print("Dry-run: no preprocessed files written")
    else:
        print(f"Preprocessed data written to: {out_root}")


if __name__ == "__main__":
    main()
