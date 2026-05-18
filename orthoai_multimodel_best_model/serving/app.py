from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image

from .config import settings
from .model_runtime import OrthoPatientFusionRuntime, RuntimeImage, load_images_from_paths, normalize_modality, normalize_view
from .schemas import HealthResponse, PatientPathPredictionRequest, PredictionResponse


runtime = OrthoPatientFusionRuntime(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime.load()
    yield


app = FastAPI(
    title="OrthoAI Multimodal Best Model API",
    description="Patient-level Exp 1.7 OrthoPatientFusion late_fusion inference service.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", model_loaded=runtime.loaded, device=str(runtime.device))


@app.get("/api/v1/model-info")
def model_info():
    return runtime.model_info()


@app.post("/api/v1/predict/from-paths", response_model=PredictionResponse)
def predict_from_paths(payload: PatientPathPredictionRequest) -> PredictionResponse:
    try:
        images = load_images_from_paths([item.model_dump() for item in payload.images])
        return PredictionResponse(**runtime.predict(payload.patient_id, images))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/predict", response_model=PredictionResponse)
async def predict_uploads(
    patient_id: str = Form(default="unknown"),
    files: List[UploadFile] = File(...),
    modalities: List[str] = Form(...),
    views: Optional[List[str]] = Form(default=None),
) -> PredictionResponse:
    if len(files) != len(modalities):
        raise HTTPException(status_code=400, detail="files and modalities must have the same length.")
    if views is not None and len(views) not in {0, len(files)}:
        raise HTTPException(status_code=400, detail="views must be omitted or have the same length as files.")

    runtime_images: List[RuntimeImage] = []
    try:
        for idx, upload in enumerate(files):
            with Image.open(upload.file) as image:
                image.load()
                modality = normalize_modality(modalities[idx])
                view = normalize_view(views[idx] if views else None, modality, upload.filename or "")
                runtime_images.append(
                    RuntimeImage(
                        image=image.copy(),
                        source=upload.filename or f"upload_{idx}",
                        modality=modality,
                        view=view,
                    )
                )
        return PredictionResponse(**runtime.predict(patient_id, runtime_images))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

