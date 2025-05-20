import asyncio, os, tempfile, time, base64, json
from pathlib import Path
from playwright.async_api import async_playwright

LOGIN_URL   = "https://moneyforward.com/cf"
EMAIL_SELECTOR = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SELECTOR  = 'input[type="password"], input[name="mfid_user[password]"]'
DL_MENU_TEXT   = "ダウンロード"
CSV_LINK_TEXT  = "CSVファイル"

async def _login(page):
    email    = os.environ["MF_EMAIL"]
    password = os.environ["MF_PASSWORD"]

    try:
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=90_000)
        await page.fill(EMAIL_SELECTOR, email)
        await page.fill(PASS_SELECTOR,  password)
        await page.press(PASS_SELECTOR, "Enter")
    except Exception as e:
        raise RuntimeError("ログインフォームが描画されずタイムアウトしました") from e

    # ログイン完了待ち（サイドバーが出るなど）
    await page.wait_for_url("**/cf", timeout=90_000)

async def _restore_storage(context):
    b64 = os.getenv("MF_STORAGE_B64")
    if not b64:
        return False
    state_path = Path(tempfile.gettempdir()) / f"mf_state_{int(time.time())}.json"
    state_path.write_bytes(base64.b64decode(b64))
    await context.add_cookies([])
    context.storage_state(path=str(state_path))
    return True

async def download_csv_async(tmpdir: str, headless=True) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page    = await context.new_page()

        # ① Cookie 復元（あれば）
        if not await _restore_storage(context):
            await page.goto(LOGIN_URL)
            await _login(page)

            # 新しい storageState を出力（ローカル開発用）
            state = await context.storage_state()
            (Path(tmpdir) / "storageState.json").write_text(json.dumps(state, ensure_ascii=False))

        # ② CSV ダウンロード
        await page.goto(LOGIN_URL)
        await page.get_by_role("link", name=DL_MENU_TEXT).click()
        async with page.expect_download(timeout=60_000) as dl_info:
            await page.get_by_role("link", name=CSV_LINK_TEXT).click()
        download = await dl_info.value
        out_path = Path(tmpdir) / download.suggested_filename
        await download.save_as(out_path)

        await browser.close()
        return out_path
