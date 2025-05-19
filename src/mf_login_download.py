# src/mf_login_download.py
#
# MoneyForward から “収入・支出詳細” CSV をダウンロードするユーティリティ
# ------------------------------------------------------------
# ・環境変数 MF_EMAIL / MF_PASSWORD で認証
# ・Playwright（async）を使用
# ・ヘッドレス／GUI は引数で切替
# ------------------------------------------------------------
from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Final

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

MF_ID_URL:   Final = "https://id.moneyforward.com/sign_in"
MF_CF_URL:   Final = "https://moneyforward.com/cf"

EMAIL  = os.getenv("MF_EMAIL")
PWD    = os.getenv("MF_PASSWORD")

if not EMAIL or not PWD:
    raise EnvironmentError("MF_EMAIL / MF_PASSWORD が環境変数に設定されていません。")


# ----------------------------------------------------------------------
# 内部ヘルパ
# ----------------------------------------------------------------------
async def _login(page) -> None:
    """MoneyForward ID でログイン (必要ならメールリンクをクリックして展開)"""
    await page.goto(MF_ID_URL, wait_until="domcontentloaded")

    # --- フォームを開く -------------------------------------------------
    # 「メールアドレスでログイン」リンクがあればクリック
    if await page.locator('text="メールアドレスでログイン"').count():
        await page.click('text="メールアドレスでログイン"')

    # 入力欄が現れるまで最大 90 秒待つ
    try:
        await page.wait_for_selector('input[name="email"]', timeout=90_000)
    except PWTimeout as e:
        raise RuntimeError("ログインフォームが描画されずタイムアウトしました") from e

    # --- 認証情報を入力 -------------------------------------------------
    await page.fill('input[name="email"]', EMAIL)
    await page.fill('input[name="password"]', PWD)
    await page.click('button[type="submit"]')

    # 完全に遷移するまで待機
    await page.wait_for_url(lambda url: "sign_in" not in url, timeout=90_000)


# ----------------------------------------------------------------------
# 外部 API
# ----------------------------------------------------------------------
async def download_csv_async(tmp_dir: str | Path, *, headless: bool = True) -> Path:
    """
    CSV を tmp_dir に保存してその Path を返す
    """
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=["--no-sandbox"])
        context = await browser.new_context(
            **(p.devices["Desktop Chrome HiDPI"] if headless else {})
        )
        page = await context.new_page()

        # ログインが必要かどうかを判定
        await page.goto(MF_CF_URL, wait_until="domcontentloaded")
        if "sign_in" in page.url:
            await _login(page)
            await page.goto(MF_CF_URL, wait_until="networkidle")

        # ダウンロードメニューを開く
        # 家計簿ページの上部バーにあるアイコン (DOM 側は <i class="icon-download-alt">)
        await page.click('i.icon-download-alt')

        # "CSVファイル" をクリックして download
        async with page.expect_download() as dl_info:
            await page.get_by_role("link", name="CSVファイル").click()
        dl = await dl_info.value

        # ファイル名を日付入りで置き換え保存
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = tmp_dir / f"収入・支出詳細_{ts}.csv"
        await dl.save_as(csv_path)

        await context.close()
        await browser.close()

    return csv_path


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _cli() -> None:
    parser = argparse.ArgumentParser(description="MoneyForward CSV downloader")
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode (default)"
    )
    parser.add_argument(
        "--with-gui", action="store_true", help="Run browser with GUI (overrides --headless)"
    )
    args = parser.parse_args()

    headless = not args.with_gui
    out = asyncio.run(download_csv_async(tempfile.gettempdir(), headless=headless))
    print(f"✓ Downloaded: {out}")


if __name__ == "__main__":
    _cli()
