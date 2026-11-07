# KEF Connector

Home Assistant integration for KEF W2-platform wireless speakers: LS50 Wireless II, LS60 Wireless, LSX II, LSX II LT, XIO and LS LUXE. It talks to the speaker over the local network through [pykefcontrol](https://github.com/N0ciple/pykefcontrol), with no cloud involved.

[![Open in HACS / Marketplace](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=N0ciple&repository=hass-kef-connector&category=integration)
[![Add the integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=kef_connector)

## Features

- Local push: state changes appear as soon as the speaker reports them.
- Set up from the UI; speakers are found automatically through zeroconf.
- Media player with power, volume, mute, source selection, transport controls, play media and media browsing.
- EQ/DSP settings (treble, bass extension, desk and wall modes, subwoofer...) and speaker settings (LEDs, auto standby, maximum volume...) as entities, plus restart and Bluetooth pairing buttons. Only what the speaker model supports is created; rarely used settings are disabled by default.
- Diagnostics download for bug reports.

Requires Home Assistant 2026.10.0 or newer.

## Installation

With HACS or the Home Assistant Marketplace: click the badge above, or search for "KEF Connector", download it and restart Home Assistant. Pre-releases are only offered if you enable the pre-release switch.

Manually: copy the `custom_components/kef_connector` folder into the `custom_components` folder of your Home Assistant configuration (or unzip `kef_connector.zip` from a release into `custom_components/kef_connector`), then restart.

## Configuration

Go to Settings > Devices & services. A discovered speaker is offered automatically; otherwise click "Add integration", pick KEF Connector and enter the speaker's IP address (use a static lease on your router). Use the second badge above to jump straight to it.

The integration options "Volume cap in Home Assistant" and "Volume step in Home Assistant" are expressed in percent and only apply to volume changes made from Home Assistant; the speaker's own maximum volume and volume step are separate entities (Speaker maximum volume, Speaker volume step).

## Upgrading from 0.x

YAML configuration is no longer the way to set up the integration, but your existing `media_player: - platform: kef_connector` block is imported automatically at the first start: the entity is kept, so automations and dashboards keep working. Once the import has happened, Home Assistant shows a repair asking you to remove the YAML block; delete it from `configuration.yaml` and restart. YAML support will be removed around mid-2027.

Things that change: the speaker now appears as a device with additional entities, and the volume options are now in percent. See the [changelog](CHANGELOG.md). If you had renamed the media player entity yourself, Home Assistant now shows the device name in front of your custom name: check the name after upgrading and adjust it if needed.

**Make a backup before upgrading.** Going back to 0.x afterwards is not clean: the old version takes the entity back from the YAML block, and the new config entry fails to load until you delete it by hand. Restoring the backup is the simple way back.

## Playing files and media

The media player can play a stream URL or a Home Assistant media source item (radio, TTS...) directly on the speaker. For full file playback (local media, DLNA/Plex/Jellyfin servers, track position), the speaker is also a DLNA renderer and a Google Cast device: use Home Assistant's built-in [DLNA Digital Media Renderer](https://www.home-assistant.io/integrations/dlna_dmr/) or [Google Cast](https://www.home-assistant.io/integrations/cast/) integration alongside this one. KEF Connector keeps handling power, source, volume and settings.

## Troubleshooting

Download diagnostics from the speaker's device page (three dots menu > Download diagnostics) and attach them to any bug report. To get debug logs, add this to `configuration.yaml`, restart, reproduce the problem and download the full log from Settings > System > Logs:

```yaml
logger:
  default: warning
  logs:
    custom_components.kef_connector: debug
    pykefcontrol: debug
```

Report problems in the [issue tracker](https://github.com/N0ciple/hass-kef-connector/issues).

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md). Licensed under Apache-2.0.
