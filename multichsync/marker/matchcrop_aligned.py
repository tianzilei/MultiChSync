"""
matchcrop_aligned: Crop multi-device data based on aligned device timelines
Uses consensus time range from marker matching and applies drift corrections.
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .matchcrop import crop_ecg_data, crop_eeg_data, crop_fnirs_data, detect_device_type


def calculate_aligned_time_range(metadata) -> Tuple[float, float]:
    """
    Extract aligned time range from metadata.

    Prefers consensus_time_range from timeline_metadata.
    Falls back to calculating intersection of all device time_ranges.

    Parameters:
    -----------
    metadata : Dict or str
        The loaded matched_metadata.json (dict), or path to JSON file (str)

    Returns:
    --------
    Tuple[float, float]: (start_time, end_time) in consensus time
    """
    # Handle string input (file path)
    if isinstance(metadata, (str, Path)):
        json_path = Path(metadata) if isinstance(metadata, str) else metadata
        with open(json_path, "r") as f:
            metadata = json.load(f)

    timeline_meta = metadata.get("timeline_metadata", {})

    # Preferred: use consensus_time_range
    consensus_range = timeline_meta.get("consensus_time_range")
    if consensus_range and len(consensus_range) == 2:
        return (consensus_range[0], consensus_range[1])

    # Fallback: calculate intersection of device time ranges
    device_info = metadata.get("device_info", [])
    if not device_info:
        raise ValueError("No device_info found in metadata")

    # Find the overlapping range across all devices
    starts = []
    ends = []
    for dev in device_info:
        time_range = dev.get("time_range", [0, 0])
        if time_range and len(time_range) == 2:
            starts.append(time_range[0])
            ends.append(time_range[1])

    if not starts or not ends:
        raise ValueError("No valid time ranges found in device_info")

    # Return intersection (max of starts, min of ends)
    return (max(starts), min(ends))


def apply_drift_correction(consensus_time: float, drift_params: Dict) -> float:
    """
    Apply drift correction to convert consensus time to device time.

    Formula: device_time = consensus_time * scale + offset

    Parameters:
    -----------
    consensus_time : float
        Time in consensus timeline
    drift_params : Dict
        Dict with 'offset' and 'scale' keys

    Returns:
    --------
    float: Time in device's original timeline
    """
    if not drift_params:
        return consensus_time

    offset = drift_params.get("offset", 0.0)
    scale = drift_params.get("scale", 1.0)

    return consensus_time * scale + offset


def extract_taskname_from_filename(filename: str) -> Optional[str]:
    """
    Extract task name from BIDS format filename.

    Example: 'sub-068_ses-01_task-rest_fnirs' -> 'rest'
    """
    # Match pattern: _task-{taskname}_
    match = re.search(r"_task-([^_]+)_", filename)
    if match:
        return match.group(1)
    return None


def rename_bids_task(filename: str, old_taskname: str, new_taskname: str) -> str:
    """
    Rename BIDS task name in filename.

    Example: 'sub-068_ses-01_task-rest_fnirs.snirf'
             with new_taskname='mytask'
             -> 'sub-068_ses-01_task-mytask_fnirs.snirf'
    """
    # Replace the old task name with new task name
    pattern = f"_task-{old_taskname}_"
    replacement = f"_task-{new_taskname}_"

    # Handle case where task is at end before extension
    if pattern.rstrip("_") not in filename:
        pattern = f"_task-{old_taskname}(\\.|$)"
        replacement = f"_task-{new_taskname}\\1"

    return re.sub(pattern, replacement, filename)


def crop_and_rename_device(
    device_info: Dict,
    crop_start_consensus: float,
    crop_end_consensus: float,
    output_dir: Path,
    old_taskname: str,
    new_taskname: str,
) -> Dict:
    """
    Crop one device's data and rename output files.

    Parameters:
    -----------
    device_info : Dict
        Device info from matched_metadata.json
    crop_start_consensus : float
        Start time in consensus timeline
    crop_end_consensus : float
        End time in consensus timeline
    output_dir : Path
        Output directory
    old_taskname : str
        Original task name (for renaming)
    new_taskname : str
        New task name (to rename to)

    Returns:
    --------
    Dict: Crop result with output files info
    """
    device_name = device_info["name"]
    device_type = detect_device_type(device_name)
    converted_file_path = device_info.get("converted_data_file_path")

    if not converted_file_path:
        raise ValueError(f"No converted_data_file_path for device: {device_name}")

    input_file = Path(converted_file_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Data file not found: {input_file}")

    # Get drift correction for this device
    drift_corrections = device_info.get("drift_correction") or {}
    offset = drift_corrections.get("offset", 0.0)
    scale = drift_corrections.get("scale", 1.0)

    # Crop the data using existing functions
    if device_type == "ecg":
        # ECG: output is CSV file
        output_filename = f"{device_name}_ecg.csv"
        output_filename = rename_bids_task(output_filename, old_taskname, new_taskname)
        output_file = output_dir / output_filename

        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=crop_start_consensus,
            end_time=crop_end_consensus,
            device_offset=offset,
        )
        return result

    # Get this device's own task name for proper renaming
    device_name = device_info["name"]
    device_old_taskname = extract_taskname_from_filename(device_name)
    if not device_old_taskname:
        device_old_taskname = old_taskname  # Fallback to global old_taskname

    if device_type == "eeg":
        # EEG: output is directory with .vhdr, .vmrk, .eeg files
        # First crop with original name, then rename

        # Crop to temp location first
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_output_dir = Path(tmpdir) / "eeg_output"
            result = crop_eeg_data(
                input_file=input_file,
                output_dir=tmp_output_dir,
                start_time=crop_start_consensus,
                end_time=crop_end_consensus,
                device_offset=offset,
            )

            # Copy files to final location with renamed task
            output_dir.mkdir(parents=True, exist_ok=True)

            # FIX: Instead of assuming filename pattern, glob for actual output files
            # Then apply rename logic to each file found
            for ext in [".vhdr", ".vmrk", ".eeg"]:
                # Find files matching this extension in temp output dir
                # The cropped files use the input_file stem (original device name)
                cropped_files = list(tmp_output_dir.glob(f"*{ext}"))

                for src in cropped_files:
                    # Get the base name (stem + extension) from the actual cropped file
                    actual_filename = src.name

                    # Apply rename logic using THIS device's task name
                    new_name = rename_bids_task(
                        actual_filename, device_old_taskname, new_taskname
                    )

                    # Copy to final location with new name
                    dst = output_dir / new_name
                    shutil.copy2(src, dst)

        return result

    elif device_type == "fnirs":
        # fNIRS: output is SNIRF file
        output_filename = f"{device_name}.snirf"
        output_filename = rename_bids_task(
            output_filename, device_old_taskname, new_taskname
        )
        output_file = output_dir / output_filename

        result = crop_fnirs_data(
            input_file=input_file,
            output_file=output_file,
            start_time=crop_start_consensus,
            end_time=crop_end_consensus,
            device_offset=offset,
        )
        return result

    else:
        raise ValueError(f"Unknown device type: {device_type}")


def save_crop_metadata(
    output_dir: Path,
    crop_params: Dict,
    devices_cropped: List[str],
    original_metadata: Dict,
) -> Path:
    """
    Save metadata about the crop operation.
    """
    metadata = {
        "crop_parameters": crop_params,
        "devices_cropped": devices_cropped,
        "original_matched_metadata": original_metadata,
    }

    output_file = output_dir / "crop_metadata.json"
    with open(output_file, "w") as f:
        json.dump(metadata, f, indent=2)

    return output_file


def matchcrop_aligned(
    json_path,
    start_time: float,
    end_time: float,
    taskname: str = None,
) -> Dict:
    """
    Crop multi-device data based on aligned device timelines.

    This function:
    1. Reads matched_metadata.json to get device info and aligned timeline
    2. Calculates aligned time range using consensus_time_range for validation
    3. Uses user-provided start_time and end_time (required)
    4. Crops each device's raw data using drift-corrected time ranges
    5. Renames output files with new task name
    6. Saves to JSON's parent directory

    Parameters:
    -----------
    json_path : str or Path
        Path to matched_metadata.json
    start_time : float
        Start time in consensus timeline (required)
    end_time : float
        End time in consensus timeline (required)
    taskname : str
        New task name for output files (required)

    Returns:
    --------
    Dict: Processing results with cropped files info

    Raises:
    -------
    ValueError: If taskname is not provided or time range is invalid
    FileNotFoundError: If json_path doesn't exist
    """
    # Convert string to Path if needed
    if isinstance(json_path, str):
        json_path = Path(json_path)

    # Validate inputs
    if not json_path.exists():
        raise FileNotFoundError(f"Metadata JSON not found: {json_path}")

    if not taskname:
        raise ValueError("taskname is required (no default)")

    # Load metadata
    with open(json_path, "r") as f:
        metadata = json.load(f)

    # Calculate aligned time range for validation
    aligned_start, aligned_end = calculate_aligned_time_range(metadata)

    # Use user-provided times (required)
    crop_start = start_time
    crop_end = end_time

    # Validate time range
    if crop_start >= crop_end:
        raise ValueError(f"Invalid time range: start={crop_start} >= end={crop_end}")

    # Warn if user times are outside aligned range (but allow it)
    if crop_start < aligned_start or crop_end > aligned_end:
        print(f"  Warning: Crop range [{crop_start:.3f}s, {crop_end:.3f}s] extends beyond aligned range [{aligned_start:.3f}s, {aligned_end:.3f}s]")
        print(f"  This may result in missing data or errors if devices don't have data in the requested range.")

    # Get output directory (same as input JSON)
    output_dir = json_path.parent

    # Get device info
    device_info = metadata.get("device_info", [])
    if not device_info:
        raise ValueError("No device_info found in metadata")

    # Get old task name from first device
    first_device = device_info[0]
    old_taskname = extract_taskname_from_filename(first_device["name"])
    if not old_taskname:
        old_taskname = "unknown"
        print(f"  Warning: Could not extract task name, using '{old_taskname}'")

    # Process each device
    results = {
        "input_json": str(json_path),
        "output_dir": str(output_dir),
        "crop_time_range": [crop_start, crop_end],
        "old_taskname": old_taskname,
        "new_taskname": taskname,
        "cropped_devices": [],
        "output_files": {},
        "errors": [],
    }

    print(f"Cropping devices using aligned timeline:")
    print(f"  Time range: {crop_start:.3f}s - {crop_end:.3f}s")
    print(f"  Task name: {old_taskname} -> {taskname}")
    print(f"  Output directory: {output_dir}")

    for device in device_info:
        device_name = device["name"]
        device_type = detect_device_type(device_name)

        print(f"  Processing: {device_name} ({device_type})")

        try:
            crop_result = crop_and_rename_device(
                device_info=device,
                crop_start_consensus=crop_start,
                crop_end_consensus=crop_end,
                output_dir=output_dir,
                old_taskname=old_taskname,
                new_taskname=taskname,
            )

            results["cropped_devices"].append(device_name)
            results["output_files"][device_name] = crop_result
            print(f"    -> Cropped successfully")

        except Exception as e:
            error_msg = f"Failed to crop {device_name}: {str(e)}"
            print(f"    -> Error: {error_msg}")
            results["errors"].append(error_msg)

    # Save crop metadata
    crop_metadata_path = save_crop_metadata(
        output_dir=output_dir,
        crop_params={
            "crop_start": crop_start,
            "crop_end": crop_end,
            "taskname": taskname,
        },
        devices_cropped=results["cropped_devices"],
        original_metadata=metadata,
    )
    results["output_files"]["metadata"] = str(crop_metadata_path)

    # Print summary
    print(f"\nCrop complete:")
    print(f"  Devices processed: {len(results['cropped_devices'])}/{len(device_info)}")
    print(f"  Errors: {len(results['errors'])}")

    return results


def main():
    """Command-line entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Crop multi-device data based on aligned device timelines"
    )
    parser.add_argument(
        "--json-path", "-j", required=True, help="Path to matched_metadata.json"
    )
    parser.add_argument(
        "--start-time",
        "-s",
        type=float,
        required=True,
        help="Start time in consensus timeline (required)",
    )
    parser.add_argument(
        "--end-time",
        "-e",
        type=float,
        required=True,
        help="End time in consensus timeline (required)",
    )
    parser.add_argument(
        "--taskname",
        "-t",
        required=True,
        help="New task name for output files (required)",
    )

    args = parser.parse_args()

    result = matchcrop_aligned(
        json_path=Path(args.json_path),
        start_time=args.start_time,
        end_time=args.end_time,
        taskname=args.taskname,
    )

    print(f"\nProcessing complete!")
    print(f"  Output directory: {result['output_dir']}")


if __name__ == "__main__":
    main()
