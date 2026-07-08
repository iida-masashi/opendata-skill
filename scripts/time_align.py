"""時系列アラインメント層 (Phase 2 ④)。

異なる周波数（日次/週次/月次）の外生変数を、予測モデルが結合できる共通周波数に
リサンプリングする。OpenDataHub が返す正規化済み DataFrame (date / value 列) を
入力に取る。
"""
import argparse

import polars as pl

_AGG = {
    "mean": pl.col("value").mean(),
    "sum": pl.col("value").sum(),
    "last": pl.col("value").last(),
    "first": pl.col("value").first(),
    "max": pl.col("value").max(),
    "min": pl.col("value").min(),
}


def align_frequency(
    df: pl.DataFrame,
    freq: str = "1mo",
    agg: str = "mean",
    date_col: str = "date",
    value_col: str = "value",
    upsample_fill: str = "forward",
    filter_col: str | None = None,
    filter_val: str | None = None,
) -> pl.DataFrame:
    """単一の時系列を目標周波数 freq にリサンプリングする。

    - freq: Polars の duration 文字列 ('1d', '1w', '1mo', '1q', '1y' 等)
    - agg: ダウンサンプル時の集約 ('mean'/'sum'/'last'/'first'/'max'/'min')
    - upsample_fill: アップサンプルで生じた欠損の埋め方 ('forward'/'backward'/None)
    - filter_col/filter_val: date あたり複数行ある多次元テーブル（例: e-Stat の
      景気動向指数 = 系列×表章項目、訪日外客数 = 港×国籍）を、特定の1系列に
      絞ってから揃えるためのフィルタ。指定しないと date あたり複数値が集約され
      混ざるので、こうしたソースでは必須。

    戻り値は date / value の2列。空入力は空DFを返す。
    """
    if df.is_empty() or date_col not in df.columns or value_col not in df.columns:
        return pl.DataFrame()
    if agg not in _AGG:
        raise ValueError(f"Unknown agg '{agg}'. Available: {list(_AGG)}")

    if filter_col is not None and filter_col in df.columns:
        df = df.filter(pl.col(filter_col) == filter_val)
        if df.is_empty():
            return pl.DataFrame()

    out = df.select([date_col, value_col]).rename({date_col: "date", value_col: "value"})

    # date を Date 型へ
    if out["date"].dtype == pl.Utf8:
        out = out.with_columns(
            pl.coalesce(
                [
                    pl.col("date").str.strptime(pl.Date, fmt, strict=False)
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y%m", "%Y-%m")
                ]
            ).alias("date")
        )
    out = out.drop_nulls("date").sort("date")
    if out.is_empty():
        return pl.DataFrame()

    # value を数値化
    out = out.with_columns(pl.col("value").cast(pl.Float64, strict=False))

    # 目標グリッドへ集約（ダウンサンプル）
    grid = (
        out.group_by_dynamic("date", every=freq)
        .agg(_AGG[agg].alias("value"))
        .sort("date")
    )

    # アップサンプル: グリッドに欠けた周期を補い、指定方式で埋める
    if upsample_fill and len(grid) > 1:
        grid = grid.upsample(time_column="date", every=freq)
        if upsample_fill == "forward":
            grid = grid.with_columns(pl.col("value").forward_fill())
        elif upsample_fill == "backward":
            grid = grid.with_columns(pl.col("value").backward_fill())

    return grid


def align_many(
    sources: dict[str, pl.DataFrame],
    freq: str = "1mo",
    agg: str = "mean",
    upsample_fill: str = "forward",
) -> pl.DataFrame:
    """複数ソースを共通グリッドにアラインし、date を軸に横結合する。

    sources: {名前: DataFrame}。各 DataFrame の value 列が名前列にリネームされる。
    退化（空/全null）したソースはスキップする。
    """
    merged: pl.DataFrame | None = None
    for name, df in sources.items():
        aligned = align_frequency(df, freq=freq, agg=agg, upsample_fill=upsample_fill)
        if aligned.is_empty():
            continue
        aligned = aligned.rename({"value": name})
        merged = aligned if merged is None else merged.join(aligned, on="date", how="full", coalesce=True)

    if merged is None:
        return pl.DataFrame()
    return merged.sort("date")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resample a time-series CSV to a target frequency.")
    parser.add_argument("--input", required=True, help="Input CSV (date, value columns).")
    parser.add_argument("--freq", default="1mo", help="Target frequency (1d/1w/1mo/1q/1y).")
    parser.add_argument("--agg", default="mean", help="Downsample aggregation.")
    parser.add_argument("--out", help="Output CSV filename.")
    args = parser.parse_args()

    df = pl.read_csv(args.input)
    out = align_frequency(df, freq=args.freq, agg=args.agg)
    if args.out:
        out.write_csv(args.out)
        print(f"Saved {len(out)} rows to {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
