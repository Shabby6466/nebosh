"""Runs CPU-bound model inference (InsightFace, YOLO, liveness) off the event
loop. Calling these directly from an `async def` handler stalls every other
request and WebSocket on that worker for the full inference time.

A dedicated, bounded pool (rather than the default executor) caps how many
frames one worker evaluates at once, so ONNX threads don't oversubscribe the
CPU when several workers/containers share a host.
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.core.metrics import INFERENCE_QUEUE_WAIT

_executor = ThreadPoolExecutor(max_workers=settings.inference_threads, thread_name_prefix="inference")


async def run_inference(fn, *args, **kwargs):
    submitted = time.perf_counter()

    def _timed():
        INFERENCE_QUEUE_WAIT.observe(time.perf_counter() - submitted)
        return fn(*args, **kwargs)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _timed)
