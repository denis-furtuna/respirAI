# app/

The **web app** that runs in Chrome on the phone (demo device: Samsung S25 Ultra) and on desktop Chrome. No native app, no app store. Not supported on iPhone — Safari has no Web Bluetooth.

What belongs here:

- Web Bluetooth connection to the `respirAI` device, per [contract 1](../docs/ARCHITECTURE.md#1-firmware--app-ble)
- packet reassembly by sequence number, gap filling, live waveform
- the torso diagram and the guided recording flow (fixed 15 s timer per chest point in v1)
- WAV encoding and upload to the AI server, per [contract 2](../docs/ARCHITECTURE.md#2-app--ai-http)
- the results screen, with the disclaimer wording

Hosting and the HTTP/HTTPS trap are explained in [`docs/PLAN.md` §5.2](../docs/PLAN.md#52-app-owner-unassigned--highest-risk-fill-this-slot-first). Task list: A1–A11.

Wording rule: the UI never says "diagnosis". Use "finding", "screening", "possible abnormal sounds — see a doctor".
