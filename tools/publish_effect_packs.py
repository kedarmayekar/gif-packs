"""Publish a reviewed collection to GitHub Releases and atomically update effects/ on main.

Uses an existing GH_TOKEN/GITHUB_TOKEN or Git Credential Manager login, never prints or saves tokens.
Run --check first. Existing release files are never replaced with different bytes.
"""
import argparse
from effect_pack_config import collection_name, validate_catalog
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "effect-assets" / "pilot"


def credentials():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    result = subprocess.run(["git", "credential", "fill"],
                            input="protocol=https\nhost=github.com\n\n", text=True,
                            capture_output=True, env=env, timeout=30)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if result.returncode != 0 or not values.get("password"):
        raise RuntimeError("No saved GitHub login is available. Sign in with Git Credential Manager or set GH_TOKEN locally.")
    return values["password"]


class GitHub:
    def __init__(self, repository):
        self.repository = repository
        self.token = credentials()

    def request(self, path, method="GET", payload=None, data=None, missing_ok=False):
        url = path if path.startswith("https://") else "https://api.github.com" + path
        if urlsplit(url).hostname not in {"api.github.com", "uploads.github.com"}:
            raise RuntimeError("Untrusted GitHub API host")
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                   "User-Agent": "ImagePicker-Effect-Packs", "X-GitHub-Api-Version": "2026-03-10"}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        elif data is not None:
            headers["Content-Type"] = "application/zip"
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method), timeout=60) as response:
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            # Do not include request headers or credential-helper output in errors.
            message = json.loads(error.read()).get("message", error.reason)
            raise RuntimeError(f"GitHub {method} {urlsplit(url).path}: HTTP {error.code}: {message}") from None

    @property
    def base(self):
        return "/repos/" + self.repository


def publish(repository, check_only, collection="pilot"):
    github = GitHub(repository)
    repo = github.request(github.base)
    if not repo.get("permissions", {}).get("push"):
        raise RuntimeError("The saved GitHub login cannot publish to this repository.")
    if repo["private"]:
        raise RuntimeError("Effect downloads require a public repository; app clients do not carry GitHub credentials.")
    if repo["default_branch"] != "main":
        raise RuntimeError("The app currently expects main. Update the hosting configuration first.")
    print(json.dumps(dict(repository=repo["full_name"], branch="main", writable=True, public=True)))
    if check_only:
        return
    collection_dir = ROOT / "effect-assets" / collection_name(collection)
    hosting = collection_dir / "hosting"
    catalog = json.loads((hosting / "effects" / "catalog.json").read_text())
    validate_catalog(catalog, repository)
    archives = []
    tags = set()
    for pack in catalog["packs"]:
        match = re.fullmatch(r"https://github.com/" + re.escape(repository) + r"/releases/download/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+\.zip)", pack["archiveUrl"])
        if not match:
            raise RuntimeError("Manifest download URL does not match the target repository")
        tag, name = match.groups()
        tags.add(tag)
        path = collection_dir / "releases" / name
        content = path.read_bytes()
        if len(content) != pack["bytes"] or hashlib.sha256(content).hexdigest() != pack["sha256"]:
            raise RuntimeError("Archive checksum does not match its manifest")
        archives.append((path, pack))
    if len(tags) != 1:
        raise RuntimeError("All collection packs must use one release tag")
    tag = tags.pop()

    # Pin the catalog and eventual parent to one revision, so concurrent publications cannot be lost.
    ref = github.request(github.base + "/git/ref/heads/main")
    parent = ref["object"]["sha"]
    previous = github.request(github.base + "/contents/effects/catalog.json?ref=" + parent, missing_ok=True)
    if previous:
        old = json.loads(base64.b64decode(previous["content"]))
        merged = {pack["category"]: pack for pack in old["packs"]}
        for pack in catalog["packs"]:
            existing = merged.get(pack["category"])
            if existing and existing != pack and existing["version"] >= pack["version"]:
                raise RuntimeError("A pack with this or a newer version already exists; build a new version")
            merged[pack["category"]] = pack
        catalog["packs"] = list(merged.values())
    validate_catalog(catalog, repository)

    release = github.request(github.base + "/releases/tags/" + quote(tag), missing_ok=True)
    if release is None:
        count = sum(len(pack["assets"]) for _, pack in archives)
        version = archives[0][1]["version"]
        categories = ", ".join(pack["category"] for _, pack in archives)
        notes = (f"{count} transparent realistic effects across {categories}. "
                 + ({"set2": "Version 2 adds 21 objects and retains all five original pilot assets. ",
                     "set3": "Version 3 adds three flower effects and retains all 26 previous assets. ",
                     "set4": "Version 4 adds three food effects and retains all 29 previous assets. ",
                     "set5": "Version 5 adds three coffee and tea effects and retains all 32 previous assets. "}.get(collection, "Data-driven realistic image effects. "))
                 + "Category archives include optimized WebP assets. Sizes and SHA-256 checksums are published in effects/catalog.json. "
                 "Existing category owners can update without repurchasing. "
                 "These are static cutouts with app-driven motion, not multi-frame animations. Generated with the built-in image_gen tool.")
        release = github.request(github.base + "/releases", "POST", dict(
            tag_name=tag, target_commitish="main", name=f"Realistic effects {'pilot' if collection == 'pilot' else 'collection'} v{version}",
            body=notes,
            draft=True, prerelease=False, make_latest="false"))
    uploaded = {asset["name"]: asset for asset in release.get("assets", [])}
    for path, pack in archives:
        asset = uploaded.get(path.name)
        if asset:
            if asset["size"] != pack["bytes"] or asset.get("digest") != "sha256:" + pack["sha256"]:
                raise RuntimeError("An existing release asset has different or unverifiable content; use a new version")
        else:
            if not release["draft"]:
                raise RuntimeError("Published releases are immutable in this workflow; use a new version")
            upload = release["upload_url"].split("{")[0] + "?name=" + quote(path.name)
            asset = github.request(upload, "POST", data=path.read_bytes())
            if asset["size"] != pack["bytes"] or asset.get("digest") != "sha256:" + pack["sha256"]:
                raise RuntimeError("GitHub upload verification failed")
        print("Verified release asset:", path.name)
    if release["draft"]:
        release = github.request(github.base + "/releases/" + str(release["id"]), "PATCH", dict(draft=False, make_latest="false"))

    # One commit publishes manifests and previews together. A concurrent main update is never forced.
    commit = github.request(github.base + "/git/commits/" + parent)
    tree_entries = []
    files = {}
    for path in sorted(hosting.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(hosting).as_posix()
        content = (json.dumps(catalog, indent=2) + "\n").encode() if name == "effects/catalog.json" else path.read_bytes()
        files[name] = content
    # Preserve newly authored encodings in the same commit for exact-byte inheritance by future batches.
    for _, pack in archives:
        for asset in pack["assets"]:
            if not (collection_dir / "source" / (asset["effectId"] + ".png")).is_file():
                continue
            path = collection_dir / "encoded" / (asset["effectId"] + ".webp")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != asset["sha256"]:
                raise RuntimeError("Reviewed encoding does not match its manifest")
            files[f"effect-assets/{collection}/encoded/{path.name}"] = content
    for name, content in files.items():
        blob = github.request(github.base + "/git/blobs", "POST", dict(encoding="base64", content=base64.b64encode(content).decode()))
        tree_entries.append(dict(path=name, mode="100644", type="blob", sha=blob["sha"]))
    tree = github.request(github.base + "/git/trees", "POST", dict(base_tree=commit["tree"]["sha"], tree=tree_entries))
    created = github.request(github.base + "/git/commits", "POST", dict(
        message=f"Publish realistic effect collection {tag}", tree=tree["sha"], parents=[parent]))
    github.request(github.base + "/git/refs/heads/main", "PATCH", dict(sha=created["sha"], force=False))
    print(json.dumps(dict(release=release["html_url"], commit=f"https://github.com/{repository}/commit/{created['sha']}",
                          catalog=f"https://raw.githubusercontent.com/{repository}/main/effects/catalog.json"), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="kedarmayekar/gif-packs")
    parser.add_argument("--check", action="store_true", help="Check saved authentication and repository permissions without writing")
    parser.add_argument("--collection", type=collection_name, default="pilot")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Invalid repository")
    try:
        publish(args.repository, args.check, args.collection)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
