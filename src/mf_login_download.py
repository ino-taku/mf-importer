import asyncio
import base64
import gzip
import os
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PwTimeout

#―――――――― 環境変数 ――――――――#
MF_STORAGE_B64 = os.getenv("MF_STORAGE_B64", "")
MF_EMAIL       = os.getenv("MF_EMAIL", "")
MF_PASSWORD    = os.getenv("MF_PASSWORD", "")

# 直リンクでダウンロード画面へ
DL_URL          = "https://moneyforward.com/cf/download"
CSV_LINK_TEXT   = "CSVファイル"          # ボタンの可視テキスト

EMAIL_SELECTOR  = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR   = 'input[name="password"], input[name="mfid_user[password]"]'

#―――――――― ヘルパ ――――――――#
def _load_storage() -> dict | None:
    if not MF_STORAGE_B64:
        return None
    raw = base64.b64decode(MF_STORAGE_B64)
    try:                      # gzip 圧縮→展開
        raw = gzip.decompress(raw)
    except gzip.BadGzipFile:
        pass
    return raw.decode("utf-8")


async def _login(page):
    """メール/パスワード入力を伴うログイン。
    保存済み storageState が使えれば呼ばれない。"""
    try:
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
        await page.fill(EMAIL_SELECTOR, MF_EMAIL)
        await page.fill(PASS_SELECTOR,  MF_PASSWORD)
        await page.keyboard.press("Enter")
        # ログイン成功まで待つ（家計簿トップが出れば OK）
        await page.wait_for_url("**/cf", timeout=90_000)
    except PwTimeout as e:
        raise RuntimeError("ログインフォームの検出に失敗しました") from e


#―――――――― メイン ――――――――#
async def download_csv_async(tmp_dir: str, *, headless: bool = True) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context_kwargs = dict(
            viewport={"width": 1280, "height": 960},
            locale="ja-JP",
            user_agent=p.devices["Desktop Chrome HiDPI"]["user_agent"],
        )
        if st := _load_storage():
            context_kwargs["storage_state"] = st

        context = await browser.new_context(**context_kwargs)
        page    = await context.new_page()

        # 1️⃣ ダウンロード画面へ直行
        await page.goto(DL_URL, wait_until="networkidle")

        # もし storage が無効でログイン画面に飛ばされたらログインを試みる
        if "/sign_in" in page.url:
            await _login(page)
            await page.goto(DL_URL, wait_until="networkidle")

        # 2️⃣ CSV リンクを待ってクリック
        try:
            link = page.get_by_role("link", name=CSV_LINK_TEXT)
            await link.wait_for(timeout=30_000)
        except PwTimeout as e:
            # デバッグ用: 全リンクのテキストを出力して原因を掴む
            txts = await page.locator("a").all_inner_texts()
            raise RuntimeError(
                f"CSV リンクが見つかりません。\n"
                f"リンク一覧:\n{txts}"
            ) from e

        async with page.expect_download() as dl_info:
            await link.click()
        dl = await dl_info.value

        # 3️⃣ Downloads フォルダ → 引数で渡された tmp_dir へ保存
        dst = Path(tmp_dir) / dl.suggested_filename
        await dl.save_as(dst)
        await context.close()
        await browser.close()
        return dst


#―――――――― CLI 実行時 ――――――――#
if __name__ == "__main__":
    csv_path = asyncio.run(
        download_csv_async(tempfile.gettempdir(), headless=False)
    )
    print("Downloaded:", csv_path)
