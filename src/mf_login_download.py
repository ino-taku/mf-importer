"""
MoneyForward から CSV を取得するユーティリティ
"""
from __future__ import annotations

import asyncio
import gzip
import os
import tempfile
from pathlib import Path
from typing import Final

from playwright.async_api import async_playwright, Page, BrowserContext

LOGIN_URL:  Final = "https://id.moneyforward.com/sign_in"
CSV_URL_TPL: Final = (
    "https://moneyforward.com/cf/csv?from={y}/{m:02d}/01&month={m}&year={y}"
)

# -------------------- ログイン -------------------- #
async def _login_if_needed(page: Page) -> None:
    """Cookie が切れていたらログインフォームに入力して submit"""
    if page.url.startswith("https://moneyforward.com"):
        return  # 既にアプリ側に入れている

    await page.goto(LOGIN_URL)
    await page.fill('input[name="mfid_user[email]"]', os.environ["MF_EMAIL"])
    await page.fill('input[name="mfid_user[password]"]', os.environ["MF_PASSWORD"])
    async with page.expect_navigation():
        await page.click('button[type="submit"]')


# -------------------- DL 本体 -------------------- #
async def download_csv_async(
    out_dir: str | os.PathLike,
    year: int,
    month: int,
    *,
    headless: bool = True,
) -> Path:
    """
    指定年月の CSV をダウンロードして保存パスを返す
    """
    b64 = os.getenv("MF_STORAGE_B64")
    storage_state: str | None = None
    if b64:
        raw = gzip.decompress(gzip.compress(b64.encode())) if b64[:2] != "{ " else b64
        fp = Path(tempfile.mkdtemp()) / "state.json"
        fp.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
        storage_state = str(fp)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context: BrowserContext = await browser.new_context(
            storage_state=storage_state
        )
        page = await context.new_page()

        # 1) 必要ならログイン
        await _login_if_needed(page)

        # 2) CSV を HTTP クライアントで直接 GET（同じ Cookie が付く）
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


# デバッグ実行
if __name__ == "__main__":
    asyncio.run(
        download_csv_async(tempfile.gettempdir(), 2025, 5, headless=False)
    )
