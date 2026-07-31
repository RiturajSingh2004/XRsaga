#!/usr/bin/env python3
"""
05_composite.py
Track B — Composite background + shadow + car beauty pass into final image.
Uses OpenCV for fast, debuggable alpha blending with scale, vertical alignment,
color temperature matching, contact shadows, and edge feathering.
"""

import os
import sys
import argparse
import cv2
import numpy as np
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, "..")

CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
BG_DIR = os.path.join(ROOT_DIR, "outputs", "backgrounds")
CAR_DIR = os.path.join(ROOT_DIR, "outputs", "car_passes")
OUT_DIR = os.path.join(ROOT_DIR, "outputs", "final")

SCALE_FACTORS = {
    "urban_street": 0.55,
    "forest":       0.55,
    "desert":       0.55,
    "racetrack":    0.55,
    "showroom":     0.65,
}

ROAD_MARGIN_PX = {
    "urban_street": 40,
    "forest":       60,
    "desert":       50,
    "racetrack":    45,
    "showroom":     80,
}

# The relative wheel positions in the car's bounding box [x_pct, y_pct]
# Assumes a 3/4 camera view where front and rear wheels are visible near the bottom.
WHEEL_PCTS = [
    (0.25, 0.92),  # rear wheel
    (0.75, 0.95),  # front wheel
]

def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)

def match_exposure(car_rgb, car_alpha, bg):
    """Nudge car brightness/contrast toward the background's overall tone."""
    car_pixels = car_rgb[car_alpha > 10]
    if car_pixels.size == 0:
        return car_rgb
    car_mean = car_pixels.mean()
    bg_mean = bg.mean()
    correction = 1.0 + 0.3 * ((bg_mean - car_mean) / 255.0)
    corrected = np.clip(car_rgb.astype(np.float32) * correction, 0, 255).astype(np.uint8)
    return corrected

def match_color_temperature(car_rgb, car_alpha, bg, strength=0.35):
    """Shift car's color balance toward the background's dominant hue."""
    mask = car_alpha > 10
    car_mean = car_rgb[mask].mean(axis=0)  # BGR
    bg_mean = bg.reshape(-1, 3).mean(axis=0)  # BGR

    shift = (bg_mean - car_mean) * strength
    corrected = np.clip(car_rgb.astype(np.float32) + shift, 0, 255).astype(np.uint8)
    return corrected

def add_contact_shadow(canvas, wheel_positions, radius=25, darkness=0.4):
    # Create an empty mask for the contact shadows
    shadow_mask = np.zeros(canvas.shape[:2], dtype=np.float32)
    for (x, y) in wheel_positions:
        cv2.ellipse(shadow_mask, (x, y), (radius, radius//3), 0, 0, 360, 1.0, -1)
    
    # Blur the mask significantly to create soft ambient occlusion
    shadow_mask = cv2.GaussianBlur(shadow_mask, (51, 51), 0)
    
    # Darken the original canvas where the shadow mask is active
    result = canvas.astype(np.float32)
    for c in range(3):
        result[:, :, c] *= (1.0 - (shadow_mask * darkness))
        
    return np.clip(result, 0, 255).astype(np.uint8)

def composite(env_name: str):
    bg_path = os.path.join(BG_DIR, f"{env_name}.png")
    shadow_path = os.path.join(CAR_DIR, f"shadow_{env_name}.png")
    car_path = os.path.join(CAR_DIR, f"beauty_{env_name}.png")
    out_path = os.path.join(OUT_DIR, f"{env_name}.png")

    bg = cv2.imread(bg_path)
    shadow = cv2.imread(shadow_path, cv2.IMREAD_UNCHANGED)
    car = cv2.imread(car_path, cv2.IMREAD_UNCHANGED)

    assert bg is not None, f"missing background for {env_name}"
    assert shadow is not None and shadow.shape[2] == 4, f"{env_name}: shadow pass missing alpha"
    assert car is not None and car.shape[2] == 4, f"{env_name}: beauty pass missing alpha"

    h, w = bg.shape[:2]
    scale = SCALE_FACTORS.get(env_name, 0.55)
    margin = ROAD_MARGIN_PX.get(env_name, 50)

    # --- scale car + shadow together ---
    orig_h_s, orig_w_s = shadow.shape[:2]
    new_w_s, new_h_s = int(orig_w_s * scale), int(orig_h_s * scale)
    shadow_scaled = cv2.resize(shadow, (new_w_s, new_h_s), interpolation=cv2.INTER_AREA)

    orig_h_c, orig_w_c = car.shape[:2]
    new_w_c, new_h_c = int(orig_w_c * scale), int(orig_h_c * scale)
    car_scaled = cv2.resize(car, (new_w_c, new_h_c), interpolation=cv2.INTER_AREA)

    new_h, new_w = car_scaled.shape[:2]

    # --- paste onto full-size transparent canvases ---
    def place_on_canvas(layer):
        canvas = np.zeros((h, w, 4), dtype=np.uint8)
        x_off = (w - new_w) // 2
        y_off = h - new_h - margin
        y_off = max(0, y_off)
        x_off = max(0, x_off)
        y_end = min(h, y_off + new_h)
        x_end = min(w, x_off + new_w)
        canvas[y_off:y_end, x_off:x_end] = layer[:y_end - y_off, :x_end - x_off]
        return canvas, x_off, y_off

    shadow_full, s_x, s_y = place_on_canvas(shadow_scaled)
    car_full, c_x, c_y = place_on_canvas(car_scaled)

    result = bg.copy().astype(np.float32)

    # --- contact shadows ---
    wheel_coords = [
        (c_x + int(new_w * px), c_y + int(new_h * py))
        for px, py in WHEEL_PCTS
    ]
    contact_radius = int(new_w * 0.18)
    
    # We apply contact shadow directly to the background
    result_uint8 = result.astype(np.uint8)
    result_with_contact = add_contact_shadow(result_uint8, wheel_coords, radius=contact_radius, darkness=0.5)
    result = result_with_contact.astype(np.float32)

    # --- multiply-blend real shadow pass ---
    shadow_alpha = shadow_full[:, :, 3] / 255.0
    for c in range(3):
        result[:, :, c] = (
            result[:, :, c] * (1 - shadow_alpha)
            + result[:, :, c] * (shadow_full[:, :, c] / 255.0) * shadow_alpha
        )

    # --- exposure and color temperature match ---
    car_rgb = car_full[:, :, :3]
    car_alpha_arr = car_full[:, :, 3]
    
    car_rgb = match_exposure(car_rgb, car_alpha_arr, bg)
    car_rgb = match_color_temperature(car_rgb, car_alpha_arr, bg, strength=0.35)

    # --- edge feathering ---
    car_alpha_arr = cv2.GaussianBlur(car_alpha_arr.astype(np.float32), (3, 3), 0).astype(np.uint8)
    car_alpha = car_alpha_arr / 255.0

    # --- alpha-over car ---
    for c in range(3):
        result[:, :, c] = result[:, :, c] * (1 - car_alpha) + car_rgb[:, :, c] * car_alpha

    result = np.clip(result, 0, 255).astype(np.uint8)
    cv2.imwrite(out_path, result)
    print(f"  composited {env_name}: scale={scale}, margin={margin}px -> {out_path}")

def main():
    parser = argparse.ArgumentParser(description="Composite final images")
    parser.add_argument("--env", help="Composite only one environment")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    cfg = load_config()

    if args.env:
        print(f"Compositing: {args.env}")
        composite(args.env)
    else:
        print("Compositing all environments...")
        for env in cfg["environments"]:
            name = env["name"]
            print(f"[COMP] {name}")
            try:
                composite(name)
            except Exception as e:
                print(f"  ERROR: {e}")

    print(f"\nDone. Finals in {OUT_DIR}")

if __name__ == "__main__":
    main()
