"""Phase 3: local webcam sanity check.

Opens the camera, shows frames with an FPS overlay and exits cleanly on 'q' / ESC.
With --headless it grabs N frames without a window and prints a summary, which is
how the automated check runs.

Usage:
    python scripts/camera_test.py                 # interactive window
    python scripts/camera_test.py --headless -n 100
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import cv2
import psutil

MAX_CONSECUTIVE_FAILURES = 30  # ~1 s at 30 FPS before treating the camera as disconnected


def open_camera(index: int) -> cv2.VideoCapture | None:
    # CAP_DSHOW opens much faster than MSMF on Windows; fall back to the default backend elsewhere.
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return None
    return cap


def run(index: int, headless: bool, max_frames: int | None) -> int:
    cap = open_camera(index)
    if cap is None:
        print(f"ERROR: camera {index} unavailable (not connected, in use by another app, "
              "or blocked by Windows camera privacy settings).", file=sys.stderr)
        return 2

    proc = psutil.Process(os.getpid())
    rss_start = proc.memory_info().rss
    frames = 0
    failures = 0
    fps = 0.0
    t_window = time.perf_counter()
    window_frames = 0
    t0 = time.perf_counter()
    shape = None
    exit_code = 0

    try:
        while max_frames is None or frames < max_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    print("ERROR: camera stopped delivering frames (disconnected?).", file=sys.stderr)
                    exit_code = 3
                    break
                continue
            failures = 0
            frames += 1
            window_frames += 1
            shape = frame.shape

            now = time.perf_counter()
            if now - t_window >= 1.0:
                fps = window_frames / (now - t_window)
                t_window, window_frames = now, 0

            if not headless:
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            1.0, (0, 255, 0), 2)
                cv2.imshow("camera_test (q to quit)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if cv2.getWindowProperty("camera_test (q to quit)", cv2.WND_PROP_VISIBLE) < 1:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if not headless:
            cv2.destroyAllWindows()

    elapsed = time.perf_counter() - t0
    rss_end = proc.memory_info().rss
    print(f"frames={frames} elapsed_s={elapsed:.2f} avg_fps={frames / elapsed if elapsed else 0:.1f} "
          f"shape={shape} rss_start_mb={rss_start / 2**20:.1f} rss_end_mb={rss_end / 2**20:.1f} "
          f"released={not cap.isOpened()}")
    if frames == 0 and exit_code == 0:
        exit_code = 3
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("-n", "--frames", type=int, default=None)
    args = parser.parse_args()
    sys.exit(run(args.camera, args.headless, args.frames))


if __name__ == "__main__":
    main()
