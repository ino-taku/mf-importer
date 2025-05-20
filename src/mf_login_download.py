import asyncio, base64, gzip, json, os, tempfile
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PwTimeout

# ── 環境変数 ──────────────────────────────────────────────
MF_STORAGE_B64 = os.getenv("MF_STORAGE_B64", "")
MF_EMAIL       = os.getenv("MF_EMAIL", "")
MF_PASSWORD    = os.getenv("MF_PASSWORD", "")

DL_URL         = "https://moneyforward.com/cf/download"
CSV_LINK_TEXT  = "CSVファイル"
EMAIL_SELECTOR = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR  = 'input[name="password"], input[name="mfid_user[password]"]'

# ── Base64 → dict へ変換 ────────────────────────────────
def _load_storage() -> dict | None:
    """MF_STORAGE_B64 (plain または gzip) を Python dict で返す"""
    if not MF_STORAGE_B64:
        return None
    raw = base64.b64decode(MF_STORAGE_B64)
    try:
        raw = gzip.decompress(raw)          # gzip 圧縮なら展開
    except gzip.BadGzipFile:
        pass
    return json.loads(raw.decode("utf-8"))   # ←★ dict を返す ★

# ── ログイン処理 ────────────────────────────────────────
async def _login(page):
    try:
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
        await page.fill(EMAIL_SELECTOR, MF_EMAIL)
        await page.fill(PASS_SELECTOR,  MF_PASSWORD)
        await page.keyboard.press("Enter")
        await page.wait_for_url("**/cf", timeout=90_000)
    except PwTimeout as e:
        raise RuntimeError("ログインフォーム検出に失敗") from e

# ── CSV ダウンロード ────────────────────────────────────
async def download_csv_async(tmp_dir: str, *, headless: bool = True) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)

        context_kwargs = dict(
            viewport={"width": 1280, "height": 960},
            locale="ja-JP",
            user_agent=p.devices["Desktop Chrome HiDPI"]["user_agent"],
        )
        if (st := _load_storage()) is not None:
            context_kwargs["storage_state"] = st        # ←★ dict 渡し

        context = await browser.new_context(**context_kwargs)
        page    = await context.new_page()

        await page.goto(DL_URL, wait_until="networkidle")
        if "/sign_in" in page.url:
            await _login(page)
            await page.goto(DL_URL, wait_until="networkidle")

        link = page.get_by_role("link", name=CSV_LINK_TEXT)
        await link.wait_for(timeout=30_000)

        async with page.expect_download() as dl_info:
            await link.click()
        dl  = await dl_info.value
        dst = Path(tmp_dir) / dl.suggested_filename
        await dl.save_as(dst)

        await context.close(); await browser.close()
        return dst

if __name__ == "__main__":
    csv_path = asyncio.run(
        download_csv_async(tempfile.gettempdir(), headless=False)
    )
    print("Downloaded:", csv_path)
