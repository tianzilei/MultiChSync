"""
ACQ文件解析器
支持Biopac ACQ格式文件读取和基本信息提取
"""

import os
import re
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union

try:
    import bioread
    BIOREAD_AVAILABLE = True
except ImportError:
    BIOREAD_AVAILABLE = False

try:
    import neurokit2 as nk
    NEUROKIT2_AVAILABLE = True
except ImportError:
    NEUROKIT2_AVAILABLE = False


def normalize_name(name: str) -> str:
    """
    标准化列名
    
    Parameters
    ----------
    name : str
        原始列名
        
    Returns
    -------
    str
        标准化后的列名
    """
    name = str(name).lower().strip()
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"[()\[\]_\-]", "", name)
    return name


def parse_acq_file(acq_path: str, sampling_rate: Optional[int] = None) -> Dict:
    """
    解析ACQ文件，返回数据字典
    
    Parameters
    ----------
    acq_path : str
        ACQ文件路径
    sampling_rate : int, optional
        目标采样率（Hz），如果为None则保持原始采样率
        
    Returns
    -------
    dict
        包含以下键的字典：
        - 'data': DataFrame，包含所有通道数据
        - 'channels': 通道信息列表
        - 'original_sr': 原始采样率
        - 'sampling_rate': 实际采样率（重采样后）
        - 'duration': 数据时长（秒）
        - 'metadata': 文件元数据
    """
    if not os.path.exists(acq_path):
        raise FileNotFoundError(f"ACQ文件不存在: {acq_path}")
    
    # Prefer bioread, then neurokit2
    if BIOREAD_AVAILABLE:
        return _parse_with_bioread(acq_path, sampling_rate)
    elif NEUROKIT2_AVAILABLE:
        return _parse_with_neurokit2(acq_path, sampling_rate)
    else:
        raise ImportError("需要安装 bioread 或 neurokit2 库来读取ACQ文件")


def _parse_with_bioread(acq_path: str, sampling_rate: Optional[int] = None) -> Dict:
    """
    使用bioread库解析ACQ文件
    """
    data = bioread.read(acq_path)
    
    # Get channel info
    channels = []
    channel_data = {}
    
    for i, ch in enumerate(data.channels):
        channel_name = ch.name if ch.name else f"Channel_{i+1}"
        channel_info = {
            'index': i,
            'name': channel_name,
            'normalized_name': normalize_name(channel_name),
            'original_name': ch.name,
            'samples': len(ch.data),
            'sampling_rate': ch.samples_per_second,
            'units': ch.units if hasattr(ch, 'units') else 'unknown'
        }
        channels.append(channel_info)
        channel_data[channel_name] = ch.data
    
    # Create DataFrame
    df = pd.DataFrame(channel_data)
    
    # Determine original sampling rate (assume all channels have same rate)
    original_sr = data.channels[0].samples_per_second if data.channels else 1000
    
    # Resample
    if sampling_rate and sampling_rate != original_sr:
        df = _resample_data(df, original_sr, sampling_rate)
        final_sr = sampling_rate
    else:
        final_sr = original_sr
    
    # Calculate duration
    duration = len(df) / final_sr if len(df) > 0 else 0
    
    return {
        'data': df,
        'channels': channels,
        'original_sr': original_sr,
        'sampling_rate': final_sr,
        'duration': duration,
        'metadata': {
            'filename': os.path.basename(acq_path),
            'file_size': os.path.getsize(acq_path),
            'channel_count': len(channels),
            'total_samples': len(df)
        }
    }


def _parse_with_neurokit2(acq_path: str, sampling_rate: Optional[int] = None) -> Dict:
    """
    使用neurokit2库解析ACQ文件
    """
    try:
        data, original_sr = nk.read_acqknowledge(acq_path)
    except Exception as e:
        raise ValueError(f"使用neurokit2读取ACQ文件失败: {e}")
    
    # Get channel info
    channels = []
    for col in data.columns:
        channel_info = {
            'index': len(channels),
            'name': col,
            'normalized_name': normalize_name(col),
            'original_name': col,
            'samples': len(data[col]),
            'sampling_rate': original_sr,
            'units': 'unknown'
        }
        channels.append(channel_info)
    
    # Resample
    if sampling_rate and sampling_rate != original_sr:
        resampled = {}
        for col in data.columns:
            resampled[col] = nk.signal_resample(
                data[col].values,
                sampling_rate=original_sr,
                desired_sampling_rate=sampling_rate,
                method="FFT"
            )
        df = pd.DataFrame(resampled)
        final_sr = sampling_rate
    else:
        df = data.copy()
        final_sr = original_sr
    
    # Calculate duration
    duration = len(df) / final_sr if len(df) > 0 else 0
    
    return {
        'data': df,
        'channels': channels,
        'original_sr': original_sr,
        'sampling_rate': final_sr,
        'duration': duration,
        'metadata': {
            'filename': os.path.basename(acq_path),
            'file_size': os.path.getsize(acq_path),
            'channel_count': len(channels),
            'total_samples': len(df)
        }
    }


def _resample_data(df: pd.DataFrame, original_sr: int, target_sr: int) -> pd.DataFrame:
    """
    使用简单线性插值进行重采样
    
    Parameters
    ----------
    df : DataFrame
        原始数据
    original_sr : int
        原始采样率
    target_sr : int
        目标采样率
        
    Returns
    -------
    DataFrame
        重采样后的数据
    """
    if original_sr == target_sr:
        return df.copy()
    
    # Calculate new time points
    original_length = len(df)
    original_times = np.arange(original_length) / original_sr
    target_length = int(original_length * target_sr / original_sr)
    target_times = np.arange(target_length) / target_sr
    
    # Interpolate each channel
    resampled_data = {}
    for col in df.columns:
        # Linear interpolation
        resampled_data[col] = np.interp(target_times, original_times, df[col].values)
    
    return pd.DataFrame(resampled_data)


def get_channel_info(acq_path: str) -> List[Dict]:
    """
    获取ACQ文件的通道信息
    
    Parameters
    ----------
    acq_path : str
        ACQ文件路径
        
    Returns
    -------
    list
        通道信息列表
    """
    parsed = parse_acq_file(acq_path, sampling_rate=None)
    return parsed['channels']


def group_channels_by_type(channels: List[Dict]) -> Dict[str, List[str]]:
    """
    根据通道名称分组
    
    Parameters
    ----------
    channels : list
        通道信息列表
        
    Returns
    -------
    dict
        分组后的通道字典
        - 'ecg': ECG相关通道
        - 'eeg': EEG相关通道  
        - 'egg': EGG相关通道
        - 'input': 输入通道
        - 'other': 其他通道
    """
    grouped = {
        'ecg': [],
        'eeg': [],
        'egg': [],
        'input': [],
        'other': []
    }
    
    for ch in channels:
        normalized = ch['normalized_name']
        
        if 'ecg' in normalized:
            grouped['ecg'].append(ch['name'])
        elif 'eeg' in normalized:
            grouped['eeg'].append(ch['name'])
        elif 'egg' in normalized:
            grouped['egg'].append(ch['name'])
        elif 'input' in normalized:
            grouped['input'].append(ch['name'])
        else:
            grouped['other'].append(ch['name'])
    
    return grouped