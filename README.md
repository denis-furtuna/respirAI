<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/logo-lockup-dark.png">
  <img src="docs/brand/logo-lockup-light.png" alt="respirAI" height="64">
</picture>

**A low-cost digital stethoscope that guides the patient, listens to the lungs, and screens the sounds with AI.**

[![License: MIT](https://img.shields.io/badge/license-MIT-0F4C75?style=flat-square)](LICENSE)
![Status: pre-build](https://img.shields.io/badge/status-pre--build-64748B?style=flat-square)
![ESP32-S3](https://img.shields.io/badge/device-ESP32--S3-0F4C75?style=flat-square)
![Web Bluetooth](https://img.shields.io/badge/app-Web%20Bluetooth-0F4C75?style=flat-square)
![Dataset: ICBHI 2017](https://img.shields.io/badge/dataset-ICBHI%202017-0F4C75?style=flat-square)

[Project plan](docs/PLAN.md) · [Architecture](docs/ARCHITECTURE.md) · [Enclosure](docs/ENCLOSURE.md) · [Add-ons](docs/ADDONS.md)

> [!IMPORTANT]
> respirAI is a student hackathon project, **not a medical device**. It does not diagnose and must not be used to make health decisions. If you are unwell, see a doctor.

## Overview

The stethoscope has barely changed since Laennec invented it in 1816, and interpreting what it hears still takes a trained ear.

respirAI answers one question: *do these lungs sound normal, or should you see a doctor?*

1. The phone shows a torso diagram marking where to place the chest piece.
2. An LED matrix on the device paces the patient's breathing.
3. The device records each chest position and streams the audio to the phone over Bluetooth.
4. A neural network screens each recording for **crackles** and **wheezes** and reports a per-position finding.

No clinical training is needed to take a recording.

## How it works

<img src="docs/architecture.svg" alt="System architecture: device streams audio over BLE to the phone, which uploads a WAV for inference and shows the result" width="720">

The device captures audio at 16 kHz, downsamples to 8 kHz and streams 10 ms packets over Bluetooth Low Energy. The phone reassembles them, guides the user through the seven ICBHI chest positions, and sends each recording for inference. Results come back as JSON and are shown per position.

The system is split along three fixed interfaces, so each part can be built independently:

| Interface | Contract |
|---|---|
| Firmware → App | BLE service `7b8c9d00-0001-…`, 162-byte packets: 2-byte sequence + 10 ms of 8 kHz 16-bit mono PCM |
| App → AI | `POST /analyze` with a WAV and a chest position code; returns `finding`, `confidence`, `quality` |
| Electronics → CAD | measured component dimensions in [`cad/components.csv`](cad/components.csv) |

Full specification: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Hardware

Everything is off the shelf. There is no custom PCB, and the whole device costs roughly 200 lei.

| Part | Role | |
|---|---|---|
| Seeed XIAO ESP32-S3 | MCU, Bluetooth, battery charging | core |
| INMP441 | I²S MEMS microphone | core |
| Stethoscope chest piece + tube | acoustic front end | core |
| LiPo 3.7 V 2500 mAh | power | core |
| WS2812B 8×8 matrix | breathing guide | core |
| AD8232 | single-lead ECG | [add-on](docs/ADDONS.md) |
| MAX30102 | pulse and SpO2 | [add-on](docs/ADDONS.md) |

The add-ons are extensions to the same platform, which already provides the power, sensor bus and app pipeline. They are built only once the core is finished.

## The model

Trained on the **ICBHI 2017 Respiratory Sound Database** (920 recordings, 126 participants). It classifies each respiratory cycle as *normal*, *crackles*, *wheezes* or *both*.

- **Sound labels, not disease labels.** ICBHI's disease labels are ~86 % COPD, so a model trained on them scores well by always guessing one class.
- **Patient-wise splits, never random.** A random split puts the same patient in train and test and inflates accuracy.

Per-class results will be published here once training runs, with the split described.

## Repository

```
firmware/   ESP32: I²S capture, downsampling, BLE service, LED guide
app/        web app: Web Bluetooth, guided recording, results
ai/         preprocessing, training, inference server
cad/        enclosure models, print files, components.csv
docs/       plan, architecture, enclosure design, add-ons
```

## Status

Built for the **Medical Renaissance** hackathon in Timișoara. Hardware is on order.

| Part | State |
|---|---|
| Architecture and interface contracts | defined |
| Firmware | not started |
| Web app | not started |
| AI model | not started |
| Enclosure | not started |

## Team

| Name | Role |
|---|---|
| *TBD* | firmware, electronics |
| *TBD* | web app |
| *TBD* | AI / data |
| *TBD* | CAD, enclosure |

## License

[MIT](LICENSE)
