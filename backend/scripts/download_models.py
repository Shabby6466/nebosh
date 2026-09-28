"""Downloads and exports the production ONNX model weights needed for the API.

- MiniFASNet V2 & V1SE: Minivision AI's Silent-Face-Anti-Spoofing (trained passive liveness ensemble)
- YOLOv8 Nano: Pretrained COCO weights exported to ONNX for person detection
- InsightFace Buffalo_L: ArcFace 512-dim facial recognition embeddings

Usage:
    python scripts/download_models.py
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
dest_yolo = "app/ml_models/yolov8n.onnx"
if not os.path.exists(dest_yolo):
    from ultralytics import YOLO  # noqa: E402
    import onnx  # noqa: E402

    yolo = YOLO("yolov8n.pt")  # auto-downloads pretrained weights
    exported_file = yolo.export(format="onnx", imgsz=640, opset=12)

    # Ensure IR version is compatible with ONNXRuntime 1.19
    yolo_model = onnx.load(exported_file)
    if yolo_model.ir_version > 10:
        yolo_model.ir_version = 10
        onnx.save(yolo_model, dest_yolo)
    else:
        if exported_file != dest_yolo:
            os.replace(exported_file, dest_yolo)

    print("Wrote app/ml_models/yolov8n.onnx (real pretrained weights)")
else:
    print("Skipping app/ml_models/yolov8n.onnx (already present)")
