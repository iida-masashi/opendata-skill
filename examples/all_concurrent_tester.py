import concurrent.futures
import os
import subprocess
import sys
import time

# List of scripts to test (fetching real data)
SCRIPTS = [
    # API Key Required (Make sure .env is loaded)
    "scripts/estat_fetcher.py",  # Needs ESTAT_API_KEY
    "scripts/mlit_fetcher.py",   # Needs MLIT_API_KEY
    "scripts/resas_fetcher.py",  # Needs RESAS_API_KEY
    "scripts/odpt_fetcher.py",   # Needs ODPT_API_KEY
    "scripts/corp_fetcher.py",   # Needs CORP_API_KEY
    "scripts/youtube_fetcher.py",# Needs YOUTUBE_API_KEY

    # No API Key Required
    "scripts/yahoo_fetcher.py",
    "scripts/meteo_fetcher.py",
    "scripts/plateau_fetcher.py",
    "scripts/worldbank_fetcher.py",
    "scripts/oecd_fetcher.py",
    "scripts/trends_fetcher.py",
    "scripts/ckan_fetcher.py",
    "scripts/zipcode_fetcher.py",
    "scripts/gsi_fetcher.py",
    "scripts/power_fetcher.py",
    "scripts/jshis_fetcher.py",
    "scripts/air_quality_fetcher.py",
    "scripts/river_fetcher.py",
    "scripts/holiday_fetcher.py",
    "scripts/events_fetcher.py"
]

# Sample arguments for each script to ensure they run and fetch data
SCRIPT_ARGS = {
    "estat_fetcher.py": ["--statsDataId", "0003445133", "--out", "test_estat.csv"], # Consumer Price Index  # noqa: E501
    "mlit_fetcher.py": ["--year", "2023", "--pref", "13", "--city", "13101", "--out", "test_mlit.csv"], # Tokyo Land Price  # noqa: E501
    "resas_fetcher.py": ["--pref", "13", "--city", "13101", "--out", "test_resas.csv"], # Chiyoda-ku Economy  # noqa: E501
    "odpt_fetcher.py": ["--type", "odpt:TrainInformation", "--operator", "odpt.Operator:Toei", "--out", "test_odpt.csv"], # Toei Subway  # noqa: E501
    "corp_fetcher.py": ["7010401052671", "--out", "test_corp.csv"], # National Tax Agency (Example Corp ID)  # noqa: E501
    "youtube_fetcher.py": ["dQw4w9WgXcQ", "--max", "10", "--out", "test_youtube.csv"], # Rick Roll (Example Video)  # noqa: E501

    "yahoo_fetcher.py": ["--tickers", "7203.T", "--start", "2024-01-01", "--out", "test_yahoo.csv"], # Toyota  # noqa: E501
    "meteo_fetcher.py": ["--lat", "35.6895", "--lon", "139.6917", "--out", "test_meteo.csv"], # Tokyo Weather  # noqa: E501
    "plateau_fetcher.py": ["--query", "千代田区", "--out", "test_plateau.csv"], # Chiyoda-ku 3D Model  # noqa: E501
    "worldbank_fetcher.py": ["--indicators", "NY.GDP.MKTP.CD", "--countries", "JPN", "--start", "2020", "--end", "2022", "--out", "test_wb.csv"], # Japan GDP  # noqa: E501
    "oecd_fetcher.py": ["--dataset", "MEI", "--countries", "JPN", "--start", "2022", "--end", "2022", "--out", "test_oecd.csv"], # Main Economic Indicators  # noqa: E501
    "trends_fetcher.py": ["--keywords", "Python", "--geo", "JP", "--out", "test_trends.csv"], # Google Trends  # noqa: E501
    "ckan_fetcher.py": ["--query", "AED", "--url", "https://data.e-gov.go.jp/data", "--out", "test_ckan.csv"], # e-Gov AED  # noqa: E501
    "zipcode_fetcher.py": ["1000001", "--out", "test_zipcode.csv"], # Chiyoda-ku Address
    "gsi_fetcher.py": ["Tokyo Tower", "--out", "test_gsi.csv"], # Geocoding
    "power_fetcher.py": ["--area", "tokyo", "--out", "test_power.csv"], # TEPCO Power
    "jshis_fetcher.py": ["--lat", "35.6895", "--lon", "139.6917", "--out", "test_jshis.csv"], # Earthquake Risk  # noqa: E501
    "air_quality_fetcher.py": ["--lat", "35.6895", "--lon", "139.6917", "--out", "test_air.csv"], # Air Quality  # noqa: E501
    "river_fetcher.py": ["--lat", "35.6895", "--lon", "139.6917", "--out", "test_river.csv"], # River Discharge  # noqa: E501
    "holiday_fetcher.py": ["--out", "test_holiday.csv"], # Japan Holidays
    "events_fetcher.py": ["--year", "2024", "--country", "JP", "--out", "test_events.csv"] # Tech Events  # noqa: E501
}

def run_script(script_path: str) -> str:
    """Runs a single script with defined arguments."""
    script_name = os.path.basename(script_path)  # noqa: PTH119
    args = SCRIPT_ARGS.get(script_name)

    if not args:
        return f"SKIP: No args defined for {script_name}"

    cmd = [sys.executable, script_path] + args  # noqa: RUF005
    print(f"RUNNING: {script_name}...")

    try:
        # Run with timeout to prevent hanging
        # Use encoding='utf-8' to handle Japanese characters in output
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace')  # noqa: PLW1510, S603

        if result.returncode == 0:
            return f"PASS: {script_name}"
        else:
            return f"FAIL: {script_name}\nError: {result.stderr}"

    except subprocess.TimeoutExpired:
        return f"TIMEOUT: {script_name}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {script_name} ({e!s})"

def test_concurrent_execution() -> None:
    """Runs all scripts in parallel using ThreadPoolExecutor."""

    # Filter scripts that exist
    valid_scripts = [s for s in SCRIPTS if os.path.exists(s)]  # noqa: PTH110

    print(f"Starting concurrent test for {len(valid_scripts)} scripts...")
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        future_to_script = {executor.submit(run_script, script): script for script in valid_scripts}  # noqa: E501

        results = []
        for future in concurrent.futures.as_completed(future_to_script):
            script = future_to_script[future]  # noqa: F841
            try:
                data = future.result()
                results.append(data)
                print(data.split('\n')[0]) # Print first line of result
            except Exception as exc:  # noqa: BLE001
                print(f"Generated an exception: {exc}")

    end_time = time.time()
    print(f"\nAll tests completed in {end_time - start_time:.2f} seconds.")

    # Summary
    pass_count = sum(1 for r in results if r.startswith("PASS"))
    fail_count = sum(1 for r in results if r.startswith("FAIL") or r.startswith("ERROR") or r.startswith("TIMEOUT"))  # noqa: E501

    print(f"\nSummary: PASS={pass_count}, FAIL={fail_count}")

    # Save results details
    with open("test_results_details.txt", "w", encoding="utf-8") as f:  # noqa: PTH123
        f.write("\n".join(results))

if __name__ == "__main__":
    test_concurrent_execution()
