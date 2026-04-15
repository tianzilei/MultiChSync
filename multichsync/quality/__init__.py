"""
Data quality assessment module for MultiChSync
支持fNIRS数据质量评估，包括坏通道检测、SNR计算等功能
"""

try:
    from .assessor import (
        assess_hb_quality,
        compute_hb_snr,
        process_one_snirf,
        batch_process_snirf_folder,
        smart_filter_raw,
        pair_hbo_hbr_channels,
        expand_fnirs_bads_to_pairs,
        # 综合信号水平评估函数
        assess_hb_quality_comprehensive,
        compute_signal_metrics,
        compute_hbo_hbr_pair_metrics,
        compute_comprehensive_score,
        compute_task_metrics,
        compute_resting_metrics,
        # 元数据写入函数（根据 snirf_quality_pipeline.py）
        process_one_snirf_with_metadata,
        batch_process_snirf_folder_with_metadata,
        # 批量静息态指标计算函数
        batch_compute_resting_metrics,
    )
except ImportError:
    # 如果依赖不可用，提供存根函数
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

__all__ = [
    'assess_hb_quality',
    'compute_hb_snr',
    'process_one_snirf',
    'batch_process_snirf_folder',
    'smart_filter_raw',
    'pair_hbo_hbr_channels',
    'expand_fnirs_bads_to_pairs',
    'assess_hb_quality_comprehensive',
    'compute_signal_metrics',
    'compute_hbo_hbr_pair_metrics',
    'compute_comprehensive_score',
    'compute_task_metrics',
    'compute_resting_metrics',
    'process_one_snirf_with_metadata',
    'batch_process_snirf_folder_with_metadata',
    'batch_compute_resting_metrics',
]