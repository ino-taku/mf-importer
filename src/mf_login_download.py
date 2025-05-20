"""
MoneyForward から家計簿 CSV をダウンロードするユーティリティ
---------------------------------------------------------------
* Playwright  + Chromium
* GitHub Actions 用にヘッドレス動作＆ログイン状態の再利用に対応
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import os
import tempfile
from pathlib import Path
from typing import Final, Optional

from playwright.async_api import Page, async_playwright

# ─────────────────────────  セレクタ類  ──────────────────────────
EMAIL_SELECTOR: Final = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR:  Final = 'input[type="password"]'
DL_ICON_CSS:    Final = 'a i.icon-download-alt'     # 親 <a> がダウンロードリンク
CSV_LINK_TEXT:  Final = "CSVファイル"               # ダウンロードダイアログ内リンク

# ───────────────────────  ストレージの読み込み  ──────────────────────
def _load_storage() -> Optional[str]:
    """
    環境変数 **MF_STORAGE_B64** に保存された storageState.json (base64; gz 可)
    をデコードして一時ファイルに展開し、そのパスを返す。
    変数が無ければ None（＝新規ログインが必要）。
    """
    b64 = os.getenv("MF_STORAGE_B64")
    if not b64:
        return None

    raw = base64.b64decode(b64)
    try:                     # gz かどうか判定
        raw = gzip.decompress(raw)
    except OSError:
        pass

    tmp = Path(tempfile.gettempdir()) / "storageState.json"
    tmp.write_bytes(raw)
    return str(tmp)


# ─────────────────────────  ログイン処理  ──────────────────────────
async def _login(page: Page) -> None:
    """メールアドレス / パスワードを入力してログイン"""
    mf_id = os.environ["MF_EMAIL"]
    mf_pw = os.environ["MF_PASSWORD"]

    # フォームが出るまで最大 90 s 待機
    await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
    await page.fill(EMAIL_SELECTOR, mf_id)
    await page.fill(PASS_SELECTOR,  mf_pw)
    await page.press(PASS_SELECTOR, "Enter")

    # 家計簿トップへリダイレクトされるまで待機
    await page.wait_for_url("https://moneyforward.com/cf", timeout=90_000)


# ──────────────────  メイン: CSV を temp に保存して返す  ───────────────
async def download_csv_async(tmp_dir: str, *, headless: bool = True) -> Path:
    """CSV ファイルを tmp_dir にダウンロードし Path を返す"""
    storage_state = _load_storage()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox"],
        )

        context = await browser.new_context(storage_state=storage_state)
        page = await context.new_page()

        # 家計簿トップ（要ログイン）
        await page.goto("https://moneyforward.com/cf", wait_until="networkidle")

        # storage が無い場合はログイン
        if storage_state is None:
            await _login(page)
            # ログイン後の state を次回用に出力（ローカルでのみ利用）
            if not headless:
                await context.storage_state(path="storageState.json")

        # ▼▼▼ 1. ダウンロード画面へ（直リンクで確実に遷移） ▼▼▼
        await page.goto("https://moneyforward.com/cf/download",
                        wait_until="networkidle")

        # ▼▼▼ 2. CSV ファイルをクリック ▼▼▼
        await page.wait_for_selector(f'a:has-text("{CSV_LINK_TEXT}")', timeout=30_000)
        async with page.expect_download() as dl_info:
            await page.get_by_role("link", name=CSV_LINK_TEXT).click()

        download = dl_info.value
        csv_path = Path(tmp_dir) / download.suggested_filename
        await download.save_as(str(csv_path))

        await browser.close()
        return csv_path


# ────────────────────────────────  CLI  ───────────────────────────────
if __name__ == "__main__":
    async def _wrap():
        path = await download_csv_async(tempfile.gettempdir(), headless=False)
        print("Downloaded ->", path)

    asyncio.run(_wrap())
