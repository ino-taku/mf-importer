import asyncio, base64, gzip, os, re, tempfile
from pathlib import Path
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

HOME_URL    = "https://moneyforward.com/"
DL_PAGE_URL = "https://moneyforward.com/cf/export"   # ← 修正
WAIT        = 30_000
STORAGE_ENV = "MF_STORAGE_B64"

# ASCII / 全角どちらでもマッチ
CSV_RE = re.compile(r"[cｃCＣ][sｓSＳ][vｖVＶ]", re.I)

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

# ---------- 汎用: “CSV” を探す ----------
async def _scan_for_csv(scope: Page):
    # a)  href に .csv
    link = scope.locator('a[href$=".csv"], a[href*=".csv?"]')
    if await link.count():
        return link.first

    # b)  テキストに CSV
    node = scope.locator(
        ':is(a,button,input,span,div,li):not([role="presentation"])',
        has_text=CSV_RE
    )
    if await node.count():
        return node.first

    # c)  submit ボタン value に CSV
    btn = scope.locator('input[type="submit"]')
    for i in range(await btn.count()):
        v = (await btn.nth(i).get_attribute("value")) or ""
        if CSV_RE.search(v):
            return btn.nth(i)

    return None

# ---------- CSV リンク探索 ----------
async def _find_csv_link(page: Page):
    async def _try_everywhere():
        # main frame
        if hit := await _scan_for_csv(page):
            return hit
        # sub-frames
        for f in page.frames:
            if f is not page.main_frame and (hit := await _scan_for_csv(f)):
                return hit
        return None

    if hit := await _try_everywhere():
        return hit

    # フォームに submit 1 個だけパターン
    submit_only = page.locator('form input[type="submit"]')
    if await submit_only.count() == 1:
        return submit_only.first

    # ---------- failure debug ----------
    html = await page.content()
    head = "\n".join(html.splitlines()[:200])
    tail = "\n".join(html.splitlines()[-50:])
    print("===== page.content() head =====")
    print(head)
    print("===== page.content() tail =====")
    print(tail)
    print(f"URL   : {page.url}")
    print(f"title : {await page.title()}")
    print("================================")

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")
# ---------- メイン ----------
async def download_csv_async(out_dir: str, *, headless: bool = True):
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

        # Download オブジェクト or Locator のどちらにも対応
        if hasattr(target, "save_as"):
            download = target
        else:
            async with page.expect_download(timeout=WAIT) as dlinfo:
                await target.click()
            download = await dlinfo.value

        dst = Path(out_dir) / download.suggested_filename
        await download.save_as(dst)
        await browser.close()
        return dst
