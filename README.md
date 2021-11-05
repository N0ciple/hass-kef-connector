# hass-kef-connector
A Home Assistant integration for the Kef LS50W2 🔊

- [hass-kef-connector](#hass-kef-connector)
  - [Installation and configuration](#installation-and-configuration)
    - [⬇️ Installation](#️-installation)
    - [🔧 Configuration](#-configuration)
      - [📜 Platform configuration options](#-platform-configuration-options)
      - [🧑‍🔬 Full configuration example](#-full-configuration-example)

## Installation and configuration

### ⬇️ Installation
This custom component is currently being integrated into [HACS](https://hacs.xyz). 
However, if you want to use it asap, you can either install it manually or add it as a custom repository in HACS.

**Custom HACS repository**
Go to your Home Assistant instance, then the HACS tab and then clic on `Integrations`. Clic on the 3 dots on the top right corner. Select `Custom repositories`. Add the following url : `https://github.com/N0ciple/hass-kef-connector`, and select  `Integration` for the category. Finally clic add.\
Once this is done, clic `explore & add repositories` on the bottom right corner. Search for "Kef Connector", clic on it and then clic on `Install this repository in HACS`. Now, follow the instructions in the [configuration](#-configuration) section.


**Manual Installation**
Copy the [kef_connector](custom_components/kef_connector) folder in your home assistant `config/custom_components` folder, and then follow the [configuration](#-configuration) section.

### 🔧 Configuration

In your `configuration.yaml` file, add the following :

```yaml
media_player:
  - platform: kef_connector
    host: <IP-of-your-speakers>
```
⚠️ _Replace_ `<IP-of-your-speakers>` _with the correct IP._ 

More information on how to find the IP of your Kef speakers [here](https://github.com/N0ciple/pykefcontrol#-get-the-ip-address).

#### 📜 Platform configuration options

Here is the list of the variables you can set if your `configuration.yaml` file.

| option           | required     | default value | comment|
| ---------------- | ------------ | -------------|-------------------- |
| `host`           | **Required** | `None`        | This should be a string in the form `www.xxx.yyy.zzz`, being the IP address of your speakers.|
| `name`           | _Optional_   | _see comment_ | If you do not specify a `name`, the integration will fetch the name you set up on the KefConnect app for your speakers, if any. If you specify a `name` property, this name will be used instead.|
| `maximum_volume` | _Optional_   | `1.0`         | This should be a float between 0 and 1. 0 is muted and 1 is maximum volume. Bear in mind that this option **does not** override the maximum volume set in the KefConnect app. It will prevent hass from setting a volume higher than `maximum_volume`|
| `volume_step`    | _Optional_   | `0.03`        | This should be float bewteen 0 and 1 (however it is **not recommended** to set it higher than 0.1). This value is by how much volume will be changed when calling   `media_player.volume_up` or `media_player.volume_down` services, by clicking on ![volume_down_up](assets/images/volume_down_up.png) for example. |

#### 🧑‍🔬 Full configuration example
This is just and example ! You can copy it but **at least** change the `host` value to the IP address of you speakers. More info on how to find the IP address [here](https://github.com/N0ciple/pykefcontrol#-get-the-ip-address).
```yaml
media_player:
  - platform: kef_connector
    host: 192.168.1.42
    name: "My Kef Speakers"
    maximum_volume: 0.7
    volume_step: 0.02
```
