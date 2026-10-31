# Catalog-driven Real Effects validation — 2026-10-31

- Final Android build and test APK assembled successfully offline.
- All 39 JVM tests passed, including new unknown-category/effect, legacy-schema,
  metadata-limit, price and unsafe-category regression cases.
- Device suite for existing rendering plus dynamic effects returned `OK (7
  tests)`; its opt-in public-rendering case was skipped and six checks ran.
- Final installed build reran all three `RemoteRealEffectsTest` checks and passed:
  unknown IDs survive offline caching, JSON and Parcelable restoration; the
  picker discovers and applies a new effect after refresh; and the shared editor
  renderer plus PNG writer retain actual image pixels.
- Opt-in public `EffectPackDownloadSmokeTest` passed against the existing v4
  catalog: download, pilot-to-current upgrades, offline decoding and preservation
  after invalid/cancelled replacement attempts. Tests use isolated preferences
  and files; test PNG exports are deleted.
- Three Python tests passed in both workspaces, covering arbitrary collection/
  category/effect IDs, deterministic archives, invalid collection paths, metadata
  validation, pinned-parent publication and preservation of reviewed encodings.
- `remote-v6` built and verified independently in the Android workspace and the
  effects hosting checkout: six packs, 35 effects, 5,888,258 archive bytes.
- All 35 image checksums exactly match Set 5. The migration adds metadata and
  generic app support without creatively modifying the reviewed images.
- `git diff --check` passed.

The migration collection is staged. It has not replaced the public effects
catalog and no v6 release was created. Publish it after distributing the
catalog-driven app. Future image/motion content can then be authored and
published entirely from the effects hosting repository.

The manual GitHub Actions workflow was validated through its local build/test/
publish-mock equivalents; a hosted Actions run has not yet been executed.
