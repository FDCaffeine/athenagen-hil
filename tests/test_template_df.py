import pandas as pd

from app import build_template_df


def test_build_template_df_minimal():
    records = [{"source": "form", "full_name": "Alice", "created_at": "2024-01-01"}]
    template_cols = ["ClientName", "Date", "Source", "Status"]
    df = build_template_df(records, template_cols, invoice_index={})
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == template_cols
    assert df.shape[0] == 1
