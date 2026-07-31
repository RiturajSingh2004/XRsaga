# Architecture Decision Records — PS1 Automotive Scene Generation Pipeline

## Index

| ADR | Title | Status |
|---|---|---|
| [001](#adr-001-real-time-renderer) | Real-time renderer: Blender vs Unreal Engine vs Unity | Accepted |
| [002](#adr-002-background-generation-provider) | Background generation provider | Accepted |
| [003](#adr-003-lighting--environment-estimation-method) | Lighting / environment estimation method | Accepted |
| [004](#adr-004-compute-environment) | Compute environment for GPU-bound steps | Accepted |
| [005](#adr-005-compositing-approach) | Compositing approach | Accepted |
| [006](#adr-006-car-asset-sourcing) | Car asset sourcing strategy | Accepted |
| [007](#adr-007-camera-rig-strategy) | Camera rig: single fixed camera vs multi-angle | Accepted |
| [008](#adr-008-video-generation-models-excluded) | Video generation models excluded from scope | Accepted |
| [009](#adr-009-build-sequencing--car-independent-track-split) | Build sequencing: car-independent track split | Accepted |
| [010](#adr-010-post-processing-and-grading) | Post-processing and Grading Approach | Accepted |

---

## ADR-001: Real-time renderer

**Status:** Accepted

### Context
PS1 requires rendering a fixed, unmodified 3D car model under scene-adaptive lighting, then compositing it into a GenAI background. The core technical requirement is: import a GLB/car asset, apply an environment map or equivalent for lighting, render with physically-plausible reflections, output alpha + shadow passes, and do all of this scriptably/headlessly for automation across 5+ environments within a ~10-hour build budget.

### Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| **Unreal Engine** | Named as preferred in the brief; best-in-class real-time PBR/reflections, Lumen GI, strong material fidelity | Steep setup time for headless/scripted batch rendering; Python scripting (unreal module) is less mature for this kind of pass-based automation; heavier install footprint; slower to iterate under a 10-hr constraint |
| **Unity** | Named as acceptable; HDRP gives strong PBR/reflections; C# scripting is capable | Same headless-automation friction as Unreal; asset import pipeline for arbitrary GLBs is less turnkey than Blender's; no meaningful compute-cost advantage over Blender |
| **Blender (Cycles), scripted via bpy** | Free, fully scriptable headless via `blender --background --python`, native glTF import, per-object Shadow Catcher is a single toggle, Cycles is a physically-based path tracer (accurate reflections/GI out of the box), runs identically on Colab or local — no licensing friction | Not "real-time" in the strict game-engine sense (Cycles is offline path tracing); the brief's "real-time renderer preferred" framing slightly favors UE/Unity |

### Decision
Use **Blender + Cycles, driven entirely through `bpy` scripts**, run headlessly both locally and on Colab.

### Rationale
The brief's actual judging criteria are reflection accuracy, vehicle consistency, visual fidelity, GenAI integration quality, and pipeline automation — not real-time frame rates. Cycles is a physically-based path tracer, so reflection/GI accuracy is not a compromise versus UE/Unity; if anything it's more directly correct since it doesn't rely on real-time approximations (screen-space reflections, Lumen's probe-based GI). What UE/Unity offer that Blender doesn't is real-time interactivity, which this pipeline doesn't need — every output here is a scripted, non-interactive batch render. Blender's `bpy` scripting is also the fastest path to a fully automated, headless, Colab-compatible pipeline within a 10-hour budget, which is explicitly a judged criterion ("how well-engineered and automated the pipeline is").

### Consequences
- Full automation and free execution on Colab, no engine licensing/install overhead.

- Loses the "extra credit" framing UE might imply for judges specifically looking for engine familiarity — accepted tradeoff given the time budget.

---

## ADR-002: Background generation provider

**Status:** Accepted

### Context
Backgrounds must be GenAI-produced (not stock photos), covering 5 distinct environments (urban, forest, desert, racetrack, showroom), with consistent camera height/perspective across all 5 so the car composites believably. Initial budget assumption was "free or cheap," later clarified to specifically mean "free or cheap models via OpenRouter (Bytedance, Wan, etc.)."

### Alternatives considered

| Option | Cost | Notes |
|---|---|---|
| **Replicate / HF Inference API (SDXL-Turbo, Flux-schnell)** | Paid (Replicate) / rate-limited free tier (HF) | Original first-pass suggestion; rejected once the no-paid-API constraint was introduced |
| **OpenRouter free tier (`:free` models)** | $0 | Confirmed via direct research: no image-generation model on OpenRouter carries the `:free` suffix — the free tier is text/vision-understanding only. Not viable for this use case at all. |
| **OpenRouter metered models (Seedream 4.5, FLUX)** | ~$0.04/image (Seedream 4.5, flat rate); FLUX typically cheaper | Genuinely cheap — 5 environments × 2–3 generations each ≈ under $1 total. Same OpenAI-compatible request pattern as any other OpenRouter usage, single API key/billing surface. |
| **Google AI Studio (Gemini 2.5 Flash Image / "Nano Banana")** | $0 for base model via free API tier (Pro variant requires billing) | Genuinely free, generous quota (500–1,000 images/day on the web UI). Requires a second provider/API key alongside anything else already using OpenRouter. |
| **Wan (Alibaba)** | N/A | Investigated and ruled out — Wan is a video generation model, not image, and is served via WaveSpeedAI, not OpenRouter's core catalog. Not applicable to a static-image background task. |
| **Local SDXL-Turbo/Flux-schnell via `diffusers`** | $0 (compute only) | Fully free and offline, but consumes Colab free-GPU session time that's also needed for DiffusionLight-Turbo and Blender rendering — competes with the pipeline's actual GPU-bound steps. |

### Decision
Use **OpenRouter's metered image endpoint** (`bytedance-seed/seedream-4.5`, with FLUX as a pricing/quality fallback to check in the playground) for background generation.

### Rationale
Two provider paths cleared the bar (OpenRouter metered, and Google AI Studio free) once the true free-tier misconception was corrected. OpenRouter was chosen over Google AI Studio because:
1. **Cost is trivial relative to the stated "cheap" allowance** — under $1 total for the whole project, so the free-vs-cheap distinction is immaterial in absolute terms.
2. **Single API surface** — if the broader project already touches OpenRouter for any LLM-side work, staying on one provider, one key, and one request pattern (`/api/v1/images`, OpenAI-compatible shape) is measurably less integration surface than adding a second vendor (Google AI Studio) with its own key management and its own free-vs-Pro billing distinction.
3. **Doesn't compete for Colab GPU time** — unlike local `diffusers`, this runs from any machine with network access, so it doesn't eat into the free-tier GPU budget needed for DiffusionLight-Turbo and Blender rendering.

### Consequences
- ~$0.20–$1.00 real cost, the only cost-bearing stage in the entire pipeline — must be stated plainly in the README's cost/infra summary rather than glossed over as "free."
- Response JSON shape (`b64_json` vs hosted `url`) must be verified against the live playground before scripting batch calls — provider APIs shift field names across versions, and this isn't something to assume from memory.
- Google AI Studio's free-tier image quota should be re-verified directly (test call with billing disabled) before being relied on as a fallback — current public reporting on its limits is inconsistent.
- If OpenRouter pricing or model availability changes mid-project, Google AI Studio remains a documented fallback (see alternatives table) — not a full re-architecture.

---

## ADR-003: Lighting / environment estimation method

**Status:** Accepted (with a documented, ranked fallback)

### Context
Once a background is generated, the car's reflections and lighting must adapt to it — this is the core "physically plausible reflections" requirement judged most heavily. The system needs to convert a flat 2D generated image into something usable as a light source (an HDRI/environment map approximation, or an equivalent proxy).

### Alternatives considered

| Option | Cost | Fidelity | Risk |
|---|---|---|---|
| **DiffusionLight-Turbo** (open-weight, self-hosted) | $0 (compute only) | High — purpose-built for estimating scene illumination from a single image, ~30 sec/image inference | Install/inference friction is the single highest-risk step in the whole pipeline; unfamiliar tooling under time pressure |
| **IC-Light** (open-weight, self-hosted) | $0 (compute only) | Comparable, alternate open-weight option | Same self-hosting risk profile as DiffusionLight-Turbo; not chosen as primary only because DiffusionLight-Turbo's HDRI-style output maps more directly onto Blender's World shader input |
| **Manual/paid HDRI estimation API** | Paid or unavailable | N/A | Ruled out immediately — conflicts with the no-paid-API constraint and there's no clearly superior hosted option over the open-weight choices anyway |
| **OpenCV brightest-region heuristic (fallback)** | $0, trivial compute | Low — approximates a single dominant light direction (azimuth/elevation) plus an ambient color tint from the image average | Cheap, fast, always works, but is a crude proxy — no real environment reflections, just a directional sun + ambient fill |

### Decision
**Primary: DiffusionLight-Turbo**, run on Colab's free GPU tier, with a **hard 1.5-hour time-box**. If not producing usable environment maps within that window, **fall back immediately to the OpenCV heuristic** without further debugging, and document the fallback explicitly as a deliberate v1 design decision in the README.

### Rationale
DiffusionLight-Turbo directly targets this exact problem (single-image lighting estimation) and its output plugs cleanly into Blender's World shader as a proper environment texture — this is what makes reflections genuinely scene-adaptive rather than merely "a shadow pointing the right way." However, it's explicitly the highest-uncertainty dependency in the project (unfamiliar open-source install, GPU inference correctness), so a strict time-box protects the 10-hour budget from an open-ended debugging spiral. The OpenCV fallback isn't a "lesser" system bolted on as an afterthought — it's a legitimate, pre-planned decision point precisely so a stalled dependency doesn't take down the whole submission. Explaining *why* a fallback exists and *when* it triggers is itself part of what's being judged ("how well-engineered the pipeline is").

### Consequences
- If DiffusionLight-Turbo succeeds: full environment-map-driven relighting, genuine reflection accuracy — the strongest version of the deliverable.
- If the fallback triggers: reflections degrade to a single directional light + ambient tint, no true environmental reflections. This must be stated as a known limitation in the README, not hidden.
- Because both paths were designed and coded before the deadline (not improvised mid-crisis), switching between them costs no additional engineering time — only the render pass itself changes inputs.

---

## ADR-004: Compute environment

**Status:** Accepted

### Context
Two pipeline stages are GPU-bound: Blender/Cycles rendering and DiffusionLight-Turbo inference. The builder has no local or paid GPU access — only Google Colab's free tier is available.

### Alternatives considered

| Option | Cost | Notes |
|---|---|---|
| **Local GPU** | N/A | Not available to the builder — ruled out by circumstance, not preference |
| **Paid cloud GPU (e.g. Replicate, Lambda, RunPod)** | Paid | Conflicts with the stated budget constraint |
| **Google Colab (free tier, T4)** | $0 | Chosen — but has session-length limits, can disconnect under load, and wipes local disk on runtime recycle |
| **Kaggle Notebooks (free GPU quota)** | $0 | Comparable free-GPU alternative; kept as a documented backup if Colab's session limits become disruptive mid-build |

### Decision
Use **Google Colab's free T4 GPU tier** as primary, with **Kaggle Notebooks** documented as the fallback compute environment if Colab session interruptions become a blocker.

### Rationale
Colab is the more familiar, better-documented option for this kind of ad hoc scripted workflow (Blender headless install, Drive mounting, notebook-driven inference), and DiffusionLight-Turbo's ~30 sec/image inference time comfortably fits within a single free T4 session for 5 environments. Kaggle is functionally equivalent but wasn't made primary since there's no evidence it needs to be — it's insurance, not a first choice.

### Consequences
- **Every output from a GPU-bound step must be persisted to Google Drive immediately**, not left on Colab's local disk — local disk is wiped on runtime recycle and free-tier sessions can disconnect without warning. This is a hard operational rule, not a suggestion.
- Blender is not preinstalled on Colab — a ~2–3 minute setup cell (`apt-get`/binary download) runs once per fresh session; scripted as a reusable cell rather than repeated manual work.
- Background generation (ADR-002) was deliberately kept **off** Colab entirely (runs from any machine with network access) specifically so it doesn't compete with Blender/DiffusionLight-Turbo for the same limited free-GPU session time.

---

## ADR-005: Compositing approach

**Status:** Accepted

### Context
The final image requires layering: generated background → shadow pass (multiplied in) → car beauty pass (alpha-over). This can be done inside Blender's own compositor (node-based) or externally via a scripted image-processing library.

### Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| **Blender's built-in compositor (node graph)** | Stays within one tool; can be scripted via `bpy` node manipulation | Slower to iterate on via script (node-graph construction in `bpy` is verbose); harder to unit-test/debug outside the Blender process |
| **OpenCV (Python, external script)** | Fast to write and iterate; simple, debuggable, standard alpha-over/multiply-blend math; easy to add QA checks (edge feathering, alpha inspection) as plain Python | One more dependency in the stack (though trivial to install); output must be re-verified for color-space consistency with Blender's render (both must agree on linear vs. sRGB) |

### Decision
Use **OpenCV**, scripted externally, for all compositing.

### Rationale
Explicitly faster to script under the project's time constraint, and easier to debug/QA (inspecting an alpha channel or testing a blend formula in a plain Python script is simpler than constructing and validating a Blender node graph programmatically). The compositing math itself (multiply-blend for shadow, alpha-over for the car) is simple enough that Blender's compositor offers no meaningful fidelity advantage here.

### Consequences
- A color-space mismatch is the main risk to actively check for — Blender's render output and any color management settings must agree with how OpenCV interprets the PNGs (both treated as sRGB, or both linear, consistently).
- Edge quality (aliasing at the alpha boundary) is a manual QA step — a 1–2px Gaussian blur on the alpha channel before compositing is the documented fix if hard edges appear.

---

## ADR-006: Car asset sourcing

**Status:** Accepted

### Context
The brief permits "any public car model." The asset must not be edited (geometry, proportions, paint, wheels, decals, materials must remain untouched), so its baseline quality — clean PBR materials, sensible topology — directly determines final visual fidelity, since there's no opportunity to fix it later.

### Alternatives considered

| Option | Cost/License | Notes |
|---|---|---|
| **Sketchfab (CC-licensed, downloadable)** | Free | Large selection, filterable by license and download-ability; quality varies widely, requires manual vetting |
| **Poly Haven** | Free (CC0) | Smaller car selection than Sketchfab but consistently high asset quality and clean PBR setups — Poly Haven's whole catalog is curated for this |
| **Paid marketplace assets (e.g. TurboSquid, CGTrader)** | Paid | Ruled out by the no-paid-spend constraint; also unnecessary given free options are sufficient for the brief's bar |
| **Custom photogrammetry/scan** | Free (time cost) | Ruled out — far too time-expensive for a 10-hour build, and unnecessary since the brief explicitly allows "any public car model" |

### Decision
Source from **Sketchfab or Poly Haven**, filtered to CC-licensed/downloadable, prioritizing models explicitly tagged with proper PBR material setups (metallic/roughness maps) over baked-texture-only models.

### Rationale
Both are free and license-clean. The explicit criterion — PBR materials over baked textures — matters specifically because the pipeline's judged output includes reflection accuracy; a model with real metallic/roughness maps will respond correctly to the estimated environment lighting, while a baked-texture model has "fake" highlights painted in that won't react to relighting at all, undermining the entire premise of the pipeline.

### Consequences
- Asset selection must happen before build time starts, not mid-build — swapping a car after the rig/config is built means re-deriving the bounding box and re-validating camera framing.
- A model with import errors (missing textures, flipped normals) is a signal to swap assets immediately (see ADR-009's hard-stop rules), not to spend build time repairing — repairing crosses into "editing the car," which risks violating the no-modification constraint's spirit even if it's just texture-link fixes.

---

## ADR-007: Camera rig strategy

**Status:** Accepted

### Context
The pipeline needs a camera setup for rendering the car consistently across all 5 environments, matched closely enough to each generated background's implied perspective to read as a real photograph.

### Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| **Single fixed camera (height/distance/FOV set once in config)** | Simple, fast to implement and QA, one set of camera parameters to keep consistent with background-generation prompts | No per-environment camera variation (e.g. a lower angle for a racetrack hero shot vs. a straight-on showroom shot) |
| **Multi-angle / full turntable rig** | More dynamic, more impressive as a portfolio piece, could produce multiple images per environment | Multiplies render time and QA surface by however many angles are added; multiplies the background-generation matching problem (each angle needs a background prompt consistent with *that* camera height/perspective too); meaningfully expands scope beyond the 10-hour budget |

### Decision
Use a **single fixed camera configuration**, defined once in `config.yaml` (height, distance, FOV), reused identically across all 5 environment renders.

### Rationale
The judged criteria emphasize reflection accuracy, consistency, and pipeline automation — not shot variety. A fixed camera keeps the background-generation prompts simple and consistent (the repeated "photographed at 1.2m camera height" phrasing in every prompt only works because there's exactly one camera setup to match against), and keeps the render/QA loop to one pass per environment instead of N passes. This is explicitly named as a limitation in the README rather than treated as a hidden gap — "extra credit" language in the brief (camera/perspective matching) is satisfied at a basic level by this fixed setup; going further was judged not worth the time cost.

### Consequences
- README's "known limitations" section must state this plainly: fixed camera angle, no per-shot perspective variation.
- If time remains after the core 5 outputs are complete and QA'd, a second camera angle is the most natural scope-expansion candidate — but only after the primary deliverable is locked, never before.

---

## ADR-008: Video generation models excluded

**Status:** Accepted (scope exclusion)

### Context
The builder initially asked about using "Wan" (Alibaba) as a free/cheap generation option via OpenRouter, in the same breath as image models like Bytedance's offerings.

### Alternatives considered

| Option | Applicable? |
|---|---|
| **Wan (video generation)** | No — investigated directly. Wan is a video generation model, served via WaveSpeedAI, not part of OpenRouter's core catalog. |
| **Any video-generation model** | No — PS1's deliverable is static photorealistic images across environments, not video. Nothing in the brief calls for motion. |

### Decision
**Exclude video generation entirely from the pipeline.** All environment generation stays within image models (Seedream 4.5 / FLUX per ADR-002).

### Rationale
This isn't a cost or quality tradeoff — it's a straightforward scope mismatch. Wan produces video; the deliverable requires photorealistic still images. Including it would add integration complexity (a third provider, WaveSpeedAI) for a capability the project doesn't need.

### Consequences
- None operationally — this ADR exists mainly to document that the option was considered and deliberately ruled out, rather than simply overlooked, in case it's raised again later in the project.

---

## ADR-009: Build sequencing — car-independent track split

**Status:** Accepted (supersedes the original linear hour-by-hour plan)

### Context
The original plan sequenced work linearly: car import → studio rig → background generation → lighting estimation → relight → composite → demo → README. Partway through planning, the builder did not yet have a car model in hand.

### Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| **Original linear sequencing** (car first, then everything else) | Matches the natural conceptual order of the pipeline; simpler to describe in one pass | Blocks all downstream work — including the two highest-risk, most time-sensitive steps (background generation, lighting estimation) — behind an asset the builder didn't yet have |
| **Two-track split: Track A (car-independent) run first, Track B (car-dependent) run once the asset is available** | Front-loads the two riskiest/most API-dependent steps (background gen, DiffusionLight-Turbo) so failure modes surface early, while genuinely blocking-only work waits for the car; removes the car from the critical path for roughly half the pipeline | Slightly more complex to describe/document than a single linear list; requires care that Track A outputs (backgrounds, env maps) are correctly matched up with Track B's car renders later (same environment names/config keys) |

### Decision
Split the plan into **Track A** (background generation + lighting estimation — zero car dependency) run first, and **Track B** (car import, studio rig, relight render, composite — car-dependent) run once the asset is available.

### Rationale
This is a strict improvement with no real downside: nothing about background generation or lighting estimation requires the car, and both are also the pipeline's highest-uncertainty steps (external API behavior, unfamiliar open-source tooling). Surfacing their outcomes early — while the car is still being sourced — means any fallback decisions (e.g. triggering the OpenCV lighting fallback per ADR-003) are already made and validated by the time the car arrives, rather than competing for attention at the same moment as new problems.

### Consequences
- `config.yaml`'s environment definitions (names, prompts) must be finalized before Track A starts, since Track B's file naming (`beauty_<env>.png`, `shadow_<env>.png`) depends on matching those same environment names exactly.
- The README's architecture section must explain this sequencing choice explicitly — a reviewer reading the code chronologically (background/lighting scripts committed before the car-rig scripts) should understand why, not assume disorganization.

---

## ADR-010: Post-processing and Grading

**Status:** Accepted

### Context
After the base compositing (combining background, shadow, and car) was completed in OpenCV (`05_composite.py`), the output lacked the final visual "glue" that makes a composite look like a single photograph. The car looked slightly pasted on due to differences in color temperature, sharpness, and ambient light matching.

### Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| **Photoshop / Manual Grading** | High quality, artist control | Violates the core automation and reproducibility requirements. |
| **Blender Compositor** | Keeps everything in Blender | Slow to run, harder to script procedurally for non-3D artifacts. |
| **OpenCV + FFmpeg Scripts** | Fully automatable, fast, decoupled from rendering | Requires additional small scripts. FFmpeg handles unsharp masking easily. |

### Decision
Implement post-processing entirely through discrete Python scripts and FFmpeg. We added:
1. `06_polish.py`: Uses FFmpeg to apply an unsharp mask and global contrast/saturation tweaks.
2. `08_last_polish.py`: Uses Python (PIL/numpy) to blend a blurred version of the final composite back onto the car's alpha mask, faking ambient color bleed from the environment.
3. `07_contact_sheet.py`: A utility to generate visual grids for review.

### Rationale
Splitting post-processing into discrete, deterministic scripts keeps the pipeline automated and modular. Using FFmpeg for standard color grading/sharpening is extremely fast and reliable. The ambient bleed technique in `08_last_polish.py` significantly improves the car's integration without violating the "do not edit the car" constraint, as it's just a non-generative pixel math operation on the composited result.

### Consequences
- Requires FFmpeg to be installed and available in the system PATH.
- Requires Python `Pillow` and `numpy`.
- The pipeline now has multiple distinct output directories (`outputs/final` and `outputs/final_polished`) which must be managed and documented.