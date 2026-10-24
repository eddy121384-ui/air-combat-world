"""Package committed UE screenshots for PR #68; no UE or material operations.

Requires Pillow 12.3.0 and the Windows fonts below. Only writes review/.
"""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version


REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs/evidence/xinyi-material-ue58-round1"
CAPTURES = EVIDENCE / "captures"
OUT = EVIDENCE / "review"
SOURCE_COMMIT = "0b220f6fed7849ab8fe6bd8a0eede1891ec2a878"
SHOTS = (
    ("walkup", "老公寓 / Walk-up", (640, 250, 1152, 762)),
    ("huaxia", "華廈 / Huaxia", (520, 370, 1032, 882)),
    ("wuxing_roofs", "吳興街屋頂 / Wuxing roofs", (0, 760, 512, 1080)),
)
MATCH_KEYS = (
    "resolution", "time_of_day", "clouds", "camera_specs",
    "requested_console_settings", "observed_console_settings",
    "look_level_sha256", "baseline_city_material_sha256",
)
TITLE_FONT = Path("C:/Windows/Fonts/NotoSansTC-VF.ttf")
LABEL_FONT = Path("C:/Windows/Fonts/segoeuib.ttf")
NOTE_FONT = Path("C:/Windows/Fonts/segoeui.ttf")
MARGIN, GAP, IMAGE_Y, FOOTER = 16, 16, 112, 48


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def compose(panels, title, note):
    width, height = panels[0].size
    if panels[1].size != (width, height):
        raise RuntimeError("A/B panel dimensions differ")
    canvas = Image.new("RGB", (2 * width + GAP + 2 * MARGIN,
                               IMAGE_Y + height + FOOTER), (32, 32, 32))
    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, 8), title, font=ImageFont.truetype(str(TITLE_FONT), 30),
              fill=(235, 235, 235))
    boxes = []
    for index, (panel, label) in enumerate(zip(panels, ("Baseline", "New Materials"))):
        x = MARGIN + index * (width + GAP)
        draw.text((x, 52), label, font=ImageFont.truetype(str(LABEL_FONT), 40),
                  fill=(255, 255, 255))
        canvas.paste(panel, (x, IMAGE_Y))
        boxes.append((x, IMAGE_Y, x + width, IMAGE_Y + height))
    draw.text((MARGIN, IMAGE_Y + height + 9), note,
              font=ImageFont.truetype(str(NOTE_FONT), 22), fill=(210, 210, 210))
    return canvas, boxes


def describe(path, panel_boxes):
    with Image.open(path) as image:
        dimensions = list(image.size)
    return {"path": path.relative_to(REPO).as_posix(),
            "bytes": path.stat().st_size, "sha256": sha(path.read_bytes()),
            "dimensions_px": dimensions, "panel_boxes_xyxy": panel_boxes}


def main():
    originals = sorted(p for p in CAPTURES.rglob("*")
                       if p.is_file() and p.suffix in (".png", ".json"))
    suite_pngs = [p for p in originals if p.suffix == ".png" and p.parent != CAPTURES]
    if len(suite_pngs) != 14:
        raise RuntimeError("Expected fourteen committed A/B screenshots")
    before, committed_hashes = {}, {}
    for path in originals:
        relative = path.relative_to(REPO).as_posix()
        data = path.read_bytes()
        committed = subprocess.run(
            ["git", "-c", f"safe.directory={REPO.as_posix()}", "show",
             f"{SOURCE_COMMIT}:{relative}"], cwd=REPO, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        same_content = data == committed
        if path.suffix == ".json":  # Git autocrlf may change text checkout newlines.
            same_content = data.replace(b"\r\n", b"\n") == committed.replace(b"\r\n", b"\n")
        if not same_content:
            raise RuntimeError("Original differs from committed evidence: " + relative)
        before[relative] = sha(data)
        committed_hashes[relative] = sha(committed)
    baseline = read_json(CAPTURES / "baseline/metadata.json")
    candidate = read_json(CAPTURES / "candidate/metadata.json")
    for key in MATCH_KEYS:
        if baseline[key] != candidate[key]:
            raise RuntimeError("A/B capture conditions differ: " + key)
    if baseline["resolution"] != [1920, 1080]:
        raise RuntimeError("Unexpected source resolution")

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_commit": SOURCE_COMMIT,
        "method": "Offline layout/crop/compression of committed UE screenshots only",
        "pillow_version": pillow_version,
        "fonts_sha256": {p.name: sha(p.read_bytes())
                         for p in (TITLE_FONT, LABEL_FONT, NOTE_FONT)},
        "left": "baseline", "right": "candidate (New Materials)",
        "matched_capture_metadata_keys": list(MATCH_KEYS),
        "source_files_sha256": before,
        "source_commit_blobs_sha256": committed_hashes,
        "source_commit_comparison": "PNG bytes exact; JSON text exact after CRLF/LF normalization",
        "suite_original_png_count": len(suite_pngs),
        "additional_smoke_png_preserved": True,
        "color_processing": "Same stored RGB samples; no color, exposure, gamma, "
                            "contrast, saturation or sharpness adjustments; no ICC conversion",
        "full_frame_transform": {"source_px": [1920, 1080],
                                 "panel_px": [768, 432], "both_sides_scale": 0.4,
                                 "resampling": "Pillow LANCZOS (identical both sides)"},
        "jpeg": {"quality": 90, "subsampling": "4:4:4", "progressive": True,
                 "optimize": True, "max_bytes": 1_000_000},
        "details": "Lossless RGB PNG; same xyxy crop on both sides; "
                   "one source pixel per output panel pixel; no resizing or enhancement",
        "crop_coordinates": "Source pixels, top-left origin; right/bottom exclusive",
        "pairs": [],
    }
    for name, title, crop_box in SHOTS:
        inputs, panels, crops = [], [], []
        for variant in ("baseline", "candidate"):
            path = CAPTURES / variant / (name + "__day.png")
            with Image.open(path) as image:
                if image.size != (1920, 1080):
                    raise RuntimeError("Unexpected screenshot dimensions")
                rgb = image.convert("RGB")  # Copy RGB samples; no color transform.
            inputs.append(path.relative_to(REPO).as_posix())
            panels.append(rgb.resize((768, 432), Image.Resampling.LANCZOS))
            crops.append(rgb.crop(crop_box))

        full, full_boxes = compose(panels, title + " · UE5 A/B",
                                   "Full frame · Same camera · Both sides at 40% · No color adjustments")
        jpeg = OUT / (name + "-ab.jpg")
        full.save(jpeg, quality=90, subsampling=0, progressive=True, optimize=True)
        if jpeg.stat().st_size >= 1_000_000:
            raise RuntimeError("JPEG exceeds the 1 MB preview budget")

        detail, detail_boxes = compose(
            crops, title + " · 1:1 detail",
            f"1:1 source pixels · Crop {crop_box} · No resize / enhancement")
        png = OUT / (name + "-detail-1to1.png")
        detail.save(png, optimize=True)
        with Image.open(png) as saved:
            for crop, box in zip(crops, detail_boxes):
                if saved.crop(box).tobytes() != crop.tobytes():
                    raise RuntimeError("Lossless detail pixels changed")
        manifest["pairs"].append({
            "subject": name, "inputs_left_right": inputs,
            "source_crop_xyxy": crop_box,
            "full_frame_jpeg": describe(jpeg, full_boxes),
            "detail_png": describe(png, detail_boxes),
            "detail_rgb_pixels_exact": True,
        })

    after = {p.relative_to(REPO).as_posix(): sha(p.read_bytes()) for p in originals}
    if before != after:
        raise RuntimeError("A protected screenshot or capture metadata file changed")
    manifest["all_original_capture_files_unchanged"] = True
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"original_files_unchanged": len(before),
                      "pairs": [{"subject": p["subject"],
                                 "jpeg_bytes": p["full_frame_jpeg"]["bytes"],
                                 "detail_png_bytes": p["detail_png"]["bytes"],
                                 "detail_rgb_pixels_exact": p["detail_rgb_pixels_exact"]}
                                for p in manifest["pairs"]]}, indent=2))


if __name__ == "__main__":
    main()
