from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Modality = Literal["rgb", "xray"]


class ImagePathInput(BaseModel):
    image_path: str
    modality: Modality
    view: Optional[str] = Field(default=None, description="Optional view hint, e.g. opg, frontal, buccal_left.")


class PatientPathPredictionRequest(BaseModel):
    patient_id: str = Field(default="unknown")
    images: List[ImagePathInput]


class ClassProbability(BaseModel):
    class_name: str
    probability: float


class ImageUsed(BaseModel):
    source: str
    modality: str
    view: str


class PredictionResponse(BaseModel):
    patient_id: str
    predicted_class: str
    predicted_index: int
    confidence: float
    probabilities: List[ClassProbability]
    images_used: List[ImageUsed]
    model: Dict[str, object]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str

