"""Generates local ONNX model files needed to boot the API.

Liveness is a REAL trained model now — minivision-ai's Silent-Face-Anti-Spoofing
(Apache-2.0), fetched pre-converted to ONNX from a community fork. It's downloaded
here rather than committed to the repo to keep the checkout small. YOLO uses actual
pretrained COCO weights, exported locally via ultralytics.

Run once: python scripts/gen_stub_models.py
"""
import os
import urllib.request

os.makedirs("app/ml_models", exist_ok=True)

# --- Real liveness ensemble: Silent-Face-Anti-Spoofing (MiniFASNetV2 2.7x + MiniFASNetV1SE 4.0x) ---
_LIVENESS_BASE = "https://raw.githubusercontent.com/QingHeYang/Silent-Face-Anti-Spoofing-onnx/main/onnx"
_LIVENESS_FILES = {
    "minifasnet_v2_2.7_80x80.onnx": "2.7_80x80_MiniFASNetV2.onnx",
    "minifasnet_v1se_4.0_80x80.onnx": "4_0_0_80x80_MiniFASNetV1SE.onnx",
}
for local_name, remote_name in _LIVENESS_FILES.items():
    dest = f"app/ml_models/{local_name}"
    if os.path.exists(dest):
        print(f"Skipping {dest} (already present)")
        continue
    urllib.request.urlretrieve(f"{_LIVENESS_BASE}/{remote_name}", dest)
    print(f"Wrote {dest}")

# --- Real YOLOv8n, exported to ONNX (actual pretrained COCO weights) ---
from ultralytics import YOLO  # noqa: E402
import onnx  # noqa: E402

yolo = YOLO("yolov8n.pt")  # auto-downloads pretrained weights
try:
    yolo.export(format="onnx", imgsz=640)
except ModuleNotFoundError:
    # torch>=2.5's default ONNX exporter needs `onnxscript`; if it's not installed,
    # fall back to the legacy (non-dynamo) exporter which doesn't need it.
    yolo.export(format="onnx", imgsz=640, dynamo=False)

# onnx>=1.16's writer defaults to IR version 13, newer than onnxruntime==1.19.2
# supports (max 10) — cap it so the exported file actually loads.
yolo_model = onnx.load("yolov8n.onnx")
yolo_model.ir_version = 10
onnx.save(yolo_model, "yolov8n.onnx")

os.rename("yolov8n.onnx", "app/ml_models/yolov8n.onnx")
print("Wrote app/ml_models/yolov8n.onnx (real pretrained weights)")
