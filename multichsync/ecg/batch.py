"""
ECG批量转换
支持批量转换ACQ文件
"""

import os
from pathlib import Path
from typing import List, Dict, Optional, Union

from .converter import convert_acq_to_format, convert_acq_to_csv


def batch_convert_acq_to_csv(input_dir: str,
                              output_dir: Optional[str] = None,
                              sampling_rate: Optional[int] = 250,
                              group_by_type: bool = True,
                              float_format: str = "%.6f") -> List[Union[str, Dict[str, str]]]:
    """
    批量转换ACQ文件为CSV格式
    
    Parameters
    ----------
    input_dir : str
        输入目录路径
    output_dir : str, optional
        输出目录路径，如果为None则自动生成
    sampling_rate : int, optional
        目标采样率（Hz），默认250
    group_by_type : bool, optional
        是否按通道类型分组输出，默认True
    float_format : str, optional
        浮点数格式，默认"%.6f"
        
    Returns
    -------
    list
        转换结果列表，每个元素为文件路径或路径字典
    """
    # Handle output directory
    if output_dir is None:
        output_dir = str(Path(input_dir).parent / "convert")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    converted_files = []
    
    # Iterate input directory
    for filename in os.listdir(input_dir):
        # Skip hidden files (macOS ._ files) and system files
        if filename.startswith('.') or filename == '__MACOSX':
            continue
        if filename.lower().endswith('.acq'):
            acq_path = os.path.join(input_dir, filename)
            
            try:
                # Build output path
                base_name = Path(filename).stem
                if group_by_type:
                    # Group output to output directory (no subdirectory)
                    result = convert_acq_to_csv(
                        acq_path, output_dir, sampling_rate, 
                        group_by_type, float_format
                    )
                else:
                    # Single file output
                    output_path = os.path.join(output_dir, f"{base_name}.csv")
                    result = convert_acq_to_csv(
                        acq_path, output_path, sampling_rate, 
                        group_by_type, float_format
                    )
                
                converted_files.append(result)
                print(f"转换成功: {filename}")
                
            except Exception as e:
                print(f"转换失败 {filename}: {e}")
    
    print(f"\n共转换 {len(converted_files)} 个文件")
    return converted_files


def batch_convert_acq_to_format(input_dir: str,
                                 output_format: str = "csv",
                                 output_dir: Optional[str] = None,
                                 sampling_rate: Optional[int] = 250,
                                 group_by_type: bool = True) -> List[Union[str, Dict[str, str]]]:
    """
    批量转换ACQ文件，仅支持CSV格式输出
    
    Parameters
    ----------
    input_dir : str
        输入目录路径
    output_format : str
        输出格式，仅支持"csv"
    output_dir : str, optional
        输出目录路径，如果为None则自动生成
    sampling_rate : int, optional
        目标采样率（Hz），默认250
    group_by_type : bool, optional
        是否按通道类型分组输出，默认True
        
    Returns
    -------
    list
        转换结果列表
    """
    output_format = output_format.lower()
    
    if output_format != "csv":
        raise ValueError(f"不支持的输出格式: {output_format}，仅支持csv格式")
    
    return batch_convert_acq_to_csv(
        input_dir, output_dir, sampling_rate, group_by_type
    )