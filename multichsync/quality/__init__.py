"""
Data quality assessment module for MultiChSync
支持fNIRS数据质量评估，包括坏通道检测、SNR计算等功能
"""

try:
    from .assessor import (
        assess_hb_quality,
        # Comprehensive signal level assessment function
        assess_hb_quality_comprehensive,
        # Batch resting-state metrics calculation function
        batch_compute_resting_metrics,
        batch_process_snirf_folder,
        batch_process_snirf_folder_with_metadata,
        compute_comprehensive_score,
        compute_hb_snr,
        compute_hbo_hbr_pair_metrics,
        compute_resting_metrics,
        compute_signal_metrics,
        compute_task_metrics,
        expand_fnirs_bads_to_pairs,
        pair_hbo_hbr_channels,
        process_one_snirf,
        # Metadata write function (based on snirf_quality_pipeline.py)
        process_one_snirf_with_metadata,
        smart_filter_raw,
    )
    from .visualization import (
        generate_all_visualizations,
        generate_channel_quality_heatmap,
        generate_hbo_hbr_correlation_plot,
        generate_snr_distribution_histogram,
    )
except ImportError:
    # If dependencies not available, provide stub functions
    assess_hb_quality = None
    compute_hb_snr = None
    process_one_snirf = None
    batch_process_snirf_folder = None
    smart_filter_raw = None
    pair_hbo_hbr_channels = None
    expand_fnirs_bads_to_pairs = None
    assess_hb_quality_comprehensive = None
    compute_signal_metrics = None
    compute_hbo_hbr_pair_metrics = None
    compute_comprehensive_score = None
    compute_task_metrics = None
    compute_resting_metrics = None
    process_one_snirf_with_metadata = None
    batch_process_snirf_folder_with_metadata = None
    batch_compute_resting_metrics = None
    generate_channel_quality_heatmap = None
    generate_snr_distribution_histogram = None
    generate_hbo_hbr_correlation_plot = None
    generate_all_visualizations = None

__all__ = [
    "assess_hb_quality",
    "compute_hb_snr",
    "process_one_snirf",
    "batch_process_snirf_folder",
    "smart_filter_raw",
    "pair_hbo_hbr_channels",
    "expand_fnirs_bads_to_pairs",
    "assess_hb_quality_comprehensive",
    "compute_signal_metrics",
    "compute_hbo_hbr_pair_metrics",
    "compute_comprehensive_score",
    "compute_task_metrics",
    "compute_resting_metrics",
    "process_one_snirf_with_metadata",
    "batch_process_snirf_folder_with_metadata",
    "batch_compute_resting_metrics",
    "generate_channel_quality_heatmap",
    "generate_snr_distribution_histogram",
    "generate_hbo_hbr_correlation_plot",
    "generate_all_visualizations",
]
