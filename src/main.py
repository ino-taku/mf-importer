import asyncio, tempfile
from mf_download_csv import download_csv_async
from normalize          import normalize
from gsheet             import upload_df

async def run_once() -> None:
    # 1) MoneyForward から最新 CSV を落とす
    csv = await download_csv_async(tempfile.gettempdir(), headless=True)

    # 2) pandas DataFrame に正規化
    df  = normalize(csv)

    # 3) Google Sheets へアップロード
    upload_df(df, worksheet='raw_csv')
    print('✓ Upload complete:', csv)

if __name__ == '__main__':
    asyncio.run(run_once())
