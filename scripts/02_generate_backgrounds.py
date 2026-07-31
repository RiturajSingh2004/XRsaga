#!/usr/bin/env python3
"""
02_generate_backgrounds.py
Track A — Generate 5 background images via OpenRouter image API.
Run this immediately; it has zero dependency on the car asset.
"""

import os
import sys
import base64
import time
import requests
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "backgrounds")

API_KEY = "[ENCRYPTION_KEY]"

# OpenRouter image generation endpoint (OpenAI-compatible).
# Verify exact shape in the OpenRouter playground before batching.
API_URL = "https://openrouter.ai/api/v1/images"

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds — exponential: 2, 4, 8


def generate_image(prompt: str, out_path: str, model: str = "bytedance-seed/seedream-4.5") -> bool:
    """Generate one image and save to disk. Returns True on success.

    Retries up to MAX_RETRIES times with exponential backoff on transient failures.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "size": "1344x768",
        "n": 1,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            # OpenRouter may return b64_json or a hosted url depending on the provider.
            image_data = data.get("data", [{}])[0]

            if "b64_json" in image_data:
                img_bytes = base64.b64decode(image_data["b64_json"])
            elif "url" in image_data:
                img_url = image_data["url"]
                img_resp = requests.get(img_url, timeout=60)
                img_resp.raise_for_status()
                img_bytes = img_resp.content
            else:
                print(f"  Unknown response shape: {list(image_data.keys())}")
                return False

            with open(out_path, "wb") as f:
                f.write(img_bytes)
            return True

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            # Don't retry client errors (4xx) except 429 (rate limit)
            if status and 400 <= status < 500 and status != 429:
                print(f"  Client error ({status}), not retrying: {e}")
                return False
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt
                print(f"  Attempt {attempt}/{MAX_RETRIES} failed ({e}). "
                      f"Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  All {MAX_RETRIES} attempts failed: {e}")
                return False

        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt
                print(f"  Attempt {attempt}/{MAX_RETRIES} failed ({e}). "
                      f"Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  All {MAX_RETRIES} attempts failed: {e}")
                return False

    return False


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    print(f"Generating backgrounds -> {OUT_DIR}")
    print("Tip: validate ONE prompt in the OpenRouter playground before batching.\n")

    for env in cfg["environments"]:
        out_path = os.path.join(OUT_DIR, f"{env['name']}.png")
        if os.path.exists(out_path):
            print(f"[SKIP] {env['name']} already exists at {out_path}")
            continue

        print(f"[GEN ] {env['name']}: {env['prompt'][:60]}...")
        ok = generate_image(env["prompt"], out_path)
        if ok:
            print(f"[SAVE] {out_path}")
        else:
            print(f"[FAIL] {env['name']} — see error above")
        time.sleep(1)  # polite rate-limiting

    print("\nDone. Check outputs/backgrounds/ for results.")


if __name__ == "__main__":
    main()
