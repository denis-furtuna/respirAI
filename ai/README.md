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

The server runs the PANNs CNN14 per chest place and the patient RandomForest over the whole check, and serves the web app itself, so a demo is one laptop, one phone and one command. Only Chrome on the phone uses it: the Android app and GitHub Pages always analyse on the phone with the ONNX model.

### 1. Set up the laptop (once)

```bash
git clone https://github.com/denis-furtuna/respirAI && cd respirAI/ai
python -m venv .venv
.venv/bin/pip install -r requirements-server.txt      # Windows: .venv\Scripts\pip
```

The weights are not in git. Download these two files from the [team's Drive folder](https://drive.google.com/drive/folders/1GwzR0muWKryWnfBBQeXl7zeF77iwO2L0) into `ai/weights/`:

```
ai/weights/best_panns_finetuned_mel_hop10ms_bp50_1800_spike6ms_fade20ms_top2blocks.pt
ai/weights/patient_doctor_rf_model.pkl
```

Without them the server falls back to `weights/resp_cnn.onnx`, or to **dummy mode** (same request and response shapes, fixed answers).

### 2. Network

1. Turn on the **phone's hotspot**, with a password, and connect the laptop to it. Not the venue Wi-Fi: there anyone could reach the server.
2. Find the laptop's address on the hotspot: `hostname -I` (Linux), `ipconfig getifaddr en0` (macOS), `ipconfig` → *IPv4 Address* (Windows). Below: `10.39.40.62`.
3. If a firewall is on, allow port 8000 (`sudo ufw allow 8000` on Ubuntu).

### 3. Chrome on the phone (once)

Web Bluetooth only works on secure pages, and the laptop serves plain http. Open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, type `http://10.39.40.62:8000` (your address), set it to **Enabled**, tap **Relaunch**. If the laptop's address changes, change it here too.

### 4. Start the server

```bash
cd ai
.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Check `http://10.39.40.62:8000/health` from the phone: it must say `"backend":"panns"`. `"dummy":true` means the weights are missing.

### 5. Run the check

1. Switch the device on.
2. On the phone, in Chrome: `http://10.39.40.62:8000`. Served from port 8000, the app sends its recordings to this server by itself; leave *Settings → AI server address* empty.
3. **Connect the device** → pick `respirAI`.
4. Begin (all places) or the quick test. At each place: put the chest piece on, **Start now**; one practice breath before the first place, then 6 s are recorded, one breath (in 2.5 s, out 3.5 s).
5. The results screen shows each place and, under the overall answer, the patient verdict: *Across all places: normal (99.8 %)* or *… see a doctor (99.9 %)*.

**Rehearse without the device:** `http://10.39.40.62:8000/?fakebt&wav=wheeze.wav` (or `http://localhost:8000/?fakebt` on the laptop) streams a real recording through a fake device.

### When something is wrong

| What you see | Why |
|---|---|
| *Connect the device* does nothing | the Chrome flag is missing, or it has another address |
| No patient verdict under the result | the page isn't opened from port 8000, or `/health` doesn't say `panns` |
| *Please record again* | too quiet or too much handling noise: press the chest piece firmly on the skin |
| The phone can't reach the server | the laptop is not on the hotspot, or the firewall blocks port 8000 |

### What to know before the pitch

- `POINT_THRESHOLD` (0.87, in `inference_panns.py`) was chosen by `calibrate_panns.py` on one healthy person recorded with our device: both checks read *Normal*. Record more healthy people and run it again.
- A real wheeze (`app/dev/recordings/wheeze.wav`) is found. A real pneumonia crackle (`crackles.wav`) is **not**: on our device the model scores it like a healthy chest.
- Demo mode needs `ai/demo_clips/`, which doesn't exist yet: it answers 404.

### The API by hand

```bash
curl http://localhost:8000/health
curl -F point=Al -F session_id=test -F audio=@recording.wav http://localhost:8000/analyze
curl http://localhost:8000/session/test/summary      # with PANNs: also verdict, percentage, display
```

The PANNs path needs PyTorch (CPU is enough, about 0.25 s per place) and scikit-learn; the ONNX path only ONNX Runtime. On managed laptops where application control blocks some Python packages, check that `fastapi`, `torch`, `sklearn` and `onnxruntime` import before demo day.
