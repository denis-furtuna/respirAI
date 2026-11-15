import os
import torch
import torch.nn as nn
import torch.nn.functional as F


CNN14_ZENODO_URL = "https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth"
CNN14_CANDIDATE_PATHS = [
    "/content/drive/MyDrive/respirAI/Cnn14_mAP=0.431.pth",
    "/content/Cnn14_mAP=0.431.pth",
]


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_channels, out_channels, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1), bias=False
        )
        self.conv2 = nn.Conv2d(
            out_channels, out_channels, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1), bias=False
        )
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.bn2 = nn.BatchNorm2d(out_channels)

    def forward(self, x: torch.Tensor, pool_size=(2, 2), pool_type: str = "avg") -> torch.Tensor:
        x = F.relu_(self.bn1(self.conv1(x)))
        x = F.relu_(self.bn2(self.conv2(x)))
        if pool_type == "avg":
            x = F.avg_pool2d(x, kernel_size=pool_size)
        elif pool_type == "max":
            x = F.max_pool2d(x, kernel_size=pool_size)
        return x


class RespirPANNsCNN14(nn.Module):
    """PANNs CNN14 adaptat pe tensori precalculati 1-canal [B, 1, F, T] cu bn0(64) nativ si iesire binara."""

    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.bn0 = nn.BatchNorm2d(64)

        self.conv_block1 = ConvBlock(in_channels=1, out_channels=64)
        self.conv_block2 = ConvBlock(in_channels=64, out_channels=128)
        self.conv_block3 = ConvBlock(in_channels=128, out_channels=256)
        self.conv_block4 = ConvBlock(in_channels=256, out_channels=512)
        self.conv_block5 = ConvBlock(in_channels=512, out_channels=1024)
        self.conv_block6 = ConvBlock(in_channels=1024, out_channels=2048)

        self.fc1 = nn.Linear(2048, 2048, bias=True)
        self.fc_audioset = nn.Linear(2048, num_classes, bias=True)

    def train(self, mode: bool = True):
        super().train(mode)
        if mode:
            for name, m in self.named_modules():
                if "conv_block" in name and isinstance(m, nn.BatchNorm2d):
                    m.eval()
        return self

    def freeze_backbone(self, freeze_fc1: bool = False):
        for name, param in self.named_parameters():
            if "conv_block" in name or (freeze_fc1 and "fc1" in name):
                param.requires_grad = False
            else:
                param.requires_grad = True
        self.train(self.training)

    def unfreeze_backbone(self):
        for name, param in self.named_parameters():
            if "conv_block" in name and (".bn1." in name or ".bn2." in name):
                param.requires_grad = False
            else:
                param.requires_grad = True
        self.train()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Intrare [B, 1, F=64, T=157] -> [B, 1, T=157, F=64] identic ca orientare cu PANNs AudioSet
        x = x.transpose(2, 3)

        # Normalizare independenta pe fiecare din cele 64 benzi de frecventa Mel (stratul nativ PANNs bn0)
        x = x.transpose(1, 3)
        x = self.bn0(x)
        x = x.transpose(1, 3)

        backbone_train = False

        x = self.conv_block1(x, pool_size=(2, 2), pool_type="avg")
        x = F.dropout(x, p=0.2, training=backbone_train)
        x = self.conv_block2(x, pool_size=(2, 2), pool_type="avg")
        x = F.dropout(x, p=0.2, training=backbone_train)
        x = self.conv_block3(x, pool_size=(2, 2), pool_type="avg")
        x = F.dropout(x, p=0.2, training=backbone_train)
        x = self.conv_block4(x, pool_size=(2, 2), pool_type="avg")
        x = F.dropout(x, p=0.2, training=backbone_train)
        x = self.conv_block5(x, pool_size=(2, 2), pool_type="avg")
        x = F.dropout(x, p=0.2, training=backbone_train)
        x = self.conv_block6(x, pool_size=(1, 1), pool_type="avg")
        x = F.dropout(x, p=0.2, training=backbone_train)

        x = torch.mean(x, dim=3)
        x1, _ = torch.max(x, dim=2)
        x2 = torch.mean(x, dim=2)
        x = x1 + x2

        x = F.dropout(x, p=0.5, training=self.training)
        x = F.relu_(self.fc1(x))
        x = F.dropout(x, p=0.5, training=self.training)
        return self.fc_audioset(x)


def load_pretrained_panns_cnn14(device: torch.device, num_classes: int = 2) -> RespirPANNsCNN14:
    model = RespirPANNsCNN14(num_classes=num_classes)

    ckpt_path = next((p for p in CNN14_CANDIDATE_PATHS if os.path.exists(p)), "/content/Cnn14_mAP=0.431.pth")
    if not os.path.exists(ckpt_path):
        print(f"[Download] Descarc greutatile preantrenate AudioSet -> {ckpt_path} ...")
        torch.hub.download_url_to_file(CNN14_ZENODO_URL, ckpt_path)

    raw_ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    pretrained_state = raw_ckpt.get("model", raw_ckpt)

    model_state = model.state_dict()
    matched = {
        k: v
        for k, v in pretrained_state.items()
        if k in model_state and not k.startswith("fc_audioset") and v.shape == model_state[k].shape
    }
    missing, unexpected = model.load_state_dict(matched, strict=False)
    print(f"[PANNs] Checkpoint AudioSet incarcat din: {ckpt_path}")
    print(f"[PANNs] Tensori potriviti: {len(matched)} / {len(model_state)} | Neincarcati (head): {missing}")

    model.freeze_backbone(freeze_fc1=False)
    return model.to(device)


if __name__ == "__main__":
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_panns = load_pretrained_panns_cnn14(device=device, num_classes=2)

    trainable_count = sum(p.numel() for p in model_panns.parameters() if p.requires_grad)
    total_count = sum(p.numel() for p in model_panns.parameters())
    print(f"[PANNs] Pregatit pentru Linear Probing ({device}): {trainable_count:,} / {total_count:,} parametri antrenabili.")
