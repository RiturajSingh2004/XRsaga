#!/usr/bin/env python3
"""
run_pipeline.py
Orchestrates the full PS1 pipeline.
Track A (car-independent) can run immediately.
Track B (car-dependent) runs once assets/car.glb is present.
"""

import os
import sys
import subprocess
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, "..")


def run_python_script(script_name: str, *args):
    script_path = os.path.join(ROOT_DIR, "scripts", script_name)
    cmd = [sys.executable, script_path] + list(args)
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT_DIR)
    return result.returncode == 0


def run_blender_script(script_name: str):
    script_path = os.path.join(ROOT_DIR, "scripts", script_name)
    # Try to find blender
    blender_cmd = None
    windows_path = r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
    for cmd in ["blender", "blender3.6", "blender3.10", windows_path]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True)
            blender_cmd = cmd
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    if not blender_cmd:
        print("ERROR: Blender not found in PATH. Install Blender or adjust PATH.")
        return False

    cmd = [blender_cmd, "--background", "--python", script_path]
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT_DIR)
    return result.returncode == 0


def track_a():
    print("=" * 60)
    print("TRACK A: Background Generation + Lighting Estimation")
    print("=" * 60)

    # Step A2: Generate backgrounds
    if not run_python_script("02_generate_backgrounds.py"):
        print("Background generation failed")
        return False

    # Step A3: Lighting estimation (OpenCV fallback by default)
    if not run_python_script("03_lighting_estimation.py", "--mode", "opencv"):
        print("Lighting estimation failed")
        return False

    print("\nTrack A complete.")
    return True


def track_b():
    print("=" * 60)
    print("TRACK B: Car Render + Relight + Composite + Polish")
    print("=" * 60)

    import yaml
    try:
        cfg = yaml.safe_load(open(os.path.join(ROOT_DIR, "config.yaml")))
        car_path_rel = cfg.get("car", {}).get("path", "assets/car.glb")
    except Exception:
        car_path_rel = "assets/car.glb"
        
    car_path = os.path.join(ROOT_DIR, car_path_rel)
    if not os.path.exists(car_path):
        print(f"Car not found at {car_path}")
        print("Place your car GLB and update config.yaml, then re-run Track B.")
        return False

    # Step B1/B2: Studio rig (neutral sanity render)
    print("\n--- Studio Rig (neutral) ---")
    if not run_blender_script("01_studio_rig.py"):
        print("Studio rig failed")
        return False

    # Step B3: Relight under env maps
    print("\n--- Relight Render ---")
    if not run_blender_script("04_relight_render.py"):
        print("Relight render failed")
        return False

    # Step B4: Composite
    print("\n--- Composite ---")
    if not run_python_script("05_composite.py"):
        print("Compositing failed")
        return False
        
    print("\n--- Post-Processing (Polish 1) ---")
    if not run_python_script("06_polish.py"):
        print("Polish 1 failed")
        return False
        
    print("\n--- Final Blending (Polish 2) ---")
    if not run_python_script("08_last_polish.py"):
        print("Polish 2 failed")
        return False

    print("\n--- Contact Sheet Generation ---")
    run_python_script("07_contact_sheet.py")

    print("\nTrack B complete.")
    return True


def main():
    parser = argparse.ArgumentParser(description="PS1 Automotive Scene Generation Pipeline")
    parser.add_argument(
        "--track",
        choices=["a", "b", "all"],
        default="all",
        help="Run Track A (backgrounds+lighting), Track B (car+composite), or all",
    )
    args = parser.parse_args()

    ok = True

    if args.track in ("a", "all"):
        a_ok = track_a()
        ok = ok and a_ok

    if args.track in ("b", "all"):
        if args.track == "all" and not ok:
            print("\nTrack A failed — skipping Track B (it depends on Track A outputs).")
            print("Fix Track A issues first, then re-run with --track all or --track b.")
        else:
            b_ok = track_b()
            ok = ok and b_ok

    if ok:
        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(f"Backgrounds: {os.path.join(ROOT_DIR, 'outputs', 'backgrounds')}")
        print(f"Env maps:    {os.path.join(ROOT_DIR, 'outputs', 'envmaps')}")
        print(f"Car passes:  {os.path.join(ROOT_DIR, 'outputs', 'car_passes')}")
        print(f"Final Images:{os.path.join(ROOT_DIR, 'outputs', 'final_polished')}")
        print(f"Contact Shts:{os.path.join(ROOT_DIR, 'outputs', 'beauty_contact_sheet.png')}")
    else:
        print("\nPipeline finished with errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
