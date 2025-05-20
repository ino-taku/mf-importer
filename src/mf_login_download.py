import asyncio, base64, gzip, os, re, tempfile
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

HOME_URL    = "https://moneyforward.com/"
DL_PAGE_URL = "https://moneyforward.com/cf/csv"
WAIT        = 30_000          # ms
STORAGE_ENV = "MF_STORAGE_B64"
CSV_RE      = re.compile(r"csv", re.I)

# ---------- storageState ----------
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
    async def _try_find():
        # 直リンク .csv
        link = page.locator('a[href$=".csv"], a[href*=".csv?"]')
        if await link.count():
            return link.first
        # “CSV” を含む a / button / span / div
        node = page.locator(':is(a,button,span,div)', has_text=CSV_RE)
        if await node.count():
            return node.first
        return None

    # ① そのまま探す
    if (hit := await _try_find()):
        return hit

    # ② ダウンロードアイコンを押してメニュー展開
    icon = page.locator('i[class*="download"], i.icon-download-alt')
    if await icon.count():
        await icon.first.click()
        await page.wait_for_timeout(1_000)
        if (hit := await _try_find()):
            return hit

    # ③ 下へスクロールしつつ再探索
    for _ in range(3):
        await page.mouse.wheel(0, 800)
        await page.wait_for_timeout(500)
        if (hit := await _try_find()):
            return hit

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")

# ---------- メイン ----------
async def download_csv_async(out_dir: str, headless: bool = True) -> Path:
    storage = _decode_storage()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx_kw  = dict(storage_state=storage) if storage else {}
        context = await browser.new_context(**ctx_kw)
        page    = await context.new_page()

        await page.goto(DL_PAGE_URL, wait_until="networkidle")

        if page.url.startswith("https://id.moneyforward.com"):
            raise RuntimeError("未ログインです。storageState.json を再取得してください。")

        target = await _find_csv_link(page)

        # - 直 Download オブジェクト（メニュー→自動生成）か、
        # - Locator かで処理分岐
        if hasattr(target, "save_as"):
            download = target  # expect_download が返す Download
        else:
            async with page.expect_download(timeout=WAIT) as dl_info:
                await target.click()
            download = await dl_info.value

        dst = Path(out_dir) / download.suggested_filename
        await download.save_as(dst)
        await browser.close()
        return dst
