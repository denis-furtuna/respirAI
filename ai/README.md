# ai/

Everything on the model side: data, training and serving.

What belongs here:

- the training notebook(s) — ICBHI 2017 on Kaggle, later HF_Lung_V1
- the **preprocessing module** (resample to 4 kHz, band-pass 100–1800 Hz, log-mel) — one file, imported by both training and serving
- the patient-wise train/test split
- the FastAPI inference server implementing [contract 2](../docs/ARCHITECTURE.md#2-app--ai-http), including demo mode and the quality metric
- phase 2: ONNX export for in-browser inference

What does **not** belong here: the datasets themselves and trained weights (`*.pt`, `*.pth`). They are git-ignored — download them, don't commit them. Put datasets under `ai/data/`.

Task list: D1–D13 in [`docs/PLAN.md` §5.3](../docs/PLAN.md#53-ai-and-data-can-start-today-needs-no-hardware). Train on the sound labels, not the disease labels, and never split randomly.
