# PS1 — Automotive Scene Generation Pipeline
## Implementation Plan v2 — Car-Independent Start

This version reorders the original plan so you can start immediately without a car model in hand. Everything in **Track A** has zero dependency on the car and front-loads the two riskiest/API-dependent steps. **Track B** slots in once the car model is available — by then your backgrounds and lighting data are already sitting in Drive, ready to consume.

---

## 0. Architecture Overview

```
 TRACK A (no car needed — do first)         TRACK B (needs car — do when available)
 ┌──────────────────────────┐               ┌──────────────────────────┐
 │ OpenRouter API             │               │ Car GLB (Sketchfab/       │
 │ (local machine)            │               │ Poly Haven)                │
 └────────────┬───────────────┘               └────────────┬───────────────┘
              │ Seedream 4.5 / FLUX                        │
              ▼                                             ▼
 ┌──────────────────────────┐               ┌──────────────────────────┐
 │ 5 background images        │               │ Blender (bpy) studio rig  │
 │ outputs/backgrounds/       │               │ fixed camera, shadow      │
 └────────────┬───────────────┘               │ catcher, neutral world    │
              │                                └────────────┬───────────────┘
              ▼                                             │ beauty / shadow
 ┌──────────────────────────┐                              │ passes (neutral)
 │ DiffusionLight-Turbo        │                              │
 │ (Colab GPU) or OpenCV       │                              │
 │ fallback → env maps         │                              │
 │ outputs/envmaps/            │                              │
 └────────────┬───────────────┘                              │
              │                                               │
              └───────────────────┬───────────────────────────┘
                                  ▼
                     ┌──────────────────────────┐
                     │ Blender re-render:          │
                     │ car + shadow catcher lit     │
                     │ by each env map              │
                     └────────────┬───────────────┘
                                  ▼
                     ┌──────────────────────────┐
                     │ Composite (OpenCV)          │
                     │ bg → shadow → car            │
                     └────────────┬───────────────┘
                                  ▼
                        5 final images + demo + README
```

**Cost surface unchanged:** only background generation costs anything (~$0.20–1.00 via OpenRouter).

---

## Track A — start now, no car required

### A0. Scaffold the repo (15 min)

```bash
mkdir -p ps1-car-pipeline/{assets,scripts,notebooks,outputs/{car_passes,backgrounds,envmaps,final,demo},docs}
cd ps1-car-pipeline && git init
```

Directory layout for reference:

```
ps1-car-pipeline/
├── README.md
├── requirements.txt
├── config.yaml
├── assets/                 # car.glb goes here later
├── scripts/
│   ├── 01_studio_rig.py         # needs car — Track B
│   ├── 02_generate_backgrounds.py   # Track A, run now
│   ├── 03_lighting_estimation.py    # Track A, run now
│   ├── 04_relight_render.py     # needs car — Track B
│   ├── 05_composite.py          # needs car — Track B
│   └── run_pipeline.py
├── notebooks/
│   └── colab_pipeline.ipynb
├── outputs/
│   ├── car_passes/
│   ├── backgrounds/         # fills up in Track A
│   ├── envmaps/             # fills up in Track A
│   ├── final/
│   └── demo/
└── docs/
    └── architecture.png
```

### A1. Write `config.yaml` now (30 min)

Everything except `bounding_box` can be filled in without the car:

```yaml
car:
  path: "assets/car.glb"        # placeholder — fill path once car is chosen
  bounding_box: null            # TODO once car is imported (Track B, step B1)

camera:
  height_m: 1.2
  distance_m: 6.0
  fov_deg: 40

environments:
  - name: urban_street
    prompt: "empty urban city street, asphalt road, buildings lining both sides, midday overcast light, wide angle, photographed at 1.2m camera height, no cars, no people, clean composition for product placement"
  - name: forest
    prompt: "forest dirt road clearing, tall pine trees, dappled sunlight through canopy, golden hour, photographed at 1.2m camera height, no vehicles, clean composition"
  - name: desert
    prompt: "desert highway, sand dunes, clear blue sky, harsh midday sun, long shadows, photographed at 1.2m camera height, empty road, clean composition"
  - name: racetrack
    prompt: "asphalt racetrack straight, grandstands blurred in background, overcast diffuse light, photographed at 1.2m camera height, no vehicles on track, clean composition"
  - name: showroom
    prompt: "minimalist car showroom interior, polished concrete floor, soft studio lighting from above, white walls, photographed at 1.2m camera height, empty floor space, clean composition"
```

The repeated "photographed at 1.2m camera height... clean composition" phrasing keeps the horizon line consistent across all 5 generations — that consistency is what makes the eventual car placement look plausible, so don't drop it even though the car isn't here yet.

### A2. Background generation — OpenRouter (Hr 0–1, runs locally, no GPU)

`scripts/02_generate_backgrounds.py`:

```python
import requests, yaml, os, base64

API_KEY = os.environ["OPENROUTER_API_KEY"]
cfg = yaml.safe_load(open("config.yaml"))

def generate_image(prompt, out_path):
    resp = requests.post(
        "https://openrouter.ai/api/v1/images",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": "bytedance-seed/seedream-4.5",  # or a FLUX variant
            "prompt": prompt,
            "size": "1344x768"
        }
    )
    resp.raise_for_status()
    data = resp.json()
    img_b64 = data["data"][0]["b64_json"]  # verify exact field name in playground first
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(img_b64))

for env in cfg["environments"]:
    out = f"outputs/backgrounds/{env['name']}.png"
    generate_image(env["prompt"], out)
    print(f"saved {out}")
```

**Before batching all 5:** test one prompt (`urban_street`) in the OpenRouter playground first. Confirm the response JSON shape (`b64_json` vs a hosted `url` field varies by provider) and that the horizon/camera-height reads consistently — adjust prompt language now if it looks drone-shot or ground-level, since fixing this after all 5 are generated means redoing all 5.

**Checkpoint:** 5 PNGs in `outputs/backgrounds/`, all sharing a similar horizon line and empty foreground (no stray cars/people the generator slipped in).

### A3. Lighting estimation — DiffusionLight-Turbo on Colab (Hr 1–2.5)

This is your highest-risk step — doing it now, decoupled from the car, means you find out today whether you need the fallback, not later when you're also blocked on a missing asset.

**Hard stop rule: 1.5 hours max. If not producing usable env maps by then, switch to the OpenCV fallback below and move on — do not keep debugging.**

Colab notebook:

```python
# Cell 1 — mount Drive, install
from google.colab import drive
drive.mount('/content/drive')

!git clone https://github.com/DiffusionLight/DiffusionLight-Turbo
%cd DiffusionLight-Turbo
!pip install -r requirements.txt -q
```

```python
# Cell 2 — upload backgrounds to Drive first (from local machine),
# then run inference over all 5
import glob, subprocess

bg_dir = "/content/drive/MyDrive/ps1-car-pipeline/outputs/backgrounds"
out_dir = "/content/drive/MyDrive/ps1-car-pipeline/outputs/envmaps"

for bg_path in glob.glob(f"{bg_dir}/*.png"):
    # follow DiffusionLight-Turbo's documented inference call —
    # verify exact CLI/Python API against their README, this is illustrative
    subprocess.run(["python", "inference.py", "--input", bg_path, "--output_dir", out_dir])
```

Save everything to Drive (`/content/drive/MyDrive/...`), not Colab's local disk — local disk is wiped on runtime recycle, and free-tier sessions can disconnect without warning.

**Fallback (OpenCV heuristic):**

```python
import cv2, numpy as np

def estimate_light_direction(bg_path):
    img = cv2.imread(bg_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (51,51), 0)
    _, maxVal, _, maxLoc = cv2.minMaxLoc(blurred)
    h, w = gray.shape
    azimuth = (maxLoc[0]/w - 0.5) * 180
    elevation = max(10, 90 - (maxLoc[1]/h) * 90)
    ambient_color = cv2.mean(img)[:3]  # BGR average as ambient tint
    return azimuth, elevation, ambient_color
```

Save the azimuth/elevation/ambient_color per environment (e.g. to a small JSON in `outputs/envmaps/fallback_lighting.json`) — Track B's relight step reads from this instead of an env map if you land here.

**Checkpoint (end of Track A):** `outputs/backgrounds/` has 5 images, `outputs/envmaps/` has 5 env maps (or the fallback JSON). Everything downstream is now just waiting on the car.

### A4. Write README skeleton + architecture doc (whenever you have downtime)

Draft the structure now so you're not starting from a blank page later:
1. Architecture diagram (export the one above as `docs/architecture.png`)
2. Pipeline stages, one paragraph each
3. Explicit constraints honored (car untouched, background 100% GenAI, lighting adapts per-scene)
4. Known limitations
5. Cost/infra summary table
6. How to run it

---

## Track B — once you have the car model

### B1. Import + sanity render (30–45 min)

1. Place GLB at `assets/car.glb`.
2. Import into Blender, check for missing textures / broken normals. Fix only import errors — never redesign.
3. Fill in `bounding_box` in `config.yaml`.
4. Quick default-lit render to confirm the model isn't broken.

### B2. Studio rig script (45–60 min)

`scripts/01_studio_rig.py` — fixed camera per `config.yaml`, shadow-catcher ground plane, neutral gray world, film-transparent render. Output `beauty_<env>.png` and `shadow_<env>.png` per environment (5x each) into `outputs/car_passes/`.

```python
import bpy, yaml

def setup_scene(car_path, cam_height, cam_distance, fov_deg):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=car_path)

    car_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    # compute bounding box center across all car meshes
    ...

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens_unit = 'FOV'
    cam_data.angle = fov_deg * 3.14159/180
    cam_obj = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = (0, -cam_distance, cam_height)

    # aim camera at car center (assumes car center ~ world origin at ground level)
    target = mathutils.Vector((0, 0, cam_height * 0.4))  # rough mid-car height, adjust once bbox is known
    direction = target - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    bpy.context.scene.camera = cam_obj

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0))
    plane = bpy.context.active_object
    plane.is_shadow_catcher = True

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'

    return car_objs, plane
```

**Checkpoint:** clean cutout, plausible shadow, no clipping in the sanity render.

### B3. Re-render under Track A's lighting (45–60 min)

`scripts/04_relight_render.py` — load each env map (or fallback azimuth/elevation/ambient) into the World shader, re-render `beauty_<env>.png` / `shadow_<env>.png` per environment.

```python
def set_env_lighting(envmap_path=None, sun_azimuth=None, sun_elevation=None, ambient_color=None):
    world = bpy.data.worlds.new("EnvWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes["Background"]

    if envmap_path:
        env_tex = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
        env_tex.image = bpy.data.images.load(envmap_path)
        world.node_tree.links.new(env_tex.outputs["Color"], bg_node.inputs["Color"])
    else:
        bg_node.inputs["Color"].default_value = (*[c/255 for c in ambient_color], 1.0)
        bpy.ops.object.light_add(type='SUN')
        sun = bpy.context.active_object
        import math
        sun.rotation_euler = (math.radians(sun_elevation), 0, math.radians(sun_azimuth))
```

### B4. Composite & Post-Processing (45 min)

`scripts/05_composite.py`:
Composites the generated background, the shadow pass, and the car beauty pass using OpenCV. We also add soft, Gaussian-blurred contact shadows under the wheels to ground the car better.

`scripts/06_polish.py`:
Applies an unsharp mask and contrast/saturation grade via FFmpeg to the final composites to unify the look.

`scripts/07_contact_sheet.py`:
Generates a side-by-side comparison grid (e.g., of the raw beauty passes or final images) for easy review.

`scripts/08_last_polish.py`:
A final ambient reflection approximation pass that blends a heavily blurred version of the composite back onto the car's alpha region at low opacity. This helps the car pick up ambient colors from the environment.

Visual QA: check for hard/aliased edges (feather alpha with a 1–2px Gaussian blur if needed), confirm shadow direction roughly agrees with each background's implied light source, and ensure contact shadows aren't too harsh.

### B5. Orchestration, demo, final README (60–90 min)

- `scripts/run_pipeline.py` ties everything together — be explicit in the README that Track A steps ran ahead of time / straddle local + Colab, that's a legitimate architecture choice.
- Screen-record 60–90 sec showing the pipeline running and the 5 final images.
- Finish the README using the A4 skeleton, filling in specifics now that the full run is complete.

---

## Submission checklist

- [x] Working pipeline code (`scripts/`, `notebooks/colab_pipeline.ipynb`)
- [ ] README with architecture explanation
- [ ] Demo video (60–90 sec)
- [x] 5 sample outputs in `outputs/final/` and `outputs/final_polished/`
- [x] `config.yaml` committed
- [x] Sanity-check render + car reference image included for visual consistency proof
- [x] Fallback documented explicitly if OpenCV heuristic was used instead of DiffusionLight

## Hard stop rules

| Checkpoint | Rule |
|---|---|
| Track A, background gen | One prompt validated in playground before batching all 5 |
| Track A, lighting estimation | 1.5 hrs max on DiffusionLight → OpenCV fallback, no further debugging |
| Track B, car import | Import fails or looks broken → swap car model, don't debug a broken asset |
| Track B, composite | All 5 visually acceptable → move to demo/README, stop polishing pixels |