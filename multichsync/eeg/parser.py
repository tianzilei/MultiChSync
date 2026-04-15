"""
EEG文件解析器
支持Curry、EEGLAB格式文件读取
"""

import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Union
import warnings

try:
    import mne
    MNE_AVAILABLE = True
except ImportError:
    MNE_AVAILABLE = False


def guess_input_format(file_path: Union[str, Path]) -> str:
    """
    根据文件扩展名猜测输入格式
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
        
    Returns
    -------
    str
        格式名称: "eeglab" 或 "curry"
        
    Raises
    ------
    ValueError
        如果无法确定格式
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    # EEGLAB format
    if suffix == ".set":
        return "eeglab"
    
    # Curry format extensions
    curry_suffixes = {
        ".cdt", ".dap", ".dat", ".rs3", ".cef", ".cdt.dpa"
    }
    if suffix in curry_suffixes:
        return "curry"
    
    # Try to determine by file existence (EEGLAB .set files usually have corresponding .fdt files)
    if suffix == ".fdt":
        set_file = path.with_suffix(".set")
        if set_file.exists():
            return "eeglab"
    
    raise ValueError(f"Cannot determine format for: {path}")


def read_eeg_file(file_path: Union[str, Path], 
                  preload: bool = False,
                  verbose: Optional[bool] = None) -> Dict:
    """
    读取EEG文件
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
    preload : bool, optional
        是否预加载数据到内存，默认False
    verbose : bool, optional
        是否显示详细输出
        
    Returns
    -------
    dict
        包含以下键的字典：
        - 'raw': mne.io.BaseRaw对象
        - 'format': 输入格式名称
        - 'file_path': 文件路径
        - 'metadata': 文件元数据
        - 'info': 通道信息等
    """
    if not MNE_AVAILABLE:
        raise ImportError("需要安装 mne 库来读取EEG文件")
    
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"EEG文件不存在: {file_path}")
    
    # Guess input format
    input_format = guess_input_format(file_path)
    
    # Read file
    if input_format == "eeglab":
        # EEGLAB format may have separate .fdt data file
        raw = mne.io.read_raw_eeglab(file_path, preload=preload, verbose=verbose)
    else:
        # Curry format
        raw = mne.io.read_raw_curry(file_path, preload=preload, verbose=verbose)
    
    # Extract metadata
    metadata = {
        'filename': file_path.name,
        'file_size': file_path.stat().st_size,
        'format': input_format,
        'n_channels': len(raw.ch_names),
        'sfreq': raw.info['sfreq'],
        'n_samples': raw.n_times,
        'duration': raw.times[-1] if len(raw.times) > 0 else 0,
    }
    
    # Channel information
    channels = []
    for i, ch_name in enumerate(raw.ch_names):
        ch_info = {
            'index': i,
            'name': ch_name,
            'type': raw.get_channel_types()[i],
            'unit': raw._orig_units.get(ch_name, 'unknown') if hasattr(raw, '_orig_units') else 'unknown'
        }
        channels.append(ch_info)
    
    return {
        'raw': raw,
        'format': input_format,
        'file_path': str(file_path),
        'metadata': metadata,
        'channels': channels,
        'info': raw.info
    }


def get_file_info(file_path: Union[str, Path]) -> Dict:
    """
    获取EEG文件信息（不加载数据）
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
        
    Returns
    -------
    dict
        文件信息字典
    """
    try:
        # Try quick read without preloading data
        parsed = read_eeg_file(file_path, preload=False, verbose=False)
        return {
            'format': parsed['format'],
            'metadata': parsed['metadata'],
            'channels': parsed['channels']
        }
    except Exception as e:
        # If read fails, return basic info
        path = Path(file_path)
        return {
            'format': guess_input_format(file_path) if path.exists() else 'unknown',
            'metadata': {
                'filename': path.name,
                'file_size': path.stat().st_size if path.exists() else 0,
                'exists': path.exists()
            },
            'channels': [],
            'error': str(e)
        }