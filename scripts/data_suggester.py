import argparse
import os
from pathlib import Path

from api_utils import cli_entry


def suggest_data(keyword: str) -> None:
    """
    Suggests relevant Open Data APIs based on a keyword (Industry, Product, Use Case).
    Parses INDUSTRY_GUIDE.md for matches.
    """
    script_dir = Path(__file__).resolve().parent
    guide_path = script_dir.parent / "references" / "INDUSTRY_GUIDE.md"

    if not os.path.exists(guide_path):
        raise FileNotFoundError(f"INDUSTRY_GUIDE.md not found: {guide_path}")

    print(f"Searching for data sources related to: '{keyword}'...")
    print("-" * 60)

    found = False
    current_section = ""

    with guide_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()

            # Track sections
            if line.startswith("## "):
                current_section = line.replace("## ", "")

            # Check for match in table rows
            if "|" in line and keyword.lower() in line.lower():
                # Format: | Use Case | Source | Script | Description |
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 4:
                    print(f"[{current_section}]")
                    print(f"  Use Case:    {parts[0]}")
                    print(f"  Source:      {parts[1].replace('**', '')}")
                    print(f"  Script:      {parts[2].replace('`', '')}")
                    print(f"  Description: {parts[3]}")
                    print("-" * 60)
                    found = True

    if not found:
        print("No exact matches found in the guide.")
        print("Try broader keywords like 'Manufacturing', 'Retail', 'Price', 'Weather'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest Open Data APIs for a given industry/keyword.")
    parser.add_argument("keyword", help="Keyword to search (e.g., 'Logistics', 'Price', 'Tourism')")

    args = parser.parse_args()
    suggest_data(args.keyword)


if __name__ == "__main__":
    cli_entry(main)
