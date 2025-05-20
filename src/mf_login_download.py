import os
import asyncio
import base64
import gzip
import json
import tempfile
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page


# ────────────────────────────────────────────────────────────────
# ユーティリティ
# ────────────────────────────────────────────────────────────────
def _load_storage_state_from_env() -> Optional[dict]:
    """
    ▸ 環境変数 ``MF_STORAGE_B64`` から storageState.json を復元
      - そのまま Base-64 文字列 でも
      - gzip 圧縮 → Base-64 文字列でも OK
    """
    b64 = os.getenv("MF_STORAGE_B64")
    if not b64:
        return None

    raw = base64.b64decode(b64)

    # gzip ならヘッダが 1F 8B
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)

    return json.loads(raw)


EMAIL_SELECTOR = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR = 'input[type="password"], input[name="mfid_user[password]"]'
DL_LINK_TEXT   = "ダウンロード"
CSV_LINK_ROLE  = "link"
CSV_LINK_NAME  = "CSVファイル"


# ────────────────────────────────────────────────────────────────
async def _login(page: Page) -> None:
    """ログインフォームが出る場合のみログインを行う。既に Cookie があればスキップ"""
    try:
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
    except Exception:
        # フォームが無い = 既にログイン済み
        return

    email    = os.environ["MF_EMAIL"]
    password = os.environ["MF_PASSWORD"]

    await page.fill(EMAIL_SELECTOR, email)
    await page.fill(PASS_SELECTOR, password)
    await asyncio.gather(
        page.keyboard.press("Enter"),
        page.wait_for_load_state("networkidle"),
    )


# ────────────────────────────────────────────────────────────────
async def download_csv_async(tmp_dir: str, headless: bool = True) -> Path:
    """MoneyForward から CSV をダウンロードし、保存ファイルパスを返す"""
    storage_state = _load_storage_state_from_env()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx_opts = {"storage_state": storage_state} if storage_state else {}
        context = await browser.new_context(**ctx_opts)

        page = await context.new_page()
        await page.goto("https://moneyforward.com/cf", wait_until="domcontentloaded")

        # ログイン必要なら実施
        await _login(page)

        # ダウンロード画面 ↴
        await page.locator("a", has_text=DL_LINK_TEXT).click()
        async with page.expect_download() as dl_info:
            await page.get_by_role(CSV_LINK_ROLE, name=CSV_LINK_NAME).click()

        download = await dl_info.value
        dest = Path(tmp_dir) / download.suggested_filename
        await download.save_as(dest)

        await browser.close()
        return dest


# ────────────────────────────────────────────────────────────────
# モジュール単体実行時: 動作確認用
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch MoneyForward CSV")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    out = asyncio.run(download_csv_async(tempfile.gettempdir(),
                                         headless=args.headless))
    print("Downloaded:", out)
