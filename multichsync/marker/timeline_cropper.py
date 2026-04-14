"""
Timeline cropping functions for matched marker data.

Crops other device timelines to match the shortest sequence's length and position.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def crop_timelines_to_shortest(
    timeline_csv: str | Path,
    metadata_json: str | Path,
    output_dir: str | Path | None = None,
    output_prefix: str = "cropped",
    include_metadata: bool = True,
) -> Dict[str, any]:
    """
    Crop device timelines to match the shortest sequence's length and position.

    Args:
        timeline_csv: Path to matched_timeline.csv
        metadata_json: Path to matched_metadata.json
        output_dir: Output directory (default: same as input)
        output_prefix: Prefix for output files
        include_metadata: Whether to include cropped metadata

    Returns:
        Dictionary containing:
        - cropped_timeline: DataFrame with cropped timelines
        - crop_info: Info about what was cropped
        - output_files: Paths to output files
    """
    timeline_csv = Path(timeline_csv)
    metadata_json = Path(metadata_json)

    # Load data
    df = pd.read_csv(timeline_csv, encoding="utf-8-sig")
    with open(metadata_json, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Find shortest sequence
    device_info = metadata["device_info"]
    time_ranges = {}
    for device in device_info:
        name = device["name"]
        time_range = device["time_range"]
        duration = time_range[1] - time_range[0]
        time_ranges[name] = {
            "start": time_range[0],
            "end": time_range[1],
            "duration": duration,
        }

    # Find shortest (by duration)
    shortest_device = min(time_ranges.items(), key=lambda x: x[1]["duration"])
    shortest_name = shortest_device[0]
    shortest_start = shortest_device[1]["start"]
    shortest_end = shortest_device[1]["end"]
    shortest_duration = shortest_device[1]["duration"]

    print(f"Shortest sequence: {shortest_name}")
    print(f"  Time range: {shortest_start:.3f} - {shortest_end:.3f}")
    print(f"  Duration: {shortest_duration:.3f}s")

    # Crop other devices
    crop_info = {
        "reference_device": shortest_name,
        "reference_start": shortest_start,
        "reference_end": shortest_end,
        "reference_duration": shortest_duration,
        "cropped_devices": {},
    }

    # Get device columns (time and weight columns)
    device_columns = {}
    for col in df.columns:
        if col.startswith("sub-") and col.endswith("_time"):
            # Extract device name
            device_name = col.replace("_time", "")
            device_columns[device_name] = {
                "time_col": col,
                "weight_col": col.replace("_time", "_weight"),
            }

    # Process each device
    cropped_data = {df.columns[0]: df.iloc[:, 0].copy()}  # consensus_time

    for device_name, cols in device_columns.items():
        time_col = cols["time_col"]
        weight_col = cols["weight_col"]

        if device_name == shortest_name:
            # Keep reference device as-is
            cropped_data[time_col] = df[time_col].copy()
            cropped_data[weight_col] = df[weight_col].copy()
            crop_info["cropped_devices"][device_name] = {
                "action": "keep",
                "original_range": [
                    time_ranges[device_name]["start"],
                    time_ranges[device_name]["end"],
                ],
                "cropped_range": None,
            }
            print(f"  {device_name}: KEEP (reference)")
        else:
            # Crop this device to match shortest sequence
            orig_start = time_ranges[device_name]["start"]
            orig_end = time_ranges[device_name]["end"]

            # Calculate crop: align to shortest_start position
            # New times = old times - offset, where offset aligns start times
            offset = shortest_start - orig_start

            # Crop: keep events within [shortest_start, shortest_end]
            # For each row, if the device has a time value, check if it's in range

            new_times = []
            new_weights = []

            for idx in range(len(df)):
                orig_time = df[time_col].iloc[idx]
                orig_weight = df[weight_col].iloc[idx]

                if pd.isna(orig_time):
                    # No event for this device at this consensus time
                    new_times.append(None)
                    new_weights.append(orig_weight)
                else:
                    # Apply offset to align position
                    adjusted_time = orig_time + offset

                    # Check if within target range
                    if (
                        adjusted_time >= shortest_start
                        and adjusted_time <= shortest_end
                    ):
                        new_times.append(adjusted_time)
                        new_weights.append(orig_weight)
                    else:
                        # Outside range - set to NaN (not matched)
                        new_times.append(None)
                        new_weights.append(0.0)

            cropped_data[time_col] = new_times
            cropped_data[weight_col] = new_weights

            new_range = [shortest_start, shortest_end]
            crop_info["cropped_devices"][device_name] = {
                "action": "crop",
                "original_range": [orig_start, orig_end],
                "cropped_range": new_range,
                "offset_applied": offset,
            }
            print(f"  {device_name}: CROP (offset={offset:.3f}s, range={new_range})")

    # Create output DataFrame
    result_df = pd.DataFrame(cropped_data)

    # Reorder columns: consensus_time first, then device columns (time + weight)
    ordered_cols = ["consensus_time"]
    if "consensus_confidence" in result_df.columns:
        ordered_cols.append("consensus_confidence")

    # Add device columns in order
    for device_name in device_columns.keys():
        ordered_cols.append(f"{device_name}_time")
        ordered_cols.append(f"{device_name}_weight")

    # Reorder if all columns exist
    existing_ordered = [c for c in ordered_cols if c in result_df.columns]
    result_df = result_df[existing_ordered]

    # Save output
    if output_dir is None:
        output_dir = timeline_csv.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    output_csv = output_dir / f"{output_prefix}_timeline.csv"
    result_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"\nSaved cropped timeline: {output_csv}")

    # Save metadata
    if include_metadata:
        cropped_metadata = {
            "original_metadata": metadata,
            "crop_info": crop_info,
            "processing_parameters": {
                "function": "crop_timelines_to_shortest",
                "reference_device": shortest_name,
                "target_range": [shortest_start, shortest_end],
            },
        }
        output_json = output_dir / f"{output_prefix}_metadata.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(cropped_metadata, f, indent=2, ensure_ascii=False)
        print(f"Saved cropped metadata: {output_json}")
    else:
        output_json = None

    return {
        "cropped_timeline": result_df,
        "crop_info": crop_info,
        "output_files": {
            "timeline_csv": str(output_csv),
            "metadata_json": str(output_json) if output_json else None,
        },
    }


def get_crop_summary(crop_info: Dict) -> str:
    """Generate a human-readable summary of crop operations."""
    lines = []
    lines.append("=" * 60)
    lines.append("TIMELINE CROPPING SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Reference (shortest): {crop_info['reference_device']}")
    lines.append(
        f"  Range: {crop_info['reference_start']:.3f} - {crop_info['reference_end']:.3f}s"
    )
    lines.append(f"  Duration: {crop_info['reference_duration']:.3f}s")
    lines.append("")
    lines.append("Devices processed:")

    for device, info in crop_info["cropped_devices"].items():
        action = info["action"].upper()
        if action == "KEEP":
            lines.append(f"  {device}: {action}")
        else:
            orig = info["original_range"]
            cropped = info["cropped_range"]
            offset = info["offset_applied"]
            lines.append(f"  {device}: {action}")
            lines.append(f"    Original: {orig[0]:.3f} - {orig[1]:.3f}s")
            lines.append(f"    Cropped:  {cropped[0]:.3f} - {cropped[1]:.3f}s")
            lines.append(f"    Offset:   {offset:+.3f}s")

    return "\n".join(lines)


# CLI entry point
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Crop matched timelines to shortest sequence"
    )
    parser.add_argument(
        "--timeline",
        required=True,
        help="Path to matched_timeline.csv",
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="Path to matched_metadata.json",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory (default: same as input)",
    )
    parser.add_argument(
        "--output-prefix",
        default="cropped",
        help="Prefix for output files",
    )

    args = parser.parse_args()

    result = crop_timelines_to_shortest(
        timeline_csv=args.timeline,
        metadata_json=args.metadata,
        output_dir=args.output_dir,
        output_prefix=args.output_prefix,
    )

    print("\n" + get_crop_summary(result["crop_info"]))


if __name__ == "__main__":
    main()
