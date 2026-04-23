"""
EEG数据写入器
支持多种输出格式：BrainVision、EEGLAB、EDF等
"""

import os
import numpy as np
from pathlib import Path
from typing import Optional, Union, Literal, Tuple

try:
    import mne
    from mne import export
    MNE_AVAILABLE = True
except ImportError:
    MNE_AVAILABLE = False

# Export format types
ExportFormat = Literal["BrainVision", "EEGLAB", "EDF"]


def _normalize_export_format(export_format: ExportFormat) -> Tuple[str, str]:
    """
    将导出格式转换为MNE格式和文件扩展名
    
    Parameters
    ----------
    export_format : ExportFormat
        导出格式名称
        
    Returns
    -------
    tuple
        (mne_format, file_extension)
    """
    fmt_map = {
        "BrainVision": ("brainvision", ".vhdr"),
        "EEGLAB": ("eeglab", ".set"),
        "EDF": ("edf", ".edf"),
    }
    return fmt_map[export_format]


def _clean_annotations(raw: 'mne.io.BaseRaw') -> 'mne.io.BaseRaw':
    """
    清理超出数据范围的标注
    
    Parameters
    ----------
    raw : mne.io.BaseRaw
        EEG数据对象
        
    Returns
    -------
    mne.io.BaseRaw
        清理后的数据对象（原地修改）
    """
    if raw.annotations is None or len(raw.annotations) == 0:
        return raw
    
    sfreq = raw.info['sfreq']
    n_times = raw.n_times
    mask = np.zeros(len(raw.annotations), dtype=bool)
    
    for i, onset in enumerate(raw.annotations.onset):
        sample = int(round(onset * sfreq))
        if 0 <= sample < n_times:
            mask[i] = True
        else:
            # Annotations out of data range, skip
            pass
    
    if np.all(mask):
        # All annotations are within range
        return raw
    
    # Filter annotations
    filtered_annotations = raw.annotations[mask]
    raw.set_annotations(filtered_annotations)
    
    return raw


def write_eeg_file(raw: 'mne.io.BaseRaw',
                   output_path: Union[str, Path],
                   export_format: ExportFormat = "BrainVision",
                   overwrite: bool = False,
                   verbose: Optional[bool] = None,
                   sampling_rate: Optional[float] = None) -> str:
    """
    将EEG数据写入文件
    
    Parameters
    ----------
    raw : mne.io.BaseRaw
        EEG数据对象
    output_path : str or Path
        输出文件路径
    export_format : ExportFormat, optional
        导出格式，默认"BrainVision"
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    sampling_rate : float, optional
        目标采样率（Hz），默认None（保持原始采样率）
        
    Returns
    -------
    str
        输出文件路径
    """
    if not MNE_AVAILABLE:
        raise ImportError("需要安装 mne 库来写入EEG文件")
    
    output_path = Path(output_path)
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get MNE format and extension
    mne_format, expected_ext = _normalize_export_format(export_format)
    
    # If output path has no extension or extension does not match, add correct extension
    if output_path.suffix.lower() != expected_ext.lower():
        output_path = output_path.with_suffix(expected_ext)
    
    # Clean up annotations out of data range
    raw = _clean_annotations(raw)
    
    # Export file
    export.export_raw(
        fname=str(output_path),
        raw=raw,
        fmt=mne_format,
        overwrite=overwrite,
        verbose=verbose
    )
    
    return str(output_path)


def write_eeg_to_brainvision(raw: 'mne.io.BaseRaw',
                             output_path: Union[str, Path],
                             overwrite: bool = False,
                             verbose: Optional[bool] = None,
                             sampling_rate: Optional[float] = None) -> str:
    """
    将EEG数据写入BrainVision格式
    
    Parameters
    ----------
    raw : mne.io.BaseRaw
        EEG数据对象
    output_path : str or Path
        输出文件路径
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    sampling_rate : float, optional
        目标采样率（Hz），默认None（保持原始采样率）
        
    Returns
    -------
    str
        输出文件路径
    """
    return write_eeg_file(
        raw=raw,
        output_path=output_path,
        export_format="BrainVision",
        overwrite=overwrite,
        verbose=verbose,
        sampling_rate=sampling_rate
    )


def write_eeg_to_eeglab(raw: 'mne.io.BaseRaw',
                        output_path: Union[str, Path],
                        overwrite: bool = False,
                        verbose: Optional[bool] = None,
                        sampling_rate: Optional[float] = None) -> str:
    """
    将EEG数据写入EEGLAB格式
    
    Parameters
    ----------
    raw : mne.io.BaseRaw
        EEG数据对象
    output_path : str or Path
        输出文件路径
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    sampling_rate : float, optional
        目标采样率（Hz），默认None（保持原始采样率）
        
    Returns
    -------
    str
        输出文件路径
    """
    return write_eeg_file(
        raw=raw,
        output_path=output_path,
        export_format="EEGLAB",
        overwrite=overwrite,
        verbose=verbose,
        sampling_rate=sampling_rate
    )


def write_eeg_to_edf(raw: 'mne.io.BaseRaw',
                      output_path: Union[str, Path],
                      overwrite: bool = False,
                      verbose: Optional[bool] = None,
                      sampling_rate: Optional[float] = None) -> str:
    """
    将EEG数据写入EDF格式
    
    Parameters
    ----------
    raw : mne.io.BaseRaw
        EEG数据对象
    output_path : str or Path
        输出文件路径
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    sampling_rate : float, optional
        目标采样率（Hz），默认None（保持原始采样率）
        
    Returns
    -------
    str
        输出文件路径
    """
    return write_eeg_file(
        raw=raw,
        output_path=output_path,
        export_format="EDF",
        overwrite=overwrite,
        verbose=verbose,
        sampling_rate=sampling_rate
    )