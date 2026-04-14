"""
EEG转换器
协调EEG文件读取和数据写入
"""

import os
from pathlib import Path
from typing import Optional, Union, Literal, Dict, Tuple

from .parser import read_eeg_file
from .writer import write_eeg_file, write_eeg_to_brainvision, write_eeg_to_eeglab, write_eeg_to_edf

# 导出格式类型
ExportFormat = Literal["BrainVision", "EEGLAB", "EDF"]


def convert_eeg_format(file_path: Union[str, Path],
                       export_format: ExportFormat = "BrainVision",
                       output_path: Optional[Union[str, Path]] = None,
                       preload: bool = False,
                       overwrite: bool = False,
                       verbose: Optional[bool] = None) -> Tuple['mne.io.BaseRaw', str]:
    """
    转换EEG文件格式
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
    export_format : ExportFormat, optional
        导出格式，默认"BrainVision"
    output_path : str or Path, optional
        输出文件路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
        
    Returns
    -------
    tuple
        (raw对象, 输出文件路径)
    """
    file_path = Path(file_path)
    
    # 读取EEG文件
    parsed = read_eeg_file(file_path, preload=preload, verbose=verbose)
    raw = parsed['raw']
    
    # 确定输出路径
    if output_path is None:
        # 默认输出到输入文件所在目录的convert子目录
        output_dir = file_path.parent / "convert"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 根据导出格式确定扩展名
        if export_format == "BrainVision":
            ext = ".vhdr"
        elif export_format == "EEGLAB":
            ext = ".set"
        elif export_format == "EDF":
            ext = ".edf"
        else:
            ext = ".vhdr"
        
        output_path = output_dir / (file_path.stem + ext)
    else:
        output_path = Path(output_path)
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 写入文件
    output_file = write_eeg_file(
        raw=raw,
        output_path=output_path,
        export_format=export_format,
        overwrite=overwrite,
        verbose=verbose
    )
    
    return raw, output_file


def convert_eeg_to_brainvision(file_path: Union[str, Path],
                               output_path: Optional[Union[str, Path]] = None,
                               preload: bool = False,
                               overwrite: bool = False,
                               verbose: Optional[bool] = None) -> Tuple['mne.io.BaseRaw', str]:
    """
    将EEG文件转换为BrainVision格式
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
    output_path : str or Path, optional
        输出文件路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
        
    Returns
    -------
    tuple
        (raw对象, 输出文件路径)
    """
    return convert_eeg_format(
        file_path=file_path,
        export_format="BrainVision",
        output_path=output_path,
        preload=preload,
        overwrite=overwrite,
        verbose=verbose
    )


def convert_eeg_to_eeglab(file_path: Union[str, Path],
                          output_path: Optional[Union[str, Path]] = None,
                          preload: bool = False,
                          overwrite: bool = False,
                          verbose: Optional[bool] = None) -> Tuple['mne.io.BaseRaw', str]:
    """
    将EEG文件转换为EEGLAB格式
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
    output_path : str or Path, optional
        输出文件路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
        
    Returns
    -------
    tuple
        (raw对象, 输出文件路径)
    """
    return convert_eeg_format(
        file_path=file_path,
        export_format="EEGLAB",
        output_path=output_path,
        preload=preload,
        overwrite=overwrite,
        verbose=verbose
    )


def convert_eeg_to_edf(file_path: Union[str, Path],
                       output_path: Optional[Union[str, Path]] = None,
                       preload: bool = False,
                       overwrite: bool = False,
                       verbose: Optional[bool] = None) -> Tuple['mne.io.BaseRaw', str]:
    """
    将EEG文件转换为EDF格式
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
    output_path : str or Path, optional
        输出文件路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
        
    Returns
    -------
    tuple
        (raw对象, 输出文件路径)
    """
    return convert_eeg_format(
        file_path=file_path,
        export_format="EDF",
        output_path=output_path,
        preload=preload,
        overwrite=overwrite,
        verbose=verbose
    )


def convert_eeg_to_format(file_path: Union[str, Path],
                          output_format: str = "BrainVision",
                          output_path: Optional[Union[str, Path]] = None,
                          preload: bool = False,
                          overwrite: bool = False,
                          verbose: Optional[bool] = None) -> Tuple['mne.io.BaseRaw', str]:
    """
    通用转换函数，支持多种输出格式
    
    Parameters
    ----------
    file_path : str or Path
        输入文件路径
    output_format : str
        输出格式，支持"BrainVision"、"EEGLAB"、"EDF"
    output_path : str or Path, optional
        输出文件路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
        
    Returns
    -------
    tuple
        (raw对象, 输出文件路径)
    """
    # 验证输出格式
    valid_formats = ["BrainVision", "EEGLAB", "EDF"]
    if output_format not in valid_formats:
        raise ValueError(f"不支持的输出格式: {output_format}，支持格式: {valid_formats}")
    
    return convert_eeg_format(
        file_path=file_path,
        export_format=output_format,  # type: ignore
        output_path=output_path,
        preload=preload,
        overwrite=overwrite,
        verbose=verbose
    )