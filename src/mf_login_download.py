import asyncio, base64, gzip, json, os, tempfile
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ----------------------------------------
# 定数
# ----------------------------------------
HOME_URL          = "https://moneyforward.com/"
DL_PAGE_URL       = "https://moneyforward.com/cf/csv"
CSV_LINK_TEXT_JP  = "CSVファイル"          # 画面に表示される日本語リンク
CSV_HREF_PATTERN  = 'a[href$=".csv"], a[href*=".csv?"]'  # href に .csv が入る全リンク
WAIT              = 30_000                # ms
STORAGE_ENV       = "MF_STORAGE_B64"      # Secrets に登録した Base64 文字列

# ----------------------------------------
# 辞書 → gzip → base64 で圧縮した storageState.json を復元
# ----------------------------------------
def _decode_storage() -> Path | None:
    b64 = os.getenv(STORAGE_ENV)
    if not b64:
        return None
    raw = base64.b64decode(b64)
    try:
        raw = gzip.decompress(raw)
    except OSError:  # 非圧縮の場合
        pass
    tmp = Path(tempfile.gettempdir()) / "storageState.json"
    tmp.write_bytes(raw)
    return tmp

# ----------------------------------------
async def _find_csv_link(page):
    """
    1. ARIA ロール   <a role="link" name="CSVファイル">
    2. href に .csv を含むリンク
    3. SVG アイコン付き <i class="icon-download-alt"> の親リンク
    """
    # 1. アクセシビリティロケータ
    try:
        link = page.get_by_role("link", name=CSV_LINK_TEXT_JP)
        await link.wait_for(timeout=WAIT)
        return link
    except PWTimeout:
        pass

    # 2. href に .csv
    csv_candidates = page.locator(CSV_HREF_PATTERN)
    if await csv_candidates.count():
        return csv_candidates.first

    # 3. DL アイコン
    icon_parent = page.locator("i.icon-download-alt").locator("..")
    if await icon_parent.count():
        return icon_parent.first

    raise RuntimeError("CSV ダウンロードリンクを検出できませんでした")

# ----------------------------------------
async def download_csv_async(out_dir: str, headless: bool = True) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        storage   = _decode_storage()
        context   = await browser.new_context(storage_state=storage) if storage else await browser.new_context()
        page      = await context.new_page()

        # 1. ターゲットページへ
        await page.goto(DL_PAGE_URL, wait_until="networkidle")

        # 2. ログインが必要なら自動遷移（storageState が無いケース）
        if page.url.startswith("https://id.moneyforward.com"):
            raise RuntimeError("未ログインです。storageState.json を取得して MF_STORAGE_B64 に設定してください。")

        # 3. CSV ダウンロードリンクを検出
        link = await _find_csv_link(page)

        # 4. ダウンロードを待ち受けてクリック
        async with page.expect_download() as dl_info:
            await link.click()
        download = await dl_info.value
        csv_path = Path(out_dir) / download.suggested_filename
        await download.save_as(csv_path)

        await browser.close()
        return csv_path
