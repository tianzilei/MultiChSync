"""
多模态神经影像数据转换工具
支持fNIRS、EEG、ECG等多种格式转换
"""

__version__ = '0.1.0'
__author__ = 'Neuroimaging Team'

from .ecg import (
    batch_convert_acq_to_csv,
    convert_acq_to_csv,
    get_channel_info,
    parse_acq_file,
    write_ecg_csv,
)
from .eeg import (
    batch_convert_eeg_format,
    batch_convert_eeg_to_brainvision,
    batch_convert_eeg_to_edf,
    batch_convert_eeg_to_eeglab,
    convert_eeg_format,
    convert_eeg_to_brainvision,
    convert_eeg_to_edf,
    convert_eeg_to_eeglab,
    guess_input_format,
    read_eeg_file,
    write_eeg_file,
)
from .fnirs import (
    batch_convert_fnirs_to_snirf,
    convert_fnirs_to_snirf,
    load_coordinates,
    parse_fnirs_header,
    write_snirf,
)
from .marker import (
    clean_marker_csv,
    clean_marker_folder,
    extract_biopac_marker,
    extract_brainvision_marker,
    extract_fnirs_marker,
    extract_marker_info,
    extract_marker_time_only,
    hms_to_sec,
)
from .quality import (
    assess_hb_quality,
    batch_process_snirf_folder,
    compute_hb_snr,
    expand_fnirs_bads_to_pairs,
    pair_hbo_hbr_channels,
    process_one_snirf,
    smart_filter_raw,
)

__all__ = [
    'parse_fnirs_header',
    'load_coordinates',
    'write_snirf',
    'convert_fnirs_to_snirf',
    'batch_convert_fnirs_to_snirf',
    'parse_acq_file',
    'get_channel_info',
    'write_ecg_csv',
    'convert_acq_to_csv',
    'batch_convert_acq_to_csv',
    'read_eeg_file',
    'guess_input_format',
    'write_eeg_file',
    'convert_eeg_format',
    'convert_eeg_to_brainvision',
    'convert_eeg_to_eeglab',
    'convert_eeg_to_edf',
    'batch_convert_eeg_format',
    'batch_convert_eeg_to_brainvision',
    'batch_convert_eeg_to_eeglab',
    'batch_convert_eeg_to_edf',
    'extract_biopac_marker',
    'extract_brainvision_marker',
    'extract_fnirs_marker',
    'extract_marker_time_only',
    'hms_to_sec',
    'clean_marker_csv',
    'clean_marker_folder',
    'assess_hb_quality',
    'compute_hb_snr',
    'process_one_snirf',
    'batch_process_snirf_folder',
    'smart_filter_raw',
    'pair_hbo_hbr_channels',
    'expand_fnirs_bads_to_pairs',
    'extract_marker_info',
]
