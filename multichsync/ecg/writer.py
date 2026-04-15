"""
ECG数据写入器
支持CSV格式输出
"""

import os
import pandas as pd
from typing import Dict, List, Optional
import numpy as np


def write_ecg_csv(
    data: pd.DataFrame,
    output_path: str,
    channels: Optional[List[str]] = None,
    float_format: str = "%.6f",
) -> str:
    """
    将ECG数据写入CSV文件

    Parameters
    ----------
    data : DataFrame
        ECG数据
    output_path : str
        输出文件路径
    channels : list, optional
        要写入的通道列表，如果为None则写入所有通道
    float_format : str, optional
        浮点数格式

    Returns
    -------
    str
        输出文件路径
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Select channels
    if channels is not None:
        # Only keep existing channels
        available_channels = [ch for ch in channels if ch in data.columns]
        if not available_channels:
            raise ValueError("指定的通道在数据中不存在")
        data_to_write = data[available_channels].copy()
    else:
        data_to_write = data.copy()

    # Write CSV
    data_to_write.to_csv(
        output_path, index=False, encoding="utf-8-sig", float_format=float_format
    )

    return output_path


def write_grouped_csv(
    data: pd.DataFrame,
    output_dir: str,
    base_filename: str,
    grouped_channels: Dict[str, List[str]],
    float_format: str = "%.6f",
) -> Dict[str, str]:
    """
    将分组的数据写入多个CSV文件

    Parameters
    ----------
    data : DataFrame
        原始数据
    output_dir : str
        输出目录
    base_filename : str
        基础文件名
    grouped_channels : dict
        分组通道字典
    float_format : str, optional
        浮点数格式

    Returns
    -------
    dict
        输出的文件路径字典，键为分组名
    """
    os.makedirs(output_dir, exist_ok=True)

    output_files = {}

    for group_name, channels in grouped_channels.items():
        if not channels:
            continue

        # Only keep existing channels
        available_channels = [ch for ch in channels if ch in data.columns]
        if not available_channels:
            continue

        # Extract grouped data
        group_data = data[available_channels].copy()

        # Generate output filename
        # Example: sub-060_ses-01_task-rest_ecg.csv, sub-060_ses-01_task-rest_input.csv
        # - 'ecg' group: remove suffix '_ecg', avoid duplication (e.g., ecg_ecg)
        # - 'input' group: remove '_ecg' or 'ecg' from end of base_filename, avoid ecg_input
        if group_name == "ecg":
            output_filename = f"{base_filename}.csv"
        elif group_name == "input":
            # Remove _ecg or ecg from end of base_filename
            if base_filename.endswith("_ecg"):
                base_for_input = base_filename[:-4]  # remove "_ecg"
            elif base_filename.endswith("ecg"):
                base_for_input = base_filename[:-3]  # remove "ecg"
            else:
                base_for_input = base_filename
            output_filename = f"{base_for_input}_input.csv"
        else:
            output_filename = f"{base_filename}_{group_name}.csv"
        output_path = os.path.join(output_dir, output_filename)

        # Write CSV
        write_ecg_csv(group_data, output_path, float_format=float_format)

        output_files[group_name] = output_path

    return output_files
