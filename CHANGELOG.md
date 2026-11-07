# Changelog

## [1.0.0-beta.1](https://github.com/N0ciple/hass-kef-connector/compare/0.6.5...1.0.0-beta.1) (2026-11-07)

### ⚠ BREAKING CHANGES

* YAML configuration is deprecated. Existing `media_player` platform entries are imported automatically into a config entry; remove the YAML block when the repair appears. YAML support will be removed around mid-2027.
* The speaker is now a device with additional entities (EQ/DSP and speaker settings).
* `maximum_volume` and `volume_step` options are now expressed in percent.
* A media player entity renamed by hand is now shown with the device name in front of the custom name; check its name after upgrading.
* Requires Home Assistant 2026.10.0 or newer.
* Requires pykefcontrol 1.0 (installed automatically).
* No clean downgrade: going back to 0.x leaves a config entry that fails to load and must be deleted by hand. Back up Home Assistant before upgrading.

### Features

* UI setup with zeroconf discovery
* local push updates
* play media and media browsing
* EQ/DSP and speaker settings as entities
* diagnostics

## [0.6.5](https://github.com/N0ciple/hass-kef-connector/compare/0.6.4...0.6.5)

Earlier releases: see the [GitHub releases](https://github.com/N0ciple/hass-kef-connector/releases).
