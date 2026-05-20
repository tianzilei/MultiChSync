"""
Timeline visualization and alignment module for MultiChSync.

Generates per-subject multi-device timeline figures from marker info reports,
showing recording durations and marker counts across devices (fNIRS, EEG, ECG).

Also generates per-subject alignment JSON files consumed by ``marker basematch``.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .matcher import load_marker_csv_enhanced
from .traversal_matcher import _find_marker_csv

# Default device display order and colors
DEVICE_CONFIG = {
    "fnirs": {"color": "#4C72B0", "label": "fNIRS"},
    "eeg": {"color": "#DD8452", "label": "EEG"},
    "ecg": {"color": "#55A868", "label": "ECG"},
}


def _deduplicate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate rows for the same (device, sequence_id) pair.

    For each (device, sequence_id) group, keeps the row with the highest
    n_markers (to prefer the matched marker entry over the data-only entry).
    Also prefers non-empty sequence_duration.

    Args:
        df: DataFrame with columns [device, sequence_id, n_markers, sequence_duration]

    Returns:
        Deduplicated DataFrame with one row per (device, sequence_id).
    """
    if df.empty:
        return df

    # Sort: higher n_markers first, then non-null duration first
    df_sorted = df.copy()
    df_sorted["_duration_null"] = df_sorted["sequence_duration"].isna().astype(int)
    df_sorted = df_sorted.sort_values(
        by=["_duration_null", "n_markers"],
        ascending=[True, False],
    )

    deduped = (
        df_sorted.groupby(["device", "sequence_id"], sort=False)
        .first()
        .reset_index()
        .drop(columns=["_duration_null"])
    )
    return deduped


def _parse_subject_id(csv_path: Path) -> str:
    """
    Extract subject ID from CSV filename.

    Args:
        csv_path: Path like subject_060_marker_report.csv

    Returns:
        Subject ID string, or 'unknown' if parsing fails.
    """
    stem = csv_path.stem  # e.g. subject_060_marker_report
    # Remove prefix "subject_" and suffix "_marker_report"
    name = stem
    if name.startswith("subject_"):
        name = name[len("subject_"):]
    if name.endswith("_marker_report"):
        name = name[: -len("_marker_report")]
    return name if name else "unknown"


def _build_stacked_figure(
    df: pd.DataFrame,
    devices_in_data: List[str],
    subject_id: str,
    dpi: int,
    figsize: Optional[tuple],
) -> plt.Figure:
    """
    Build a multi-device figure where each device has ONE segmented bar.

    Sessions within each device are stacked end-to-end on a single timeline,
    sorted by file_name ascending.

    Args:
        df: DataFrame with columns [device, file_name, sequence_duration, n_markers].
        devices_in_data: Ordered list of device names present in df.
        subject_id: Subject label for title.
        dpi: Figure resolution.
        figsize: Optional (width, height). Auto-computed if None.

    Returns:
        Matplotlib Figure.
    """
    n_devices = len(devices_in_data)

    # Compute total stacked duration per device to determine x-axis limit
    total_durations = {}
    for device in devices_in_data:
        dev_df = df[df["device"] == device]
        total = dev_df["sequence_duration"].dropna().sum()
        total_durations[device] = total

    max_total = max(total_durations.values()) if total_durations else 100
    if pd.isna(max_total) or max_total <= 0:
        max_total = 100
    x_limit = max_total * 1.15

    # Figure size
    if figsize is None:
        w = max(10, min(22, x_limit / 30 + 6))
        h = max(3.0, 2.2 * n_devices + 1.5)
    else:
        w, h = figsize

    fig, axes = plt.subplots(
        n_devices, 1,
        figsize=(w, h),
        sharex=True,
        squeeze=False,
    )

    # Session colormap (qualitative, cycles if many sessions)
    cmap = plt.colormaps.get_cmap("tab10")

    for idx, device in enumerate(devices_in_data):
        ax = axes[idx][0]
        dev_df = df[df["device"] == device].copy()

        # Sort by file_name ascending
        dev_df = dev_df.sort_values(by="file_name", ascending=True).reset_index(drop=True)

        dev_color = DEVICE_CONFIG[device]["color"]
        dev_label = DEVICE_CONFIG[device]["label"]

        bar_height = 0.5
        y = 0  # single row per device
        current_left = 0.0
        session_patches = []

        for j, (_, row) in enumerate(dev_df.iterrows()):
            duration = row["sequence_duration"]
            n_markers = int(row["n_markers"])
            fname = str(row["file_name"])
            has_markers = n_markers > 0

            # Color by session index
            seg_color = cmap(j % cmap.N)

            if pd.notna(duration) and duration > 0:
                ax.barh(
                    y,
                    duration,
                    height=bar_height,
                    left=current_left,
                    color=seg_color,
                    alpha=0.85 if has_markers else 0.3,
                    edgecolor="white",
                    linewidth=0.5,
                )

                # Separator line between sessions
                if j > 0:
                    ax.axvline(x=current_left, ymin=0.45, ymax=0.55, color="white", linewidth=0.8)

                # N= label above the segment
                if has_markers:
                    ax.text(
                        current_left + duration / 2,
                        y + bar_height / 2 + 0.15,
                        f"N={n_markers}",
                        ha="center",
                        va="bottom",
                        fontsize=6,
                        color="black",
                    )

                # Session label below the segment (shortened filename)
                label = Path(fname).stem
                if len(label) > 25:
                    label = label[:22] + "..."
                ax.text(
                    current_left + duration / 2,
                    y - bar_height / 2 - 0.15,
                    label,
                    ha="center",
                    va="top",
                    fontsize=5,
                    color="gray",
                    rotation=30,
                )

                session_patches.append(
                    mpatches.Patch(color=seg_color, alpha=0.85, label=f"S{j+1}")
                )

                current_left += duration
            else:
                # No duration info — show placeholder text
                ax.text(
                    current_left + 0.5,
                    y,
                    f"{Path(fname).stem}: no duration info",
                    va="center",
                    fontsize=6,
                    color="gray",
                    style="italic",
                )

        # Styling
        ax.set_xlim(0, x_limit)
        ax.set_ylim(-1.2, 1.2)
        ax.set_yticks([0])
        ax.set_yticklabels([dev_label], fontsize=10, fontweight="bold")
        ax.grid(axis="x", alpha=0.3, linestyle="--")
        ax.tick_params(axis="y", length=0)

    # Shared x-axis label
    axes[-1][0].set_xlabel("Cumulative time (seconds)", fontsize=10)

    # Overall title
    fig.suptitle(
        f"Subject {subject_id} — Stacked Marker Timeline",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    # Legend per device (session colors)
    # Only show session legend for the first device as representative
    if devices_in_data:
        first_dev_df = df[df["device"] == devices_in_data[0]]
        n_sessions = len(first_dev_df)
        if n_sessions > 0:
            session_patches_legend = [
                mpatches.Patch(color=cmap(j % cmap.N), alpha=0.85, label=f"S{j+1}")
                for j in range(n_sessions)
            ]
            fig.legend(
                handles=session_patches_legend,
                loc="lower center",
                ncol=min(n_sessions, 12),
                frameon=True,
                fontsize=8,
                bbox_to_anchor=(0.5, -0.02),
            )

    plt.tight_layout(rect=[0, 0.06, 1, 0.94])
    return fig


def _build_alignment_json(
    df: pd.DataFrame,
    devices_in_data: List[str],
    subject_id: str,
) -> Dict[str, Any]:
    """
    Build alignment data for a subject, suitable for ``marker basematch``.

    ``starttime_align`` and ``endtime_align`` are pre-populated with
    one example group each (first-device first files, last-device last
    files).  The user edits these to define filename groups that should
    start (or end) at the same time.

    Per-device fields (``filenames``, ``durations``, ``n_markers``) are
    provided for basematch to look up individual session properties.

    Args:
        df: DataFrame with columns [device, file_name, sequence_id,
            n_markers, sequence_duration].
        devices_in_data: Ordered list of device names present in df.
        subject_id: Subject identifier.

    Returns:
        Dictionary with keys ``subject_id``, ``starttime_align``,
        ``endtime_align``, and ``devices``.
    """
    devices_list = []
    all_file_names: List[str] = []

    for device in devices_in_data:
        dev_df = df[df["device"] == device].copy()
        dev_df = dev_df.sort_values(by="file_name", ascending=True)

        sessions = []
        for _, row in dev_df.iterrows():
            fname = str(row["file_name"])
            dur = float(row["sequence_duration"]) if pd.notna(row["sequence_duration"]) and row["sequence_duration"] != "" else 0.0
            sessions.append({
                "file_name": fname,
                "sequence_id": str(row["sequence_id"]),
                "n_markers": int(row["n_markers"]),
                "duration": dur,
            })
            all_file_names.append(fname)

        devices_list.append({
            "device": device,
            "filenames": [s["file_name"] for s in sessions],
            "sequence_ids": [s["sequence_id"] for s in sessions],
            "n_markers": [s["n_markers"] for s in sessions],
            "durations": [s["duration"] for s in sessions],
        })

    # Pre-populate start/end groups by sequence_id across devices.
    # Each sequence_id that appears in multiple devices forms a start group
    # and an end group, so the user sees the expected format immediately.
    from collections import defaultdict, Counter
    _seq_to_fnames: Dict[str, List[str]] = defaultdict(list)
    _seq_device_count: Counter = Counter()
    for d in devices_list:
        for sid, fname in zip(d["sequence_ids"], d["filenames"]):
            _seq_to_fnames[sid].append(fname)
            _seq_device_count[sid] += 1
    # Only include sequence_ids that appear on **multiple** devices.
    _shared_seqs = sorted(
        (s for s, c in _seq_device_count.items() if c > 1),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    start_groups = [_seq_to_fnames[s] for s in _shared_seqs]
    # End groups: last shared sequence across all devices
    end_groups = []
    if _shared_seqs:
        end_groups.append(_seq_to_fnames[_shared_seqs[-1]])

    return {
        "subject_id": subject_id,
        "starttime_align": start_groups,
        "endtime_align": end_groups,
        # needmatch is no longer generated; basematch uses all filenames
        # from devices[].filenames when needmatch is absent.
        "devices": devices_list,
    }


def generate_timeline_figures(
    input_dir: Union[str, Path] = "Data/marker/info",
    output_dir: Union[str, Path] = "Data/marker/timeline",
    dpi: int = 150,
    figsize: Optional[tuple] = None,
    subject_data: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, Dict[str, Path]]:
    """
    Generate multi-device timeline figures **and alignment JSONs** from marker
    info report CSVs.

    Reads ``subject_*_marker_report.csv`` files from *input_dir*, or uses
    pre-computed *subject_data* DataFrames if provided.

    Produces:
    - One PNG figure per subject (stacked segmented timeline per device).
    - One JSON file per subject with alignment data consumed by
      ``multichsync marker basematch --timeline-dir``.

    Args:
        input_dir: Directory containing subject_*_marker_report.csv files
            (ignored when *subject_data* is provided).
        output_dir: Directory where timeline figures and alignment JSONs
            will be saved.
        dpi: Figure resolution (default: 150).
        figsize: Optional (width, height) in inches. If None, computed
            automatically from data.
        subject_data: Optional dict of subject_id -> DataFrame, bypassing
            CSV file reading.  When provided, *input_dir* is not scanned.

    Returns:
        Dictionary mapping subject_id to ``{"figure": Path, "alignment_json": Path}``.

    Raises:
        FileNotFoundError: If no report CSV files are found in input_dir.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved: Dict[str, Dict[str, Path]] = {}

    # Determine data source: pre-computed DataFrames > CSV files
    if subject_data:
        items = sorted(subject_data.items())
    else:
        csv_files = sorted(input_dir.glob("subject_*_marker_report.csv"))
        if not csv_files:
            raise FileNotFoundError(
                f"No subject_*_marker_report.csv files found in {input_dir}"
            )
        items = []
        for csv_path in csv_files:
            subject_id = _parse_subject_id(csv_path)
            try:
                df = pd.read_csv(csv_path, encoding="utf-8-sig")
            except Exception as e:
                print(f"  [skip] {csv_path.name}: failed to read ({e})")
                continue
            items.append((subject_id, df))

    for subject_id, df in items:

        # Validate required columns
        required_cols = {"device", "sequence_id", "n_markers", "sequence_duration"}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            print(f"  [skip] {subject_id}: missing columns {missing}")
            continue

        # Filter to known devices
        known_devices = set(DEVICE_CONFIG.keys())
        df = df[df["device"].isin(known_devices)].copy()
        if df.empty:
            print(f"  [skip] {subject_id}: no known devices found")
            continue

        # Deduplicate
        df = _deduplicate_rows(df)

        # Parse numeric sequence_id
        df["_seq_num"] = pd.to_numeric(df["sequence_id"], errors="coerce").fillna(0)

        # Sort by device order, then sequence
        df["_device_order"] = df["device"].map(
            {d: i for i, d in enumerate(DEVICE_CONFIG.keys())}
        )
        df = df.sort_values(by=["_device_order", "_seq_num"]).reset_index(drop=True)

        devices_in_data = [
            d for d in DEVICE_CONFIG.keys() if d in df["device"].values
        ]

        # ── Generate figure ────────────────────────────────────────────
        fig = _build_stacked_figure(
            df=df,
            devices_in_data=devices_in_data,
            subject_id=subject_id,
            dpi=dpi,
            figsize=figsize,
        )
        png_path = output_dir / f"subject_{subject_id}_timeline.png"
        fig.savefig(png_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        print(f"  [ok]   subject_{subject_id}_marker_report.csv -> {png_path.name}")

        # ── Generate alignment JSON ────────────────────────────────────
        alignment = _build_alignment_json(df, devices_in_data, subject_id)

        # Embed raw marker timestamps so basematch can read them directly
        # from JSON instead of locating separate marker CSV files.
        marker_base = input_dir.parent  # e.g. Data/marker (parent of info dir)
        for dev_entry in alignment["devices"]:
            device = dev_entry["device"]
            raw_list = []
            for fname in dev_entry["filenames"]:
                marker_path = _find_marker_csv(fname, device, str(marker_base))
                if marker_path is not None:
                    try:
                        dev_info = load_marker_csv_enhanced(marker_path)
                        ts = dev_info.timestamps_raw.tolist()
                    except Exception:
                        ts = []
                else:
                    ts = []
                raw_list.append(ts)
            dev_entry["raw_markers"] = raw_list

        json_path = output_dir / f"subject_{subject_id}_alignment.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(alignment, f, indent=2, default=str)
        print(f"  [ok]   alignment -> {json_path.name}")

        saved[subject_id] = {
            "figure": png_path,
            "alignment_json": json_path,
        }

    if not saved:
        raise RuntimeError("No timeline figures were generated successfully.")

    print(f"\nTimeline figures generated: {len(saved)}")
    print(f"Alignment JSONs generated: {len(saved)}")
    print(f"Output directory: {output_dir.resolve()}")

    return saved
