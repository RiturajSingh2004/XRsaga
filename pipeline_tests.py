"""
pipeline_tests.py -- run before B5 (orchestration/demo/README)
Checks B1 (car import) -> B2 (studio rig) -> B3 (relight render) -> B4 (composite)
"""

import os
import sys
import glob
import math
import cv2
import numpy as np
import yaml
from PIL import Image

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ENVIRONMENTS = ["urban_street", "forest", "desert", "racetrack", "showroom"]
FAILURES = []

def fail(msg):
    FAILURES.append(msg)
    print(f"  [FAIL] {msg}")

def ok(msg):
    print(f"  [OK]   {msg}")


# ── B1: Car import / config ─────────────────────────────────────
print("\n=== B1: Car asset + config ===")

if not os.path.exists("config.yaml"):
    fail("config.yaml missing")
else:
    cfg = yaml.safe_load(open("config.yaml"))
    car_path = cfg.get("car", {}).get("path")
    if not car_path or not os.path.exists(car_path):
        fail(f"car.path in config.yaml points to missing file: {car_path}")
    else:
        ok(f"car asset found at {car_path}")

    bbox = cfg.get("car", {}).get("bounding_box")
    if bbox is None:
        fail("car.bounding_box still null in config.yaml — needed for accurate camera aim (B2 fix)")
    else:
        ok("bounding_box is set")

    cam = cfg.get("camera", {})
    if not cam:
        fail("camera block missing from config.yaml")
    else:
        ok(f"camera config: height={cam.get('height_m')}, distance={cam.get('distance_m')}, fov={cam.get('fov_deg')}")

    envs_in_cfg = [e["name"] for e in cfg.get("environments", [])]
    missing_envs = set(ENVIRONMENTS) - set(envs_in_cfg)
    if missing_envs:
        fail(f"environments missing from config.yaml: {missing_envs}")
    else:
        ok("all 5 environments present in config.yaml")


# ── B2: Studio rig — neutral passes ─────────────────────────────
print("\n=== B2: Studio rig (neutral beauty/shadow) ===")

studio_beauty = glob.glob("outputs/car_passes/beauty_neutral.png")
studio_shadow = glob.glob("outputs/car_passes/shadow_neutral.png")

if not studio_beauty:
    fail("no neutral studio beauty pass found -- check B2 output path")
else:
    ok(f"found neutral beauty pass: {studio_beauty[0]}")
if not studio_shadow:
    fail("no neutral studio shadow pass found -- check B2 output path")
else:
    ok(f"found neutral shadow pass: {studio_shadow[0]}")


# ── B3: Relight renders — alpha, per-env presence, distinctness ─
print("\n=== B3: Relight renders (per environment) ===")

beauty_imgs = {}

for env in ENVIRONMENTS:
    beauty_path = f"outputs/car_passes/beauty_{env}.png"
    shadow_path = f"outputs/car_passes/shadow_{env}.png"

    if not os.path.exists(beauty_path):
        fail(f"{env}: missing beauty_{env}.png")
        continue
    if not os.path.exists(shadow_path):
        fail(f"{env}: missing shadow_{env}.png")

    img = Image.open(beauty_path)
    if img.mode != "RGBA":
        fail(f"{env}: beauty pass has no alpha channel (mode={img.mode})")
        continue

    w, h = img.size
    corners = [(0,0), (w-1,0), (0,h-1), (w-1,h-1)]
    corner_alphas = [img.getpixel(xy)[3] for xy in corners]
    if any(a != 0 for a in corner_alphas):
        fail(f"{env}: background not fully transparent, corner alphas={corner_alphas}")
    else:
        ok(f"{env}: transparent background confirmed")

    cx, cy = w//2, h//2
    center_alpha = img.getpixel((cx, cy))[3]
    if center_alpha == 0:
        fail(f"{env}: center pixel (car body) has zero alpha — car may not have rendered")

    beauty_imgs[env] = np.array(img.convert("RGB"))

# cross-environment distinctness check — catches "rotation didn't apply" bug
print("\n  -- distinctness check (catches silently-identical relights) --")
envs_with_imgs = list(beauty_imgs.keys())
for i in range(len(envs_with_imgs)):
    for j in range(i+1, len(envs_with_imgs)):
        a, b = envs_with_imgs[i], envs_with_imgs[j]
        if beauty_imgs[a].shape != beauty_imgs[b].shape:
            continue
        diff = np.mean(np.abs(beauty_imgs[a].astype(int) - beauty_imgs[b].astype(int)))
        if diff < 1.0:
            fail(f"{a} vs {b}: near-identical pixels (mean diff={diff:.3f}) — lighting likely not applied, check radians conversion")
        else:
            ok(f"{a} vs {b}: distinct (mean diff={diff:.2f})")


# ── B4: Composite outputs ───────────────────────────────────────
print("\n=== B4: Final composites ===")

for env in ENVIRONMENTS:
    bg_path = f"outputs/backgrounds/{env}.png"
    final_path = f"outputs/final/{env}.png"

    if not os.path.exists(bg_path):
        fail(f"{env}: missing source background at {bg_path}")
    if not os.path.exists(final_path):
        fail(f"{env}: missing final composite at {final_path}")
        continue

    final = cv2.imread(final_path)
    if final is None:
        fail(f"{env}: final composite failed to load/decode")
        continue

    bg = cv2.imread(bg_path)
    if bg is not None and final.shape[:2] != bg.shape[:2]:
        fail(f"{env}: final composite resolution {final.shape[:2]} != background resolution {bg.shape[:2]}")

    # edge-hardness spot check: sample alpha gradient isn't relevant post-flatten,
    # so instead check for obvious white/magenta artifact pixels (common compositing bugs)
    flat = final.reshape(-1, 3)
    pure_white = np.sum(np.all(flat > 250, axis=1))
    pure_magenta = np.sum((flat[:,2] > 200) & (flat[:,1] < 50) & (flat[:,0] > 200))
    if pure_magenta > 50:
        fail(f"{env}: {pure_magenta} near-pure-magenta pixels found — possible missing texture artifact")
    if pure_white > (flat.shape[0] * 0.3):
        print(f"  ⚠ {env}: {pure_white} near-pure-white pixels ({100*pure_white/flat.shape[0]:.1f}% of image) — verify this is expected (e.g. showroom scene) not a compositing bug")

    ok(f"{env}: composite loads and dimensions match")


# ── Summary ──────────────────────────────────────────────────────
print("\n" + "="*50)
if FAILURES:
    print(f"[FAIL] {len(FAILURES)} FAILURE(S) -- fix before B5:")
    for f in FAILURES:
        print(f"   - {f}")
else:
    print("[OK] ALL CHECKS PASSED -- safe to proceed to B5 (orchestration/demo/README)")
