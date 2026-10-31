"""Verify local or publicly hosted effect archives, metadata, decoding and transparency."""
import argparse
from effect_pack_config import collection_name, validate_catalog
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile
from PIL import Image

PILOT = Path(__file__).resolve().parents[1] / "effect-assets" / "pilot"
VERIFY_RUN = str(time.time_ns())


def fetch(url):
    if url.startswith("https://raw.githubusercontent.com/"):
        url += ("&" if "?" in url else "?") + "verify=" + VERIFY_RUN
    request = Request(url, headers={"User-Agent": "ImagePicker-Effect-Pack-Verification"})
    with urlopen(request, timeout=60) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    assert len(data) <= 20 * 1024 * 1024
    return data


def verify(repository, live, collection="pilot"):
    collection_dir = PILOT.parent / collection_name(collection)
    base = f"https://raw.githubusercontent.com/{repository}/main/effects/"
    catalog_bytes = fetch(base + "catalog.json") if live else (collection_dir / "hosting/effects/catalog.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    validate_catalog(catalog, repository)
    count = 0
    for pack in catalog["packs"]:
        data = fetch(pack["archiveUrl"]) if live else (collection_dir / "releases" / pack["archiveUrl"].rsplit("/", 1)[1]).read_bytes()
        assert len(data) == pack["bytes"]
        assert hashlib.sha256(data).hexdigest() == pack["sha256"]
        manifest_bytes = fetch(base + pack["id"] + "/manifest.json") if live else (collection_dir / "hosting/effects" / pack["id"] / "manifest.json").read_bytes()
        assert json.loads(manifest_bytes) == pack
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert sorted(archive.namelist()) == sorted(asset["path"] for asset in pack["assets"])
            assert archive.testzip() is None
            for asset in pack["assets"]:
                encoded = archive.read(asset["path"])
                assert len(encoded) == asset["bytes"]
                assert hashlib.sha256(encoded).hexdigest() == asset["sha256"]
                with Image.open(io.BytesIO(encoded)) as image:
                    image.load()
                    assert image.size == (asset["width"], asset["height"])
                    assert image.mode == "RGBA" and image.getchannel("A").getextrema()[0] == 0
                preview = fetch(base + "previews/" + asset["effectId"] + ".webp") if live else (collection_dir / "hosting/effects/previews" / (asset["effectId"] + ".webp")).read_bytes()
                with Image.open(io.BytesIO(preview)) as image:
                    image.load()
                    assert image.mode == "RGBA" and max(image.size) <= 384
                count += 1
        print("Verified:", pack["id"], pack["bytes"], "bytes", flush=True)
    print(json.dumps(dict(source="public GitHub downloads" if live else "local packs", packs=len(catalog["packs"]), effects=count)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="kedarmayekar/gif-packs")
    parser.add_argument("--live", action="store_true", help="Download public catalog, archives and previews without credentials")
    parser.add_argument("--collection", type=collection_name, default="pilot")
    args = parser.parse_args()
    verify(args.repository, args.live, args.collection)
