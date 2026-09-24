# Licenses

This file tracks licenses for every repository, pretrained weight file and dataset the project uses. Source code, weights and training data are recorded separately, because a public repository does not mean everything in it shares one license.

Audit date: 2026-09-24. Sources were checked on the official GitHub repositories. Items marked **unverified** could not be confirmed from a primary source.

**Bottom line:** everything below is usable for **local, non-commercial research**. The InsightFace model weights (detection, recognition, landmarks) are **not** licensed for commercial use. A commercial use would need a separate license from InsightFace and different datasets.

## 1. InsightFace: SCRFD detector, ArcFace recognizer, 2d106 landmarks

| Field | Value |
|---|---|
| Repository | deepinsight/insightface |
| URL | https://github.com/deepinsight/insightface |
| Version / commit | Model pack `buffalo_l.zip` from release `v0.7`. Repo HEAD at audit: 1480e705 (2026-09-09) |
| Repository (code) license | MIT (stated in the README "License" section; the repo has no LICENSE file at its root) |
| Pretrained weight license | **Non-commercial research only.** README: "The training data containing the annotation (and the models trained with these data) are available for non-commercial research purposes only. Both manual-downloading models from our github repo and auto-downloading models with our python-library follow the above license policy." model_zoo README: "ALL models are available for non-commercial research purposes only." Since 2025-11 the README also says to contact recognition-oss-pack@insightface.ai for licensing buffalo_l. |
| Files used | `det_10g.onnx` (SCRFD-10GF), `w600k_r50.onnx` (ArcFace ResNet-50), `2d106det.onnx` (106-pt landmarks). Not used: `1k3d68.onnx`, `genderage.onnx`. |
| Download | https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip (288,621,354 bytes). SHA-256 `80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f` matches the digest published on the `model-zoo` release. |
| Training datasets | Recognition: WebFace600K (a subset of WebFace260M; that relationship is **unverified**). Detection: WIDER FACE. 106 landmarks: not documented. |
| Dataset licenses | WebFace260M: academic research only, signed agreement required (from search results; the official page did not load, so **unverified**). WIDER FACE: reported as CC BY-NC-ND / non-commercial (secondary sources, **unverified**). |
| Research restrictions | Non-commercial research only. No redistribution of weights in this repo (they are git-ignored). |

## 2. Silent-Face-Anti-Spoofing: passive liveness (MiniFASNet)

| Field | Value |
|---|---|
| Repository | minivision-ai/Silent-Face-Anti-Spoofing |
| URL | https://github.com/minivision-ai/Silent-Face-Anti-Spoofing |
| Version / commit | b6d5f04a (2020-08-05, last commit; the repo is inactive) |
| Repository (code) license | Apache-2.0 (LICENSE file) |
| Pretrained weight license | No separate statement. The weights ship inside the Apache-2.0 repo, so Apache-2.0 presumably applies, but this is not explicit. |
| Files used | `2.7_80x80_MiniFASNetV2.pth` (1,849,453 B, SHA-256 a5eb02e1…99bec0) and `4_0_0_80x80_MiniFASNetV1SE.pth` (1,856,130 B, SHA-256 84ee1d37…ec2f5990). Converted locally to ONNX by `training/scripts/export_silentface_onnx.py`. |
| Vendored code | `training/scripts/silentface_vendor/MiniFASNet.py`, verbatim with an attribution header, Apache-2.0. Used only for the ONNX export. |
| Training dataset | **Not disclosed and not released.** The README only says the training framework and preprocessing are open-sourced. |
| Dataset license | Unknown |
| Research restrictions | None stated beyond Apache-2.0. Because the training data is unknown, the attack types the model generalises to are unknown too (see MODEL_DOCUMENTATION.md). |

## 3. Datasets used for evaluation

| Dataset | Use | Source | License / terms | Notes |
|---|---|---|---|---|
| LFW (Labeled Faces in the Wild) | Threshold calibration (Phase 12), tests | `lfw.tgz` + `pairs.txt` from the figshare mirror used by scikit-learn (https://ndownloader.figshare.com/files/5976018, /5976006). SHA-256 of lfw.tgz: `055f7d9c632d7370e6fb4afc7468d40f970c34a80d4c6f50ffec63f5a8d536c0` | No explicit license. Images are news photos collected from the web and released by UMass Amherst for research. | Research benchmark only. The subjects did not consent to biometric processing. The data stays local and git-ignored. |
| Local liveness recordings | PAD evaluation (Phase 15) | Recorded by the researcher with `scripts/record_sample.py` | Own data. Consent is required from every recorded person. | Never committed (`datasets/` is git-ignored) |

## 4. Alternatives reviewed, not used

| Component | License | Weights | Why not used |
|---|---|---|---|
| yakhyo/face-anti-spoofing (MiniFASNet ONNX) | Apache-2.0 | Released (release `weights`, 2025-12) | Its preprocessing (whether it divides by 255) is undocumented. We export from the original weights instead and check the ONNX output numerically against PyTorch. |
| facenox/face-antispoof-onnx | Apache-2.0 | Retrained MiniFASNetV2-SE | Validated on CelebA-Spoof, whose non-commercial terms may carry over (**unverified**) |
| CDCN (ZitongYu/CDCN) | MIT-style, "just for research purpose" | No official weights | Would need training data (OULU-NPU etc. under EULA) |
| FAS-SGTD | MIT "just for research purpose" (**unverified**) | Drive links (**unverified**) | Provenance unclear |
| DeepPixBiS (Idiap) | **Unverified** (the server was unreachable) | Trained on OULU-NPU / Replay-Mobile (EULA) | License unverified |
| RetinaFace (alternative detector) | Part of InsightFace, same terms | Not downloaded | SCRFD is faster at similar accuracy. The `FaceDetector` interface allows adding it later. |
| MediaPipe Face Landmarker | Apache-2.0 code; model-file license **unverified** | — | Not needed: 2d106det comes from the same InsightFace pack |

## 5. Software dependencies (runtime, `backend/requirements.txt`)

| Package | License |
|---|---|
| numpy | BSD-3-Clause |
| opencv-python | Apache-2.0 (OpenCV); wheels bundle FFmpeg (LGPL) |
| onnxruntime | MIT |
| fastapi, starlette | MIT, BSD-3-Clause |
| uvicorn | BSD-3-Clause |
| pydantic, pydantic-settings | MIT |
| psycopg | LGPL-3.0 |
| pgvector (Python) | MIT |
| psutil | BSD-3-Clause |
| pgvector (PostgreSQL extension v0.8.6, built locally) | PostgreSQL License |
| Dev: pytest (MIT), httpx (BSD-3), matplotlib (PSF-based) | |
| Conversion only: torch (BSD-3-Clause), onnx (Apache-2.0) | |
| Frontend: Angular (MIT) and its default dependencies | |
