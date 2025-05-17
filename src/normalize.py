# src/normalize.py
from pathlib import Path
import pandas as pd

# MoneyForward 明細 CSV の列 → 変換後列
COL_MAP = {
    "日付": "date",
    "内容": "item",
    "金額": "amount",
    "保有金融機関": "account",
    "大項目": "category",
}

def normalize(csv_path: str | Path) -> pd.DataFrame:
    """
    MoneyForward の Shift-JIS CSV を読み込み、英字列名に変換して返す
    """
    df = pd.read_csv(csv_path, encoding="shift_jis")
    # 不要列は捨て、定義されている列だけ残す
    df = df[list(COL_MAP.keys())].rename(columns=COL_MAP)

    # 型変換
    df["date"]   = pd.to_datetime(df["date"], format="%Y/%m/%d")
    df["amount"] = df["amount"].astype(int)

    return df
