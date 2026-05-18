# OrthoAI Multimodal Best Model API

FastAPI backend package for the best confirmed Exp 1.7 OrthoPatientFusion model.

## Selected Model

Selected checkpoint:

- Architecture: `late_fusion`
- Checkpoint: `weights/late_fusion_best.ckpt`
- Source run: `models/exp1_7_orthopatientfusion_runs/exp1_7_orthopatientfusion_20260517_155245_job135724/late_fusion`
- Validation macro F1: `0.5893`
- Test macro F1: `0.5235`
- Test accuracy: `0.6438`
- Test macro AUC: `0.7051`

This was selected over `attention_mil` because `attention_mil` reached a higher validation peak but generalized worse on the confirmed held-out test set.

## Inputs

The deployed model is patient-level multimodal inference:

```text
patient_id -> OPG/X-ray + intraoral RGB images -> malocclusion class probability
```

By default, the API requires at least:

- one `xray` image, usually OPG/panoramic
- one `rgb` intraoral image

## Layout

- `serving/app.py`: FastAPI app and HTTP routes
- `serving/model_runtime.py`: checkpoint loading, preprocessing, and inference
- `serving/schemas.py`: request/response schemas
- `weights/late_fusion_best.ckpt`: model checkpoint with trained weights
- `artifacts/final_results.json`: validation/test metrics for the selected checkpoint
- `artifacts/metadata.json`: training data and split metadata

## Run

From the repository root:

```bash
cd /home/hamzah.al-omairi/Documents/orthoai/orthoai_multimodel_best_model
/home/hamzah.al-omairi/miniconda3/envs/ortho-deepspeedv/bin/pip install -r requirements.txt
/home/hamzah.al-omairi/miniconda3/envs/ortho-deepspeedv/bin/uvicorn serving.app:app --host 0.0.0.0 --port 8000
```

Use CPU if needed:

```bash
ORTHOAI_DEVICE=cpu /home/hamzah.al-omairi/miniconda3/envs/ortho-deepspeedv/bin/uvicorn serving.app:app --host 0.0.0.0 --port 8000
```

## Endpoints

Health:

```bash
curl http://localhost:8000/health
```

Model metadata:

```bash
curl http://localhost:8000/api/v1/model-info
```

Predict from backend-accessible file paths:

```bash
curl -X POST http://localhost:8000/api/v1/predict/from-paths \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "patient-001",
    "images": [
      {
        "image_path": "/abs/path/opg.png",
        "modality": "xray",
        "view": "opg"
      },
      {
        "image_path": "/abs/path/frontal.jpg",
        "modality": "rgb",
        "view": "frontal"
      }
    ]
  }'
```

Predict with multipart uploads:

```bash
curl -X POST http://localhost:8000/api/v1/predict \
  -F "patient_id=patient-001" \
  -F "files=@/abs/path/opg.png" \
  -F "modalities=xray" \
  -F "views=opg" \
  -F "files=@/abs/path/frontal.jpg" \
  -F "modalities=rgb" \
  -F "views=frontal"
```

## Response

The API returns:

- predicted class label
- confidence
- class probabilities
- images selected/used by the patient-level bag logic
- deployed model metadata and test metrics

## Integration Note

This backend is intended for system integration and research workflow support. It is not a standalone clinical decision system; outputs should be reviewed by qualified orthodontic clinicians.

