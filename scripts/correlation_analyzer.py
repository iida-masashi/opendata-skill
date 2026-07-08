import argparse

import matplotlib.pyplot as plt
import polars as pl
import seaborn as sns


def analyze_correlation(
    file1: str,
    col1: str,
    file2: str,
    col2: str,
    date_col: str = "Date",
    output_img: str | None = None,
) -> None:
    """
    Analyzes correlation between two time-series datasets.
    Merges data on a common date column and plots scatter/line charts.
    """

    print(f"Loading {file1}...")
    try:
        df1 = pl.read_csv(file1)
    except Exception as e:  # noqa: BLE001
        print(f"Error reading {file1}: {e}")
        return

    print(f"Loading {file2}...")
    try:
        df2 = pl.read_csv(file2)
    except Exception as e:  # noqa: BLE001
        print(f"Error reading {file2}: {e}")
        return

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
        print(f"Error: Could not find date column '{date_col}' in one of the files.")
        print(f"File1 cols: {df1.columns}")
        print(f"File2 cols: {df2.columns}")
        return

    print(f"Merging on: {date_col1} (File1) and {date_col2} (File2)")

    # Convert to datetime
    try:
        # Attempt to parse dates if they are strings
        if df1.schema[date_col1] == pl.Utf8:
            df1 = df1.with_columns(pl.col(date_col1).str.to_datetime(strict=False))
        if df2.schema[date_col2] == pl.Utf8:
            df2 = df2.with_columns(pl.col(date_col2).str.to_datetime(strict=False))
    except Exception as e:  # noqa: BLE001
        print(f"Note: Automatic datetime conversion failed or not needed: {e}")

    # Merge
    # Use inner join to find common timeframes
    merged = df1.join(df2, left_on=date_col1, right_on=date_col2, how='inner')

    if merged.height == 0:
        print("Error: No common dates found between the two files.")
        return

    print(f"Merged data: {merged.height} records.")

    # Select target columns
    # If user didn't specify exact columns, try to guess or use all numeric

    if col1 not in merged.columns:
        print(f"Warning: Column '{col1}' not found. Using first numeric column from File1.")  # noqa: E501
        nums = [c for c, t in df1.schema.items() if t.is_numeric()]
        if nums:
            col1 = nums[0]
        else:
            print("Error: No numeric columns in File1.")
            return

    if col2 not in merged.columns:
        print(f"Warning: Column '{col2}' not found. Using first numeric column from File2.")  # noqa: E501
        nums = [c for c, t in df2.schema.items() if t.is_numeric()]
        if nums:
            col2 = nums[0]
        else:
            print("Error: No numeric columns in File2.")
            return

    print(f"Analyzing correlation: {col1} vs {col2}")

    # Calculate Correlation
    try:
        corr_df = merged.select(pl.corr(col1, col2))
        corr = corr_df.to_series()[0]
    except Exception as e:  # noqa: BLE001
        print(f"Error calculating correlation: {e}")
        return

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
    # Use to_pandas() for seaborn plotting compatibility
    sns.regplot(data=merged.to_pandas(), x=col1, y=col2)
    plt.title(f"Correlation: {col1} vs {col2} (r={corr:.2f})")
    plt.grid(True)  # noqa: FBT003

    try:
        plt.savefig(output_img)
        print(f"Saved plot to {output_img}")
    except Exception as e:  # noqa: BLE001
        print(f"Error saving plot: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze correlation between two CSVs.")  # noqa: E501
    parser.add_argument("file1", help="First CSV file")
    parser.add_argument("file2", help="Second CSV file")
    parser.add_argument("--col1", help="Target column in file1")
    parser.add_argument("--col2", help="Target column in file2")
    parser.add_argument("--date", default="Date", help="Common date column name (optional)")  # noqa: E501
    parser.add_argument("--out", help="Output image filename")

    args = parser.parse_args()
    analyze_correlation(args.file1, args.col1, args.file2, args.col2, args.date, args.out)  # noqa: E501
