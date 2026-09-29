"""Process-wide ONNX Runtime threading defaults — import before any model loads.

InsightFace and Ultralytics create their own InferenceSessions without
exposing SessionOptions, so the defaults are applied by wrapping the
constructor (only when the caller didn't pass sess_options itself).

Why: by default every session gets one intra-op thread per core and spins
while idle. With INFERENCE_THREADS concurrent calls per worker, and several
workers per host, that oversubscribes the CPU many times over — load tests
showed 4 inference threads *slower* than 2. Size so that
UVICORN_WORKERS x INFERENCE_THREADS x ONNX_INTRA_OP_THREADS ~= host cores.
"""
import onnxruntime as ort

from app.core.config import settings


def _default_session_options() -> ort.SessionOptions:
    so = ort.SessionOptions()
    if settings.onnx_intra_op_threads:
        so.intra_op_num_threads = settings.onnx_intra_op_threads
    so.inter_op_num_threads = 1
    # Idle threads block instead of busy-waiting, so they don't steal CPU
    # from the other sessions/workers that have real work.
    so.add_session_config_entry("session.intra_op.allow_spinning", "0")
    return so


_original_init = ort.InferenceSession.__init__


def _init_with_defaults(self, path_or_bytes, sess_options=None, *args, **kwargs):
    _original_init(self, path_or_bytes, sess_options or _default_session_options(), *args, **kwargs)


if not getattr(ort.InferenceSession, "_proctoring_defaults", False):
    ort.InferenceSession.__init__ = _init_with_defaults
    ort.InferenceSession._proctoring_defaults = True
