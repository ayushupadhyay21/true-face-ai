# Environment Audit

Audit date: 2026-09-24 (Phase 0). Values below come from commands run on the developer machine; nothing was installed or changed during the audit.

| Item | Value | Command used |
|---|---|---|
| OS | Windows 11 Home Single Language 10.0.26200 (build 26200), 64-bit | `Win32_OperatingSystem` |
| Python | 3.14.3 (MSC v.1944, AMD64) — only interpreter installed | `python --version`, `py -0p` |
| pip | 25.3 (bound to Python 3.14) | `pip --version` |
| uv | 0.12.5 | `uv --version` |
| Node | v20.20.0 | `node --version` |
| npm | 10.8.2 | `npm --version` |
| Angular CLI | 21.2.3 | `ng version` |
| Git | 2.51.0.windows.1 | `git --version` |
| PostgreSQL | 18.1, Windows service `postgresql-x64-18`, running, automatic start | `Get-Service`, `psql --version` |
| PostgreSQL install | `C:\Program Files\PostgreSQL\18` (data dir `...\18\data`), port 5432 | `postgresql.conf` |
| pgvector | **Not installed** (`share\extension\vector.control` missing) | file check |
| GPU | Intel UHD Graphics (integrated, driver 31.0.101.4314). No NVIDIA GPU. | `Win32_VideoController`, `nvidia-smi` (not found) |
| CUDA | Not available (`nvcc` not found, no NVIDIA GPU) | `nvcc --version` |
| cuDNN | Not applicable | — |
| RAM | 15.71 GB total (~3.1 GB free at audit time) | `Win32_OperatingSystem` |
| CPU | 13th Gen Intel Core i3-1315U, 6 cores / 8 threads | `Win32_Processor` |
| Disk | C: 165.3 GB free; D: 73.2 GB free (project on D:) | `Get-PSDrive` |
| Cameras | "Integrated Camera" (status OK) | `Win32_PnPEntity` |
| Docker / conda | Not installed (not needed) | `Get-Command` |

## Findings that affect later phases

1. **CPU-only inference.** No CUDA-capable GPU. All models must run on CPU via ONNX Runtime (`CPUExecutionProvider`). PyTorch, if needed for evaluation or training, must be the CPU build. Latency expectations should be set accordingly (low-power U-series CPU).
2. **Python 3.14 is too new for parts of the ML stack.** Packages such as `insightface` (built from source, needs a C++ compiler) and some `onnxruntime` / `torch` releases may not ship wheels for 3.14. Proposal for Phase 1: create the project virtual environment with a pinned Python 3.12 via `uv python install 3.12` (installs into uv's own directory; does not alter the system Python). To be confirmed before Phase 1.
3. **pgvector missing.** It must be installed into PostgreSQL 18 before Phase 8. On Windows this usually means building from source with Visual Studio Build Tools (`nmake`) or using a prebuilt binary matching PG 18. To be decided in Phase 8.
4. **PostgreSQL listens on `0.0.0.0:5432` and `[::]:5432`** (all interfaces). For a local research project, restricting `listen_addresses = 'localhost'` is recommended. Not changed during the audit.
5. **`psql` is not on PATH.** Use the full path `C:\Program Files\PostgreSQL\18\bin\psql.exe` or add the bin directory to PATH.
6. **Free RAM was low (~3 GB)** at audit time because of other running programs. Close unused applications during evaluation and benchmarking.
