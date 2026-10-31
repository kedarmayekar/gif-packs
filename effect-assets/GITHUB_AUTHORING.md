# Publish future Real Effects entirely from GitHub

The catalog-driven app needs to be distributed once. After that, supported
image effects, categories, names, ordering, pack prices, images, previews and
motion parameters are content in `kedarmayekar/gif-packs`; they do not require
new `EffectItem` or `EffectCategory` values or another Android build.

The existing procedural/vector Effects picker remains bundled app code.
The remote renderer supports PNG/WebP cutouts, bobbing, drift, rotation and
sparkle. Adding a new rendering engine or multi-frame format still requires
an app change. GitHub content is data, never downloaded executable code.

## Repository layout

```text
tools/                          build, verify and publish scripts
.github/workflows/publish-real-effects.yml
effect-assets/<collection>/collection.json
effect-assets/<collection>/source/<effectId>.png
effect-assets/<collection>/encoded/      reviewed reusable images
effect-assets/<collection>/generation.json
effects/catalog.json            live discovery index
effects/<packId>/manifest.json   live pack metadata
effects/previews/<effectId>.webp
GitHub Releases                 immutable versioned ZIP archives
```

`remote-v6` is a staged migration collection of the existing 35 cutouts with
explicit labels, prices and motion. It does not introduce a new category beyond
CoffeeTea. It has not replaced the live catalog. Earlier source collections are
retained so the first GitHub build can reuse their reviewed encoded bytes.

## Add a batch using only the effects repository

1. Create a new directory such as `effect-assets/cafe-v7/`. Add transparent RGBA
   PNG sources under `source/`, with filenames matching their stable effect IDs.
2. Add `collection.json` (example below). Any valid new category/effect IDs work;
   no Android enum or Python collection allowlist needs changing.
3. Commit the files to `gif-packs`. In GitHub Actions, run **Build and publish
   Real Effects** with the collection directory name and `publish` disabled.
4. Download the build artifact and inspect the preview sheets on dark and light
   backgrounds. When ready, run the same workflow with `publish` enabled.
5. The app refreshes discovery whenever Real Effects opens or **Check for
   updates** is tapped. Owners download/update packs once; images and the last
   validated catalog remain available offline after app restarts.

```json
{
  "version": 7,
  "tag": "effects-v7",
  "sourceRoots": ["source"],
  "groups": {
    "future-cafe": {
      "category": "FutureCafe2050",
      "title": "Future Café",
      "price": 75,
      "description": "A new collection published from GitHub.",
      "effects": ["MoonLatte2050"]
    }
  },
  "assets": {
    "MoonLatte2050": {
      "label": "Moon Latte",
      "motion": {"bob": 0.018, "drift": 0.02, "rotation": 3, "sparkle": false}
    }
  }
}
```

The example is a specification, not an included/generated image. Supply a real
`source/MoonLatte2050.png` before building it.

## Updating existing categories

Keep the category ID stable to retain ownership (`effect_<category>`). Keep
effect IDs stable to retain saved references. Always increment the version and
use a new release tag. A replacement pack must include every effect you want
available in that category; retain prior sources or use inherited `sourceRoots`
as in `remote-v6`. The publisher merges unrelated categories into the live
catalog. To retire a category, remove its live catalog entry in GitHub; installed
images remain available to saved effects offline.

`price` is a nonnegative integer in Celestial Tears; zero means free. Existing
owners stay owners after a price change. Legacy manifests with no price use
the original category prices for known categories and free for new categories.
Always set an explicit price for new content. Purchase uses the current online
offer and the existing conditional database debit.

Labels/titles are limited to 120 characters; descriptions to 2,000. Category IDs
use letters, digits, `_` and `-`, starting with a letter, at most 64 characters.
Effect IDs use letters/digits, starting with a letter, at most 64 characters and
must be globally unique. Pack IDs are lowercase letters/digits/hyphens, starting
with a letter, at most 40 characters. Collection names are simple directory names.

Motion values are bounded: `bob` and `drift` are fractions of rendered size in
0–0.2, `rotation` is degrees in 0–30, and `sparkle` is boolean. Defaults are
0.018, 0, 1.2 and false. Catalog order controls category/effect order.

The app validates repository origin, schema, sizes, SHA-256 checksums, ZIP paths,
dimensions and metadata before promoting a download. Invalid/interrupted updates
retain the last installed pack. Future catalogs are cached atomically; offline
fallback never requires a successfully completed network refresh.

## Local equivalent

```powershell
python -m pip install 'Pillow>=10,<14'
python -m unittest discover -s tools -p 'test_effect_pack*.py'
python tools/build_effect_packs.py --collection cafe-v7
python tools/verify_effect_packs.py --collection cafe-v7
python tools/publish_effect_packs.py --collection cafe-v7 --check
python tools/publish_effect_packs.py --collection cafe-v7
python tools/verify_effect_packs.py --collection cafe-v7 --live
```

The workflow uses its repository-scoped `GITHUB_TOKEN`. Local publishing uses
saved Git Credential Manager credentials or a locally set `GH_TOKEN`/
`GITHUB_TOKEN`; the app contains no publishing credentials.

Publication also commits encodings for sources owned by that collection. Future
batches can inherit those reviewed bytes instead of depending on re-encoding
with a potentially different Pillow version. The catalog update uses the same
pinned Git parent it read; a concurrent main update is rejected instead of lost.
