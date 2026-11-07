# Development

## Dev Home Assistant instance

```sh
scripts/setup     # creates .venv with Home Assistant 2026.11 (do not use it for tests)
HASS_PORT=8124 scripts/develop   # 8123 may already be in use
```

The instance loads the integration from `./custom_components` through a symlink in `config/`. Log in with `dev` / `dev`; a long-lived token is stored in `config/.dev_token`. On NixOS, `scripts/setup` builds `pymicro-vad` and `pyspeex-noise` with gcc from `nix-shell -p gcc`.

## Tests and lint

```sh
scripts/test            # pytest + coverage in .venv-test (extra args go to pytest)
scripts/lint            # ruff check, ruff format --check, mypy --strict
scripts/lint --fix      # apply ruff fixes and formatting
```

`.venv-test` is separate from `.venv` because `pytest-homeassistant-custom-component` pins its own Home Assistant version (currently 2026.10.4). It is built from `uv.lock` (`uv sync --locked --group test`, as in CI), so `pykefcontrol` comes from PyPI at the version pinned in `pyproject.toml`. After changing a pin in `pyproject.toml`, run `uv lock` and commit `uv.lock` with it.

To test unreleased library changes, run with `KEF_PYKEFCONTROL_LOCAL=1` (e.g. `KEF_PYKEFCONTROL_LOCAL=1 scripts/test`): the sibling checkout `../pykefcontrol` is then installed editable over the PyPI release. The next run without the variable puts the locked release back.

CI also runs the suite against the newest Home Assistant release (latest `pytest-homeassistant-custom-component`, weekly and on every push). That job is informative: it warns early about upcoming breaking changes without blocking merges.

Git hooks (ruff, ruff format, JSON/YAML checks) are configured in `.pre-commit-config.yaml` for [prek](https://github.com/j178/prek), the runner Home Assistant core uses (pre-commit works too): `uvx prek install` once, or `uvx prek run --all-files`.

## Release process

Commits follow Conventional Commits. [release-please](https://github.com/googleapis/release-please) keeps a release PR open on `main` that bumps the `version` in `manifest.json`; it does not touch `CHANGELOG.md` (`skip-changelog`), which is written by hand. Merging it creates the tag (no `v` prefix, equal to the manifest version) and the GitHub release, then the same workflow builds `kef_connector.zip` and attaches it, since releases created with `GITHUB_TOKEN` cannot trigger `release.yml`. `release.yml` also runs on manually published releases and fails if the tag differs from the manifest version.

The zip asset is required for HACS/Marketplace download counts (`zip_release` in `hacs.json`).

Betas: `release-please-config.json` has `prerelease: true`, `prerelease-type: beta` and `release-as: 1.0.0-beta.1`. After the first beta, remove `release-as`; further betas then bump `beta.N`. For the stable release set `prerelease` to false and use `release-as` (e.g. `1.0.0`) once. Update `CHANGELOG.md` before merging the release PR, and after the release is created replace its generated body with curated notes (breaking changes and required actions first): HACS/Marketplace users see the release body in the update dialog.

The release-please workflow needs "Allow GitHub Actions to create and approve pull requests" enabled in the repository settings. Checks on the release PR do not run when it is opened with `GITHUB_TOKEN`; close and reopen it, or use a PAT, if you need them.

## pykefcontrol releases

The integration pins `pykefcontrol==1.0.0` in `manifest.json` (runtime) and in the `test` group of `pyproject.toml` (tests, locked in `uv.lock`); keep both pins equal. A change that needs a new library version: develop it with `KEF_PYKEFCONTROL_LOCAL=1`, publish the library from `../pykefcontrol` (`uv build && uv publish`), then bump both pins and run `uv lock`. Renovate opens these bumps for new releases.
