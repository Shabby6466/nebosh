"""Generates placeholder ONNX models so the API can boot locally without real
trained weights. NOT for production or accuracy testing — the liveness model
always reports "real" and YOLO uses actual pretrained COCO weights (person
detection is legitimate; only liveness is stubbed since a real anti-spoofing
model isn't available off-the-shelf without training/licensing a specific one).

Run once: python scripts/gen_stub_models.py
"""
import os

import numpy as np
import onnx
from onnx import TensorProto, helper

os.makedirs("app/ml_models", exist_ok=True)

# --- Stub liveness model: ignores input, always outputs [spoof=0.1, real=0.9] ---
input_tensor = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 80, 80])
output_tensor = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 2])

const_node = helper.make_node(
    "Constant",
    inputs=[],
    outputs=["output"],
    value=helper.make_tensor(
        name="const_val",
        data_type=TensorProto.FLOAT,
        dims=[1, 2],
        vals=np.array([[0.1, 0.9]], dtype=np.float32).flatten().tolist(),
    ),
)

graph = helper.make_graph([const_node], "stub_liveness", [input_tensor], [output_tensor])
model = helper.make_model(graph, producer_name="stub-gen")
model.opset_import[0].version = 13
model.ir_version = 10  # cap for compatibility with onnxruntime==1.19.2 (max supported IR version 10)
onnx.checker.check_model(model)
onnx.save(model, "app/ml_models/minifasnet_liveness.onnx")
print("Wrote app/ml_models/minifasnet_liveness.onnx (STUB — always passes liveness)")

# --- Real YOLOv8n, exported to ONNX (actual pretrained COCO weights) ---
from ultralytics import YOLO  # noqa: E402

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
