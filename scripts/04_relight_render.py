#!/usr/bin/env python3
"""
04_relight_render.py
Track B — Re-render car under each environment's estimated lighting.
Supports both HDRI env maps and OpenCV fallback (directional sun + ambient).
Run inside Blender:
  blender --background --python scripts/04_relight_render.py
"""

import sys
import os
import math
import json
import yaml
import bpy

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, "..")
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import blender_utils as bu  # noqa: E402 — must come after sys.path setup

CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
ENV_DIR = os.path.join(ROOT_DIR, "outputs", "envmaps")
OUT_DIR = os.path.join(ROOT_DIR, "outputs", "car_passes")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def find_envmap_for(env_name):
    """Look for an HDRI env map matching this environment name.

    Checks .hdr, .exr, .png extensions in order of preference.
    Returns the path if found, else None.
    """
    for ext in (".hdr", ".exr", ".png"):
        path = os.path.join(ENV_DIR, f"{env_name}{ext}")
        if os.path.exists(path):
            return path
    return None


def has_any_envmaps(env_names):
    """Return True if at least one environment has a matching env map file."""
    return any(find_envmap_for(name) is not None for name in env_names)


def set_env_lighting(envmap_path=None, sun_azimuth=None, sun_elevation=None,
                       ambient_color=None, intensity_scale=1.0, max_brightness=None):
    """Configure world lighting from an env map or fallback sun + ambient."""
    world = bpy.data.worlds.new("EnvWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    bg_node = tree.nodes["Background"]

    for link in list(tree.links):
        if link.to_node == bg_node:
            tree.links.remove(link)

    if envmap_path and os.path.exists(envmap_path):
        print(f"  Loading env map: {envmap_path}")
        env_tex = tree.nodes.new("ShaderNodeTexEnvironment")
        env_tex.image = bpy.data.images.load(envmap_path)
        tree.links.new(env_tex.outputs["Color"], bg_node.inputs["Color"])
        bg_node.inputs["Strength"].default_value = 1.0
    else:
        print("  Using fallback directional + ambient lighting")
        brightness_factor = (max_brightness / 255.0) if max_brightness else 0.7

        if ambient_color:
            col = [c / 255.0 for c in ambient_color]
            bg_node.inputs["Color"].default_value = (*col, 1.0)
        else:
            bg_node.inputs["Color"].default_value = (0.5, 0.5, 0.5, 1.0)
        bg_node.inputs["Strength"].default_value = 0.5 * brightness_factor * intensity_scale

        bpy.ops.object.light_add(type="SUN", location=(0, 0, 15))
        sun = bpy.context.active_object
        sun.name = "SunLight"
        sun.rotation_euler = (
            math.radians(sun_elevation or 45),
            0.0,
            math.radians(sun_azimuth or 0),
        )
        sun.data.energy = 5.0 * brightness_factor * intensity_scale


def main():
    cfg = load_config()
    car_path = os.path.join(ROOT_DIR, cfg["car"]["path"])
    cam_cfg = cfg["camera"]
    env_names = [env["name"] for env in cfg["environments"]]

    os.makedirs(OUT_DIR, exist_ok=True)

    # Determine lighting mode: per-environment env maps vs fallback JSON
    use_envmaps = has_any_envmaps(env_names)
    fallback_data = {}
    if not use_envmaps:
        fallback_json = os.path.join(ENV_DIR, "fallback_lighting.json")
        if os.path.exists(fallback_json):
            with open(fallback_json) as f:
                fallback_data = json.load(f)
            print("Using OpenCV fallback lighting data")
        else:
            print("WARNING: No env maps and no fallback_lighting.json found. "
                  "Using default lighting.")

    for env in cfg["environments"]:
        name = env["name"]
        print(f"\n[RELIGHT] {name}")

        # Fresh scene per environment (clean world/lighting state)
        bu.clear_scene()
        car_objs = bu.import_car(car_path)
        center, _, _ = bu.get_bounding_box(car_objs)
        bu.setup_camera(center, cam_cfg["height_m"], cam_cfg["distance_m"], cam_cfg["fov_deg"])
        shadow_catcher = bu.setup_shadow_catcher()
        bu.setup_render_settings(samples=256)

        # Set per-environment lighting
        envmap_path = find_envmap_for(name)
        if use_envmaps and envmap_path:
            set_env_lighting(envmap_path=envmap_path)
        else:
            fb = fallback_data.get(name, {})
            set_env_lighting(
                sun_azimuth=fb.get("azimuth", 45),
                sun_elevation=fb.get("elevation", 45),
                ambient_color=fb.get("ambient_color", [128, 128, 128]),
                max_brightness=fb.get("max_brightness"),
                intensity_scale=2.0,
            )

        # Render separate beauty and shadow passes
        beauty_path = os.path.join(OUT_DIR, f"beauty_{name}.png")
        shadow_path = os.path.join(OUT_DIR, f"shadow_{name}.png")
        bu.render_beauty_and_shadow(car_objs, shadow_catcher, beauty_path, shadow_path)

    print("\nRelight render complete.")


if __name__ == "__main__":
    main()
