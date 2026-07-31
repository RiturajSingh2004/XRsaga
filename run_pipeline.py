#!/usr/bin/env python3
"""
run_pipeline.py
Top-level orchestration script for the PS1 Car Pipeline.
Runs stages 01 through 05 sequentially.
"""

import os
import sys
import subprocess
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = [
    ("scripts/01_studio_rig.py", "Blender Studio Rig (Neutral Passes)", True),
    ("scripts/02_generate_backgrounds.py", "Generate Backgrounds", False),
    ("scripts/03_lighting_estimation.py", "Estimate Lighting", False),
    ("scripts/04_relight_render.py", "Blender Relight Render", True),
    ("scripts/05_composite.py", "Composite Finals", False),
]

def load_config():
    cfg_path = os.path.join(SCRIPT_DIR, "config.yaml")
    if not os.path.exists(cfg_path):
        print("ERROR: config.yaml not found.")
        sys.exit(1)
    with open(cfg_path) as f:
        return yaml.safe_load(f)

def run_script(script_path, description, is_blender, blender_exe=None):
    print(f"\n{'='*50}")
    print(f"🚀 Running: {description}")
    print(f"{'='*50}")

    if is_blender:
        if not blender_exe:
            print("ERROR: blender_exe not provided for a Blender script.")
            sys.exit(1)
        cmd = [blender_exe, "--background", "--python", script_path]
    else:
        cmd = [sys.executable, script_path]

    try:
        subprocess.run(cmd, check=True, cwd=SCRIPT_DIR)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Pipeline failed at: {description}")
        print(f"Error code: {e.returncode}")
        sys.exit(1)

def main():
    cfg = load_config()
    # Expect blender executable path in config, fallback to "blender" in PATH
    blender_exe = cfg.get("blender_exe", "blender")
    
    # We can pass an optional argument to skip steps
    start_step = 1
    if len(sys.argv) > 1:
        try:
            start_step = int(sys.argv[1])
        except ValueError:
            pass

    for i, (script_path, desc, is_blender) in enumerate(SCRIPTS, 1):
        if i < start_step:
            print(f"Skipping Step {i}: {desc}")
            continue
            
        full_path = os.path.join(SCRIPT_DIR, script_path)
        if not os.path.exists(full_path):
            print(f"ERROR: Script not found at {full_path}")
            sys.exit(1)
            
        run_script(script_path, desc, is_blender, blender_exe)

    print("\n" + "="*50)
    print("✅ Pipeline Complete! Check outputs/final/ for the results.")

if __name__ == "__main__":
    main()
