"""Export Silent-Face-Anti-Spoofing MiniFASNet .pth weights to ONNX.

The exported graph includes the softmax, so the ONNX output is a (N, 3) probability
vector. Class index 1 = real face (as in the upstream test.py). Input is BGR, 80x80,
float32, raw 0..255 values (upstream to_tensor does NOT divide by 255).

After export, the script checks that ONNX Runtime output matches PyTorch output.

Usage (needs backend/requirements-convert.txt):
    python training/scripts/export_silentface_onnx.py
"""
from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from silentface_vendor.MiniFASNet import MiniFASNetV1SE, MiniFASNetV2  # noqa: E402

MODELS = {
    "2.7_80x80_MiniFASNetV2": MiniFASNetV2,
    "4_0_0_80x80_MiniFASNetV1SE": MiniFASNetV1SE,
}


class WithSoftmax(torch.nn.Module):
    def __init__(self, net: torch.nn.Module):
        super().__init__()
        self.net = net

    def forward(self, x):
        return F.softmax(self.net(x), dim=1)


def get_kernel(h: int, w: int) -> tuple[int, int]:
    return (h + 15) // 16, (w + 15) // 16  # upstream utility.get_kernel


def export(name: str, factory) -> None:
    src = ROOT / "models" / "liveness" / f"{name}.pth"
    dst = ROOT / "models" / "liveness" / f"{name}.onnx"
    net = factory(conv6_kernel=get_kernel(80, 80))
    state = torch.load(src, map_location="cpu", weights_only=True)
    if next(iter(state)).startswith("module."):
        state = OrderedDict((k[7:], v) for k, v in state.items())
    net.load_state_dict(state)
    model = WithSoftmax(net).eval()

    dummy = torch.rand(1, 3, 80, 80) * 255.0
    torch.onnx.export(model, dummy, str(dst), input_names=["input"], output_names=["prob"],
                      dynamic_axes={"input": {0: "batch"}, "prob": {0: "batch"}}, opset_version=17,
                      dynamo=False)

    rng = np.random.default_rng(0)
    x = (rng.random((4, 3, 80, 80)) * 255).astype(np.float32)
    with torch.no_grad():
        ref = model(torch.from_numpy(x)).numpy()
    sess = ort.InferenceSession(str(dst), providers=["CPUExecutionProvider"])
    out = sess.run(None, {"input": x})[0]
    diff = float(np.abs(ref - out).max())
    print(f"{name}: exported -> {dst.name}, output shape {out.shape}, max |torch-onnx| = {diff:.2e}")
    if diff > 1e-4:
        raise SystemExit(f"ONNX output mismatch for {name}")


if __name__ == "__main__":
    for model_name, model_factory in MODELS.items():
        export(model_name, model_factory)
