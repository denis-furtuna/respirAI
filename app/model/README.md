# app/model/

The trained model for the AI on the phone (`app/ai/`). Empty until the model is trained: the app then answers in dummy mode, exactly like the AI server without weights (fixed answers, real quality check).

To add the model, put the two files from the Kaggle notebook's `respirai_export.zip` here, then push:

| File | What it is |
|---|---|
| `resp_cnn.onnx` | the model (ResNet18, about 45 MB) |
| `resp_cnn.json` | its version, classes and preprocessing settings; the app refuses a model whose settings differ from `app/ai/pipeline.js` |
| `demo_clips/` | optional: the notebook's `demo_clips/` folder (`manifest.json` + WAVs), for demo mode |

The same two files go to `ai/weights/` for the Python server. The web app, the GitHub Pages site and the Android app all pick the model up from here on the next build. *Settings → Test the AI server* then shows the model's version instead of `dummy-0.0`.
