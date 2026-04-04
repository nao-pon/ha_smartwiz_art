# Home Assistant 用 SMARTWIZ+ art

**SMARTWIZ+ art 電子ペーパーパネル**のための強力な Home Assistant カスタム統合です。
ローカルデバイス登録、高度な画像レンダリング、および信頼性の高いプッシュワークフローを実現します。

---

## ✨ 主な機能

### 🔧 デバイス連携

* Config Flow によるセットアップ
* Zeroconf 自動検出
* ローカル登録 / 登録解除
* キー交換

---

### 🖼️ レンダリング

* テンプレート描画（today など）
* エンティティデータ連携
* 多言語対応（日本語 / 英語）
* テーマ・レイアウト対応
* 解像度対応（将来のデバイスにも対応）

---

### 📸 画像処理

* フォトプリセット
* 明るさ・コントラスト自動調整
* フィットモード（crop / fit / stretch）
* ディザリング制御
* パレット変換

---

### 🚀 プッシュ

* update_and_push 統合処理
* リトライ機構
* スリープ対応
* 最新画像優先

---

### 📊 診断

* 最終プッシュ時刻
* プッシュ状態（リトライ含む）
* 実行状態の属性情報

---

## 📦 インストール

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nao-pon&repository=ha_smartwiz_art&category=integration)

1. HACS → Integrations
2. Custom Repository 追加
3. **SMARTWIZ+ art** をインストール
4. Home Assistant 再起動
5. デバイスのボタンを押して自動検出

> [!IMPORTANT]
> デバイスの Wi-Fi 設定は公式アプリで行ってください。
> また、この統合で使用するには、公式アプリ上からデバイスを削除する必要があります。
> (公式アプリに登録されたままだと、鍵交換が失敗します。)

---

### 手動

```text
config/custom_components/smartwiz_art/
```

に配置して再起動

---

## 📱 Android Wi-Fi セットアップアプリ（おまけ）

SMARTWIZ+ art デバイスの Wi-Fi 設定のみを行うシンプルな Android アプリです。

* ユーザー登録不要
* BLE 経由で Wi-Fi 設定が可能

👉 ダウンロード (Android/v1.0.1): [smartwiz_art_setup_1.0.1.apk](https://github.com/nao-pon/ha_smartwiz_art/releases/download/v1.0.0/smartwiz_art_setup_1.0.1.apk)

> [!NOTE]
> このアプリは Wi-Fi 設定専用の補助ツールです。
> Zeroconf により device_id は Home Assistant 側で取得可能なため、
> Wi-Fi 設定のみ行えば本統合を利用できます。

---

## ⚙️ 設定

* device_id（必須）
* host（任意）
* 解像度

---

## 🧩 サービス

主に使うのは：

* `update_and_push` ⭐

---

### 使用例

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

## 🔁 運用のポイント

デバイスは：

* 普段スリープ
* 約1時間ごとに1分起床
* ボタンでも起床可能

👉 推奨：

* 約10秒間隔でリトライ
* 最新画像を常に送る

---

## ⚠️ 注意

* ローカル通信のみ
* 登録失敗時：

  * 公式アプリから削除
  * 再登録
* スリープ中：

  * ボタンで起こす
  * 1分以内に実行

---

## 📊 エンティティ

* Last Push
* Push Status

---

## 🛠️ 応用

* input_selectでスライドショー
* automationと組み合わせ
* variables / source_map活用

---

## 📊 source_map 設定

`source_map` は Home Assistant のエンティティとテンプレート表示内容を対応付ける設定です。

シンプルな指定：

```yaml
source_map:
  weather: weather.home
  message: input_text.smartwiz_message
```

属性を使った指定：

```yaml
source_map:
  high_temp:
    entity_id: weather.home
    attribute: forecast.0.temperature
```

---

### 🔑 優先順位

```
variables > source_map > default
```

---

### 📚 詳細ドキュメント

👉 https://github.com/nao-pon/smartwiz_art/blob/main/docs/source_map.md

---

### 💡 使用例

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
    lang: ja
```

---

## 🔧 variables (上書き設定)

`variables` (変数) を使用してテンプレートデータを上書きまたは補足することができます。

```yaml
variables:
  message: "Custom message"
  temperature: "25 / 18℃"
```

優先順位:

```
variables > source_map > default
```

詳細ドキュメント:
👉 https://github.com/nao-pon/smartwiz_art/blob/main/docs/variables.md

---

## 📦 Blueprint（スライドショー自動化）

このリポジトリにはスライドショー用の Blueprint も含まれています。

---

### Blueprint のインポート方法

1. **設定 → オートメーションとシーン → ブループリント**
2. 「Blueprintをインポート」
3. 以下のURLを貼り付け

```text
https://raw.githubusercontent.com/nao-pon/ha_smartwiz_art/main/blueprints/automation/smartwiz_art/slideshow-ja.yaml
```

---

### このBlueprintでできること

* input_select の画像を順送り
* 一定間隔で update_and_push 実行
* HA再起動後の自動復帰
* 最終push時刻ベースで再開
* スリープデバイスにも対応

---

### 必要なもの

* SMARTWIZ+ art 統合
* 最終push時刻センサー
* input_select（画像リスト）
* timer エンティティ

---

## 🐞 サポート

* Issues:
  https://github.com/nao-pon/ha_smartwiz_art/issues

---

## 📄 ライセンス

MIT License
