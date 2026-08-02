from types import SimpleNamespace

import numpy as np
import pytest

from app.core.dental_segmentation import (
    DentalSegmentationError,
    dino_initialization_only_record,
    parse_segmentation_result,
    summarise_segmentations,
)


def _result(*, with_masks: bool = True):
    boxes = SimpleNamespace(
        xyxy=np.array([[0.0, 0.0, 2.0, 2.0], [2.0, 0.0, 4.0, 4.0]]),
        xyxyn=np.array([[0.0, 0.0, 0.5, 0.5], [0.5, 0.0, 1.0, 1.0]]),
        conf=np.array([0.9, 0.6]),
        cls=np.array([0, 2]),
    )
    masks = None
    if with_masks:
        masks = SimpleNamespace(
            data=np.array(
                [
                    [[1, 0], [0, 0]],
                    [[0, 1], [1, 1]],
                ]
            ),
            xyn=[
                np.array([[0.0, 0.0], [0.5, 0.0], [0.5, 0.5]]),
                np.array([[0.5, 0.0], [1.0, 0.0], [1.0, 1.0]]),
            ],
        )
    return SimpleNamespace(boxes=boxes, masks=masks, orig_shape=(4, 4))


def test_parse_segmentation_result_preserves_quantitative_measurements():
    parsed = parse_segmentation_result(
        _result(), image_id=7, filename="opg_case.png", modality="xray"
    )

    assert parsed["status"] == "completed"
    assert parsed["detection_count"] == 2
    assert parsed["detections"][0]["label"] == "Caries"
    assert parsed["detections"][0]["coco_category_id"] == 1
    assert parsed["detections"][0]["mask_area_pixels"] == 4
    assert parsed["detections"][0]["mask_area_percent"] == 25.0
    assert parsed["detections"][1]["label"] == "Filling"
    assert parsed["detections"][1]["mask_area_percent"] == 75.0


def test_summarise_segmentations_reports_counts_without_score_fusion():
    parsed = parse_segmentation_result(
        _result(), image_id=7, filename="opg_case.png", modality="xray"
    )
    skipped = {
        "image_id": 8,
        "status": "skipped",
        "detections": [],
    }

    summary = summarise_segmentations([parsed, skipped])

    assert summary["images_completed"] == 1
    assert summary["images_skipped"] == 1
    assert summary["total_instances"] == 2
    assert summary["classes_present"] == 2
    assert summary["classes"][0]["mean_confidence"] == 0.9


def test_boxes_without_masks_fail_closed():
    with pytest.raises(DentalSegmentationError, match="without instance masks"):
        parse_segmentation_result(
            _result(with_masks=False), image_id=7, filename="opg_case.png", modality="xray"
        )


def test_coco_dino_checkpoint_is_explicitly_non_deployed():
    record = dino_initialization_only_record()

    assert record["status"] == "not_deployed"
    assert record["provenance"]["class_count"] == 91
    assert record["provenance"]["deployment_eligible"] is False
