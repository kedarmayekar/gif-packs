"""Encode reviewed transparent source PNGs and build reproducible GitHub Release packs.

Requires Pillow. No network access or image generation is performed by this script.
"""
import argparse
from effect_pack_config import collection_name, validate_catalog
import hashlib
import json
import shutil
from pathlib import Path
import zipfile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "effect-assets" / "pilot"
GROUPS = {
    "vehicles": ("VehiclesTransport", ["Bus"]),
    "sports": ("SportsGames", ["F1Car", "Football", "BowlingBall"]),
    "jewels": ("JewelsGems", ["Diamonds"]),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build(repository, version, collection="pilot"):
    output_dir = ROOT / "effect-assets" / collection_name(collection)
    configuration = output_dir / "collection.json"
    config = json.loads(configuration.read_text()) if configuration.exists() else {}
    if config and version is not None and version != config["version"]:
        raise ValueError("Update collection.json version and tag together before building a different version")
    version = version or config.get("version", 1)
    groups = {key: (value["category"], value["effects"]) for key, value in config["groups"].items()} if config else GROUPS
    effect_ids = [effect for _, effects in groups.values() for effect in effects]
    if len(effect_ids) != len(set(effect_ids)):
        raise ValueError("An effect ID can appear in only one pack")
    sources = [output_dir / path for path in config.get("sourceRoots", ["source"])]
    hosting = output_dir / "hosting" / "effects"
    releases = output_dir / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    (hosting / "previews").mkdir(parents=True, exist_ok=True)
    tag = config.get("tag", f"effects-pilot-v{version}")
    packs = []
    for group, (category, effect_ids) in groups.items():
        assets = []
        encoded = {}
        for effect_id in effect_ids:
            source = next((root / f"{effect_id}.png" for root in sources if (root / f"{effect_id}.png").is_file()), None)
            if source is None:
                raise FileNotFoundError(f"Missing source image: {effect_id}")
            with Image.open(source) as original:
                assert original.mode == "RGBA", f"{effect_id}: missing alpha channel"
                assert original.getchannel("A").getextrema()[0] == 0, f"{effect_id}: opaque background"
                image = original.copy()
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            asset_path = output_dir / "encoded" / f"{effect_id}.webp"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            # Inherited sources retain their previously reviewed encoded bytes.
            # Sources owned by this collection are always encoded afresh.
            prior = source.parent.parent / "encoded" / f"{effect_id}.webp"
            inherited = source.parent.parent.resolve() != output_dir.resolve() and prior.is_file()
            if inherited:
                asset_path.write_bytes(prior.read_bytes())
            else:
                image.save(asset_path, "WEBP", quality=91, method=6, exact=True)
            # Reopen the deliverable and verify transparent borders survived encoding.
            with Image.open(asset_path) as check:
                assert check.mode == "RGBA" and check.getchannel("A").getextrema()[0] == 0
                # Generated/resampled alpha may round a clear corner to 1/255; preserve it verbatim.
                assert check.getpixel((0, 0))[3] <= 1, f"{effect_id}: non-transparent corner"
            data = asset_path.read_bytes()
            name = f"images/{effect_id}.webp"
            encoded[name] = data
            metadata = config.get("assets", {}).get(effect_id, {})
            asset = dict(effectId=effect_id, path=name, bytes=len(data), sha256=sha(data),
                         width=image.width, height=image.height)
            asset.update({key: metadata[key] for key in ("label", "motion") if key in metadata})
            assets.append(asset)
            preview = hosting / "previews" / f"{effect_id}.webp"
            prior_preview = source.parent.parent / "hosting/effects/previews" / f"{effect_id}.webp"
            if inherited and prior_preview.is_file():
                shutil.copyfile(prior_preview, preview)
            else:
                image.thumbnail((384, 384), Image.Resampling.LANCZOS)
                image.save(preview, "WEBP", quality=86, method=6, exact=True)
        archive = releases / f"{group}-v{version}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
            for name, data in sorted(encoded.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                output.writestr(info, data)
        data = archive.read_bytes()
        pack = dict(id=group, category=category, version=version,
                    archiveUrl=f"https://github.com/{repository}/releases/download/{tag}/{archive.name}",
                    bytes=len(data), sha256=sha(data), assets=assets)
        metadata = config.get("groups", {}).get(group, {})
        pack.update({key: metadata[key] for key in ("title", "price", "description") if key in metadata})
        validate_catalog(dict(schemaVersion=1, packs=[pack]), repository)
        write_json(hosting / group / "manifest.json", pack)
        packs.append(pack)
        print(f"Built {group}: {len(assets)} effects, {len(data)} bytes", flush=True)
    validate_catalog(dict(schemaVersion=1, packs=packs), repository)
    write_json(hosting / "catalog.json", dict(schemaVersion=1, packs=packs))
    # A QA sheet presents the same encoded images on light and dark UI backgrounds.
    ids = [effect for _, effects in groups.values() for effect in effects]
    for group, (_, effect_ids) in groups.items():
        save_sheet(output_dir, effect_ids, f"{group}-preview.jpg")
    save_sheet(output_dir, ids, "pilot-preview.jpg" if collection == "pilot" else "collection-preview.jpg")
    print(json.dumps(dict(repository=repository, tag=tag, packs=len(packs), effects=len(ids),
                          archiveBytes=sum(pack["bytes"] for pack in packs), output=str(output_dir)), indent=2))


def save_sheet(output_dir, ids, filename):
    columns = min(5, len(ids))
    rows = (len(ids) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 240, rows * 540), "#101827")
    draw = ImageDraw.Draw(sheet)
    for index, effect_id in enumerate(ids):
        col, item_row = index % columns, index // columns
        for row, background in enumerate(("#101827", "#EDF2F6")):
            x, y = col * 240, item_row * 540 + row * 270
            draw.rectangle((x, y, x+239, y+269), fill=background)
            with Image.open(output_dir / "encoded" / f"{effect_id}.webp") as img:
                img.thumbnail((220, 220), Image.Resampling.LANCZOS)
                sheet.paste(img, (x+(240-img.width)//2, y+12+(220-img.height)//2), img)
            draw.text((x+14, y+242), effect_id, fill="#D9EAF9" if row == 0 else "#18324C")
    sheet.save(output_dir / filename, quality=92)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="kedarmayekar/gif-packs")
    parser.add_argument("--version", type=int)
    parser.add_argument("--collection", type=collection_name, default="pilot")
    args = parser.parse_args()
    if args.version is not None and args.version < 1:
        parser.error("version must be positive")
    build(args.repository, args.version, args.collection)
