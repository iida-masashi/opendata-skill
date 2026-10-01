import argparse
import math

import matplotlib.pyplot as plt
import polars as pl
import seaborn as sns
from api_utils import cli_entry


def analyze_correlation(
    file1: str,
    col1: str | None,
    file2: str,
    col2: str | None,
    date_col: str = "Date",
    output_img: str | None = None,
) -> float:
    """
    Analyzes correlation between two time-series datasets.
    Merges data on a common date column and plots scatter/line charts.
    Returns the Pearson correlation coefficient. Failures raise instead of printing.
    """

    print(f"Loading {file1}...")
    df1 = pl.read_csv(file1)

    print(f"Loading {file2}...")
    df2 = pl.read_csv(file2)

    # Normalize column names for merge
    # We assume 'date_col' exists or we try to find a datetime-like column

    def find_date_col(df: pl.DataFrame, hint: str) -> str | None:
        if hint in df.columns:
            return hint
        for col in df.columns:
            if 'date' in col.lower() or 'time' in col.lower() or '年' in col or '日' in col:  # noqa: E501
                return col
        return None

    date_col1 = find_date_col(df1, date_col)
    date_col2 = find_date_col(df2, date_col)

    if not date_col1 or not date_col2:
        raise KeyError(
            f"Could not find date column '{date_col}' in one of the files. "
            f"File1 cols: {df1.columns} / File2 cols: {df2.columns}"
        )

    print(f"Merging on: {date_col1} (File1) and {date_col2} (File2)")

    # Select target columns
    # If user didn't specify a column, use the first numeric (non-date) column of that file.
    # An explicitly given column that doesn't exist is an error (no silent substitution).

    def pick_value_col(df: pl.DataFrame, col: str | None, date: str, label: str) -> str:
        if col is not None:
            if col not in df.columns:
                raise KeyError(f"Column '{col}' not found in {label}. Available: {df.columns}")
            return col
        nums = [c for c, t in df.schema.items() if t.is_numeric() and c != date]
        if not nums:
            raise ValueError(f"No numeric columns in {label}.")
        print(f"Warning: No column given. Using first numeric column from {label}: {nums[0]}")
        return nums[0]

    col1 = pick_value_col(df1, col1, date_col1, "File1")
    col2 = pick_value_col(df2, col2, date_col2, "File2")

    # Convert to datetime. strict=True: unparseable dates raise instead of becoming
    # null and being silently dropped by the inner join.
    if df1.schema[date_col1] == pl.Utf8:
        df1 = df1.with_columns(pl.col(date_col1).str.to_datetime(strict=True))
    if df2.schema[date_col2] == pl.Utf8:
        df2 = df2.with_columns(pl.col(date_col2).str.to_datetime(strict=True))

    # Rename before the join so same-named columns (e.g. both 'value') don't collide
    # and we never correlate a column with itself.
    c1, c2 = f"{col1}_1", f"{col2}_2"
    left = df1.select(pl.col(date_col1).alias("date"), pl.col(col1).alias(c1))
    right = df2.select(pl.col(date_col2).alias("date"), pl.col(col2).alias(c2))

    # Merge
    # Use inner join to find common timeframes
    merged = left.join(right, on="date", how='inner')

    if merged.height == 0:
        raise ValueError("No common dates found between the two files.")

    print(f"Merged data: {merged.height} records.")
    print(f"Analyzing correlation: {col1} (File1) vs {col2} (File2)")

    # Calculate Correlation
    corr = merged.select(pl.corr(c1, c2)).item()
    if corr is None or math.isnan(corr):
        raise ValueError(
            f"Correlation could not be computed for {col1} vs {col2} "
            f"({merged.height} common rows; constant or all-null series?)"
        )

    print(f"\nCorrelation Coefficient: {corr:.4f}")

    if abs(corr) > 0.7:  # noqa: PLR2004
        print(">> Strong Correlation detected!")
    elif abs(corr) > 0.4:  # noqa: PLR2004
        print(">> Moderate Correlation.")
    else:
        print(">> Weak Correlation.")

    # Plot
    if not output_img:
        output_img = f"correlation_{col1}_vs_{col2}.png"

    plt.figure(figsize=(10, 6))
    # numpy 配列で渡す（to_pandas() は未導入の pyarrow を要求するため）
    sns.regplot(x=merged[c1].to_numpy(), y=merged[c2].to_numpy())
    plt.xlabel(c1)
    plt.ylabel(c2)
    plt.title(f"Correlation: {col1} vs {col2} (r={corr:.2f})")
    plt.grid(True)  # noqa: FBT003

    plt.savefig(output_img)
    print(f"Saved plot to {output_img}")
    return float(corr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze correlation between two CSVs.")  # noqa: E501
    parser.add_argument("file1", help="First CSV file")
    parser.add_argument("file2", help="Second CSV file")
    parser.add_argument("--col1", help="Target column in file1")
    parser.add_argument("--col2", help="Target column in file2")
    parser.add_argument("--date", default="Date", help="Common date column name (optional)")  # noqa: E501
    parser.add_argument("--out", help="Output image filename")

    args = parser.parse_args()
    analyze_correlation(args.file1, args.col1, args.file2, args.col2, args.date, args.out)  # noqa: E501

if __name__ == "__main__":
    cli_entry(main)
