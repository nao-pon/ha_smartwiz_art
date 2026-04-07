# SMARTWIZ+ art for Home Assistant

A powerful Home Assistant custom integration for **SMARTWIZ+ art e-paper panels**, enabling local device registration, advanced image rendering, and reliable push workflows.

---

## ✨ Features

### 🔧 Device Integration

* Config Flow UI setup
* Zeroconf auto discovery
* Local device registration / unregistration
* Secure key exchange handling

### 🖼️ Rendering System

* Template-based rendering (`today`, `today_with_image`, etc.)
* Dynamic data binding from Home Assistant entities
* Multi-language rendering (EN / JA)
* Theme and layout support
* Resolution-aware rendering (future-proof for different panels)

### 📸 Image Processing

* Photo presets (`auto`, `natural`, etc.)
* Automatic brightness / contrast adjustment
* Image fit modes:

  * `crop`
  * `fit`
  * `stretch`
* Optional dithering control
* Palette-based rendering support (e-paper optimized)

### 🚀 Push System

* `update_and_push` unified workflow
* Retry loop with smart recovery
* Wake-window aware delivery
* Always prioritizes latest image

### 📊 Diagnostics

* Last push timestamp
* Push status (including retry state)
* Runtime info via sensor attributes

---

## 📦 Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nao-pon&repository=ha_smartwiz_art&category=integration)

1. Go to HACS → Integrations
2. Add this repository as a Custom Repository
3. Install **SMARTWIZ+ art**
4. Restart Home Assistant
5. Press the device button to trigger auto discovery

> [!IMPORTANT]
> Configure Wi-Fi using the official app first.
> Then remove the device from the app before using this integration.
> (Otherwise, key exchange will fail.)

---

### Manual

```text
config/custom_components/smartwiz_art/
```

Restart Home Assistant and add the integration.

---

## 📱 Android Wi-Fi Setup App (Optional)

A simple Android app for configuring Wi-Fi on SMARTWIZ+ art devices.

* No official app required
* No account registration required
* Wi-Fi provisioning via BLE

👉 Download (Android/v1.0.1): [smartwiz_art_setup_1.0.1.apk](https://github.com/nao-pon/ha_smartwiz_art/releases/download/1.0.0/smartwiz_art_setup_1.0.1.apk)

> [!NOTE]
> This is a lightweight helper app for Wi-Fi setup only.
> Since device_id can be obtained via Zeroconf in Home Assistant,
> only Wi-Fi configuration is required to use this integration.

---

## ⚙️ Configuration

Supports:

* Manual input:

  * device ID (required)
  * host (optional)
  * resolution (width / height)
* Zeroconf auto discovery

💡 If IP changes dynamically, leaving host empty is recommended.

---

## 🧩 Services

Main services:

* `update_and_push` ⭐ recommended
* `push_file`
* `update`
* `render_today`
* `register_device`
* `unregister_device`

---

### Example

```yaml
action: smartwiz_art.update_and_push
data:
  ha_device_id: "{{ device_id }}"
  template: today_with_image
  filename: output.png
  image_path_entity: input_select.smartwiz_art_pics
  message_entity: input_text.smartwiz_art_message
  photo_preset: auto
  fit_mode: crop
```

---

## 🔁 Automation Strategy (Important)

SMARTWIZ+ art devices:

* Sleep most of the time
* Wake ~1 minute per hour OR via button

Recommended:

* Run push every ~10 seconds during wake window
* Use retry loop (integration handles this)
* Always push **latest image**

---

## ⚠️ Notes

* Local network only
* If registration fails:

  * remove device from official app
  * retry
* If device is sleeping:

  * press button
  * retry within ~1 minute

---

## 📊 Entities

* Last Push
* Push Status

---

## 🛠️ Advanced Tips

* Use input_select for slideshow image switching
* Combine with automation timers for slideshow
* Use variables / source_map for flexible templates

---

## 📊 source_map Configuration

`source_map` defines how Home Assistant entities are mapped to template data.

You can use simple entity IDs:

```yaml
source_map:
  weather: weather.home
  message: input_text.smartwiz_message
```

Or advanced attribute mapping:

```yaml
source_map:
  high_temp:
    entity_id: weather.home
    attribute: forecast.0.temperature
```

---

### 🔑 Priority

Values are resolved in the following order:

```
variables > source_map > default
```

---

### 📚 Full Documentation

👉 https://github.com/nao-pon/smartwiz_art/blob/main/docs/source_map.md

---

### 💡 Example

```yaml
action: smartwiz_art.update_and_push
data:
  template: today_with_image

  source_map:
    weather: weather.home

    high_temp:
      entity_id: weather.home
      attribute: forecast.0.temperature

    low_temp:
      entity_id: weather.home
      attribute: forecast.0.templow

    message: input_text.smartwiz_message
    image_path: input_select.smartwiz_pics

  variables:
    lang: en
```

---

## 🔧 variables (Overrides)

You can override or supplement template data using `variables`.

```yaml
variables:
  message: "Custom message"
  temperature: "25 / 18℃"
```

Priority:

```
variables > source_map > default
```

Full documentation:
👉 https://github.com/nao-pon/smartwiz_art/blob/main/docs/variables.md

---

## 📦 Blueprint (Slideshow Automation)

This repository also provides a ready-to-use Home Assistant Blueprint for slideshow automation.

### Import Blueprint

1. Go to
   **Settings → Automations & Scenes → Blueprints**
2. Click **Import Blueprint**
3. Paste the URL below:

```text
https://raw.githubusercontent.com/nao-pon/ha_smartwiz_art/main/blueprints/automation/smartwiz_art/slideshow.yaml
```

---

### What this Blueprint does

* Automatically cycles images from an `input_select`
* Calls `update_and_push` at a fixed interval
* Handles Home Assistant restarts
* Resumes timers based on last successful push
* Works with device sleep / wake behavior

---

### Requirements

You need:

* SMARTWIZ+ art integration installed
* A sensor with last push timestamp
* An `input_select` containing image paths
* A `timer` entity

---

## 🐞 Support

* Issues: https://github.com/nao-pon/ha_smartwiz_art/issues
* Repository: https://github.com/nao-pon/ha_smartwiz_art

---

## 📄 License

MIT License
