"""LLM "Structured Output" — a clinician-facing narrative explanation of the
malocclusion classification.

Grounded strictly in the deployed model's actual output (malocclusion class +
confidence + the images provided). It must NOT invent findings the model did not
produce (no caries/fillings/implants/measurements). When OPENAI_API_KEY is not
configured it degrades to a deterministic, faithful fallback narrative.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

# Numeric model labels -> readable malocclusion class
CLASS_DISPLAY = {"0": "Class I", "1": "Class II div 1", "2": "Class III"}

SYSTEM_PROMPT = (
    "You are OrthoAI, an orthodontic AI decision-support assistant. You write a "
    "concise, professional clinical explanation of an AI malocclusion "
    "classification for a qualified dentist/orthodontist. Ground EVERY statement "
    "strictly in the provided model output and image inventory. Do NOT invent or "
    "imply any findings the model did not produce — in particular do NOT mention "
    "caries, fillings, implants, impactions, ages, sex, or specific millimetre "
    "measurements unless they are given to you. Explain what the predicted "
    "Angle malocclusion class means and what the confidence/probability spread "
    "implies about certainty. End by stating this is AI decision support that "
    "must be validated by a qualified clinician. Write ONE paragraph, 4-6 "
    "sentences, no headers, no lists."
)


def display_class(raw: Any) -> str:
    value = str(raw if raw is not None else "").strip()
    return CLASS_DISPLAY.get(value, value or "Unclassified")


def _modality_breakdown(images_used: List[Dict[str, Any]]) -> str:
    xray = sum(1 for i in images_used if i.get("modality") == "xray")
    rgb = sum(1 for i in images_used if i.get("modality") == "rgb")
    parts = []
    if xray:
        parts.append(f"{xray} panoramic/X-ray image{'s' if xray != 1 else ''}")
    if rgb:
        parts.append(f"{rgb} intra-oral photograph{'s' if rgb != 1 else ''}")
    return ", ".join(parts) if parts else f"{len(images_used)} image(s)"


def _confidence_phrase(conf: float) -> str:
    if conf >= 0.8:
        return "high confidence"
    if conf >= 0.6:
        return "moderate confidence"
    if conf >= 0.45:
        return "low-to-moderate confidence"
    return "low confidence"


def _fallback_explanation(
    cls: str, confidence: float, probabilities: List[Dict[str, Any]], images_used: List[Dict[str, Any]], model_version: str
) -> str:
    conf_pct = round(confidence * 100, 1)
    spread = ", ".join(
        f"{display_class(p.get('class_name'))} {round(p.get('probability', 0) * 100)}%"
        for p in probabilities
    )
    return (
        f"Based on multimodal analysis of {_modality_breakdown(images_used)}, OrthoAI "
        f"classifies this case as {cls} with {conf_pct}% confidence ({_confidence_phrase(confidence)}). "
        f"The full class probability distribution is: {spread}. "
        f"This indicates the model's leading interpretation of the patient's Angle "
        f"malocclusion classification from the provided records (model {model_version}). "
        f"The narrower the margin between the top classes, the more borderline the case and the "
        f"more important clinician review becomes. This output is AI-assisted decision support "
        f"only and must be reviewed and validated by a qualified clinician before any treatment decision."
    )


def _build_user_prompt(
    cls: str, confidence: float, probabilities: List[Dict[str, Any]], images_used: List[Dict[str, Any]], model_version: str
) -> str:
    spread = "; ".join(
        f"{display_class(p.get('class_name'))}: {round(p.get('probability', 0) * 100, 1)}%"
        for p in probabilities
    )
    return (
        f"Model version: {model_version}\n"
        f"Predicted malocclusion class: {cls}\n"
        f"Confidence: {round(confidence * 100, 1)}%\n"
        f"Class probabilities: {spread}\n"
        f"Images analysed: {_modality_breakdown(images_used)}\n\n"
        f"Write the clinical explanation paragraph."
    )


def generate_explanation(prediction: Dict[str, Any], model_version: str) -> Tuple[str, str]:
    """Returns (explanation_text, source) where source is 'openai' or 'fallback'."""
    cls = display_class(prediction.get("predicted_class"))
    confidence = float(prediction.get("confidence") or 0.0)
    probabilities = list(prediction.get("probabilities") or [])
    images_used = list(prediction.get("images_used") or [])

    if not settings.openai_api_key:
        return _fallback_explanation(cls, confidence, probabilities, images_used, model_version), "fallback"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(cls, confidence, probabilities, images_used, model_version)},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise ValueError("Empty completion")
        return text, "openai"
    except Exception as exc:  # noqa: BLE001 - any failure falls back gracefully
        logger.warning("OpenAI explanation failed, using fallback: %r", exc)
        return _fallback_explanation(cls, confidence, probabilities, images_used, model_version), "fallback"
