"""
EEG批量转换
支持批量转换EEG文件
"""

import os
from pathlib import Path
from typing import List, Optional, Union, Literal, Tuple

from .converter import convert_eeg_format, convert_eeg_to_brainvision, convert_eeg_to_eeglab, convert_eeg_to_edf

# Export format types
ExportFormat = Literal["BrainVision", "EEGLAB", "EDF"]


def batch_convert_eeg_format(input_dir: Union[str, Path],
                             export_format: ExportFormat = "BrainVision",
                             output_dir: Optional[Union[str, Path]] = None,
                             preload: bool = False,
                             overwrite: bool = False,
                             verbose: Optional[bool] = None,
                             recursive: bool = False) -> List[Tuple[str, str]]:
    """
    批量转换EEG文件格式
    
    Parameters
    ----------
    input_dir : str or Path
        输入目录路径
    export_format : ExportFormat, optional
        导出格式，默认"BrainVision"
    output_dir : str or Path, optional
        输出目录路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    recursive : bool, optional
        是否递归搜索子目录，默认False
        
    Returns
    -------
    list
        转换结果列表，每个元素为(输入文件名, 输出文件路径)元组
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")
    
    # Determine output directory
    if output_dir is None:
        output_dir = input_dir.parent / "convert"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Supported input file extensions
    supported_extensions = {
        # EEGLAB format
        '.set',
        # Curry format
        '.cdt', '.dap', '.dat', '.rs3', '.cef', '.cdt.dpa'
    }
    
    # Collect files
    eeg_files = []
    if recursive:
        # Recursive search
        for root, dirs, files in os.walk(input_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__MACOSX']
            for file in files:
                # Skip hidden files
                if file.startswith('.') or file == '__MACOSX':
                    continue
                file_path = Path(root) / file
                if file_path.suffix.lower() in supported_extensions:
                    # For .fdt files, only process corresponding .set files
                    if file_path.suffix.lower() == '.fdt':
                        set_file = file_path.with_suffix('.set')
                        if set_file.exists():
                            # Skip .fdt, let .set file handle
                            continue
                    eeg_files.append(file_path)
    else:
        # Non-recursive search
        for file in os.listdir(input_dir):
            # Skip hidden files (macOS ._ files) and system files
            if file.startswith('.') or file == '__MACOSX':
                continue
            file_path = input_dir / file
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                # For .fdt files, only process corresponding .set files
                if file_path.suffix.lower() == '.fdt':
                    set_file = file_path.with_suffix('.set')
                    if set_file.exists() and set_file in input_dir.iterdir():
                        # Skip .fdt, let .set file handle
                        continue
                eeg_files.append(file_path)
    
    total_files = len(eeg_files)
    if total_files == 0:
        print(f"在 {input_dir} 中没有找到支持的EEG文件")
        return []
    
    print(f"找到 {total_files} 个EEG文件")
    print(f"输出格式: {export_format}")
    print(f"输出目录: {output_dir}")
    
    converted_files = []
    
    for i, input_file in enumerate(eeg_files, 1):
        try:
            # Determine relative path (for maintaining directory structure)
            if recursive:
                rel_path = input_file.relative_to(input_dir)
                # Remove possible parent directory reference
                rel_path = Path(*rel_path.parts)
                output_subdir = output_dir / rel_path.parent
                output_subdir.mkdir(parents=True, exist_ok=True)
                output_file = output_subdir / (input_file.stem + _get_extension_for_format(export_format))
            else:
                output_file = output_dir / (input_file.stem + _get_extension_for_format(export_format))
            
            # Execute conversion
            raw, output_path = convert_eeg_format(
                file_path=input_file,
                export_format=export_format,
                output_path=output_file,
                preload=preload,
                overwrite=overwrite,
                verbose=verbose
            )
            
            converted_files.append((str(input_file), output_path))
            print(f"[{i}/{total_files}] 转换成功: {input_file.name} -> {os.path.relpath(output_path, output_dir)}")
            
        except Exception as e:
            print(f"[{i}/{total_files}] 转换失败 {input_file.name}: {e}")
    
    print(f"\n共转换 {len(converted_files)}/{total_files} 个文件")
    return converted_files


def batch_convert_eeg_to_brainvision(input_dir: Union[str, Path],
                                     output_dir: Optional[Union[str, Path]] = None,
                                     preload: bool = False,
                                     overwrite: bool = False,
                                     verbose: Optional[bool] = None,
                                     recursive: bool = False) -> List[Tuple[str, str]]:
    """
    批量转换EEG文件为BrainVision格式
    
    Parameters
    ----------
    input_dir : str or Path
        输入目录路径
    output_dir : str or Path, optional
        输出目录路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    recursive : bool, optional
        是否递归搜索子目录，默认False
        
    Returns
    -------
    list
        转换结果列表
    """
    return batch_convert_eeg_format(
        input_dir=input_dir,
        export_format="BrainVision",
        output_dir=output_dir,
        preload=preload,
        overwrite=overwrite,
        verbose=verbose,
        recursive=recursive
    )


def batch_convert_eeg_to_eeglab(input_dir: Union[str, Path],
                                output_dir: Optional[Union[str, Path]] = None,
                                preload: bool = False,
                                overwrite: bool = False,
                                verbose: Optional[bool] = None,
                                recursive: bool = False) -> List[Tuple[str, str]]:
    """
    批量转换EEG文件为EEGLAB格式
    
    Parameters
    ----------
    input_dir : str or Path
        输入目录路径
    output_dir : str or Path, optional
        输出目录路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    recursive : bool, optional
        是否递归搜索子目录，默认False
        
    Returns
    -------
    list
        转换结果列表
    """
    return batch_convert_eeg_format(
        input_dir=input_dir,
        export_format="EEGLAB",
        output_dir=output_dir,
        preload=preload,
        overwrite=overwrite,
        verbose=verbose,
        recursive=recursive
    )


def batch_convert_eeg_to_edf(input_dir: Union[str, Path],
                             output_dir: Optional[Union[str, Path]] = None,
                             preload: bool = False,
                             overwrite: bool = False,
                             verbose: Optional[bool] = None,
                             recursive: bool = False) -> List[Tuple[str, str]]:
    """
    批量转换EEG文件为EDF格式
    
    Parameters
    ----------
    input_dir : str or Path
        输入目录路径
    output_dir : str or Path, optional
        输出目录路径，如果为None则自动生成
    preload : bool, optional
        是否预加载数据到内存，默认False
    overwrite : bool, optional
        是否覆盖已存在的文件，默认False
    verbose : bool, optional
        是否显示详细输出
    recursive : bool, optional
        是否递归搜索子目录，默认False
        
    Returns
    -------
    list
        转换结果列表
    """
    return batch_convert_eeg_format(
        input_dir=input_dir,
        export_format="EDF",
        output_dir=output_dir,
        preload=preload,
        overwrite=overwrite,
        verbose=verbose,
        recursive=recursive
    )


def _get_extension_for_format(export_format: ExportFormat) -> str:
    """
    获取导出格式对应的文件扩展名
    
    Parameters
    ----------
    export_format : ExportFormat
        导出格式
        
    Returns
    -------
    str
        文件扩展名
    """
    if export_format == "BrainVision":
        return ".vhdr"
    elif export_format == "EEGLAB":
        return ".set"
    elif export_format == "EDF":
        return ".edf"
    else:
        return ".vhdr"