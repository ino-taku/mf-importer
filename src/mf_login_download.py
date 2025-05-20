"""
MoneyForward から指定年月の CSV を取得して保存する
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import json
import os
import tempfile
from pathlib import Path
from typing import Final

from playwright.async_api import async_playwright, BrowserContext, Page

LOGIN_URL: Final = "https://id.moneyforward.com/sign_in"
CSV_URL_TPL: Final = (
    "https://moneyforward.com/cf/csv?from={y}/{m:02d}/01&month={m}&year={y}"
)

# ──────────────────────────────────────────────────────────
EMAIL_SEL = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SEL = 'input[type="password"]'
SUBMIT_SEL = 'button[type="submit"]'
# ──────────────────────────────────────────────────────────


def _decode_storage_state(b64: str) -> Path:
    """env:MF_STORAGE_B64 → bytes → (必要なら gunzip) → JSON → 一時ファイル"""
    raw = base64.b64decode(b64)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    json.loads(raw.decode())  # validation
    fp = Path(tempfile.mkdtemp()) / "state.json"
    fp.write_bytes(raw)
    return fp


async def _login_if_needed(page: Page) -> None:
    """Cookie が有効なら何もしない。未ログインならフォームに入力して submit"""
    if page.url.startswith("https://moneyforward.com"):
        return

    await page.goto(LOGIN_URL, wait_until="load")

    # フォームがどちらの DOM でも取れるように待機
    await page.wait_for_selector(EMAIL_SEL, timeout=60_000)

    await page.fill(EMAIL_SEL, os.environ["MF_EMAIL"])
    await page.fill(PASS_SEL, os.environ["MF_PASSWORD"])

    async with page.expect_navigation():
        await page.click(SUBMIT_SEL)


async def download_csv_async(
    out_dir: str | os.PathLike,
    year: int,
    month: int,
    *,
    headless: bool = True,
) -> Path:
    """指定年月の CSV をダウンロードし out_dir に保存して Path を返す"""
    storage_state_file = None
    if b64 := os.getenv("MF_STORAGE_B64"):
        storage_state_file = str(_decode_storage_state(b64))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context: BrowserContext = await browser.new_context(storage_state=storage_state_file)
        page = await context.new_page()

        await _login_if_needed(page)

        csv_url = CSV_URL_TPL.format(y=year, m=month)
        resp = await context.request.get(csv_url)
        if resp.status != 200:
            raise RuntimeError(f"CSV ダウンロード失敗: {resp.status} {csv_url}")

        out_path = Path(out_dir) / f"moneyforward_{year}{month:02d}.csv"
        out_path.write_bytes(await resp.body())
        print(f"✓ CSV saved to {out_path}")

        await context.close()
        await browser.close()
        return out_path


# 手動実行用
if __name__ == "__main__":
    asyncio.run(download_csv_async(tempfile.gettempdir(), 2025, 5, headless=False))
