# SMARTWIZ+ art – variables Specification

This document describes how to use `variables` (variables_map) in SMARTWIZ+ art.

---

## 🧩 Overview

`variables` allows you to override or supplement values used in templates.

```yaml
variables:
  key: value
```

---

## 🔑 Priority

Values are resolved in the following order:

```
variables > source_map > default
```

---

## 🎯 Purpose

`variables` is used for:

* Manual override of values
* Adding extra data not available from entities
* Customizing display behavior

---

## 📋 Common Variables

### 🌐 Common (All Templates)

```yaml
variables:
  theme: washi
  template: today
  lang: ja
```

| Key      | Description        |
| -------- | ------------------ |
| theme    | UI theme           |
| template | Template name      |
| lang     | Language (ja / en) |

---

## 📊 today Template

```yaml
variables:
  date: "2026 / 4 / 7"
  weekday: "Tue"
  weather: "Sunny"
  temperature: "25 / 18℃"
  rain: "10%"

  schedule:
    - Meeting
    - Shopping

  home_status:
    - Door: Locked
    - Indoor: 23℃

  message: "Good morning!"
  image_path: "/config/www/pic.png"

  photo_preset: natural
```

---

### Keys

#### date / weekday

Override automatic date display

---

#### weather / temperature / rain

Override weather data

---

#### schedule

Supports list or multiline string

---

#### home_status

List of status lines

---

#### message

Free text

---

#### image_path

Image file path

---

#### photo_preset

* natural
* vivid
* mono
* auto

---

## 📢 notice Template

```yaml
variables:
  title: "System Alert"
  body: "Door is open"
  level: warning
  icon: "⚠️"
```

---

### Keys

#### title

Notice title

---

#### body

Main message

---

#### level

* info
* warning
* alert

---

#### icon

Emoji or short text

---

## 🔧 Behavior

### Override Example

```yaml
source_map:
  temperature:
    entity_id: weather.home
    attribute: forecast.0.temperature

variables:
  temperature: "Custom Value"
```

→ `variables` value is used

---

### Merge Example

```yaml
source_map:
  schedule: sensor.today_schedule

variables:
  schedule:
    - Extra Task
```

→ variables replaces entire value

---

## 💡 Tips

### Use variables for testing

```yaml
variables:
  weather: "Rainy"
```

→ no need to modify HA entities

---

### Use variables for fallback

```yaml
variables:
  message: "No data available"
```

---

### Combine with source_map

* source_map → dynamic data
* variables → static customization

---

## 🚀 Best Practice

* Keep source_map as main data source
* Use variables only when needed
* Avoid duplicating same values in both

---

## 📎 Related

* source_map: docs/source_map.md
* Templates: render/template_*.py
* Resolver: core/resolver.py

---
