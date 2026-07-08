import argparse
import os


def suggest_data(keyword: str) -> None:
    """
    Suggests relevant Open Data APIs based on a keyword (Industry, Product, Use Case).
    Parses INDUSTRY_GUIDE.md for matches.
    """

    # Path to INDUSTRY_GUIDE.md
    # Assuming script is in opendata-skill/scripts/ and guide is in opendata-skill/references/  # noqa: E501
    script_dir = os.path.dirname(os.path.abspath(__file__))  # noqa: PTH100, PTH120
    guide_path = os.path.join(script_dir, "..", "references", "INDUSTRY_GUIDE.md")  # noqa: PTH118

    if not os.path.exists(guide_path):  # noqa: PTH110
        print("Error: INDUSTRY_GUIDE.md not found.")
        return

    print(f"Searching for data sources related to: '{keyword}'...")
    print("-" * 60)

    found = False
    current_section = ""

    with open(guide_path, encoding="utf-8") as f:  # noqa: PTH123
        for line in f:
            line = line.strip()  # noqa: PLW2901

            # Track sections
            if line.startswith("## "):
                current_section = line.replace("## ", "")

            # Check for match in table rows
            if "|" in line and keyword.lower() in line.lower():
                # Format: | Use Case | Source | Script | Description |
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 4:  # noqa: PLR2004
                    print(f"[{current_section}]")
                    print(f"  Use Case:    {parts[0]}")
                    print(f"  Source:      {parts[1].replace('**', '')}")
                    print(f"  Script:      {parts[2].replace('`', '')}")
                    print(f"  Description: {parts[3]}")
                    print("-" * 60)
                    found = True

    if not found:
        print("No exact matches found in the guide.")
        print("Try broader keywords like 'Manufacturing', 'Retail', 'Price', 'Weather'.")  # noqa: E501

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Suggest Open Data APIs for a given industry/keyword.")  # noqa: E501
    parser.add_argument("keyword", help="Keyword to search (e.g., 'Logistics', 'Price', 'Tourism')")  # noqa: E501

    args = parser.parse_args()
    suggest_data(args.keyword)
