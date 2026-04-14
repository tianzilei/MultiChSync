"""
ECG转换器
协调ACQ文件解析和数据写入
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Union

from .parser import parse_acq_file, group_channels_by_type
from .writer import write_ecg_csv, write_grouped_csv


def convert_acq_to_csv(acq_path: str, 
                       output_path: Optional[str] = None,
                       sampling_rate: Optional[int] = 250,
                       group_by_type: bool = True,
                       float_format: str = "%.6f") -> Union[str, Dict[str, str]]:
    """
    将ACQ文件转换为CSV格式
    
    Parameters
    ----------
    acq_path : str
        输入ACQ文件路径
    output_path : str, optional
        输出文件路径，如果为None则自动生成
    sampling_rate : int, optional
        目标采样率（Hz），默认250
    group_by_type : bool, optional
        是否按通道类型分组输出多个文件，默认True
    float_format : str, optional
        浮点数格式，默认"%.6f"
        
    Returns
    -------
    str or dict
        如果group_by_type为False，返回单个文件路径
        如果group_by_type为True，返回文件路径字典
    """
    # 解析ACQ文件
    parsed = parse_acq_file(acq_path, sampling_rate)
    data = parsed['data']
    channels = parsed['channels']
    
    # 获取基础文件名
    base_filename = Path(acq_path).stem
    
    # 处理输出路径
    if output_path is None:
        output_dir = Path(acq_path).parent / "convert"
        os.makedirs(output_dir, exist_ok=True)
        if group_by_type:
            output_path = str(output_dir)
        else:
            output_path = str(output_dir / f"{base_filename}.csv")
    
    # 分组输出
    if group_by_type:
        # 按通道类型分组
        grouped = group_channels_by_type(channels)
        
        # 对于分组输出，output_path应该是目录路径
        # 确保目录存在
        os.makedirs(output_path, exist_ok=True)
        output_dir = output_path
        
        # 写入分组文件
        output_files = write_grouped_csv(
            data, output_dir, base_filename, grouped, float_format
        )
        
        return output_files
    else:
        # 单个文件输出
        # 如果output_path是目录，则创建文件名
        if os.path.isdir(output_path):
            output_path = os.path.join(output_path, f"{base_filename}.csv")
        else:
            # 确保输出文件的父目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 写入CSV
        result_path = write_ecg_csv(data, output_path, float_format=float_format)
        
        return result_path


def convert_acq_to_format(acq_path: str,
                          output_format: str = "csv",
                          output_path: Optional[str] = None,
                          sampling_rate: Optional[int] = 250,
                          group_by_type: bool = True) -> Union[str, Dict[str, str]]:
    """
    通用转换函数，仅支持CSV格式输出
    
    Parameters
    ----------
    acq_path : str
        输入ACQ文件路径
    output_format : str
        输出格式，仅支持"csv"
    output_path : str, optional
        输出文件路径，如果为None则自动生成
    sampling_rate : int, optional
        目标采样率（Hz），默认250
    group_by_type : bool, optional
        是否按通道类型分组输出，默认True
        
    Returns
    -------
    str or dict
        输出文件路径或路径字典
    """
    output_format = output_format.lower()
    
    if output_format != "csv":
        raise ValueError(f"不支持的输出格式: {output_format}，仅支持csv格式")
    
    return convert_acq_to_csv(
        acq_path, output_path, sampling_rate, group_by_type
    )