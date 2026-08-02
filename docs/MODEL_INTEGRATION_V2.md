# OrthoAI v2 model integration

The v2 inference result deliberately keeps the models as separate clinical outputs. It does **not** average, vote, or otherwise fuse their confidence scores.

## Runtime roles

| Artifact | Runtime role | Output |
| --- | --- | --- |
| `late_fusion_best.ckpt` | Deployed | One patient-level malocclusion classification |
| `best.pt` | Deployed on explicitly identified dental radiographs | YOLOv8 instance masks, boxes, classes, counts, model scores, and image-plane areas |
| `checkpoint0033_4scale.pth` | Blocked / initialization only | None. This is a 91-class COCO DINO checkpoint until dental fine-tuning and validation are completed. |

Artifact metadata and immutable SHA-256 values are recorded in `model_artifacts/manifest.json`. The GPU container excludes the COCO initialization checkpoint because it has no valid inference role.

## Quantitative segmentation output

Each segmentation instance contains:

- zero-based model class ID and one-based COCO category ID;
- exact label from the embedded 31-class schema;
- model confidence score;
- pixel and normalized bounding boxes;
- estimated mask area in original-image pixels;
- mask area as a percentage of the image plane;
- a bounded normalized polygon for evidence overlays.

The class summary reports instance and image counts, mean/max model scores, summed pixel areas, and mean/max instance area percentages. Pixel and percentage areas are not physical measurements. Millimetres or square millimetres require acquisition geometry or a validated calibration object.

## Fail-closed controls

Inference is rejected when:

- a required artifact is missing or its SHA-256 differs;
- the Ultralytics task is not `segment`;
- the embedded class order differs from the versioned 31-label schema;
- output tensors have inconsistent counts;
- boxes are returned without instance masks;
- no input is explicitly inside the validated radiograph modality scope.

`DENTAL_SEGMENTATION_REQUIRED=false` may be used only for an explicitly approved degraded deployment. Errors are still published as an error status; they are never replaced with fabricated findings.

## Result contract

The result JSON uses schema `orthoai.combined-result/2.0.0` and records one `model_run_id`, build commit, timestamps, preprocessing versions, label schema versions, checksums, thresholds, timings, task-specific outputs, and interpretation limits. Legacy top-level malocclusion fields remain temporarily for older clients.

## Deployment settings

```env
MODEL_VERSION=v2.0.0
BUILD_COMMIT=<immutable git commit>
DENTAL_SEGMENTATION_ENABLED=true
DENTAL_SEGMENTATION_REQUIRED=true
DENTAL_SEGMENTATION_CHECKPOINT=model_artifacts/dental_segmentation/best.pt
DENTAL_SEGMENTATION_CONFIDENCE=0.25
DENTAL_SEGMENTATION_IOU=0.7
DENTAL_SEGMENTATION_IMGSZ=640
DENTAL_SEGMENTATION_MODALITIES=xray
```

The public-checkpoint DINO path must remain absent from inference configuration until a dental checkpoint has its own semantic version, dental label schema, calibration/validation evidence, and new artifact digest.

GPU workers install `requirements-gpu.txt`. API and non-inference worker images use `requirements.txt` and intentionally exclude both deployed inference weights; the GPU-specific Docker ignore file admits the malocclusion and segmentation weights while continuing to block the COCO-only DINO artifact.
