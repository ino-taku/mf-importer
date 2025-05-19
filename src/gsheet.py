# src/gsheet.py
import json, os, gspread, pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _client():
    sa_info = json.loads(os.environ["GSHEET_SERVICE_JSON"])
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return gspread.authorize(creds)

def upload_df(df: pd.DataFrame, worksheet: str = "Sheet1"):
    """DataFrame を指定シートへ上書きアップロード"""
    sh = _client().open_by_key(os.environ["GSHEET_KEY"])
    try:
        ws = sh.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet, rows="1000", cols=str(len(df.columns)))
    ws.clear()
    # USER_ENTERED にすると日付や数値がセル書式で入る
    ws.update([df.columns.tolist()] + df.astype(str).values.tolist(),
              value_input_option="USER_ENTERED")
