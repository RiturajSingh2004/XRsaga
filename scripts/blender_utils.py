#!/usr/bin/env python3
"""
blender_utils.py
Shared Blender/Cycles utility functions used by 01_studio_rig.py and 04_relight_render.py.
Eliminates duplication of scene setup, car import, camera, shadow catcher, and render config.
"""

import os
import math
import bpy
import mathutils


def clear_scene():
    """Reset Blender to a clean, empty state."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_car(car_path: str):
    """Import a glTF/GLB car model. Returns list of mesh objects.

    Raises FileNotFoundError if car_path does not exist.
    Raises RuntimeError if no mesh objects are found after import.
    """
    if not os.path.exists(car_path):
        raise FileNotFoundError(f"Car not found: {car_path}")
    bpy.ops.import_scene.gltf(filepath=car_path)
    car_objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not car_objs:
        raise RuntimeError("No mesh objects found after import")
    return car_objs


def get_bounding_box(objects):
    """Compute world-space bounding box across all mesh objects.

    Returns:
        tuple: (center, min_corner, max_corner) — each a list of 3 floats.
    """
    min_c = [float("inf")] * 3
    max_c = [float("-inf")] * 3
    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                min_c[i] = min(min_c[i], world_corner[i])
                max_c[i] = max(max_c[i], world_corner[i])
    center = [(min_c[i] + max_c[i]) / 2.0 for i in range(3)]
    return center, [float(v) for v in min_c], [float(v) for v in max_c]


def setup_camera(center, height_m, distance_m, fov_deg):
    """Create and position a fixed camera aimed at the car center.

    Camera is placed in front of the car (negative Y) at the specified
    height offset from the car center, looking toward the center.
    """
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens_unit = "FOV"
    cam_data.angle = math.radians(fov_deg)
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)

    cam_obj.location = (center[0], center[1] - distance_m, center[2] + height_m)
    direction = mathutils.Vector(center) - cam_obj.location
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam_obj.rotation_euler = rot_quat.to_euler()

    bpy.context.scene.camera = cam_obj
    return cam_obj


def setup_shadow_catcher(size=30):
    """Add a ground plane configured as a Cycles shadow catcher.

    Returns the plane object so callers can toggle hide_render for
    separate beauty / shadow passes.
    """
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = "ShadowCatcher"
    plane.is_shadow_catcher = True
    return plane


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
        bg_node.inputs["Strength"].default_value = 1.0 * intensity_scale
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


def setup_render_settings(samples=128):
    """Configure Cycles with transparent film, RGBA output, and GPU if available."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    # Use GPU if available, else CPU
    prefs = bpy.context.preferences
    cprefs = prefs.addons["cycles"].preferences
    cprefs.get_devices()
    found_gpu = False
    for d in cprefs.devices:
        if d.type in {"CUDA", "OPTIX", "HIP", "ONEAPI", "METAL"}:
            d.use = True
            found_gpu = True
        else:
            d.use = False
    if found_gpu:
        scene.cycles.device = "GPU"
        print("Using GPU rendering")
    else:
        scene.cycles.device = "CPU"
        print("Using CPU rendering")

    scene.cycles.samples = samples


def render_pass(out_path: str, shadow_catcher=None):
    """Render current scene and save to disk.

    Re-applies film_transparent, PNG/RGBA, and shadow catcher flag fresh
    before every render — these settings can be lost when set_env_lighting()
    or clear_scene() recreate World/scene objects between iterations.
    """
    scene = bpy.context.scene
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    if shadow_catcher is not None:
        shadow_catcher.is_shadow_catcher = True

    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print(f"  Rendered -> {out_path}")


def render_beauty_and_shadow(car_objs, shadow_catcher, beauty_path, shadow_path):
    """Render separate beauty (car-only) and shadow (shadow-only) passes.

    Beauty pass:  shadow catcher hidden -> pure car cutout on transparent bg.
    Shadow pass:  shadow catcher visible, car hidden from camera but still
                  casts shadows via ray visibility -> pure shadow on transparent bg.
    """
    # --- Beauty pass: hide shadow catcher so we get a clean car cutout ---
    shadow_catcher.hide_render = True
    render_pass(beauty_path, shadow_catcher=shadow_catcher)

    # --- Shadow pass: show shadow catcher, hide car from camera only ---
    # visible_camera=False keeps the car invisible to camera rays but
    # visible_shadow remains True (default), so the car still casts shadows.
    shadow_catcher.hide_render = False
    for obj in car_objs:
        obj.visible_camera = False
    render_pass(shadow_path, shadow_catcher=shadow_catcher)

    # --- Restore visibility for next iteration ---
    for obj in car_objs:
        obj.visible_camera = True
