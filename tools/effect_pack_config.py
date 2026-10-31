"""Shared data-only collection validation, independent of Android enums."""
import math
import re


def collection_name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("Collection must be a simple directory name under effect-assets")
    return value


def validate_catalog(catalog, repository):
    assert catalog["schemaVersion"] == 1 and len(catalog["packs"]) <= 100
    categories, pack_ids, effect_ids = set(), set(), set()
    for pack in catalog["packs"]:
        assert re.fullmatch(r"[a-z][a-z0-9-]{0,39}", pack["id"])
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", pack["category"])
        assert pack["category"] not in categories and pack["id"] not in pack_ids
        categories.add(pack["category"])
        pack_ids.add(pack["id"])
        assert type(pack["version"]) is int and pack["version"] > 0
        assert 1 <= pack["bytes"] <= 20 * 1024 * 1024
        assert re.fullmatch(r"[a-f0-9]{64}", pack["sha256"])
        assert re.fullmatch(r"https://github.com/" + re.escape(repository) + r"/releases/download/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.zip", pack["archiveUrl"])
        assert 0 < len(pack["assets"]) <= 100
        assert len({a["path"] for a in pack["assets"]}) == len(pack["assets"])
        assert sum(a["bytes"] for a in pack["assets"]) <= 40 * 1024 * 1024
        assert isinstance(pack.get("title", pack["category"]), str) and 0 < len(pack.get("title", pack["category"]).strip()) <= 120
        assert len(pack.get("description", "")) <= 2000
        if pack.get("price") is not None:
            assert type(pack["price"]) is int and 0 <= pack["price"] <= 1000000
        for asset in pack["assets"]:
            assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", asset["effectId"])
            assert asset["effectId"] not in effect_ids, "Preview IDs must be globally unique"
            effect_ids.add(asset["effectId"])
            assert re.fullmatch(r"images/[A-Za-z][A-Za-z0-9_-]{0,63}\.(webp|png)", asset["path"])
            assert 1 <= asset["bytes"] <= 8 * 1024 * 1024
            assert re.fullmatch(r"[a-f0-9]{64}", asset["sha256"])
            assert 1 <= asset["width"] <= 2048 and 1 <= asset["height"] <= 2048
            assert 0 < len(asset.get("label", asset["effectId"]).strip()) <= 120
            motion = asset.get("motion", {})
            assert set(motion) <= {"bob", "drift", "rotation", "sparkle"}
            for name, maximum in (("bob", .2), ("drift", .2), ("rotation", 30)):
                value = motion.get(name, 0)
                assert type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum
            assert type(motion.get("sparkle", False)) is bool
