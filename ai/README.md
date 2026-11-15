# ai/

Everything on the model side: data, training and serving.

Task list: D1–D13 in [`docs/PLAN.md` §5.3](../docs/PLAN.md#53-ai-and-data-can-start-today-needs-no-hardware). Train on the sound labels, not the disease labels, and never split randomly.

## Files

| File | What it does | Task |
|---|---|---|
| [`notebooks/train_icbhi.ipynb`](notebooks/train_icbhi.ipynb) | Kaggle notebook: explore, split, train, test, export, pick demo clips | D1–D6 |
| `preprocess.py` | 4 kHz → band-pass 100–1000 Hz → 4 s windows → log-mel, each band's mean taken out. **Imported by both training and the server.** NumPy/SciPy only. | D2 |
| `train_local.py` | trains on this computer's GPU instead of Kaggle: by patient, with one stethoscope left out, or the model to ship; counts false alarms on our own device's recordings | D4, D6 |
| `icbhi.py` | reads ICBHI files and cycle labels, labels windows, splits by patient | D1, D3 |
| `model.py` | ResNet18 with 1 input channel and 4 classes; ONNX export (PyTorch, training only) | D4 |
| `inference.py` | whole recording → one finding, using the ONNX model | D5 |
| `quality.py` | 0–1 recording quality: silence, clipping, dropped packets, handling noise | D7 |
| `service.py` | the server's logic: `/analyze`, demo mode, session summary | D5, D6, D8 |
| `server.py` | thin FastAPI layer over `service.py` | D5 |
| `preprocess_panns.py` | the PANNs model's preprocessing: 8 → 4 kHz, centre 5 s, 50–1800 Hz, quiet recordings raised to the training level, the V3 repairs, log-mel 64 × 501 in dB (NumPy, no torchaudio) | — |
| `mel_panns_model.py` | PANNs CNN14, normal / abnormal (trained in Colab: `mel_train_*.py`) | — |
| `icbhi_patient_doctor_classifier.py` | the patient RandomForest: the places' findings → "Normal" / "Go see a doctor" | — |
| `inference_panns.py` | both together, for the server: per place and per check; `POINT_THRESHOLD` | — |
| `calibrate_panns.py` | picks `POINT_THRESHOLD` on healthy recordings from our device (`data/denis_*.wav`) | — |

**Which model the server uses.** If `weights/` holds the PANNs checkpoint and `patient_doctor_rf_model.pkl`, those (needs PyTorch and scikit-learn; `/session/…/summary` then also returns `verdict`, `percentage`, `display`). Otherwise `weights/resp_cnn.onnx`, or dummy mode. `RESPIRAI_WEIGHTS=<file>.onnx` forces the ONNX model (the CI golden tests do).

Not committed: datasets (`ai/data/`) and trained models (`ai/weights/`). Committed on purpose: `ai/demo_clips/` and `ai/results/`.

## Train on Kaggle

1. On kaggle.com: *Create* → *New Notebook* → *File* → *Import Notebook* → upload `notebooks/train_icbhi.ipynb`.
2. *Add Input* → search **Respiratory Sound Database** (by vbookshelf) → *Add*.
3. *Settings*: Accelerator **GPU T4 x2** or **P100**, Internet **On**.
4. *Run All*. It takes about 10–20 minutes.
5. Download `respirai_export.zip` from *Output*, then put the files where the notebook's last cell says.

The notebook clones this repo from GitHub to get the code, so **push your changes before running it**.

## Train on this computer

```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv/Scripts/python -m pip install numpy scipy pandas scikit-learn soundfile onnx onnxruntime av kagglehub
cd ai
python train_local.py split --data <ICBHI folder>     # train / val / test by patient
python train_local.py lodo  --data <ICBHI folder>     # each stethoscope left out in turn
python train_local.py final --data <ICBHI folder> --noise data/own_noise --own data/own_healthy   # writes weights/resp_cnn.onnx + .json
```

`--noise` is a folder of background recordings from our device, mixed into the training sound. `--own` is a folder of healthy people recorded with our device, one sub-folder per person; it is only used to count false alarms.

### What was measured (15 November 2026, one run each, ResNet18)

Scores are per 4 s window; patients never shared between train and test. "Score" is the ICBHI score, (normal recognised + abnormal given its exact class) / 2; AUC is normal against abnormal.

| | Old preprocessing (100–1800 Hz) | New (100–1000 Hz, band means out, our device's noise mixed in) |
|---|---|---|
| New patients, same stethoscopes | score 50.7 %, AUC 0.68 | score 49.7 %, AUC 0.67 |
| AKG C417L left out | 45.0 %, 0.62 | 48.7 %, 0.65 |
| Littmann 3200 left out | 30.8 %, 0.52 | 35.8 %, 0.53 |
| Littmann Classic II SE left out | 56.5 %, 0.78 | 62.4 %, 0.87 |
| Meditron left out | 40.5 %, 0.60 | 39.6 %, 0.57 |
| Our device, one healthy person, 12 windows called not normal | 67–100 % | 25–67 % |

The model does not carry well to a stethoscope it has not heard, ours included. The new preprocessing helps a little there and clearly on our own recordings, which is why it is now the default. The numbers are in `results/`.

**Threshold.** The model's JSON can carry `"suspect_threshold"`: a recording at least that likely to be abnormal is reported as abnormal (`pick()` in `inference.py`, `finding()` in the app). Without it the most probable of the four classes wins. It has to be chosen on healthy people recorded with our device; that is not done yet.

## On the phone

The app runs this same AI on the phone, with no server: [`app/ai/pipeline.js`](../app/ai/pipeline.js) is `preprocess.py`, `quality.py` and `combine()` in JavaScript, and the model runs with ONNX Runtime Web. To give the phone the trained model, copy `resp_cnn.onnx` and `resp_cnn.json` (and `demo_clips/`, if any) into [`app/model/`](../app/model/README.md) and push.

**Change the preprocessing or the quality check here, and `pipeline.js` must change the same way.** GitHub checks it on every push: [`app/tests/make_golden.py`](../app/tests/make_golden.py) runs these Python files on a set of recordings, and `app/tests/ai.html` fails if the JavaScript gives different numbers anywhere. The app also refuses a model whose `resp_cnn.json` preprocessing settings differ from its own.

## Run the server

```bash
cd ai
pip install -r requirements-server.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

**With the PANNs model and the patient classifier.** The weights are not in git: copy these two files (from the team's Drive) into `ai/weights/`, then start the server as above.

```
ai/weights/best_panns_finetuned_mel_hop10ms_bp50_1800_spike6ms_fade20ms_top2blocks.pt
ai/weights/patient_doctor_rf_model.pkl
```

`/health` then says `"backend": "panns"`. Open the app from the server itself (`http://<laptop>:8000`, see `app/README.md` → *On a phone*): served from port 8000, the app sends its recordings to that server and shows the patient verdict ("Normal" / "Go see a doctor") under the overall answer. The Android app and GitHub Pages always use the on-phone ONNX model.

Check it at `http://localhost:8000/health`. Once the web app (`app/`) is in the same checkout, the server also serves it at `http://localhost:8000`, so the demo needs only this one command. With no model in `ai/weights/`, it runs in **dummy mode**: same request and response shapes, fixed answers. That's enough for the app to be built against it today.

```bash
curl -F point=Al -F session_id=test -F audio=@recording.wav http://localhost:8000/analyze
curl -F point=Al -F session_id=test -F demo=true -F demo_case=crackles http://localhost:8000/analyze
curl http://localhost:8000/session/test/summary
```

The server needs no PyTorch: the model runs with ONNX Runtime. On managed laptops where application control blocks some Python packages, check that `fastapi`, `pydantic` and `onnxruntime` import before demo day.
