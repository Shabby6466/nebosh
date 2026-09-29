"""The real models (YOLO + InsightFace + liveness) through the inference pool."""
import asyncio

import numpy as np
from insightface.data import get_image

from app.routers.proctoring import _analyze_frame as real_analyze  # imported before stubbing
from app.services.inference import run_inference
from conftest import REFERENCE_EMBEDDING


def _analyze(image):
    async def go():
        return await asyncio.gather(*(run_inference(real_analyze, image.copy(), REFERENCE_EMBEDDING, True)
                                      for _ in range(4)))
    return [r for _, r, _ in asyncio.run(go())]


def test_empty_frame_is_candidate_missing():
    results = _analyze(np.zeros((480, 640, 3), np.uint8))
    assert {r.violation for r in results} == {"candidate_missing"}


def test_group_photo_is_multiple_people_consistently_under_concurrency():
    results = _analyze(get_image("t1"))  # insightface sample: 6 people
    assert {(r.person_count, r.violation) for r in results} == {(6, "multiple_people")}
