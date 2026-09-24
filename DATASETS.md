# Datasets

Everything under `datasets/` is git-ignored except `datasets/README.md`. Biometric data never leaves the machine.

| Dataset | Path | Used for | Provenance | Consent / license |
|---|---|---|---|---|
| LFW | `datasets/lfw/` (`lfw.tgz`, `lfw/`, `pairs.txt`) | Identity threshold calibration (6000 pairs, 10 folds) and unit/e2e test images | figshare mirror of the UMass LFW release (URLs and SHA-256 in LICENSES.md) | No explicit license; web news photos released for research. The subjects did not consent to biometric processing, so use it only for local research benchmarking. |
| Local liveness recordings | `datasets/liveness/<CATEGORY>/*.mp4` and `metadata.csv` | PAD evaluation and attack matrix | Recorded locally with `scripts/record_sample.py` | Every recorded person must give informed consent. Use pseudonymous subject ids (`s01`) and record no names. |

Liveness categories: `BONA_FIDE, PRINT_ATTACK, PHONE_PHOTO, PHONE_VIDEO, LAPTOP_PHOTO, LAPTOP_VIDEO, MONITOR_PHOTO, MONITOR_VIDEO, TABLET_PHOTO, TABLET_VIDEO`.

No data is used for training: every model is used as released. So none of the evaluation data overlaps with training data, **except** that it is unknown whether LFW identities appear in WebFace600K (the recognition training set). Some identity overlap is plausible for public figures, which would make LFW accuracy optimistic.

## Download LFW again

```powershell
Invoke-WebRequest https://ndownloader.figshare.com/files/5976006 -OutFile datasets\lfw\pairs.txt
Invoke-WebRequest https://ndownloader.figshare.com/files/5976018 -OutFile datasets\lfw\lfw.tgz
tar -xzf datasets\lfw\lfw.tgz -C datasets\lfw
```
