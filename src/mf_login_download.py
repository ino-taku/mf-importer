"""
MoneyForward から指定年月の CSV を取得して保存する
(iframe 内ログインフォームにも対応)
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

from playwright.async_api import async_playwright, BrowserContext, Frame, Page

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
    raw = base64.b64decode(b64)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    json.loads(raw.decode())
    fp = Path(tempfile.mkdtemp()) / "state.json"
    fp.write_bytes(raw)
    return fp


async def _find_login_frame(page: Page) -> Frame | None:
    """フォームを含むフレーム(トップレベル含む)を返す"""
    # 1️⃣ 最上位
    try:
        await page.wait_for_selector(EMAIL_SEL, timeout=5_000)
        return page.main_frame
    except Exception:
        pass

    # 2️⃣ iframe 群
    for frame in page.frames:
        try:
            if await frame.query_selector(EMAIL_SEL):
                return frame
        except Exception:
            continue
    return None


async def _login_if_needed(page: Page) -> None:
    if page.url.startswith("https://moneyforward.com"):
        return

    await page.goto(LOGIN_URL, wait_until="load")

    frame = await _find_login_frame(page)
    if frame is None:
        # デバッグ用に HTML を出す
        print("===== login page head =====")
        print((await page.content())[:1200])
        print("===== login page tail =====")
        print((await page.content())[-1200:])
        raise RuntimeError("ログインフォームを検出できませんでした (iframe も含め)")

    await frame.fill(EMAIL_SEL, os.environ["MF_EMAIL"])
    await frame.fill(PASS_SEL, os.environ["MF_PASSWORD"])
    async with page.expect_navigation():
        await frame.click(SUBMIT_SEL)


async def download_csv_async(
    out_dir: str | os.PathLike,
    year: int,
    month: int,
    *,
    headless: bool = True,
):
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


if __name__ == "__main__":
    asyncio.run(download_csv_async(tempfile.gettempdir(), 2025, 5, headless=False))
