import asyncio, os, base64, json, tempfile, time
from pathlib import Path
from playwright.async_api import async_playwright

LOGIN_URL        = "https://moneyforward.com/cf"
DL_MENU_TEXT     = "ダウンロード"
CSV_LINK_TEXT    = "CSVファイル"

EMAIL_SELECTOR   = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR    = 'input[type="password"], input[name="mfid_user[password]"]'

# ---------- 1. ログイン -------------------------------------------------- #
async def _login(page):
    email, password = os.environ["MF_EMAIL"], os.environ["MF_PASSWORD"]

    try:
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
        await page.fill(EMAIL_SELECTOR, email)
        await page.fill(PASS_SELECTOR,  password)
        await page.press(PASS_SELECTOR, "Enter")
        await page.wait_for_url("**/cf", timeout=90_000)
    except Exception as e:
        raise RuntimeError("ログインフォームが描画されずタイムアウトしました") from e

# ---------- 2. storageState → temp ファイル ----------------------------- #
def _storage_state_file() -> Path | None:
    b64 = os.getenv("MF_STORAGE_B64")
    if not b64:
        return None
    path = Path(tempfile.gettempdir()) / f"mf_state_{int(time.time())}.json"
    path.write_bytes(base64.b64decode(b64))
    return path

# ---------- 3. メイン ---------------------------------------------------- #
async def download_csv_async(tmpdir: str, *, headless: bool = True) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)

        # Cookie があれば読み込む
        state_file = _storage_state_file()
        context = await browser.new_context(
            storage_state=str(state_file) if state_file else None
        )
        page = await context.new_page()

        if not state_file:                             # Cookie が無いときだけログイン
            await page.goto(LOGIN_URL)
            await _login(page)

            # 取得した Cookie をローカルに保存（開発用）
            new_state_path = Path(tmpdir) / "storageState.json"
            new_state_path.write_bytes(
                json.dumps(await context.storage_state()).encode("utf-8")
            )

        # ------- CSV ダウンロード ------- #
        await page.goto(LOGIN_URL)
        await page.get_by_role("link", name=DL_MENU_TEXT).click()
        async with page.expect_download(timeout=60_000) as dl_info:
            await page.get_by_role("link", name=CSV_LINK_TEXT).click()

        dl      = await dl_info.value
        csv_out = Path(tmpdir) / dl.suggested_filename
        await dl.save_as(csv_out)

        await browser.close()
        return csv_out
