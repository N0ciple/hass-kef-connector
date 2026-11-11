# Changelog

## [1.0.1](https://github.com/N0ciple/hass-kef-connector/compare/1.0.0...1.0.1) (2026-11-11)

### Bug fixes

* Diagnostics no longer contain the speaker's Bluetooth address, the KEF member ids or the speaker's IP address, which was part of the YAML repair id ([#31](https://github.com/N0ciple/hass-kef-connector/issues/31)).

### Documentation

* Screenshots in the README.
* Physical inputs (TV, optical, coaxial, analog, USB) have no track information.

## [1.0.0](https://github.com/N0ciple/hass-kef-connector/compare/0.6.5...1.0.0) (2026-11-08)

First stable release of the 1.0 rewrite, identical to 1.0.0-beta.1: see its notes below for the breaking changes and new features.

## [1.0.0-beta.1](https://github.com/N0ciple/hass-kef-connector/compare/0.6.5...1.0.0-beta.1) (2026-11-07)

### ⚠ BREAKING CHANGES

* YAML configuration is deprecated. Existing `media_player` platform entries are imported automatically into a config entry; remove the YAML block when the repair appears. YAML support will be removed around mid-2027.
* The speaker is now a device with additional entities (EQ/DSP and speaker settings).
* `maximum_volume` and `volume_step` options are now expressed in percent.
* A media player entity renamed by hand is now shown with the device name in front of the custom name; check its name after upgrading.
* Requires Home Assistant 2026.10.0 or newer.
* Requires pykefcontrol 1.0 (installed automatically).

### Features

* UI setup with zeroconf discovery
* local push updates
* play media and media browsing
* EQ/DSP and speaker settings as entities
* diagnostics

## [0.6.5](https://github.com/N0ciple/hass-kef-connector/compare/0.6.4...0.6.5)

Earlier releases: see the [GitHub releases](https://github.com/N0ciple/hass-kef-connector/releases).
