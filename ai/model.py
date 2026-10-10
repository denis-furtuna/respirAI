"""The CNN (task D4): ResNet18 on one-channel log-mel spectrograms, 4 classes.

PyTorch is only needed for training (on Kaggle). The trained model is
exported to ONNX, and the server runs it with ONNX Runtime.
"""
import json

import torch
import torch.nn as nn
from torchvision.models import ResNet18_Weights, resnet18

import preprocess as pp
from icbhi import CLASSES


def build_model(pretrained=True):
    net = None
    if pretrained:
        try:
            net = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        except Exception as e:  # e.g. Internet switched off in the Kaggle notebook
            print(f"Could not download ImageNet weights ({e}); training from scratch.")
    if net is None:
        net = resnet18(weights=None)
    # Spectrograms have one channel, not three: sum the RGB filters into one.
    old = net.conv1
    net.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
    with torch.no_grad():
        net.conv1.weight.copy_(old.weight.sum(dim=1, keepdim=True))
    net.fc = nn.Linear(net.fc.in_features, len(CLASSES))
    return net


def export(net, onnx_path, model_version, metrics=None):
    """Write <name>.onnx plus <name>.json (version, classes, preprocessing settings, scores)."""
    net = net.eval().cpu()
    dummy = torch.zeros(1, 1, pp.N_MELS, pp.N_FRAMES)
    kwargs = dict(input_names=["spec"], output_names=["logits"],
                  dynamic_axes={"spec": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17)
    try:  # newer PyTorch defaults to a different exporter; ask for the classic one
        torch.onnx.export(net, dummy, str(onnx_path), dynamo=False, **kwargs)
    except TypeError:  # older PyTorch has no `dynamo` argument
        torch.onnx.export(net, dummy, str(onnx_path), **kwargs)
    meta = {"model_version": model_version, "classes": CLASSES,
            "input_shape": [1, pp.N_MELS, pp.N_FRAMES], "preprocess": pp.params(),
            "metrics": metrics or {}}
    with open(str(onnx_path).replace(".onnx", ".json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta
