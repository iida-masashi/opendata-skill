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

DEFAULT_DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y%m", "%Y-%m"]


def parse_dates(series: pl.Series, date_format: str | None = None) -> pl.Series:
    """文字列の日付列を Date 型へ変換する（time_align / feature_engineer 共通）。

    date_format 明示時はそれを、未指定時は DEFAULT_DATE_FORMATS を順に試し、
    元の非null値を **全件** 解析できた最初のフォーマットを採用する。どれも
    全件を解析できない場合（一部だけ解析できる場合を含む）は、黙って null 化
    せず ValueError を送出する。元から null の値は null のまま残す。
    """
    non_null_before = series.drop_nulls().len()
    formats = [date_format] if date_format else DEFAULT_DATE_FORMATS
    best = 0
    for fmt in formats:
        cand = series.str.strptime(pl.Date, fmt, strict=False)
        parsed = cand.drop_nulls().len()
        if non_null_before > 0 and parsed == non_null_before:
            return cand
        best = max(best, parsed)
    raise ValueError(
        f"Could not parse date column '{series.name}' with formats {formats}: "
        f"at most {best} of {non_null_before} non-null values parsed. "
        "Pass date_format explicitly."
    )


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

    戻り値は date / value の2列。空入力は空DFを返す。date_col / value_col /
    filter_col が無い場合は KeyError、filter_val に一致する行が無い場合や
    日付・値の変換で元の非null値が失われる場合は ValueError を送出する
    （黙って行や値を落とさない）。
    """
    if df.is_empty():
        return pl.DataFrame()
    if agg not in _AGG:
        raise ValueError(f"Unknown agg '{agg}'. Available: {list(_AGG)}")
    for col in (date_col, value_col, filter_col):
        if col is not None and col not in df.columns:
            raise KeyError(f"Column '{col}' not found. Available: {df.columns}")

    if filter_col is not None:
        df = df.filter(pl.col(filter_col) == filter_val)
        if df.is_empty():
            raise ValueError(f"filter {filter_col}={filter_val!r} matched no rows")

    out = df.select([date_col, value_col]).rename({date_col: "date", value_col: "value"})

    # date を Date 型へ（全件を解析できるフォーマットのみ採用。元から null の行だけ落とす）
    if out["date"].dtype == pl.Utf8:
        out = out.with_columns(parse_dates(out["date"].alias(date_col)).alias("date"))
    out = out.drop_nulls("date").sort("date")
    if out.is_empty():
        return pl.DataFrame()

    # value を数値化（数値でない値が null 化されて消えるなら例外）
    before = out["value"].drop_nulls().len()
    out = out.with_columns(pl.col("value").cast(pl.Float64, strict=False))
    lost = before - out["value"].drop_nulls().len()
    if lost:
        raise ValueError(
            f"Column '{value_col}': {lost} of {before} non-null values are not numeric "
            "and would become null."
        )

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
    filters: dict[str, tuple[str, object]] | None = None,
) -> pl.DataFrame:
    """複数ソースを共通グリッドにアラインし、date を軸に横結合する。

    sources: {名前: DataFrame}。各 DataFrame の value 列が名前列にリネームされる。
    filters: {名前: (filter_col, filter_val)}。多次元ソースを1系列に絞る
    （align_frequency の filter_col/filter_val に渡す）。
    空のソースはスキップする。
    """
    filters = filters or {}
    unknown = set(filters) - set(sources)
    if unknown:
        raise KeyError(f"filters refer to unknown sources: {sorted(unknown)}")

    merged: pl.DataFrame | None = None
    for name, df in sources.items():
        filter_col, filter_val = filters.get(name, (None, None))
        aligned = align_frequency(
            df, freq=freq, agg=agg, upsample_fill=upsample_fill,
            filter_col=filter_col, filter_val=filter_val,
        )
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
