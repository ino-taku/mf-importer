"""
MoneyForward 明細ページから CSV をダウンロードするユーティリティ
────────────────────────────────────────────────────
* Playwright のストレージスナップショット（`MF_STORAGE_B64`）が
  - base64 だけ     …… そのまま decode
  - gzip → base64 …… gunzip してから decode
  どちらにも対応。
* ストレージが無効だった場合は通常のログインを自動実行。
* CSV のダウンロードリンクを “7 種” の異なる方法で探し、さらに堅牢化。
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, TimeoutError as PwTimeout

# ── MoneyForward 固有定数 ──────────────────────────────
LOGIN_URL      = "https://id.moneyforward.com/sign_in"
DL_URL         = "https://moneyforward.com/cf/expenses/download"
CSV_LINK_TEXT  = "CSVファイル"

EMAIL_SELECTOR = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR  = 'input[name="password"], input[name="mfid_user[password]"]'

# ── ストレージロード ────────────────────────────────────
def _write_storage_from_env(tmp_dir: str) -> Optional[Path]:
    """MF_STORAGE_B64 を tmp_dir に storageState.json として書き出す"""
    b64 = os.environ.get("MF_STORAGE_B64")
    if not b64:
        return None

    try:
        raw = base64.b64decode(b64)
    except Exception as e:
        raise RuntimeError("MF_STORAGE_B64 が base64 ではありません") from e

    if raw.startswith(b"\x1f\x8b"):        # gzip?
        try:
            raw = gzip.decompress(raw)
        except Exception as e:
            raise RuntimeError("MF_STORAGE_B64 の gunzip に失敗しました") from e

    try:
        json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise RuntimeError("storageState.json が JSON として不正です") from e

    fp = Path(tmp_dir, "storageState.json")
    fp.write_bytes(raw)
    return fp


# ── ログイン ────────────────────────────────────────────
async def _login(page):
    """フォーム入力によるログイン（ストレージ無効時に使用）"""
    email  = os.environ["MF_EMAIL"]
    passwd = os.environ["MF_PASSWORD"]

    try:
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
        await page.fill(EMAIL_SELECTOR, email,  timeout=30_000)
        await page.fill(PASS_SELECTOR,  passwd, timeout=30_000)
        await page.locator("button:has-text('ログイン'), input[type=submit]").click()
        await page.wait_for_load_state("networkidle")
    except PwTimeout as e:
        raise RuntimeError("ログインフォームが描画されずタイムアウトしました") from e


# ── CSV リンク探索 ──────────────────────────────────────
async def _find_csv_link(page):
    """
    可能性のある CSS / ARIA / 正規表現を総当たりで試し、
    最初に見つかったリンク（<a> または <button>）を返す。
    """
    regex_csv = re.compile("csv", re.I)

    candidate_locators = [
        page.get_by_role("link",   name=CSV_LINK_TEXT),         # ① 完全一致 (CSVファイル)
        page.get_by_role("link",   name=regex_csv),             # ② “CSV” を含む aria-name
        page.locator('a:has-text("CSVファイル")'),              # ③ テキストに “CSVファイル”
        page.locator('a:has-text("CSV")'),                      # ④ テキストに “CSV”
        page.locator('button:has-text("CSV")'),                 # ⑤ ボタン内 “CSV”
        page.locator('a[href$=".csv"]'),                        # ⑥ href が .csv
        page.locator('a[href*="format=csv"]'),                  # ⑦ href に format=csv
    ]

    for loc in candidate_locators:
        try:
            await loc.first.wait_for(timeout=5_000, state="visible")
            return loc.first
        except PwTimeout:
            continue

    # 最終手段: すべての <a> を走査し innerText に CSV を含むものを探す
    all_links = page.locator("a")
    count = await all_links.count()
    for i in range(count):
        text = await all_links.nth(i).inner_text()
        if regex_csv.search(text):
            return all_links.nth(i)

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")


# ── メイン API ───────────────────────────────────────────
async def download_csv_async(tmp_dir: str, *, headless: bool = True) -> Path:
    """
    `tmp_dir` に CSV をダウンロードし、Path を返す。
    """
    storage_file = _write_storage_from_env(tmp_dir)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=["--no-sandbox"])
        ctx_kwargs = {"storage_state": storage_file} if storage_file else {}
        context    = await browser.new_context(**ctx_kwargs)
        page       = await context.new_page()

        if not storage_file:
            await page.goto(LOGIN_URL)
            await _login(page)

        # DL ページへ遷移
        await page.goto(DL_URL, wait_until="networkidle")

        # CSV リンクをクリック
        link = await _find_csv_link(page)

        async with page.expect_download() as dl_info:
            await link.click()
        download  = await dl_info.value
        csv_path  = Path(tmp_dir, download.suggested_filename)
        await download.save_as(str(csv_path))

        await context.close()
        await browser.close()
        return csv_path


# ── 手動デバッグ用 CLI ─────────────────────────────────
if __name__ == "__main__":
    out = asyncio.run(download_csv_async(tempfile.gettempdir(), headless=False))
    print("📄  downloaded →", out)
