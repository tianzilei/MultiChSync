"""
Marker extraction module for MultiChSync
支持从不同格式的文件中提取marker信息
"""

from .extractor import (
    extract_biopac_marker,
    extract_brainvision_marker,
    extract_fnirs_marker,
    extract_marker_time_only,
    hms_to_sec,
    clean_marker_csv,
    clean_marker_folder,
)

from .info_extractor import (
    extract_marker_info,
)

from .matcher import (
    DriftResult,
    MatchConfidence,
    DeviceInfo,
    EnhancedTimeline,
    load_marker_csv_enhanced,
    match_multiple_files_enhanced,
    match_by_filename,
    load_markers_from_filename,
)

from .matchcrop_aligned import (
    matchcrop_aligned,
    calculate_aligned_time_range,
    apply_drift_correction,
    rename_bids_task,
)

from .adjust_offsets import (
    adjust_offsets,
    parse_offset_spec,
    load_and_adjust_metadata,
    rebuild_timeline,
    generate_diff_report,
)

__all__ = [
    "extract_biopac_marker",
    "extract_brainvision_marker",
    "extract_fnirs_marker",
    "extract_marker_time_only",
    "hms_to_sec",
    "clean_marker_csv",
    "clean_marker_folder",
    "extract_marker_info",
    "DriftResult",
    "MatchConfidence",
    "DeviceInfo",
    "EnhancedTimeline",
    "load_marker_csv_enhanced",
    "match_multiple_files_enhanced",
    "match_by_filename",
    "load_markers_from_filename",
    "matchcrop_aligned",
    "calculate_aligned_time_range",
    "apply_drift_correction",
    "rename_bids_task",
    "adjust_offsets",
    "parse_offset_spec",
    "load_and_adjust_metadata",
    "rebuild_timeline",
    "generate_diff_report",
]
