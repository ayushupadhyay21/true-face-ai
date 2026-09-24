"""Record a short webcam clip for the liveness evaluation (local only, git-ignored).

The clip goes to datasets/liveness/<CATEGORY>/<timestamp>.mp4. Its metadata row is
appended to datasets/liveness/metadata.csv. Only record people who have consented.

Categories: BONA_FIDE, PRINT_ATTACK, PHONE_PHOTO, PHONE_VIDEO, LAPTOP_PHOTO, LAPTOP_VIDEO,
            MONITOR_PHOTO, MONITOR_VIDEO, TABLET_PHOTO, TABLET_VIDEO

Example (hold a phone showing a photo in front of the webcam):
    python scripts/record_sample.py PHONE_PHOTO --device "Pixel 7" --resolution 1080x2400 \
        --lighting "office, daylight" --subject s01 --seconds 6
Press SPACE to start recording, q to abort.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets" / "liveness"
CATEGORIES = ["BONA_FIDE", "PRINT_ATTACK", "PHONE_PHOTO", "PHONE_VIDEO", "LAPTOP_PHOTO", "LAPTOP_VIDEO",
              "MONITOR_PHOTO", "MONITOR_VIDEO", "TABLET_PHOTO", "TABLET_VIDEO"]
FIELDS = ["file", "category", "subject", "device", "resolution", "lighting", "notes", "recorded_at"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("category", choices=CATEGORIES)
    ap.add_argument("--subject", required=True, help="pseudonymous subject id, e.g. s01")
    ap.add_argument("--device", default="", help="presentation device (phone model, printer, monitor)")
    ap.add_argument("--resolution", default="", help="presentation device resolution")
    ap.add_argument("--lighting", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--camera", type=int, default=0)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
    if not cap.isOpened():
        sys.exit("camera unavailable")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    (OUT / args.category).mkdir(parents=True, exist_ok=True)
    name = f"{args.category}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{args.subject}.mp4"
    writer = None
    t_start = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                sys.exit("camera stopped delivering frames")
            if writer is not None:
                writer.write(frame)
                if time.time() - t_start >= args.seconds:
                    break
            view = frame.copy()
            label = "REC" if writer else "SPACE = start, q = quit"
            cv2.putText(view, f"{args.category} {label}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.imshow("record_sample", view)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("aborted")
                return
            if key == ord(" ") and writer is None:
                h, w = frame.shape[:2]
                writer = cv2.VideoWriter(str(OUT / name), cv2.VideoWriter_fourcc(*"mp4v"), 15, (w, h))
                t_start = time.time()
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()

    meta = OUT / "metadata.csv"
    new = not meta.exists()
    with meta.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerow({"file": name, "category": args.category, "subject": args.subject, "device": args.device,
                    "resolution": args.resolution, "lighting": args.lighting, "notes": args.notes,
                    "recorded_at": datetime.now().isoformat(timespec="seconds")})
    print(f"saved {OUT / name}")


if __name__ == "__main__":
    main()
