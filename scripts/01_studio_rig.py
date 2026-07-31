#!/usr/bin/env python3
"""
01_studio_rig.py
Track B — Import car, set up fixed camera + shadow-catcher ground,
render beauty and shadow passes under neutral lighting.
Run inside Blender:
  blender --background --python scripts/01_studio_rig.py
"""

import sys
import os
import yaml

# Allow importing from project root and scripts dir
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, "..")
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import blender_utils as bu  # noqa: E402 — must come after sys.path setup

CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
OUT_DIR = os.path.join(ROOT_DIR, "outputs", "car_passes")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


def setup_neutral_world():
    """Neutral gray environment for sanity-check renders."""
    import bpy

    world = bpy.data.worlds.new("NeutralWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.8, 0.8, 0.8, 1.0)
    bg.inputs["Strength"].default_value = 1.0


def main():
    cfg = load_config()
    car_cfg = cfg["car"]
    cam_cfg = cfg["camera"]

    os.makedirs(OUT_DIR, exist_ok=True)

    bu.clear_scene()
    car_objs = bu.import_car(os.path.join(ROOT_DIR, car_cfg["path"]))
    center, bbox_min, bbox_max = bu.get_bounding_box(car_objs)

    # Persist computed bounding box to config.yaml for downstream scripts
    car_cfg["bounding_box"] = {
        "center": [float(v) for v in center],
        "min": [float(v) for v in bbox_min],
        "max": [float(v) for v in bbox_max],
    }
    save_config(cfg)
    print(f"Bounding box written to config.yaml: center={center}")

    bu.setup_camera(center, cam_cfg["height_m"], cam_cfg["distance_m"], cam_cfg["fov_deg"])
    shadow_catcher = bu.setup_shadow_catcher()
    setup_neutral_world()
    bu.setup_render_settings(samples=128)

    # Render ONE neutral sanity-check pass — lighting is identical regardless
    # of environment at this stage, so no need to repeat it 5x
    beauty_path = os.path.join(OUT_DIR, "beauty_neutral.png")
    shadow_path = os.path.join(OUT_DIR, "shadow_neutral.png")
    print("\n[RENDER NEUTRAL]")
    bu.render_beauty_and_shadow(car_objs, shadow_catcher, beauty_path, shadow_path)

    print("\nStudio rig complete. Check outputs/car_passes/")


if __name__ == "__main__":
    main()
