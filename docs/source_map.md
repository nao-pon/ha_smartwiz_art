# SMARTWIZ+ art – source_map Specification

This document describes how to configure `source_map` for SMARTWIZ+ art templates.

---

## 🧩 Overview

`source_map` defines how Home Assistant entities are mapped to template data.

```yaml
source_map:
  key: sensor.entity_id
```

Or with attribute access:

```yaml
source_map:
  key:
    entity_id: weather.home
    attribute: forecast.0.temperature
```

---

## 🔑 Priority Rules

Values are resolved in the following order:

```
variables > source_map > default
```

* `variables`: highest priority (manual override)
* `source_map`: entity-based values
* `default`: fallback value inside renderer/resolver

---

## 🧠 Supported Formats

### 1. Simple entity

```yaml
weather: weather.home
```

---

### 2. Entity + attribute

```yaml
high_temp:
  entity_id: weather.home
  attribute: forecast.0.temperature
```

---

### 3. Nested attribute path

```yaml
attribute: forecast.0.temperature
```

Explanation:

* `forecast` → list
* `0` → index (today)
* `temperature` → value

---

## 📋 today Template

### Example

```yaml
source_map:
  weather: weather.home

  high_temp:
    entity_id: weather.home
    attribute: forecast.0.temperature

  low_temp:
    entity_id: weather.home
    attribute: forecast.0.templow

  rain:
    entity_id: weather.home
    attribute: forecast.0.precipitation_probability

  schedule: sensor.today_schedule
  home_status: sensor.home_status

  message: input_text.smartwiz_message
  image_path: input_select.smartwiz_pics
```

---

### Keys

#### weather

* Weather condition (used for icon + label)

---

#### high_temp / low_temp

* Daily temperature
* Usually from weather forecast

---

#### rain

* Precipitation probability (%)

---

#### schedule

Supports:

```yaml
schedule:
  - Meeting
  - Shopping
```

or

```yaml
schedule: |
  Meeting
  Shopping
```

---

#### home_status

Multiple status lines

---

#### message

Free text

---

#### image_path

* File path or input_select value

---

## ⚙️ Smart Defaults (today)

If not specified:

* `rain` → derived from weather forecast
* `home_status` → generated from:

  * lock state
  * indoor temperature

---

## 📢 notice Template

### Example

```yaml
source_map:
  title: input_text.notice_title
  body: input_text.notice_body
  level: input_select.notice_level
  icon: input_text.notice_icon
```

---

### Keys

#### title

Notice title

---

#### body

Main content

---

#### level (optional)

* info
* warning
* alert

---

#### icon (optional)

* emoji or short text

---

## 🔧 variables Override

You can override any value using `variables`:

```yaml
variables:
  message: "Custom message"
  temperature: "25 / 18℃"
```

---

## 💡 Tips

### Use forecast attributes

```yaml
attribute: forecast.0.temperature
```

→ ensures daily data instead of current state

---

### Prefer structured format for complex data

```yaml
weather:
  entity_id: weather.home
  attribute: forecast.0.condition
```

---

### Keep templates minimal

Only define what you need — missing values are auto-filled.

---

## 🚀 Best Practice

* Start simple
* Add only required keys
* Use `variables` for overrides
* Use attribute paths for precise data

---

## 📎 Related

* Templates: `render/template_*.py`
* Data builders: `core/resolver.py`
* Models: `core/models.py`

---

## 🧪 Example (Full)

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
