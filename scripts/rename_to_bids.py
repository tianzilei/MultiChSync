"""
BIDS-style File Renaming Script

Renames all data files to: sub-xx_ses-x_task-xxx_modality.extension

Supported formats:
- fNIRS: 20251101060_1.TXT → sub-060_ses-1_task-rest_fnirs.TXT
- ECG: 20251101060part1.acq → sub-060_ses-1_task-rest_ecg.acq
- EEG: WJTB_060_SEG_08_Breathe3.set → sub-060_ses-08_task-breathe_eeg.set
"""

import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, List
import json


# =========================================================
# Parsing Functions
# =========================================================


def parse_fnirs_filename(filename: str) -> Optional[Dict]:
    """
    Parse fNIRS filename patterns:
    - 20251101060_1.TXT → subject_seq
    - 20251101060_01.TXT → subject_seq (with leading zero)
    """
    stem = Path(filename).stem

    # Pattern: yyyymmddnnn_nn or yyyymmddnnn_n
    match = re.match(r"^(\d{8})(\d{3})_(\d+)$", stem, re.IGNORECASE)
    if match:
        date = match.group(1)  # 20251101 (unused)
        subject = match.group(2)  # 060
        seq = match.group(3)  # 1 or 01

        return {
            "subject_id": subject.lstrip("0") or "0",
            "session": seq,  # Use sequence number as session
            "task": "rest",
            "modality": "fnirs",
            "original_stem": stem,
        }

    return None


def parse_ecg_filename(filename: str) -> Optional[Dict]:
    """
    Parse ECG filename patterns:
    - 20251101060part1.acq → date_subject_part
    """
    stem = Path(filename).stem

    # Pattern: yyyymmddnnnpartn
    match = re.match(r"^(\d{8})(\d{3})part(\d+)$", stem, re.IGNORECASE)
    if match:
        date = match.group(1)  # 20251101 (unused)
        subject = match.group(2)
        part = match.group(3)

        return {
            "subject_id": subject.lstrip("0") or "0",
            "session": part,  # Use part number as session
            "task": "rest",
            "modality": "ecg",
            "original_stem": stem,
        }

    return None


def parse_eeg_filename(filename: str, task_from_dir: str = "") -> Optional[Dict]:
    """
    Parse EEG filename patterns:
    - WJTB_060_SEG_08_Breathe3.set → project_subject_seg_task
    - WJTB_060.set → project_subject (Picture folder, session=0)
    """
    stem = Path(filename).stem

    # Pattern 1: PPPP_nnn_SEG_nn_task or PPPP_nnn_SEG_nn
    match = re.match(
        r"^([A-Za-z]{4})_(\d{3})_SEG_(\d+)(?:_(.+))?$", stem, re.IGNORECASE
    )
    if match:
        project = match.group(1).upper()
        subject = match.group(2)
        seg = match.group(3)
        task = match.group(4) if match.group(4) else task_from_dir

        # Normalize task name: simplify Breathe1-6 to breathe, etc.
        task = task.lower() if task else "rest"
        # Remove trailing numbers from task names (Breathe3 → breathe)
        task = re.sub(r"(\D+)\d+$", r"\1", task)
        if not task:  # If task was only numbers
            task = "rest"

        return {
            "subject_id": subject.lstrip("0") or "0",
            "session": f"{int(seg):02d}",
            "task": task,
            "modality": "eeg",
            "original_stem": stem,
        }

    # Pattern 2: PPPP_nnn (Picture folder pattern like WJTB_103.set)
    match = re.match(r"^([A-Za-z]{4})_(\d{3})$", stem, re.IGNORECASE)
    if match:
        project = match.group(1).upper()
        subject = match.group(2)

        # Get task from directory, default to "picture" if not found
        task = task_from_dir if task_from_dir else "picture"

        return {
            "subject_id": subject.lstrip("0") or "0",
            "session": "00",  # Session 0 for Picture folder
            "task": task.lower(),
            "modality": "eeg",
            "original_stem": stem,
        }

    return None


def build_bids_filename(parsed: Dict, suffix: str = "") -> str:
    """
    Build BIDS-style filename from parsed components.

    Args:
        parsed: Dictionary with subject_id, session, task, modality
        suffix: Optional suffix (e.g., '_input', '_marker')

    Returns:
        BIDS-style filename: sub-xx_ses-x_task-xxx_modality[SUFFIX].ext

    Examples:
        - 20251101060_1.TXT → sub-060_ses-1_task-rest_fnirs.TXT
        - 20251101060part1.acq → sub-060_ses-1_task-rest_ecg.acq
        - WJTB_060_SEG_08_Breathe3.set → sub-060_ses-08_task-breathe_eeg.set
    """
    # Format: sub-XXX_ses-NN_task-TASK_MODALITY[SUFFIX].ext
    subject = parsed["subject_id"].zfill(3)  # Ensure 3 digits
    session = str(int(parsed["session"])).zfill(
        2
    )  # Remove leading zeros, then pad to 2 digits
    task = parsed["task"].lower()
    modality = parsed["modality"]

    filename = f"sub-{subject}_ses-{session}_task-{task}_{modality}"
    if suffix:
        filename += suffix

    return filename


# =========================================================
# Directory Mapping
# =========================================================

# EEG task directories to task name mapping
EEG_TASK_MAP = {
    "Anger": "anger",
    "Breathe1": "breathe1",
    "Breathe2": "breathe2",
    "Breathe3": "breathe3",
    "Breathe4": "breathe4",
    "Breathe5": "breathe5",
    "Breathe6": "breathe6",
    "Disgust": "disgust",
    "Fear": "fear",
    "Happiness": "happiness",
    "Neutral": "neutral",
    "Picture": "picture",
    "Resting closed": "rest_closed",
    "Resting open": "rest_open",
    "Sadness": "sadness",
}


# =========================================================
# Main Renaming Functions
# =========================================================


def get_file_type(filepath: Path) -> str:
    """Determine file type from path."""
    parts = filepath.parts
    if "marker" in parts:
        return "marker"
    if "convert" in parts:
        return "convert"
    return "raw"


def get_modality_from_path(filepath: Path) -> str:
    """Get modality from path components."""
    parts = [p.lower() for p in filepath.parts]

    if "fnirs" in parts or "nirs" in parts:
        return "fnirs"
    if "eeg" in parts:
        return "eeg"
    if "ecg" in parts:
        return "ecg"

    return "unknown"


def parse_and_rename(filepath: Path, dry_run: bool = True) -> Tuple[bool, str, str]:
    """
    Parse a file path and generate new name.

    Returns:
        (success, old_name, new_name)
    """
    filename = filepath.name
    stem = filepath.stem
    ext = filepath.suffix.lower()

    modality = get_modality_from_path(filepath)

    # Check if it's a marker file
    is_marker = "_marker" in stem
    if is_marker:
        stem = stem.replace("_marker", "")
        modality = modality  # Keep original modality

    parsed = None

    # Try parsing based on modality
    if modality == "fnirs":
        parsed = parse_fnirs_filename(stem)
    elif modality == "ecg":
        # For converted ECG files, try both patterns
        if "_input" in stem:
            # Converted: 20251101060part1_input
            test_stem = stem.replace("_input", "")
            parsed = parse_ecg_filename(test_stem + ".acq")
            if parsed:
                parsed["original_stem"] = stem
        else:
            parsed = parse_ecg_filename(stem + ext)
    elif modality == "eeg":
        # Get task from directory
        task_from_dir = ""
        for part in filepath.parts:
            if part in EEG_TASK_MAP:
                task_from_dir = EEG_TASK_MAP[part]
                break

        parsed = parse_eeg_filename(stem, task_from_dir)

    if not parsed:
        return False, filename, ""

    # Build new filename
    suffix = "_marker" if is_marker else ""
    new_filename = build_bids_filename(parsed, suffix) + ext

    # Add appropriate suffix for converted files
    if "convert" in filepath.parts and modality == "ecg" and "_input" in stem:
        # For ECG converted input files, keep _input suffix
        new_filename = new_filename.replace("_ecg.", "_ecg_input.")

    return True, filename, new_filename


def rename_directory(
    root_dir: Path, modality: str, dry_run: bool = True, recursive: bool = True
) -> Dict:
    """
    Rename all files in a directory to BIDS format.

    Returns:
        Dictionary with stats: renamed, skipped, errors
    """
    stats = {"renamed": [], "skipped": [], "errors": []}

    # Determine glob pattern
    if recursive:
        files = list(root_dir.rglob("*"))
    else:
        files = list(root_dir.glob("*"))

    # Filter to actual files
    files = [f for f in files if f.is_file()]

    for filepath in files:
        # Skip hidden files and system files
        if any(part.startswith(".") or part == "__MACOSX" for part in filepath.parts):
            stats["skipped"].append((filepath.name, "hidden file"))
            continue

        # Check if modality matches
        file_modality = get_modality_from_path(filepath)
        if modality != "all" and file_modality != modality:
            stats["skipped"].append((filepath.name, f"wrong modality: {file_modality}"))
            continue

        try:
            success, old_name, new_name = parse_and_rename(filepath, dry_run)

            if success and old_name != new_name:
                if dry_run:
                    stats["renamed"].append((old_name, new_name, "DRY RUN"))
                else:
                    new_path = filepath.parent / new_name
                    # Handle filename conflicts
                    if new_path.exists():
                        # Add counter
                        counter = 1
                        while new_path.exists():
                            new_name_counter = (
                                new_path.stem + f"_{counter}" + new_path.suffix
                            )
                            new_path = filepath.parent / new_name_counter
                            counter += 1

                    filepath.rename(new_path)
                    stats["renamed"].append((old_name, new_name, str(new_path)))
            else:
                stats["skipped"].append((old_name, "no change needed or parse failed"))

        except Exception as e:
            stats["errors"].append((filepath.name, str(e)))

    return stats


def print_stats(stats: Dict, title: str = ""):
    """Print renaming statistics."""
    if title:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")

    print(f"\n✓ Renamed: {len(stats['renamed'])} files")
    for old, new, path in stats["renamed"][:10]:
        print(f"  {old} → {new}")
    if len(stats["renamed"]) > 10:
        print(f"  ... and {len(stats['renamed']) - 10} more")

    if stats["skipped"]:
        print(f"\n⊘ Skipped: {len(stats['skipped'])} files")
        for name, reason in stats["skipped"][:5]:
            print(f"  {name}: {reason}")
        if len(stats["skipped"]) > 5:
            print(f"  ... and {len(stats['skipped']) - 5} more")

    if stats["errors"]:
        print(f"\n✗ Errors: {len(stats['errors'])} files")
        for name, error in stats["errors"][:5]:
            print(f"  {name}: {error}")


# =========================================================
# Main Entry Point
# =========================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Rename files to BIDS format: sub-xx_ses-x_task-xxx_modality.ext"
    )
    parser.add_argument(
        "--input-dir", "-i", default="Data", help="Root directory containing data files"
    )
    parser.add_argument(
        "--modality",
        "-m",
        choices=["fnirs", "ecg", "eeg", "all"],
        default="all",
        help="Which modality to process",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        default=True,
        help="Preview changes without renaming",
    )
    parser.add_argument(
        "--execute",
        "-e",
        action="store_true",
        help="Execute renaming (default is dry-run)",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        default=True,
        help="Process subdirectories recursively",
    )

    args = parser.parse_args()

    root_dir = Path(args.input_dir)

    if not root_dir.exists():
        print(f"Error: Directory not found: {root_dir}")
        return

    print(f"Processing: {root_dir}")
    print(f"Modality: {args.modality}")
    print(f"Mode: {'DRY RUN (no changes)' if not args.execute else 'EXECUTE'}")

    # Process each type
    for modality in ["fnirs", "ecg", "eeg"]:
        if args.modality != "all" and args.modality != modality:
            continue

        # Process raw files
        raw_dir = root_dir / "raw" / modality
        if raw_dir.exists():
            print(f"\n--- Processing raw/{modality} ---")
            stats = rename_directory(
                raw_dir, modality, dry_run=not args.execute, recursive=args.recursive
            )
            print_stats(stats, f"raw/{modality}")

        # Process converted files
        convert_dir = root_dir / "convert" / modality
        if convert_dir.exists():
            print(f"\n--- Processing convert/{modality} ---")
            stats = rename_directory(
                convert_dir,
                modality,
                dry_run=not args.execute,
                recursive=args.recursive,
            )
            print_stats(stats, f"convert/{modality}")

        # Process marker files
        marker_dir = root_dir / "marker" / modality
        if marker_dir.exists():
            print(f"\n--- Processing marker/{modality} ---")
            stats = rename_directory(
                marker_dir, modality, dry_run=not args.execute, recursive=args.recursive
            )
            print_stats(stats, f"marker/{modality}")

    print(f"\n{'=' * 60}")
    if args.execute:
        print("✓ Renaming complete!")
    else:
        print("⊘ Dry run complete. Use --execute to rename files.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
