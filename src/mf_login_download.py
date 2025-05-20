# -*- coding: utf-8 -*-
"""
MoneyForward 明細画面から CSV をダウンロードするユーティリティ
-----------------------------------------------------------------
* 2025-05-21  MF 新 UI (エクスポート→CSV) に対応
              - 事前に「エクスポート」をクリック
              - CSV リンク検出を強化
"""

import asyncio
import base64
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
    'a:has-text("CSVファイル")',
    'a:has-text("CSV")',
    'a[href*=".csv"]',
    'a[href*="csv_download"]',
    'button:has-text("CSV")',
    'text=/CSV.*ダウンロード/i',
]

EXPORT_BUTTON_TEXTS = ["エクスポート", "ダウンロード", "明細をエクスポート"]


# --------------------------------------------------------------------------- #
# 認証
# --------------------------------------------------------------------------- #
async def _login(page: Page) -> None:
    """フォームログイン（ストレージが無い場合のみ）"""
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
    await page.fill(EMAIL_SELECTOR, os.environ["MF_EMAIL"])
    await page.fill(PASS_SELECTOR, os.environ["MF_PASSWORD"])
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")


def _decode_storage_state() -> Optional[dict]:
    b64 = os.getenv("MF_STORAGE_B64")
    if not b64:
        return None
    raw = base64.b64decode(b64)
    try:
        raw = gzip.decompress(raw)
    except gzip.BadGzipFile:
        pass
    return json.loads(raw)


# --------------------------------------------------------------------------- #
# CSV リンク検出
# --------------------------------------------------------------------------- #
async def _click_export_if_exists(page: Page) -> None:
    for txt in EXPORT_BUTTON_TEXTS:
        try:
            await page.get_by_text(txt, exact=False).first.click(timeout=3_000)
            return
        except Exception:
            continue


async def _find_csv_link(page: Page) -> Page:
    # まず「エクスポート」ボタンをクリックしてメニューを開く
    await _click_export_if_exists(page)

    # ① パターンに一致する Locator を順に探す
    for css in CSV_PATTERNS:
        loc = page.locator(css).first
        try:
            await loc.wait_for(state="visible", timeout=10_000)
            return loc
        except Exception:
            continue

    # ② すべてのリンク／ボタンを総当たりで調査
    candidates = page.locator("a, button")
    for i in range(await candidates.count()):
        el = candidates.nth(i)
        try:
            text = (await el.inner_text()).strip()
            href = await el.get_attribute("href") or ""
        except Exception:
            continue
        if re.search(r"csv|ＣＳＶ", text, re.I) or re.search(r"csv", href, re.I):
            return el

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")


# --------------------------------------------------------------------------- #
# main download routine
# --------------------------------------------------------------------------- #
async def download_csv_async(tmp_dir: str, *, headless: bool = True) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context_kwargs = {}
        if (st := _decode_storage_state()):
            tmpjson = Path(tmp_dir) / "mf_state.json"
            tmpjson.write_text(json.dumps(st), encoding="utf-8")
            context_kwargs["storage_state"] = tmpjson

        context: BrowserContext = await browser.new_context(**context_kwargs)
        page: Page = await context.new_page()
        await page.goto(MONEY_URL, wait_until="domcontentloaded")

        if not st:
            await _login(page)

        link = await _find_csv_link(page)

        async with page.expect_download() as info:
            await link.click()
        dl = await info.value
        outfile = Path(tmp_dir) / dl.suggested_filename
        await dl.save_as(outfile)

        await context.close()
        await browser.close()
        return outfile


# --------------------------------------------------------------------------- #
# CLI テスト
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    out = asyncio.run(download_csv_async(tempfile.gettempdir(), headless=False))
    print("Saved:", out)
