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

from .timeline import (
    generate_timeline_figures,
)

from .matcher import (
    DriftResult,
    MatchConfidence,
    DeviceInfo,
    EnhancedTimeline,
    load_marker_csv_enhanced,
    match_multiple_files_enhanced,
)

from .matchcrop_aligned import (
    matchcrop_aligned,
    matchcrop_by_sessions,
    batch_matchcrop_from_matching_dir,
    calculate_aligned_time_range,
    apply_drift_correction,
    rename_bids_task,
    rename_bids_session,
)

from .adjust_offsets import (
    adjust_offsets,
    parse_offset_spec,
    parse_offset_list,
    map_offset_list_to_devices,
    load_and_adjust_metadata,
    rebuild_timeline,
    generate_diff_report,
)

from .traversal_matcher import (
    TraversalMatchResult,
    match_traversal,
    match_traversal_from_files,
    match_traversal_from_info,
    match_baseline,
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
    "generate_timeline_figures",
    "DriftResult",
    "MatchConfidence",
    "DeviceInfo",
    "EnhancedTimeline",
    "load_marker_csv_enhanced",
    "match_multiple_files_enhanced",
    "matchcrop_aligned",
    "matchcrop_by_sessions",
    "batch_matchcrop_from_matching_dir",
    "calculate_aligned_time_range",
    "apply_drift_correction",
    "rename_bids_task",
    "rename_bids_session",
    "adjust_offsets",
    "parse_offset_spec",
    "parse_offset_list",
    "map_offset_list_to_devices",
    "load_and_adjust_metadata",
    "rebuild_timeline",
    "generate_diff_report",
    # Traversal matcher
    "TraversalMatchResult",
    "match_traversal",
    "match_traversal_from_files",
    "match_traversal_from_info",
    "match_baseline",
]
