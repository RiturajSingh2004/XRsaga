#!/usr/bin/env python3
"""
07_contact_sheet.py

Builds a single side-by-side comparison image from the beauty pass PNGs
(outputs/car_passes/beauty_<env>.png), arranged 3 columns x 2 rows,
with each tile's environment name labeled top-left.

Run from the project root:
    python scripts/07_contact_sheet.py
"""

from PIL import Image, ImageDraw, ImageFont
import yaml
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, "..")
CFG_PATH = os.path.join(ROOT_DIR, "config.yaml")
BEAUTY_DIR = os.path.join(ROOT_DIR, "outputs", "car_passes")
OUT_PATH = os.path.join(ROOT_DIR, "outputs", "beauty_contact_sheet.png")

COLS, ROWS = 3, 2
TILE_W, TILE_H = 640, 360        # each tile's size in the final sheet
PAD = 12                          # gap between tiles
LABEL_MARGIN = 14                 # inset of label from tile's top-left corner
LABEL_FONT_SIZE = 22

# Checkerboard background so transparent (alpha) areas of the beauty pass
# are visibly distinguishable from opaque white/gray parts of the car.
CHECK_SIZE = 20
CHECK_LIGHT = (235, 235, 235)
CHECK_DARK = (200, 200, 200)

# Zoom factor (crop size). Original is 1920x1080.
# Crop to 1440x810 for a subtle zoom, or 1280x720 for a bit more.
CROP_W, CROP_H = 1440, 810


def make_checkerboard(w, h):
    board = Image.new("RGB", (w, h), CHECK_LIGHT)
    draw = ImageDraw.Draw(board)
    for y in range(0, h, CHECK_SIZE):
        for x in range(0, w, CHECK_SIZE):
            if (x // CHECK_SIZE + y // CHECK_SIZE) % 2 == 0:
                draw.rectangle([x, y, x + CHECK_SIZE, y + CHECK_SIZE], fill=CHECK_DARK)
    return board


def load_tile(env_name):
    path = os.path.join(BEAUTY_DIR, f"beauty_{env_name}.png")
    if not os.path.exists(path):
        # placeholder tile if a render is missing
        tile = make_checkerboard(TILE_W, TILE_H)
        draw = ImageDraw.Draw(tile)
        draw.text((TILE_W // 2 - 60, TILE_H // 2), "MISSING", fill=(200, 0, 0))
        return tile

    img = Image.open(path).convert("RGBA")
    
    # fit into tile size
    if hasattr(Image, 'Resampling'):
        img.thumbnail((TILE_W, TILE_H), Image.Resampling.LANCZOS)
    else:
        img.thumbnail((TILE_W, TILE_H), Image.LANCZOS)
        
    bg = make_checkerboard(TILE_W, TILE_H).convert("RGBA")
    offset = ((TILE_W - img.width) // 2, (TILE_H - img.height) // 2)
    bg.alpha_composite(img, dest=offset)
    return bg.convert("RGB")


def label_tile(tile, text):
    draw = ImageDraw.Draw(tile)
    try:
        font = ImageFont.truetype("arial.ttf", LABEL_FONT_SIZE)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    # translucent backing rectangle
    pad_box = 6
    draw.rectangle(
        [LABEL_MARGIN - pad_box, LABEL_MARGIN - pad_box,
         LABEL_MARGIN + tw + pad_box, LABEL_MARGIN + th + pad_box],
        fill=(0, 0, 0, 160)
    )
    draw.text((LABEL_MARGIN, LABEL_MARGIN), text, fill=(255, 255, 255), font=font)
    return tile


def build_contact_sheet(env_names):
    sheet_w = COLS * TILE_W + (COLS + 1) * PAD
    sheet_h = ROWS * TILE_H + (ROWS + 1) * PAD
    sheet = Image.new("RGB", (sheet_w, sheet_h), (30, 30, 30))

    for i, env_name in enumerate(env_names[:COLS * ROWS]):
        row, col = divmod(i, COLS)
        tile = load_tile(env_name)
        tile = label_tile(tile, env_name.replace("_", " ").title())

        x = PAD + col * (TILE_W + PAD)
        y = PAD + row * (TILE_H + PAD)
        sheet.paste(tile, (x, y))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    sheet.save(OUT_PATH)
    print(f"  ✅ Saved contact sheet to {os.path.relpath(OUT_PATH)}")


if __name__ == "__main__":
    cfg = yaml.safe_load(open(CFG_PATH))
    # We want neutral first, then the 5 environments
    env_names = ["neutral"] + [e["name"] for e in cfg["environments"]]
    build_contact_sheet(env_names)
