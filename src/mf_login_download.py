import asyncio, base64, gzip, os, re, tempfile
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout, Page

HOME_URL    = "https://moneyforward.com/"
DL_PAGE_URL = "https://moneyforward.com/cf/csv"
WAIT        = 30_000           # ms
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

# ---------- 汎用: “CSV” を探す -------------
async def _scan_for_csv(page_or_frame):
    # 直リンク .csv
    link = page_or_frame.locator('a[href$=".csv"], a[href*=".csv?"]')
    if await link.count():
        return link.first

    # role≠presentation で “CSV” を含むテキスト
    node = page_or_frame.locator(
        ':is(a,button,span,div,li):not([role="presentation"])',
        has_text=CSV_RE
    )
    if await node.count():
        return node.first
    return None

# ---------- CSV リンク探索 -------------
async def _find_csv_link(page: Page):
    async def _try_everywhere():
        # 1) メインページ
        if (hit := await _scan_for_csv(page)):
            return hit
        # 2) iframe 内
        for frame in page.frames:
            if frame is not page.main_frame:
                if (hit := await _scan_for_csv(frame)):
                    return hit
        return None

    # ---- A. そのまま
    if (hit := await _try_everywhere()):
        return hit

    # ---- B. download-icon
    icon = page.locator('i[class*="download"], i.icon-download-alt')
    if await icon.count():
        await icon.first.click()
        await page.wait_for_timeout(1_000)
        if (hit := await _try_everywhere()):
            return hit

    # ---- C. dropdown-button
    dd_btn = page.locator('button[data-toggle="dropdown"], .dropdown-toggle')
    if await dd_btn.count():
        await dd_btn.first.click()
        await page.wait_for_timeout(1_000)
        if (hit := await _try_everywhere()):
            return hit

    # ---- D. スクロールしながらリトライ
    for _ in range(3):
        await page.mouse.wheel(0, 800)
        await page.wait_for_timeout(500)
        if (hit := await _try_everywhere()):
            return hit

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")

# ---------- メイン ----------
async def download_csv_async(out_dir: str, headless: bool = True):
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

        # Download オブジェクト or Locator
        if hasattr(target, "save_as"):
            download = target            # すでに Download
        else:
            async with page.expect_download(timeout=WAIT) as dl_info:
                await target.click()
            download = await dl_info.value

        dst = Path(out_dir) / download.suggested_filename
        await download.save_as(dst)
        await browser.close()
        return dst
