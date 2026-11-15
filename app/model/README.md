# app/model/

The trained model for the AI on the phone (`app/ai/`). Empty until the model is trained: the app then answers in dummy mode, exactly like the AI server without weights (fixed answers, real quality check).

To add the model, put the two files from the Kaggle notebook's `respirai_export.zip` here, then push:

| File | What it is |
|---|---|
| `resp_cnn.onnx` | the model (ResNet18, about 45 MB) |
| `resp_cnn.json` | its version, classes and preprocessing settings; the app refuses a model whose settings differ from `app/ai/pipeline.js` |
| `demo_clips/` | optional: the notebook's `demo_clips/` folder (`manifest.json` + WAVs), for demo mode |

The same two files go to `ai/weights/` for the Python server. The web app, the GitHub Pages site and the Android app all pick the model up from here on the next build. *Settings → Test the AI server* then shows the model's version instead of `dummy-0.0`.

## The model here now: provisional (15 November 2026)

`respirai-v2-own-background`: ResNet18 trained on this laptop with `ai/train_local.py` (ICBHI, 100–1000 Hz, each band's mean taken out), with one healthy person's recordings from our own device as normal and as background under every class. It is here so the app gives real answers instead of dummy ones; replace it when a better one exists.

`"suspect_threshold": 0.70` in `resp_cnn.json` decides when a recording is reported as abnormal. On ICBHI validation recordings, at 0.70: 83 % of the recordings with crackles or wheezes are flagged, 42 % of the clear ones are left alone. On our device, one healthy person: 1 of 5 unseen recordings flagged. Lower it to miss fewer (0.37: none missed on validation, but nearly every healthy recording flagged); raise it for fewer false alarms. The numbers are in [`ai/README.md`](../../ai/README.md) on the `ai-training` branch.
