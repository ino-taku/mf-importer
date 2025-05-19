from pathlib import Path
import pandas as pd

# MoneyForward CSV header to normalized column mapping
#   - 左側: CSV の実ヘッダー（複数表記があり得るものは両方書く）
#   - 右側: 正規化後の英語カラム名
COL_MAP = {
    "日付": "date",
    "内容": "item",
    "金額": "amount",          # 古い CSV 形式
    "金額（円）": "amount",     # 新しい CSV 形式
    "保有金融機関": "account",
    "大項目": "category",
    "中項目": "subcategory",
    "メモ": "note",
    "振替": "transfer",
}

# 出力時の列順（存在するもののみ retain）
PREFERRED_ORDER = [
    "date",
    "item",
    "amount",
    "account",
    "category",
    "subcategory",
    "note",
    "transfer",
]


def normalize(csv_path: str | Path) -> pd.DataFrame:
    """Normalize MoneyForward CSV (Shift‑JIS) into a tidy DataFrame.

    Steps:
    1. Read CSV with *Shift-JIS* encoding (MoneyForward default)
    2. Keep only columns defined in COL_MAP and rename to English keys
    3. Coerce `date` to datetime (YYYY/MM/DD) and `amount` to int (remove commas)
    4. Re‑order columns by *PREFERRED_ORDER*
    """
    df = pd.read_csv(csv_path, encoding="shift_jis", dtype=str)

    # --- 列抽出 & リネーム ---------------------------------------------
    available = [c for c in df.columns if c in COL_MAP]
    df = df[available].rename(columns=COL_MAP)

    # --- 型変換 ---------------------------------------------------------
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d", errors="coerce")
    if "amount" in df.columns:
        df["amount"] = (
            df["amount"].str.replace(",", "", regex=False).astype("Int64")
        )

    # --- 列順を整える ---------------------------------------------------
    ordered = [col for col in PREFERRED_ORDER if col in df.columns]
    return df[ordered]
