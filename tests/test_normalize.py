# tests/test_normalize.py
from pathlib import Path
from src.normalize import normalize

def test_column_names(tmp_path):
    # ダミー CSV を生成
    csv = tmp_path / "dummy.csv"
    csv.write_text(
        "日付,内容,金額,保有金融機関,大項目\n"
        "2025/05/01,テスト,1234,三井住友,食費\n",
        encoding="shift_jis"
    )

    df = normalize(csv)
    assert list(df.columns) == ["date", "item", "amount", "account", "category"]
    assert df["amount"].iloc[0] == 1234
