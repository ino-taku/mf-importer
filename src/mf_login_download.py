"""
MoneyForward 明細ページから CSV をダウンロードするユーティリティ
────────────────────────────────────────────────────
* Playwright のストレージスナップショット（`MF_STORAGE_B64`）が
  - base64 だけ     …… そのまま decode
  - gzip → base64 …… gunzip してから decode
  どちらにも対応。
* ストレージが無効だった場合は通常のログインを自動実行。
* CSV のダウンロードリンクを 5 種類のセレクタで探し、堅牢化。
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import os
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
    """
    MF_STORAGE_B64 があれば一時ファイルに書き出しパスを返す。
    無ければ None。
    """
    b64 = os.environ.get("MF_STORAGE_B64")
    if not b64:
        return None

    raw: bytes
    try:
        raw = base64.b64decode(b64)
    except Exception as e:  # malformed base64
        raise RuntimeError("MF_STORAGE_B64 が base64 ではありません") from e

    # gzip 圧縮されているか判定
    if raw.startswith(b"\x1f\x8b"):
        try:
            raw = gzip.decompress(raw)
        except Exception as e:  # bad gzip
            raise RuntimeError("MF_STORAGE_B64 の gunzip に失敗しました") from e

    # JSON 妥当性チェック
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
    email = os.environ["MF_EMAIL"]
    passwd = os.environ["MF_PASSWORD"]

    try:
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
        await page.fill(EMAIL_SELECTOR, email, timeout=30_000)
        await page.fill(PASS_SELECTOR, passwd, timeout=30_000)
        # MoneyForward のログインボタン
        await page.locator("button:has-text('ログイン'), input[type=submit]").click()
        await page.wait_for_load_state("networkidle")
    except PwTimeout as e:
        raise RuntimeError("ログインフォームが描画されずタイムアウトしました") from e


# ── CSV リンク探索 ──────────────────────────────────────
async def _find_csv_link(page):
    """可能性のある CSS / テキストから CSV ダウンロードリンクを探す"""
    selectors = [
        f'a:has-text("{CSV_LINK_TEXT}")',     # ① アクセシブル名
        'a:has-text("CSV")',                  # ② “CSV” を含む
        'a[href$=".csv"]',                    # ③ href が .csv
        'a[href*="format=csv"]',              # ④ format=csv パラメータ
        'a i.icon-download-alt >> xpath=ancestor::a',  # ⑤ DL アイコン
    ]
    for sel in selectors:
        link = page.locator(sel).first
        try:
            await link.wait_for(timeout=5_000, state="visible")
            return link
        except PwTimeout:
            continue
    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")


# ── メイン API ───────────────────────────────────────────
async def download_csv_async(tmp_dir: str, *, headless: bool = True) -> Path:
    """
    `tmp_dir` に CSV をダウンロードし、Path を返す。
    """
    storage_file = _write_storage_from_env(tmp_dir)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=["--no-sandbox"])
        context_kwargs = {}
        if storage_file:
            context_kwargs["storage_state"] = storage_file
        context = await browser.new_context(**context_kwargs)

        page = await context.new_page()

        # ストレージが無い場合だけ手動ログイン
        if not storage_file:
            await page.goto(LOGIN_URL)
            await _login(page)

        # DL ページへ遷移
        await page.goto(DL_URL, wait_until="networkidle")

        # CSV リンクをクリックし download 完了を待つ
        link = await _find_csv_link(page)

        async with page.expect_download() as dl_info:
            await link.click()
        download = await dl_info.value
        csv_path = Path(tmp_dir, download.suggested_filename)
        await download.save_as(str(csv_path))

        await context.close()
        await browser.close()

        return csv_path


# ── 手動デバッグ用 CLI ─────────────────────────────────
if __name__ == "__main__":
    import sys
    out = asyncio.run(download_csv_async(tempfile.gettempdir(), headless=False))
    print("📄  downloaded →", out)
    sys.exit(0)
