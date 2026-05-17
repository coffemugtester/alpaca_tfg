"""
CSV export functionality for volatility analysis results.
"""

import csv
from pathlib import Path


def export_volatility_to_csv(results: list[dict]) -> None:
    """
    Export volatility analysis results to CSV in append mode.

    Args:
        results: List of result dicts from analyze_symbol_volatility()
                 Each dict should contain: asset, period, period_type, start_date,
                 end_date, daily_vol_std, annualized_vol, atr_14, atr_pct
    """
    if not results:
        return

    # Create directory if it doesn't exist
    csv_dir = Path.cwd() / "global_comparison"
    csv_dir.mkdir(exist_ok=True)

    csv_path = csv_dir / "volatility_analysis.csv"

    # Check if file exists to determine if we need to write header
    file_exists = csv_path.exists()

    # Write to CSV in append mode
    with csv_path.open("a", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "asset",
            "period",
            "period_type",
            "start_date",
            "end_date",
            "daily_vol_std",
            "annualized_vol",
            "atr_14",
            "atr_pct",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header if file is new
        if not file_exists:
            writer.writeheader()

        # Write rows
        writer.writerows(results)

    # Extract asset and period count for summary
    assets = set(r["asset"] for r in results)
    asset_list = ", ".join(sorted(assets))
    print(f"\nResults exported to: {csv_path}")
    print(f"Appended {len(results)} rows ({asset_list})\n")


def print_volatility_summary_table(all_results: list[list[dict]]) -> None:
    """
    Print a summary table of volatility analysis results.

    Args:
        all_results: List of result lists (one per symbol)
    """
    if not all_results:
        return

    print("\n" + "=" * 120)
    print("VOLATILITY ANALYSIS SUMMARY (Minute Data)")
    print("=" * 120)

    for symbol_results in all_results:
        if not symbol_results:
            continue

        # First result is always the overall period
        overall = symbol_results[0]
        symbol = overall["asset"]

        print(f"\n{symbol} - Overall:")
        print(f"  Period: {overall['start_date']} to {overall['end_date']}")
        print(f"  Annualized Vol: {overall['annualized_vol']:.2%}")
        print(f"  ATR: ${overall['atr_14']:.2f} ({overall['atr_pct']:.2f}%)")

        # Show semester breakdown
        semester_results = [r for r in symbol_results if r["period_type"] == "semester"]
        if semester_results:
            print(f"  Semester Breakdown ({len(semester_results)} semesters):")
            for sem in semester_results[:5]:  # Show first 5 semesters
                print(f"    {sem['period']}: Vol={sem['annualized_vol']:.2%} | ATR=${sem['atr_14']:.2f}")
            if len(semester_results) > 5:
                print(f"    ... and {len(semester_results) - 5} more semesters")

    print("\n" + "=" * 120)
    print(f"\nAll results exported to: global_comparison/volatility_analysis.csv\n")
