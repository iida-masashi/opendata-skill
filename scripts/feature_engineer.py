import argparse

import polars as pl
from api_utils import cli_entry, save_output
from time_align import parse_dates


def engineer_features(
    df: pl.DataFrame,
    date_col: str,
    target_col: str,
    lags: list[int] | None = None,
    rolling_windows: list[int] | None = None,
    impute_missing: bool = True,
    date_format: str | None = None,
    output_file: str | None = None,
) -> pl.DataFrame:
    """
    Polars を使って、予測モデルに投入するための特徴量を生成する。
    ・欠損値補完 (Interpolation)
    ・ラグ特徴量 (Lagged Features)
    ・移動平均 (Rolling Mean)
    ・カレンダー特徴量 (曜日フラグ)
    """
    if rolling_windows is None:
        rolling_windows = [7]
    if lags is None:
        lags = [1, 7]
    print(f"Engineering features for target '{target_col}'...")

    # date_format 明示時はそれを、未指定時は一般的な複数フォーマットを順に試す。
    # 全行を解析できるフォーマットが無ければ黙って壊さず例外を投げる（time_align.parse_dates）。
    if df[date_col].dtype == pl.Utf8:
        df = df.with_columns(parse_dates(df[date_col], date_format).alias(date_col))

    # ソートして時系列順を保証
    df = df.sort(date_col)

    # 0. 欠損値補完 (インテリジェント補完)
    if impute_missing:
        # Polars の interpolate を用いて線形補間を実行し、端は forward/backward fill で埋める
        df = df.with_columns(
            pl.col(target_col).interpolate().forward_fill().backward_fill().alias(target_col)
        )

    exprs = []

    # 1. ラグ特徴量
    for lag in lags:
        exprs.append(
            pl.col(target_col).shift(lag).alias(f"{target_col}_lag_{lag}")
        )

    # 2. ローリング特徴量 (移動平均)
    for window in rolling_windows:
        exprs.append(
            pl.col(target_col).rolling_mean(window_size=window).alias(f"{target_col}_rolling_mean_{window}")
        )

    # 3. カレンダー特徴量
    exprs.append(
        pl.col(date_col).dt.weekday().alias("day_of_week")  # 1 (Mon) - 7 (Sun)
    )
    exprs.append(
        (pl.col(date_col).dt.weekday() >= 6).cast(pl.Int8).alias("is_weekend")
    )

    # 特徴量の一括適用
    df = df.with_columns(exprs)

    save_output(df, output_file)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Feature Engineering Pipeline for Time-Series forecasting.")
    parser.add_argument("--input", required=True, help="Input CSV file.")
    parser.add_argument("--date_col", required=True, help="Name of the date column.")
    parser.add_argument("--target_col", required=True, help="Name of the target metric column.")
    parser.add_argument(
        "--date_format",
        help="strptime format of the date column (e.g. %%Y%%m). Auto-detected if omitted.",
    )
    parser.add_argument("--out", help="Output CSV filename")

    args = parser.parse_args()

    df = pl.read_csv(args.input)
    engineer_features(df, args.date_col, args.target_col, date_format=args.date_format, output_file=args.out)


if __name__ == "__main__":
    cli_entry(main)
