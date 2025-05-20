import asyncio, base64, gzip, os, tempfile, re
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

HOME_URL         = "https://moneyforward.com/"
DL_PAGE_URL      = "https://moneyforward.com/cf/csv"
WAIT             = 30_000           # ms
STORAGE_ENV      = "MF_STORAGE_B64" # Secret 名
CSV_RE           = re.compile(r"csv", re.I)

# ---------- storageState (Base64 / gzip) ----------
def _decode_storage() -> Path | None:
    b64 = os.getenv(STORAGE_ENV)
    if not b64:
        return None
    raw = base64.b64decode(b64)
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass
    tmp = Path(tempfile.gettempdir()) / "storageState.json"
    tmp.write_bytes(raw)
    return tmp

# ---------- CSV リンク探索 ----------
async def _find_csv_link(page):
    # 1. 既に href=".csv" が存在すれば最速
    csv_href = page.locator('a[href$=".csv"], a[href*=".csv?"]')
    if await csv_href.count():
        return csv_href.first

    # 2. innerText/aria-label に “csv” を含むリンク or ボタン
    text_link = page.locator(":is(a,button)", has_text=CSV_RE)
    if await text_link.count():
        return text_link.first

    # 3. CSV ボタンを押すと JS が <a download> を生成する UI
    #    → button をクリック → href=".csv" が出るまで待つ
    csv_btn = page.locator(":is(button)", has_text=CSV_RE)
    if await csv_btn.count():
        async with page.expect_download(timeout=WAIT) as dl_info:
            await csv_btn.first.click()
        return dl_info.value  # expect_download が返す Download オブジェクト

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")

# ---------- メイン ----------
async def download_csv_async(out_dir: str, headless: bool = True) -> Path:
    storage = _decode_storage()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(storage_state=storage) if storage else await browser.new_context()
        page    = await context.new_page()

        await page.goto(DL_PAGE_URL, wait_until="networkidle")

        if page.url.startswith("https://id.moneyforward.com"):
            raise RuntimeError("未ログインです。storageState.json を再取得し Secret に登録してください。")

        target = await _find_csv_link(page)

        # target が Download オブジェクト (ケース③) か Locator かで分岐
        if hasattr(target, "save_as"):
            download = target
        else:
            async with page.expect_download(timeout=WAIT) as dl_info:
                await target.click()
            download = await dl_info.value

        csv_path = Path(out_dir) / download.suggested_filename
        await download.save_as(csv_path)
        await browser.close()
        return csv_path
