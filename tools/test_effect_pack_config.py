import json
from pathlib import Path
import tempfile
import base64
import hashlib
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
import build_effect_packs
import verify_effect_packs
import publish_effect_packs
from effect_pack_config import collection_name, validate_catalog


class DataDrivenPackTest(unittest.TestCase):
    def test_new_collection_category_and_effect_need_no_tool_code_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "effect-assets" / "future-cafe"
            (folder / "source").mkdir(parents=True)
            source = Image.new("RGBA", (64, 64))
            ImageDraw.Draw(source).ellipse((8, 8, 56, 56), fill=(30, 200, 80, 255))
            source.save(folder / "source/MoonLatte2050.png")
            config = dict(version=20, tag="effects-v20", sourceRoots=["source"], groups={
                "future-cafe": dict(category="FutureCafe2050", title="Future Café", price=75,
                                    effects=["MoonLatte2050"])}, assets={
                "MoonLatte2050": dict(label="Moon Latte", motion=dict(bob=.04, rotation=8, sparkle=True))})
            (folder / "collection.json").write_text(json.dumps(config), encoding="utf-8")
            with patch.object(build_effect_packs, "ROOT", root), patch.object(verify_effect_packs, "PILOT", root / "effect-assets/pilot"):
                build_effect_packs.build("kedarmayekar/gif-packs", None, "future-cafe")
                verify_effect_packs.verify("kedarmayekar/gif-packs", False, "future-cafe")
                archive = (folder / "releases/future-cafe-v20.zip").read_bytes()
                build_effect_packs.build("kedarmayekar/gif-packs", None, "future-cafe")
                self.assertEqual(archive, (folder / "releases/future-cafe-v20.zip").read_bytes())
            catalog = json.loads((folder / "hosting/effects/catalog.json").read_text())
            pack = catalog["packs"][0]
            self.assertEqual("Future Café", pack["title"])
            self.assertEqual(75, pack["price"])
            self.assertEqual(config["assets"]["MoonLatte2050"]["motion"], pack["assets"][0]["motion"])
            self.assertEqual("Moon Latte", pack["assets"][0]["label"])
            pack["assets"][0]["motion"]["rotation"] = 99
            with self.assertRaises(AssertionError):
                validate_catalog(catalog, "kedarmayekar/gif-packs")

    def test_collection_cannot_escape_effect_assets(self):
        for value in ("../other", "/tmp", "C:\\other", "a/b", "", "a b"):
            with self.assertRaises(ValueError):
                collection_name(value)

    def test_publication_pins_parent_and_preserves_reviewed_encodings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "effect-assets/future-cafe"
            for directory in ("source", "encoded", "releases", "hosting/effects"):
                (folder / directory).mkdir(parents=True)
            encoded = b"reviewed-encoding"
            archive = b"verified-release-archive"
            (folder / "source/MoonLatte2050.png").write_bytes(b"source-fixture")
            (folder / "encoded/MoonLatte2050.webp").write_bytes(encoded)
            (folder / "releases/future-v20.zip").write_bytes(archive)
            catalog = dict(schemaVersion=1, packs=[dict(id="future", category="FutureCafe2050", version=20,
                archiveUrl="https://github.com/kedarmayekar/gif-packs/releases/download/effects-v20/future-v20.zip",
                bytes=len(archive), sha256=hashlib.sha256(archive).hexdigest(), assets=[dict(effectId="MoonLatte2050",
                path="images/MoonLatte2050.webp", bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest(), width=32, height=32)])])
            (folder / "hosting/effects/catalog.json").write_text(json.dumps(catalog))
            calls = []

            class FakeGitHub:
                base = "/repos/kedarmayekar/gif-packs"

                def __init__(self, repository):
                    pass

                def request(self, path, method="GET", payload=None, data=None, missing_ok=False):
                    calls.append((path, method, payload))
                    if path == self.base:
                        return dict(permissions=dict(push=True), private=False, default_branch="main", full_name="kedarmayekar/gif-packs")
                    if path.endswith("/git/ref/heads/main"):
                        return dict(object=dict(sha="pinned-parent"))
                    if "/contents/" in path or "/releases/tags/" in path:
                        return None
                    if path.endswith("/releases"):
                        return dict(id=1, draft=True, assets=[], upload_url="https://uploads.github.com/assets{?name}")
                    if path.startswith("https://uploads.github.com/"):
                        return dict(size=len(data), digest="sha256:" + hashlib.sha256(data).hexdigest())
                    if path.endswith("/releases/1"):
                        return dict(draft=False, html_url="https://github.com/example/release")
                    if path.endswith("/git/commits/pinned-parent"):
                        return dict(tree=dict(sha="base-tree"))
                    if path.endswith("/git/blobs") or path.endswith("/git/trees") or path.endswith("/git/commits"):
                        return dict(sha="new-object")
                    if path.endswith("/git/refs/heads/main"):
                        return {}
                    raise AssertionError(path)

            with patch.object(publish_effect_packs, "ROOT", root), patch.object(publish_effect_packs, "GitHub", FakeGitHub):
                publish_effect_packs.publish("kedarmayekar/gif-packs", False, "future-cafe")
            self.assertTrue(any("catalog.json?ref=pinned-parent" in path for path, _, _ in calls))
            tree = next(payload for path, _, payload in calls if path.endswith("/git/trees"))
            self.assertIn("effect-assets/future-cafe/encoded/MoonLatte2050.webp", [entry["path"] for entry in tree["tree"]])
            self.assertIn(base64.b64encode(encoded).decode(), [payload["content"] for path, _, payload in calls if path.endswith("/git/blobs")])
            commit = next(payload for path, _, payload in calls if path.endswith("/git/commits"))
            self.assertEqual(["pinned-parent"], commit["parents"])
            self.assertFalse(calls[-1][2]["force"])


if __name__ == "__main__":
    unittest.main()
