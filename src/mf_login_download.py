# -*- coding: utf-8 -*-
"""
MoneyForward 明細画面から CSV をダウンロードするユーティリティ
--------------------------------------------------------------
* 2025-05-20  broaden CSV link detection to survive UI / A/B tests
  - _find_csv_link() で 7 パターンの locator → ページ内総走査の順に探索
  - 1 locator あたり 5 s タイムアウト・最大 40 s 程度で検出
* 2025-05-19  accept gzip-compressed MF_STORAGE_B64, etc.
"""
import asyncio
import gzip
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page, async_playwright

LOGIN_URL = "https://id.moneyforward.com/sign_in"
MONEY_URL = "https://moneyforward.com/"
EMAIL_SELECTOR = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR = 'input[type="password"], input[name="mfid_user[password]"]'

CSV_PATTERNS = [
    # 優先度順
    ('a:has-text("CSVファイル")'),
    ('a:has-text("CSV")'),
    ('a:has-text("ＣＳＶ")'),
    ('a[href*=".csv"]'),
    ('a[href*="csv_download"]'),
    ('button:has-text("CSV")'),
    ('text=/CSV.*ダウンロード/i'),
]

# --------------------------------------------------------------------------- #
# 認証まわり
# --------------------------------------------------------------------------- #


async def _login(page: Page) -> None:
    """通常フォームログイン（ストレージが無い場合のみ）"""
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
    await page.fill(EMAIL_SELECTOR, os.environ["MF_EMAIL"])
    await page.fill(PASS_SELECTOR, os.environ["MF_PASSWORD"])
    await asyncio.gather(
        page.wait_for_navigation(), page.click('button[type="submit"]')
    )


def _decode_storage_state() -> Optional[dict]:
    b64 = os.getenv("MF_STORAGE_B64")
    if not b64:
        return None
    data = gzip.decompress(
        gzip.compress(b"dummy")
    )  # quick import-side check that gzip is available
    try:
        raw = gzip.decompress(base64.b64decode(b64)) if b64[:3] == "H4s" else base64.b64decode(b64)
        return json.loads(raw)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# CSV ダウンロード
# --------------------------------------------------------------------------- #


async def _find_csv_link(page: Page):
    """
    CSV ダウンロード用 <a> または <button> を返す。
    表示名・href が変わるパターンが多いので複数ロケータを試行 → フォールバック総走査。
    """
    for css in CSV_PATTERNS:
        locator = page.locator(css).first
        try:
            await locator.wait_for(state="visible", timeout=5_000)
            return locator
        except Exception:
            continue

    # フォールバック：ページ内の <a> / <button> を総走査
    candidates = page.locator("a, button")
    for i in range(await candidates.count()):
        el = candidates.nth(i)
        try:
            txt = (await el.inner_text()).strip()
        except Exception:
            continue
        if re.search(r"csv|ＣＳＶ", txt, re.I):
            return el

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")


async def download_csv_async(tmp_dir: str, headless: bool = True) -> Path:
    """CSV をダウンロードしてファイルパスを返す"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        storage_state = _decode_storage_state()
        context_kwargs = {}
        if storage_state:
            # Playwright がファイルしか受け取らないので一時ファイルに書く
            tmpjson = Path(tmp_dir) / "mf_state.json"
            tmpjson.write_text(json.dumps(storage_state), encoding="utf-8")
            context_kwargs["storage_state"] = tmpjson

        context: BrowserContext = await browser.new_context(**context_kwargs)
        page: Page = await context.new_page()
        await page.goto(MONEY_URL, wait_until="domcontentloaded")

        # 未ログインならログイン
        if not storage_state:
            await _login(page)

        # 1) 画面右上「ダウンロード」アイコンをクリック（旧 UI）
        try:
            await page.get_by_role("button", name=re.compile("ダウンロード")).click(timeout=5_000)
        except Exception:
            pass  # アイコンが無い UI もあるので無視

        link = await _find_csv_link(page)
        async with page.expect_download() as dl_info:
            await link.click()
        download = await dl_info.value
        path = Path(tmp_dir) / download.suggested_filename
        await download.save_as(path)

        await context.close()
        await browser.close()
        return path


# --------------------------------------------------------------------------- #
# CLI テスト用
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    out = asyncio.run(download_csv_async(tempfile.gettempdir(), headless=False))
    print("Saved:", out)
