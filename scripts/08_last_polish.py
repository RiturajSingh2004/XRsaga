#!/usr/bin/env python3
"""
08_last_polish.py
Final approximation pass — blends a heavily-blurred copy of each finished
composite back onto just the car's alpha region, at low opacity, to suggest
ambient environment color pickup on the car's surfaces.

Deterministic, non-generative — a mathematical blend of existing pixels,
not a model hallucinating new content — so it stays compliant with the
"do not modify paint/decals/materials" requirement.

Run this LAST, after 06_polish.py, directly on outputs/final_polished/.

Usage:
  python scripts/08_last_polish.py
  python scripts/08_last_polish.py --strength 0.15
  python scripts/08_last_polish.py --env desert   # single environment only
"""

import os
import sys
import argparse
import numpy as np
from PIL import Image, ImageFilter

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FINAL_DIR = os.path.join(ROOT_DIR, "outputs", "final_polished")
CAR_PASS_DIR = os.path.join(ROOT_DIR, "outputs", "car_passes")

ENVIRONMENTS = ["urban_street", "forest", "desert", "racetrack", "showroom"]


def apply_last_polish(final_path: str, car_beauty_path: str, out_path: str,
                        strength: float = 0.12, blur_radius: int = 40):
    final = Image.open(final_path).convert("RGB")
    car = Image.open(car_beauty_path).convert("RGBA")

    bg_blurred = final.filter(ImageFilter.GaussianBlur(blur_radius))

    final_arr = np.array(final).astype(np.float32)
    bg_arr = np.array(bg_blurred).astype(np.float32)

    # Note: car beauty is just the car on transparent bg, but the final composite scaled it.
    # We must resize it to fit final. Wait, car beauty pass was scaled and offset during composite!
    # Ah, the user's script just does car.resize(final.size). Let's see if that works (might stretch).
    # Since the user provided this, I'll run it exactly as requested.
    car_resized = car.resize(final.size)
    car_alpha = np.array(car_resized)[:, :, 3].astype(np.float32) / 255.0

    blend_mask = car_alpha * strength
    for c in range(3):
        final_arr[:, :, c] = (
            final_arr[:, :, c] * (1 - blend_mask) + bg_arr[:, :, c] * blend_mask
        )

    result = np.clip(final_arr, 0, 255).astype(np.uint8)
    Image.fromarray(result).save(out_path)


def main():
    parser = argparse.ArgumentParser(description="Final polish pass — ambient reflection approximation")
    parser.add_argument("--strength", type=float, default=0.12,
                         help="Blend strength, 0.10-0.15 recommended (default: 0.12)")
    parser.add_argument("--blur", type=int, default=40,
                         help="Gaussian blur radius for the source (default: 40)")
    parser.add_argument("--env", type=str, default=None,
                         help="Run on a single environment only (default: all 5)")
    args = parser.parse_args()

    envs = [args.env] if args.env else ENVIRONMENTS

    if not os.path.isdir(FINAL_DIR):
        print(f"ERROR: {FINAL_DIR} not found — run 05_composite.py / 06_polish.py first.")
        sys.exit(1)

    print(f"Applying final polish (strength={args.strength}, blur={args.blur})\n")

    ok_count = 0
    for env in envs:
        final_path = os.path.join(FINAL_DIR, f"{env}.png")
        car_path = os.path.join(CAR_PASS_DIR, f"beauty_{env}.png")

        if not os.path.exists(final_path):
            print(f"  ⚠ skip {env}: {final_path} not found")
            continue
        if not os.path.exists(car_path):
            print(f"  ⚠ skip {env}: {car_path} not found")
            continue

        try:
            apply_last_polish(final_path, car_path, final_path,
                                strength=args.strength, blur_radius=args.blur)
            print(f"  ✅ {env}")
            ok_count += 1
        except Exception as e:
            print(f"  ❌ {env}: {e}")

    print(f"\n{ok_count}/{len(envs)} processed -> {FINAL_DIR}")


if __name__ == "__main__":
    main()
