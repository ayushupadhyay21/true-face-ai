# Model Documentation

All models run on CPU with ONNX Runtime (`CPUExecutionProvider`). The model version stored with each embedding is the first 12 hex characters of the file's SHA-256, because the files carry no version metadata. Licensing is covered in [LICENSES.md](LICENSES.md).

| Role | File | Name in DB / API | Input | Output |
|---|---|---|---|---|
| Face detection | `models/detection/det_10g.onnx` | `scrfd_10g_bnkps` | 1x3x640x640, RGB, (x-127.5)/128, letterboxed at top-left | 9 tensors: scores / bbox distances / 5 keypoints for strides 8, 16, 32, 2 anchors each |
| Recognition | `models/recognition/w600k_r50.onnx` | `arcface_w600k_r50` | 1x3x112x112, RGB, (x-127.5)/127.5 | 1x**512** (read from the graph at load time), L2-normalised by us |
| Eye landmarks | `models/recognition/2d106det.onnx` | `insightface_2d106det` | 1x3x192x192, RGB, raw 0..255 (the graph starts with Sub/Mul normalisation nodes) | 212 values = 106 (x, y) in [-1, 1] |
| Passive liveness | `models/liveness/2.7_80x80_MiniFASNetV2.onnx`, `models/liveness/4_0_0_80x80_MiniFASNetV1SE.onnx` | `silentface_minifasnet_MiniFASNetV2+MiniFASNetV1SE` | Nx3x80x80, **BGR, raw 0..255** (upstream `to_tensor` does not divide by 255) | Nx3 softmax. **Class 1 = real** |

## Detection: SCRFD-10GF

The decoder is a port of `insightface/model_zoo/scrfd.py`: anchor centres × stride, `distance2bbox`, `distance2kps`, score threshold 0.5, NMS IoU 0.4. Landmark order is left eye, right eye, nose, left mouth corner, right mouth corner, where left and right refer to the image, not the subject.

The face-count policy lives in `FaceDetectionService`:

| Faces found | Result |
|---|---|
| 0 | `NO_FACE` (the session waits) |
| 1 | continue |
| 2 or more | `MULTIPLE_FACES` (the session fails) |

Detections smaller than `DET_MIN_COUNT_FACE_SIZE` (40 px) are not counted, so tiny background false positives cannot trigger a failure. Those faces are far below the 80 px quality minimum, so they could never be verified anyway.

## Alignment

`FaceAlignmentService` maps the 5 landmarks onto the standard ArcFace 112x112 template using a least-squares similarity transform (Umeyama, closed form, NumPy), then applies `cv2.warpAffine` with a black border. The result is a 112x112x3 uint8 BGR image. `preprocessing_version = arcface-5pt-umeyama-112-v1` is stored with every embedding. The unit tests check that the process is deterministic.

## Recognition: ArcFace R50 (WebFace600K)

- The embedding is 512-d, L2-normalised, so cosine similarity equals the dot product.
- The tests check that the dimension read from the graph is 512, that there are no NaN or Inf values, that the norm is 1, that repeated runs are bit-identical, and that a wrong input size raises an error.
- The identity threshold is calibrated per model (`evaluation/recognition/threshold_config.json` stores `model_name` and `model_version`). The backend refuses a threshold calibrated for a different model.

## Eye openness (blink)

- The eye contour indices of the 106-point markup were found empirically with `scripts/find_eye_indices.py` on 200 LFW faces. The 10 points nearest each SCRFD eye keypoint were **33–42** (image-left eye) and 87–96 (image-right eye). For the image-right eye, index 99 and index 89 tied near the cut-off; 87–96 was kept because it mirrors the left-eye range.
- Openness is the ratio of the minor to the major principal extent of the eye contour (PCA). It does not change with scale or rotation, and it does not depend on point ordering.
- A blink is detected when openness drops below 0.65 × the passive-phase baseline and then recovers above 0.85 × the baseline.

## Passive liveness: Silent-Face MiniFASNet

The two models are used exactly as the upstream `test.py` uses them. The only differences are the detector and the threshold:

- **Crop:**
  1. Enlarge the face box by 2.7× (V2) or 4.0× (V1SE).
  2. Clamp the scale so the crop fits the image.
  3. Shift the crop to stay inside the image, without padding.
  4. Resize to 80x80.

  This is a port of `CropImage._get_new_box`.
- **Frame score:** the mean of the two models' class-1 probabilities, which equals upstream's `sum(softmax)/2`.
- **Decision:** upstream takes the argmax of the fused vector. We compare the fused real-class probability against `LIVENESS_THRESHOLD` (default 0.5) so the operating point can be tuned.
- **ONNX export check:** the maximum absolute difference between PyTorch and ONNX Runtime output was 1.2e-7 (V2) and 1.3e-8 (V1SE) on random inputs.

**Known domain shift.** Upstream crops around boxes from its own RetinaFace-Caffe detector; we use SCRFD boxes. The two detectors' box conventions differ slightly, so the crop context differs from what the models were trained on. The training data is undisclosed. **No claim is made about which attack types the model detects**, and only the evaluation in EVALUATION.md counts as evidence.

Observation, not an evaluation: LFW news photos pasted digitally onto a grey 640x480 canvas scored 0.33–0.55. These are not physical presentation attacks.

## Temporal aggregation

| Phase | Rule |
|---|---|
| Passive | The first `LIVENESS_MIN_FRAMES` (5) good-quality frontal frames are scored. The arithmetic mean of the frame scores must be ≥ threshold. |
| Whole session | Every frame with a face ≥ 60 px is scored, including frames during the active challenge. After the last action, the mean over all scored frames must also be ≥ threshold. |

Why the mean: it is the same score-level fusion rule upstream uses to combine its two models. Averaging reduces per-frame noise from blur, lighting and pose. The limitation: frames of a static attack are strongly correlated, so averaging makes the decision robust to noise, not to attacks the model cannot see.

## Model replacement and re-enrollment

Search only compares embeddings with an identical `(model_name, model_version, embedding_dimension, preprocessing_version)`. If any of these change:

1. Existing embeddings stay in the DB but are ignored.
2. People must be **re-enrolled** with the new model.
3. The threshold must be **re-calibrated**. `calibrate_threshold.py` writes a new config tagged with the new model, and the backend refuses to start sessions until it exists.

Old rows can be deleted with `DELETE FROM face_embeddings WHERE model_version <> '<new>'`.
