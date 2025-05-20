# -*- coding: utf-8 -*-
"""
MoneyForward 明細画面から CSV をダウンロードするユーティリティ
--------------------------------------------------------------
* 2025-05-21  replace deprecated wait_for_navigation → wait_for_load_state
  - Playwright ≥1.43 互換
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
    'a:has-text("ＣＳＶ")',
    'a[href*=".csv"]',
    'a[href*="csv_download"]',
    'button:has-text("CSV")',
    'text=/CSV.*ダウンロード/i',
]

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
    # ログイン後のリダイレクト完了を待つ
    await page.wait_for_load_state("networkidle")


def _decode_storage_state() -> Optional[dict]:
    """MF_STORAGE_B64 を base64(+gzip) で復元 → dict"""
    b64 = os.getenv("MF_STORAGE_B64")
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64)
        try:
            raw = gzip.decompress(raw)  # gzip なら展開、違えばそのまま
        except gzip.BadGzipFile:
            pass
        return json.loads(raw)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# CSV リンク検出
# --------------------------------------------------------------------------- #
async def _find_csv_link(page: Page):
    for css in CSV_PATTERNS:
        locator = page.locator(css).first
        try:
            await locator.wait_for(state="visible", timeout=5_000)
            return locator
        except Exception:
            continue

    # フォールバック：全リンク走査
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

        if not st:  # ストレージが無く未ログインなら
            await _login(page)

        # 旧 UI 向けダウンロードボタン
        try:
            await page.get_by_role("button", name=re.compile("ダウンロード")).click(timeout=5_000)
        except Exception:
            pass

        link = await _find_csv_link(page)
        async with page.expect_download() as dl_info:
            await link.click()
        download = await dl_info.value
        outfile = Path(tmp_dir) / download.suggested_filename
        await download.save_as(outfile)

        await context.close()
        await browser.close()
        return outfile


# --------------------------------------------------------------------------- #
# CLI テスト
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    out = asyncio.run(download_csv_async(tempfile.gettempdir(), headless=False))
    print("Saved:", out)
