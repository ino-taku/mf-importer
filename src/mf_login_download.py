import os, tempfile
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

DOWNLOAD_TIMEOUT = 60  # 秒

def download_csv(save_dir=".", headless=False):
    email = os.getenv("MF_EMAIL")
    password = os.getenv("MF_PASSWORD")
    if not (email and password):
        raise EnvironmentError("MF_EMAIL / MF_PASSWORD が未設定です")

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless,
                                    args=["--disable-dev-shm-usage"])
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # --- ログイン ---
        page.goto("https://moneyforward.com/cf")
        page.fill('input[name="email"]', email)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        # --- 明細画面へ ---
        page.wait_for_url("**/home")
        page.click('a:has-text("家計簿")')
        page.click('a:has-text("明細")')

        # --- CSV ダウンロード ---
        with page.expect_download(timeout=DOWNLOAD_TIMEOUT * 1000) as dl:
            page.click('role=button[name="CSVダウンロード"]')
        download = dl.value
        csv_path = save_dir / download.suggested_filename
        download.save_as(csv_path)

        context.close()
        browser.close()
    return csv_path


if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    try:
        path = download_csv(tempfile.gettempdir(), headless=args.headless)
        print(f"Downloaded: {path}")
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
