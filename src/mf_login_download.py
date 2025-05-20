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

from playwright.async_api import async_playwright, Page, BrowserContext

LOGIN_URL: Final = "https://id.moneyforward.com/sign_in"
CSV_URL_TPL: Final = (
    "https://moneyforward.com/cf/csv?from={y}/{m:02d}/01&month={m}&year={y}"
)


# ---------- 共通ユーティリティ ---------- #
def _decode_storage_state(b64: str) -> Path:
    """
    env:MF_STORAGE_B64 を bytes に戻し（必要なら gunzip して）一時ファイルへ保存
    """
    data = base64.b64decode(b64)

    # gzip されていれば解凍（先頭 2 byte = 0x1f 0x8b）
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)

    # validate
    json.loads(data.decode())  # ←壊れていればここで例外

    fp = Path(tempfile.mkdtemp()) / "state.json"
    fp.write_bytes(data)
    return fp


async def _login_if_needed(page: Page) -> None:
    if page.url.startswith("https://moneyforward.com"):
        return
    await page.goto(LOGIN_URL, wait_until="load")
    await page.fill('input[name="mfid_user[email]"]', os.environ["MF_EMAIL"])
    await page.fill('input[name="mfid_user[password]"]', os.environ["MF_PASSWORD"])
    async with page.expect_navigation():
        await page.click('button[type="submit"]')


# ---------- メイン ---------- #
async def download_csv_async(
    out_dir: str | os.PathLike,
    year: int,
    month: int,
    *,
    headless: bool = True,
) -> Path:
    """
    :param out_dir:   保存先ディレクトリ
    :param year:      取得する年 (e.g. 2025)
    :param month:     取得する月 (1-12)
    :returns:         保存した CSV の Path
    """

    storage_state_file: str | None = None
    if (b64 := os.getenv("MF_STORAGE_B64")):
        storage_state_file = str(_decode_storage_state(b64))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context: BrowserContext = await browser.new_context(
            storage_state=storage_state_file
        )
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


# 手動デバッグ用
if __name__ == "__main__":
    asyncio.run(download_csv_async(tempfile.gettempdir(), 2025, 5, headless=False))
