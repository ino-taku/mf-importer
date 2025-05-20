import os
import asyncio
import tempfile
from datetime import date

from .mf_login_download import download_csv_async
from .normalize          import normalize
from .gsheet             import upload_df


async def run_once() -> None:
    """
    1) MoneyForward から対象年月の CSV をダウンロード
    2) pandas DataFrame へ正規化
    3) Google Sheets へアップロード
    """
    # GitHub Actions から渡される YEAR / MONTH（無ければ当月）
    year  = int(os.getenv("YEAR", 0))
    month = int(os.getenv("MONTH", 0))
    if not (1 <= month <= 12 and year):
        today = date.today()
        year, month = today.year, today.month

    csv_path = await download_csv_async(
        tempfile.gettempdir(), year, month, headless=True
    )

    df = normalize(csv_path)
    upload_df(df, worksheet="raw_csv")
    print(f"✓ Upload complete: {csv_path}")


if __name__ == "__main__":
    asyncio.run(run_once())
