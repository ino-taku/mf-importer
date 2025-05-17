import os, sys, tempfile
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE = BASE_DIR / "storageState.json"

# .env 読込
load_dotenv(BASE_DIR / ".env")

DOWNLOAD_TIMEOUT = 60  # 秒


def download_csv(save_dir=".", headless=False):
    email = os.getenv("MF_EMAIL")
    password = os.getenv("MF_PASSWORD")

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage"],
        )

        # ---------------- Cookie 優先 ---------------- #
        if STORAGE.exists():
            context = browser.new_context(
                storage_state=str(STORAGE),
                accept_downloads=True,
            )
            page = context.new_page()
            page.goto("https://moneyforward.com/cf")  # ダッシュボードへ直行
        else:
            # ---------- 初回のみメール/パスでログイン ----------
            if not (email and password):
                raise EnvironmentError("MF_EMAIL / MF_PASSWORD が未設定です")

            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto("https://moneyforward.com/cf")
            page.fill('input[name="email"]', email)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_url("**/home")
            # Cookie を保存
            context.storage_state(path=str(STORAGE))

        # ---------------- 明細 → CSV ---------------- #
            page.locator("a", has_text="ダウンロード").first.click()

            with page.expect_download(timeout=DOWNLOAD_TIMEOUT * 1000) as dl:
                page.get_by_role("link", name="CSVファイル").click()
            download = dl.value
            csv_path = save_dir / download.suggested_filename
            download.save_as(csv_path)

        context.close()
        browser.close()
    return csv_path


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    try:
        out = download_csv(tempfile.gettempdir(), headless=args.headless)
        print(f"Downloaded: {out}")
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
