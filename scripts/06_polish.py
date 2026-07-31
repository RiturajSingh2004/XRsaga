#!/usr/bin/env python3
"""
06_polish.py
Final post-process pass — global sharpen + subtle contrast/saturation grade
via FFmpeg, applied uniformly to the whole frame (car + background together).

Deterministic, non-generative — no selective/AI modification of car pixels,
stays compliant with the "do not modify paint/decals/materials" requirement.

Run after 05_composite.py:
  python scripts/06_polish.py
"""

import os
import subprocess
import sys

ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
IN_DIR = os.path.join(ROOT_DIR, "outputs", "final")
OUT_DIR = os.path.join(ROOT_DIR, "outputs", "final_polished")

# Tune these by eye on one image before trusting the batch run.
# Keep values modest — this should read as "consistent photo," not "processed/HDR."
UNSHARP = "5:5:0.8:5:5:0.4"
EQ = "contrast=1.05:saturation=1.08:brightness=0.01"


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: ffmpeg not found on PATH. Install it before running this script.")
        sys.exit(1)


def polish_image(in_path: str, out_path: str):
    cmd = [
        "ffmpeg", "-y",  # -y: overwrite without prompting
        "-i", in_path,
        "-vf", f"unsharp={UNSHARP},eq={EQ}",
        out_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(f"  FAILED: {os.path.basename(in_path)}")
        print(f"     {result.stderr.decode(errors='ignore').strip().splitlines()[-1]}")
        return False
    print(f"  OK: {os.path.basename(in_path)} -> {out_path}")
    return True


def main():
    check_ffmpeg()

    if not os.path.isdir(IN_DIR):
        print(f"ERROR: {IN_DIR} not found — run 05_composite.py first.")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    inputs = sorted(f for f in os.listdir(IN_DIR) if f.lower().endswith(".png"))
    if not inputs:
        print(f"ERROR: no PNG files found in {IN_DIR}")
        sys.exit(1)

    print(f"Polishing {len(inputs)} image(s) from {IN_DIR}\n")

    ok_count = 0
    for fname in inputs:
        in_path = os.path.join(IN_DIR, fname)
        out_path = os.path.join(OUT_DIR, fname)
        if polish_image(in_path, out_path):
            ok_count += 1

    print(f"\n{ok_count}/{len(inputs)} polished successfully -> {OUT_DIR}")
    if ok_count < len(inputs):
        sys.exit(1)


if __name__ == "__main__":
    main()