# Test recordings

Real lung sounds for the fake devices (`?fakebt&wav=…` and `fake_device.py --file …`). For testing only; they are not part of the app.

| File | Original | Author | Licence |
|---|---|---|---|
| `crackles.wav` | [Crackles pneumoniaO.ogg](https://commons.wikimedia.org/wiki/File:Crackles_pneumoniaO.ogg) — crackles in a patient with pneumonia | James Heilman, MD | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| `wheeze.wav` | [Wheeze2O.ogg](https://commons.wikimedia.org/wiki/File:Wheeze2O.ogg) — wheezing | James Heilman, MD | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |

Converted from the Commons originals (22 kHz Ogg Vorbis) to 8 kHz 16-bit mono WAV, the device's format, and scaled to half of full range. Same licence. When the Kaggle notebook has produced the ICBHI demo clips (`ai/demo_clips/`), those can be streamed too: `?fakebt&wav=demo_clips/crackles_Al.wav` with `dev_server.py`.
