# MF Importer

Money Forward ME から当月分のCSVを自動ダウンロードし、Google Sheets にアップロードするための **個人用** スクリプトです。
GitHub Actions 上で毎日実行し、自分の家計管理データを自動で取得・整理します。

---

## 📂 リポジトリ構成

```text
.
├─ .github/
│   └─ workflows/
│       └─ import.yml        # GitHub Actions ワークフロー
├─ src/
│   ├─ main.py               # メインエントリーポイント
│   ├─ mf_login_download.py  # Playwright でログイン & CSV取得
│   ├─ normalize.py          # データ整形処理
│   └─ gsheet.py             # Google Sheets へのアップロード
├─ requirements.txt          # Python 依存リスト
└─ README.md
```

---

## 🚀 機能

- Money Forward ME へのステルスログイン（Playwright）
- 当月分CSVの取得とリネーム保存
- Google Sheets への自動アップロード
- エラー時にスクリーンショットをアーティファクトとして収集

---

## 🛠 前提条件

- Python 3.12+
- Node.js（Playwright CLI を使う場合）
- GitHub リポジトリに以下の **Secrets** を登録済みであること
  - `MF_EMAIL`
  - `MF_PASSWORD`
  - `MF_STORAGE_B64`
  - `GSHEET_KEY`
  - `GSHEET_SERVICE_JSON`

---

## ⚙️ ローカルセットアップ

```bash
git clone https://github.com/ino-taku/mf-importer.git
cd mf-importer

# 仮想環境を作成・有効化 (任意)
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows PowerShell

# 依存ライブラリをインストール
pip install -r requirements.txt

# Playwright ブラウザをインストール
python -m playwright install --with-deps
```

---

## 🔑 Secrets／環境変数

| 変数名                 | 内容                                                         |
|:----------------------|:------------------------------------------------------------|
| `MF_EMAIL`            | Money Forward ME のログインメール                            |
| `MF_PASSWORD`         | 上記アカウントのパスワード                                   |
| `MF_STORAGE_B64`      | `storageState.json` を **gzip→base64** エンコードした文字列 |
| `GSHEET_KEY`          | Google Sheets のキー                                         |
| `GSHEET_SERVICE_JSON` | サービスアカウントキー（JSON 文字列）                        |

---

## 📦 storageState.json の生成手順（月1回更新）

1. ローカルで以下スクリプト（例）を用意し、`scripts/generate_storage_state.py` として保存。

   ```python
   # scripts/generate_storage_state.py
   from playwright.sync_api import sync_playwright

   with sync_playwright() as p:
       browser = p.chromium.launch(headless=False)
       context = browser.new_context(locale="ja-JP")
       page = context.new_page()
       page.goto("https://id.moneyforward.com/me")
       print("ブラウザで手動ログインしてください。ログイン後Enterを押すと完了します。")
       input()
       context.storage_state(path="storageState.json")
       browser.close()
       print("storageState.json が生成されました。")
   ```

2. スクリプトを実行し、手動ログイン後に `storageState.json` を出力。

   ```bash
   python scripts/generate_storage_state.py
   ```

3. 出力された `storageState.json` を **gzip → base64** エンコード。

   ```bash
   gzip -c storageState.json | base64
   ```

4. 上記文字列をコピーし、GitHub の **Settings > Secrets** に `MF_STORAGE_B64` として登録。

> **Tip:** 毎月初めにこの手順を実施し、新しい Cookie／localStorage 情報で Secrets を更新してください。

---

## 📅 GitHub Actions ワークフロー

- **トリガー**
  - `schedule: cron('0 0 * * *')` → UTC 0:00（JST 9:00）に毎日実行
  - `workflow_dispatch` → 手動実行
  - `push` → `main` / `fix/**` ブランチへのプッシュ時

- **主なステップ**
  1. Python + Playwright ブラウザをセットアップ
  2. `python -m src.main` を実行
  3. 失敗時に `login_issue.png` をアーティファクトとして保存

---

## 🐛 トラブルシュート

- **KeyError: 'GSHEET_SERVICE_JSON'**
  → Secrets に `GSHEET_SERVICE_JSON` が正しく登録されているか確認
- **BrowserType.launch: Executable doesn't exist**
  → `python -m playwright install --with-deps` が実行されているかチェック
- **login_issue.png が見当たらない**
  → ログイン失敗時のみ生成されます。手動実行で意図的に失敗させて Artifacts を確認

---

## 🤝 開発フロー

1. ブランチ命名は `fix/` / `feature/` から開始
2. プルリクエストを作成 → CI 通過 & レビュー → **main** へマージ
3. 定期実行後のログ・アーティファクトを確認

---

以上でセットアップ完了です。何か問題があれば Issue を立ててください！
