"""
Timeline visualization module for MultiChSync.

Generates per-subject multi-device timeline figures from marker info reports,
showing recording durations and marker counts across devices (fNIRS, EEG, ECG).
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd


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


def _build_combined_figure(
    df: pd.DataFrame,
    devices_in_data: List[str],
    subject_id: str,
    dpi: int,
    figsize: Optional[tuple],
) -> plt.Figure:
    """
    Build a combined multi-device figure with one subplot row per device.

    Args:
        df: DataFrame with columns [device, _seq_num, sequence_duration, n_markers].
        devices_in_data: Ordered list of device names present in df.
        subject_id: Subject label for title.
        dpi: Figure resolution.
        figsize: Optional (width, height). Auto-computed if None.

    Returns:
        Matplotlib Figure.
    """
    unique_seqs = sorted(df["_seq_num"].unique())
    seq_labels = {s: f"S{s:.0f}" for s in unique_seqs}
    n_devices = len(devices_in_data)

    # Figure size
    if figsize is None:
        w = max(10, min(20, 2.0 * len(unique_seqs) + 6))
        h = max(3.0, 2.5 * n_devices + 1.5)
    else:
        w, h = figsize

    fig, axes = plt.subplots(
        n_devices, 1,
        figsize=(w, h),
        sharex=True,
        squeeze=False,
    )

    # Global x-axis limit
    max_duration = df["sequence_duration"].dropna().max()
    if pd.isna(max_duration) or max_duration <= 0:
        max_duration = 100
    x_limit = max_duration * 1.05

    legend_patches = []

    for idx, device in enumerate(devices_in_data):
        ax = axes[idx][0]
        dev_df = df[df["device"] == device]
        dev_color = DEVICE_CONFIG[device]["color"]
        dev_label = DEVICE_CONFIG[device]["label"]

        y_positions = []
        y_labels = []
        bar_height = 0.6

        for j, (_, row) in enumerate(dev_df.iterrows()):
            y = j
            duration = row["sequence_duration"]
            n_markers = int(row["n_markers"])
            seq_num = int(row["_seq_num"])

            y_positions.append(y)
            y_labels.append(seq_labels.get(seq_num, str(seq_num)))

            has_markers = n_markers > 0

            if pd.notna(duration) and duration > 0:
                ax.barh(
                    y,
                    duration,
                    height=bar_height,
                    left=0,
                    color=dev_color,
                    alpha=0.85 if has_markers else 0.25,
                    edgecolor=dev_color,
                    linewidth=0.5,
                )

                if has_markers:
                    ax.text(
                        duration + x_limit * 0.01,
                        y,
                        f"N={n_markers}",
                        va="center",
                        fontsize=7,
                        color="black",
                    )
                else:
                    ax.text(
                        duration + x_limit * 0.01,
                        y,
                        "no markers",
                        va="center",
                        fontsize=6,
                        color="gray",
                        style="italic",
                    )
            else:
                ax.text(
                    x_limit * 0.02,
                    y,
                    "no duration info" if n_markers == 0 else f"N={n_markers}",
                    va="center",
                    fontsize=6,
                    color="gray",
                    style="italic",
                )

        ax.set_xlim(0, x_limit)
        ax.set_ylim(-0.5, len(dev_df) - 0.5)
        ax.set_ylabel(dev_label, fontsize=10, fontweight="bold")
        ax.set_yticks(y_positions if y_positions else [])
        ax.set_yticklabels(y_labels if y_labels else [], fontsize=8)
        ax.grid(axis="x", alpha=0.3, linestyle="--")
        ax.tick_params(axis="y", length=0)

        legend_patches.append(
            mpatches.Patch(color=dev_color, alpha=0.85, label=dev_label)
        )

    axes[-1][0].set_xlabel("Time (seconds)", fontsize=10)

    fig.suptitle(
        f"Subject {subject_id} — Marker Timeline Overview",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    fig.legend(
        handles=legend_patches,
        loc="lower center",
        ncol=n_devices,
        frameon=True,
        fontsize=9,
        bbox_to_anchor=(0.5, -0.02),
    )

    plt.tight_layout(rect=[0, 0.06, 1, 0.94])
    return fig


def generate_timeline_figures(
    input_dir: Union[str, Path] = "Data/marker/info",
    output_dir: Union[str, Path] = "Data/marker/timeline",
    dpi: int = 150,
    figsize: Optional[tuple] = None,
    stack: bool = False,
) -> Dict[str, Path]:
    """
    Generate multi-device timeline figures from marker info report CSVs.

    Reads all ``subject_*_marker_report.csv`` files from *input_dir*.

    When *stack* is ``False`` (default): produces one combined figure per subject
    with one horizontal track per device (fNIRS, EEG, ECG) showing recording
    duration bars and marker counts, sorted by session/sequence number.

    When *stack* is ``True``: produces one figure per subject where each device
    has a **single segmented timeline bar** — sessions are stacked end-to-end
    in file name ascending order, with each session shown as a colored segment.

    Args:
        input_dir: Directory containing subject_*_marker_report.csv files.
        output_dir: Directory where timeline figures will be saved.
        dpi: Figure resolution (default: 150).
        figsize: Optional (width, height) in inches. If None, computed
            automatically from data.
        stack: If True, each device shows one segmented timeline bar with
            sessions stacked end-to-end, sorted by file_name ascending.

    Returns:
        Dictionary mapping subject_id to saved figure path.

    Raises:
        FileNotFoundError: If no report CSV files are found in input_dir.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all subject report CSVs
    csv_files = sorted(input_dir.glob("subject_*_marker_report.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No subject_*_marker_report.csv files found in {input_dir}"
        )

    saved_paths: Dict[str, Path] = {}

    for csv_path in csv_files:
        subject_id = _parse_subject_id(csv_path)

        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except Exception as e:
            print(f"  [skip] {csv_path.name}: failed to read ({e})")
            continue

        # Validate required columns
        required_cols = {"device", "sequence_id", "n_markers", "sequence_duration"}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            print(f"  [skip] {csv_path.name}: missing columns {missing}")
            continue

        # Filter to known devices
        known_devices = set(DEVICE_CONFIG.keys())
        df = df[df["device"].isin(known_devices)].copy()
        if df.empty:
            print(f"  [skip] {csv_path.name}: no known devices found")
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

        if stack:
            # --- Stack mode: one segmented bar per device, sessions end-to-end ---
            fig = _build_stacked_figure(
                df=df,
                devices_in_data=devices_in_data,
                subject_id=subject_id,
                dpi=dpi,
                figsize=figsize,
            )

            out_path = output_dir / f"subject_{subject_id}_timeline_stacked.png"
            fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
            plt.close(fig)

            saved_paths[subject_id] = out_path
            print(f"  [ok]   {csv_path.name} -> {out_path.name}")
        else:
            # --- Combined mode: one figure with subplots per device ---
            fig = _build_combined_figure(
                df=df,
                devices_in_data=devices_in_data,
                subject_id=subject_id,
                dpi=dpi,
                figsize=figsize,
            )

            out_path = output_dir / f"subject_{subject_id}_timeline.png"
            fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
            plt.close(fig)

            saved_paths[subject_id] = out_path
            print(f"  [ok]   {csv_path.name} -> {out_path.name}")

    if not saved_paths:
        raise RuntimeError("No timeline figures were generated successfully.")

    # Print summary
    mode = "stacked (segmented)" if stack else "combined"
    print(f"\nTimeline figures generated: {len(saved_paths)} ({mode})")
    print(f"Output directory: {output_dir.resolve()}")

    return saved_paths
