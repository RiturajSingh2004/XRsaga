#!/usr/bin/env python3
"""
03_lighting_estimation.py
Track A — Estimate per-scene lighting from generated backgrounds.
Two modes:
  1) diffusionlight  — assumes DiffusionLight-Turbo is installed and callable.
  2) opencv          — fast local fallback using brightest-region heuristic.
The OpenCV fallback is the default because it requires no external GPU/dependencies.
"""

import os
import sys
import json
import argparse
import cv2
import numpy as np
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
BG_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "backgrounds")
ENV_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "envmaps")


def opencv_estimate(bg_path: str, margin_frac: float = 0.08) -> dict:
    """
    OpenCV heuristic: find brightest region -> dominant light direction.
    Returns azimuth (deg), elevation (deg), ambient_color (BGR tuple).

    A border margin (default 8%) is excluded before searching for the
    brightest region, so the algorithm can't lock onto edge-clipped pixels
    (e.g. blown-out sky at row 0 or window glare at column 0).

    Ambient color is sampled from the lower two-thirds of the frame only,
    excluding sky-dominated upper pixels that skew the tint toward blue.
    """
    img = cv2.imread(bg_path)
    if img is None:
        raise ValueError(f"Could not read {bg_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (51, 51), 0)
    h, w = gray.shape

    # Exclude border margin before searching for brightest region
    my, mx = int(h * margin_frac), int(w * margin_frac)
    interior = blurred[my:h - my, mx:w - mx]
    _, max_val, _, max_loc_interior = cv2.minMaxLoc(interior)
    # Map back to full-image coordinates
    max_loc = (max_loc_interior[0] + mx, max_loc_interior[1] + my)

    # Azimuth: -90 (left) to +90 (right), 0 = center
    azimuth = (max_loc[0] / w - 0.5) * 180.0
    # Elevation: 10 deg minimum (don't let sun go below horizon)
    elevation = max(10.0, 90.0 - (max_loc[1] / h) * 90.0)

    # Ambient color from lower two-thirds of frame (excludes sky)
    lower_region = img[int(h * 0.35):, :]
    mean_color = cv2.mean(lower_region)[:3]  # BGR
    ambient_color = [float(c) for c in mean_color]

    return {
        "azimuth": round(azimuth, 2),
        "elevation": round(elevation, 2),
        "ambient_color": ambient_color,
        "max_brightness": float(max_val),
        "brightest_pixel": max_loc,
    }


def run_opencv_fallback():
    """Process all backgrounds with the OpenCV heuristic and write fallback_lighting.json."""
    os.makedirs(ENV_DIR, exist_ok=True)
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    results = {}
    for env in cfg["environments"]:
        name = env["name"]
        bg_path = os.path.join(BG_DIR, f"{name}.png")
        if not os.path.exists(bg_path):
            print(f"[SKIP] Background not found: {bg_path}")
            continue

        print(f"[PROC] OpenCV heuristic: {name}")
        results[name] = opencv_estimate(bg_path)

    out_json = os.path.join(ENV_DIR, "fallback_lighting.json")
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVE] Fallback lighting data -> {out_json}")


def run_diffusionlight():
    """
    Run DiffusionLight-Turbo inference on all backgrounds.
    ASSUMPTION: DiffusionLight-Turbo is cloned and installed in the current environment.
    This is intended primarily for Google Colab usage.
    """
    # This is a thin wrapper; the heavy lifting is in notebooks/colab_pipeline.ipynb.
    # Exit with code 1 so the orchestrator knows no output files were produced.
    print("DiffusionLight-Turbo mode selected.")
    print("This script does not run DiffusionLight-Turbo directly.")
    print("For Colab, use notebooks/colab_pipeline.ipynb instead.")
    print("For local usage, ensure DiffusionLight-Turbo is installed and run:")
    print("  python inference.py --input <bg> --output_dir outputs/envmaps/")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Lighting estimation for PS1 pipeline")
    parser.add_argument(
        "--mode",
        choices=["opencv", "diffusionlight"],
        default="opencv",
        help="Estimation method (default: opencv)",
    )
    args = parser.parse_args()

    if args.mode == "opencv":
        run_opencv_fallback()
    else:
        run_diffusionlight()


if __name__ == "__main__":
    main()
