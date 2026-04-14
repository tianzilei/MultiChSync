"""
多模态神经影像数据转换工具
支持fNIRS、EEG、ECG等多种格式转换
"""

__version__ = '0.1.0'
__author__ = 'Neuroimaging Team'

from .fnirs import (
    parse_fnirs_header,
    load_coordinates,
    write_snirf,
    convert_fnirs_to_snirf,
    batch_convert_fnirs_to_snirf,
)

from .ecg import (
    parse_acq_file,
    get_channel_info,
    write_ecg_csv,
    convert_acq_to_csv,
    batch_convert_acq_to_csv,
)

from .eeg import (
    read_eeg_file,
    guess_input_format,
    write_eeg_file,
    convert_eeg_format,
    convert_eeg_to_brainvision,
    convert_eeg_to_eeglab,
    convert_eeg_to_edf,
    batch_convert_eeg_format,
    batch_convert_eeg_to_brainvision,
    batch_convert_eeg_to_eeglab,
    batch_convert_eeg_to_edf,
)

from .marker import (
    extract_biopac_marker,
    extract_brainvision_marker,
    extract_fnirs_marker,
    extract_marker_time_only,
    hms_to_sec,
    clean_marker_csv,
    clean_marker_folder,
    extract_marker_info,
)

from .quality import (
    assess_hb_quality,
    compute_hb_snr,
    process_one_snirf,
    batch_process_snirf_folder,
    smart_filter_raw,
    pair_hbo_hbr_channels,
    expand_fnirs_bads_to_pairs,
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