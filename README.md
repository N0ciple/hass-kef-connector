# 🏠🔉 KEF Connector
A Home Assistant integration for KEF speakers 🔊

KEF Connector is compatible with W2 Platform speakers:
- LSX II  
- LSX II LT  
- LS50 Wireless II  
- LS60 Wireless  
- XIO Soundbar  

---

## 📦 Installation

This custom component is available via [HACS](https://hacs.xyz).  
Search for **KEF Connector** in HACS and click **Download**. Restart Home Assistant to complete installation.

**Manual installation**  
Copy the [`kef_connector`](custom_components/kef_connector) folder into your Home Assistant `config/custom_components` directory. Restart Home Assistant to activate the integration.

---

## ⚙️ Configuration

KEF Connector uses **Config Flow** and is configured entirely through the **Home Assistant UI**.  
**YAML configuration is no longer supported.**

You can add the integration manually or wait for it to be discovered.

### 🔍 Auto Discovery
When your KEF speaker is discovered via Google Cast or AirPlay:
- **Name**, **IP Address** and **Speaker Model** are automatically filled in.
- You can review and adjust parameters before completing setup.

### 🛠 Manual Setup
If your speaker isn’t discovered automatically, you can add it manually via the Integrations page.  
You’ll be prompted to enter:

| Field                     | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| **IP Address**            | IP of your KEF speaker (e.g. `192.168.1.42`)                                |
| **Speaker Model**         | Choose from LSX II, LSX II LT, LS50 Wireless II, LS60 Wireless, or XIO      |
| **Scan Interval**         | How often to poll the speaker when online (5–300 seconds)                   |
| **Offline Retry Interval**| How often to check if an offline speaker is back online (30–600 seconds)    |
| **Volume Step**           | Volume change per up/down command (0.01–0.10)                               |
| **Maximum Volume**        | Safety limit for volume (0.1–1.0)                                           |

All these settings can be changed later from the **Integration settings page**.

---

## 🔁 Migrating from YAML

If you previously configured KEF Connector via `configuration.yaml`:
- Remove any `kef_connector` entries from your YAML file.
- Install or enable the integration via the UI:  
  **Settings → Devices & Services → Add Integration → KEF Connector**
- Recreate your previous settings during setup.  
  All parameters are editable later from the Integration page — no restart required.

---

## 📚 Documentation & Support

- [KEF Connector GitHub](https://github.com/N0ciple/hass-kef-connector)  
- [Issue Tracker](https://github.com/N0ciple/hass-kef-connector/issues)  
- [Library used: pykefcontrol](https://github.com/N0ciple/pykefcontrol)
