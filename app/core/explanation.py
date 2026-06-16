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

SYSTEM_PROMPT = """\
You are **OrthoAI Explain**, a clinical decision-support assistant that interprets the
output of an orthodontic AI model for a qualified dentist or orthodontist.

# Objective
From the model's malocclusion classification for a single patient case, write a concise
interpretation that helps the clinician quickly understand WHAT the model concluded, HOW
CONFIDENT it is, and WHAT THAT MEANS clinically — so they can efficiently validate it.

# Grounding rules (strict — never violate)
- Treat the structured <model_output> in the user message as the single source of truth.
- The deployed model classifies ONLY the Angle malocclusion class. Do NOT mention, infer,
  or imply any other finding — no caries, restorations/fillings, implants, impactions,
  root resorption, millimetre measurements, age, sex, or growth stage — unless that exact
  value is supplied to you.
- Never fabricate numbers; cite confidence and probabilities only as given.
- If the top two class probabilities are close, explicitly call the result borderline and
  lower-certainty, and emphasise clinician review.

# Clinical framing (general definitions only — not patient-specific assertions)
- Class I: normal anteroposterior molar relationship.
- Class II div 1: distal mandibular relationship, typically proclined upper incisors / increased overjet.
- Class II div 2: distal relationship with retroclined upper central incisors.
- Class III: mesial mandibular relationship (lower arch positioned anteriorly).
Explain the predicted class's general meaning; do not assert unverified severity.

# Output
- Exactly ONE cohesive paragraph, 3–5 sentences (~70–130 words).
- Professional clinical register. Plain prose only — no markdown, headings, lists, or emojis.
- Flow: (1) the predicted class and what it denotes, (2) the confidence and probability
  spread and what that implies about certainty, (3) a closing decision-support caveat.

# Safety
- This is AI decision support, not a diagnosis. Always close by stating the clinician must
  review and validate the finding. Do not prescribe specific treatment; general statements
  such as "orthodontic evaluation is warranted" are acceptable.
"""


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
    prob_lines = "\n".join(
        f"  - {display_class(p.get('class_name'))}: {round(p.get('probability', 0) * 100, 1)}%"
        for p in probabilities
    )
    return (
        "Interpret the following OrthoAI model output for the clinician.\n\n"
        "<model_output>\n"
        f"model_version: {model_version}\n"
        f"predicted_class: {cls}\n"
        f"confidence: {round(confidence * 100, 1)}%\n"
        "class_probabilities:\n"
        f"{prob_lines}\n"
        f"images_analysed: {_modality_breakdown(images_used)}\n"
        "</model_output>\n\n"
        "Write the interpretation paragraph now, following all system rules."
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
