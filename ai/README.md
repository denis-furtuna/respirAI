# ai/

Everything on the model side: data, training and serving.

Task list: D1–D13 in [`docs/PLAN.md` §5.3](../docs/PLAN.md#53-ai-and-data-can-start-today-needs-no-hardware). Train on the sound labels, not the disease labels, and never split randomly.

## Files

| File | What it does | Task |
|---|---|---|
| [`notebooks/train_icbhi.ipynb`](notebooks/train_icbhi.ipynb) | Kaggle notebook: explore, split, train, test, export, pick demo clips | D1–D6 |
| `preprocess.py` | 4 kHz → band-pass 100–1800 Hz → 4 s windows → log-mel. **Imported by both training and the server.** NumPy/SciPy only. | D2 |
| `icbhi.py` | reads ICBHI files and cycle labels, labels windows, splits by patient | D1, D3 |
| `model.py` | ResNet18 with 1 input channel and 4 classes; ONNX export (PyTorch, training only) | D4 |
| `inference.py` | whole recording → one finding, using the ONNX model | D5 |
| `quality.py` | 0–1 recording quality: silence, clipping, dropped packets, handling noise | D7 |
| `service.py` | the server's logic: `/analyze`, demo mode, session summary | D5, D6, D8 |
| `server.py` | thin FastAPI layer over `service.py` | D5 |

Not committed: datasets (`ai/data/`) and trained models (`ai/weights/`). Committed on purpose: `ai/demo_clips/` and `ai/results/`.

## Train on Kaggle

1. On kaggle.com: *Create* → *New Notebook* → *File* → *Import Notebook* → upload `notebooks/train_icbhi.ipynb`.
2. *Add Input* → search **Respiratory Sound Database** (by vbookshelf) → *Add*.
3. *Settings*: Accelerator **GPU T4 x2** or **P100**, Internet **On**.
4. *Run All*. It takes about 10–20 minutes.
5. Download `respirai_export.zip` from *Output*, then put the files where the notebook's last cell says.

The notebook clones this repo from GitHub to get the code, so **push your changes before running it**.

## Run the server

```bash
cd ai
pip install -r requirements-server.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

Check it at `http://localhost:8000/health`. With no model in `ai/weights/`, it runs in **dummy mode**: same request and response shapes, fixed answers. That's enough for the app to be built against it today.

```bash
curl -F point=Al -F session_id=test -F audio=@recording.wav http://localhost:8000/analyze
curl -F point=Al -F session_id=test -F demo=true -F demo_case=crackles http://localhost:8000/analyze
curl http://localhost:8000/session/test/summary
```

The server needs no PyTorch: the model runs with ONNX Runtime. On managed laptops where application control blocks some Python packages, check that `fastapi`, `pydantic` and `onnxruntime` import before demo day.
