"""
MatchCrop: 匹配后裁剪多设备原始数据
结合marker匹配与原始数据裁剪，将多设备数据裁剪到统一时间范围
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import h5py
import mne
import numpy as np
import pandas as pd


# 数据文件路径映射表
DATA_PATH_MAP = {
    "ecg": "Data/convert/ECG",
    "eeg": "Data/convert/EEG",
    "fnirs": "Data/convert/fnirs",
}


def detect_device_type(device_name: str) -> str:
    """从设备名称检测设备类型"""
    device_name_lower = device_name.lower()
    if "_input" in device_name_lower or "_ecg" in device_name_lower:
        return "ecg"
    elif "_eeg" in device_name_lower:
        return "eeg"
    elif "_fnirs" in device_name_lower:
        return "fnirs"
    else:
        raise ValueError(f"无法识别设备类型: {device_name}")


def find_raw_data_file(device_name: str, device_type: str) -> Optional[Path]:
    """根据设备名称和类型查找原始数据文件"""
    base_dir = Path("Data")

    if device_type == "ecg":
        # ECG: 设备名称可能使用 _input 后缀（marker文件名），需要映射到 _ecg（数据文件名）
        # 例如：sub-071_ses-01_task-rest_input -> sub-071_ses-01_task-rest_ecg.csv
        search_name = device_name
        if "_input" in device_name.lower():
            # 将 _input 后缀替换为 _ecg
            search_name = device_name.replace("_input", "_ecg")

        ecg_dir = base_dir / "convert" / "ECG"
        if ecg_dir.exists():
            # 首先尝试精确匹配（替换后的名称）
            for f in ecg_dir.glob(f"{search_name}_ecg.csv"):
                if f.exists():
                    return f
            # 然后尝试模糊匹配（设备名在文件名中）
            for f in ecg_dir.glob("*_ecg.csv"):
                if search_name in f.stem or device_name in f.stem:
                    return f
        # 备选：直接在marker路径中查找
        marker_file = base_dir / "marker" / "ecg" / f"{device_name}_marker.csv"
        if marker_file.exists():
            # 从marker文件反推原始ecg数据
            ecg_dir = base_dir / "convert" / "ECG"
            if ecg_dir.exists():
                for f in ecg_dir.glob(f"{search_name}*_ecg.csv"):
                    return f

    elif device_type == "eeg":
        # EEG: 查找 .vhdr 文件（BrainVision格式）
        eeg_dir = base_dir / "convert" / "EEG"
        if eeg_dir.exists():
            for f in eeg_dir.glob(f"{device_name}.vhdr"):
                return f

    elif device_type == "fnirs":
        # fNIRS: 查找 .snirf 文件
        fnirs_dir = base_dir / "convert" / "fnirs"
        if fnirs_dir.exists():
            for f in fnirs_dir.glob(f"{device_name}.snirf"):
                return f

    return None


def crop_ecg_data(
    input_file: Path,
    output_file: Path,
    start_time: float,
    end_time: float,
    device_offset: float = 0.0,
) -> Dict:
    """裁剪ECG数据"""
    import warnings

    # Try reading with default header first
    df = pd.read_csv(input_file)

    # Lookup time column
    time_col = None
    for col in ["Time(sec)", "time", "Time", "reference_time"]:
        if col in df.columns:
            time_col = col
            break

    # If time column not found, might be headerless CSV
    if time_col is None:
        # Check if first row looks like numeric data (headerless case)
        # If all values in first row are numeric, it's likely headerless
        first_row = df.iloc[0]
        first_row_numeric = pd.to_numeric(first_row, errors="coerce").notna().all()

        if first_row_numeric:
            # Re-read with header=None and assign column names
            warnings.warn(
                f"CSV file '{input_file.name}' appears to have no header row. "
                f"Auto-assigning column names. If this is incorrect, "
                f"please ensure the CSV has a header row.",
                UserWarning,
            )

            # Re-read without header
            df = pd.read_csv(input_file, header=None)

            # Assign default column names based on common ECG format
            # Assume: time, ECG channel 1, ECG channel 2, ... (or detect from ncols)
            n_cols = len(df.columns)
            if n_cols >= 1:
                col_names = ["Time(sec)"] + [f"CH{i}" for i in range(1, n_cols)]
                df.columns = col_names
                time_col = "Time(sec)"
            else:
                raise ValueError(
                    f"Cannot determine column structure for CSV: {input_file}"
                )
        else:
            # First row has non-numeric values - might be actual header
            # Try again with the first row as header (might have different column names)
            df.columns = first_row.values
            df = df.iloc[1:]  # Remove the header row from data

            # Try to find time column again
            for col in ["Time(sec)", "time", "Time", "reference_time"]:
                if col in df.columns:
                    time_col = col
                    break

    if time_col is None:
        raise ValueError(f"无法找到时间列: {df.columns.tolist()}")

    # Convert time column to numeric (in case it was read as string)
    df[time_col] = pd.to_numeric(df[time_col], errors="coerce")

    # Drop rows with NaN time values
    df = df.dropna(subset=[time_col])

    # Calculate actual crop range (consider device offset)
    actual_start = start_time - device_offset
    actual_end = end_time - device_offset

    # Filter data within time range
    mask = (df[time_col] >= actual_start) & (df[time_col] <= actual_end)
    cropped_df = df[mask].copy()

    # Adjust time (subtract start offset so time starts from 0)
    cropped_df[time_col] = cropped_df[time_col] - actual_start

    # Save output
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cropped_df.to_csv(output_file, index=False)

    return {
        "original_rows": len(df),
        "cropped_rows": len(cropped_df),
        "time_range": [actual_start, actual_end],
        "output_file": str(output_file),
    }


def crop_eeg_data(
    input_file: Path,
    output_dir: Path,
    start_time: float,
    end_time: float,
    device_offset: float = 0.0,
) -> Dict:
    """裁剪EEG数据（BrainVision格式）"""
    # 读取原始数据
    raw = mne.io.read_raw_brainvision(input_file, preload=True, verbose=False)

    # 计算实际裁剪范围
    sfreq = raw.info["sfreq"]
    actual_start = start_time - device_offset
    actual_end = end_time - device_offset

    # 转换为采样点
    start_sample = max(0, int(actual_start * sfreq))
    end_sample = min(raw.n_times, int(actual_end * sfreq))

    # 确保有效范围
    if start_sample >= end_sample:
        raise ValueError(f"无效的裁剪范围: start={start_sample}, end={end_sample}")

    # 裁剪数据
    cropped_data = raw.get_data()[:, start_sample:end_sample]

    # 创建新的info对象并设置正确的times
    info = raw.info.copy()
    if info.get("meas_date") is not None:
        info.set_meas_date(None)

    # 创建新的Raw对象 - 使用从0开始的时间（通过first_samp参数）
    cropped_times = np.arange(cropped_data.shape[1]) / sfreq
    first_samp_offset = int(cropped_times[0] * sfreq) if len(cropped_times) > 0 else 0
    cropped_raw = mne.io.RawArray(
        cropped_data, info, first_samp=first_samp_offset, verbose=False
    )

    # 保存到输出目录（需要所有3个文件）
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = input_file.stem

    # 使用MNE导出
    output_path = output_dir / f"{base_name}.vhdr"
    cropped_raw.export(output_path, overwrite=True)

    # 同时复制 .vmrk 和 .eeg 文件（如果存在）
    for ext in [".vmrk", ".eeg"]:
        src = input_file.parent / f"{base_name}{ext}"
        if src.exists():
            dst = output_dir / f"{base_name}{ext}"
            shutil.copy2(src, dst)

    return {
        "original_samples": raw.n_times,
        "cropped_samples": cropped_raw.n_times,
        "time_range": [actual_start, actual_end],
        "sampling_freq": sfreq,
        "output_dir": str(output_dir),
    }


def crop_fnirs_data(
    input_file: Path,
    output_file: Path,
    start_time: float,
    end_time: float,
    device_offset: float = 0.0,
) -> Dict:
    """裁剪fNIRS数据（SNIRF格式）"""
    # 使用h5py直接操作SNIRF文件
    actual_start = start_time - device_offset
    actual_end = end_time - device_offset

    # 读取原始数据
    with h5py.File(input_file, "r") as f:
        # 获取时间数据 - SNIRF格式使用 nirs/data1/time
        time_key = "nirs/data1/time"
        if time_key in f:
            times = f[time_key][:]
            # 确保是一维数组
            if times.ndim > 1:
                times = times.flatten()
        else:
            # 尝试其他可能的键
            for key in f.keys():
                if isinstance(f[key], h5py.Dataset) and "time" in key.lower():
                    times = f[key][:]
                    if times.ndim > 1:
                        times = times.flatten()
                    break
            else:
                raise ValueError("无法在SNIRF文件中找到时间数据")

        # 找到需要保留的索引
        start_idx = max(0, np.searchsorted(times, actual_start))
        end_idx = min(len(times), np.searchsorted(times, actual_end))

        # 确保有效范围（如果请求的范围超出数据范围，使用整个数据）
        if start_idx >= end_idx:
            # 如果请求的时间范围超出数据范围，使用整个数据集
            start_idx = 0
            end_idx = len(times)
            print(f"    警告: 请求的时间范围超出数据范围，使用整个数据集")

        # 读取数据
        data_key = "nirs/data1/dataTimeSeries"
        if data_key in f:
            data = f[data_key][:]
            # 确保是2D数组 (samples x channels)
            if data.ndim == 1:
                data = data.reshape(-1, 1)
        else:
            # 尝试其他可能的键
            for key in f.keys():
                if isinstance(f[key], h5py.Dataset) and "data" in key.lower():
                    data = f[key][:]
                    if data.ndim == 1:
                        data = data.reshape(-1, 1)
                    break
            else:
                raise ValueError("无法在SNIRF文件中找到数据")

        # 裁剪数据 - 确保索引有效
        if start_idx < len(times) and end_idx <= data.shape[0]:
            cropped_times = times[start_idx:end_idx]
            data = data[start_idx:end_idx, :]
        else:
            cropped_times = times
            # 如果索引超出范围，使用整个数据
            if start_idx >= len(times):
                start_idx = 0
            if end_idx > data.shape[0]:
                end_idx = data.shape[0]
            cropped_times = times[start_idx:end_idx]
            data = data[start_idx:end_idx, :]

        # 调整时间
        cropped_times = cropped_times - cropped_times[0]

    # 创建新的SNIRF文件 - 使用 shutil 复制整个文件，然后修改数据
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 先复制整个文件
    import shutil as shutil_module

    shutil_module.copy2(input_file, output_file)

    # 然后打开并修改时间/数据
    with h5py.File(output_file, "r+") as out_f:
        # 删除并重新创建 time 数据集
        if "nirs/data1/time" in out_f:
            del out_f["nirs/data1/time"]
        out_f.create_dataset("nirs/data1/time", data=cropped_times)

        # 删除并重新创建 dataTimeSeries 数据集
        if "nirs/data1/dataTimeSeries" in out_f:
            del out_f["nirs/data1/dataTimeSeries"]
        out_f.create_dataset("nirs/data1/dataTimeSeries", data=data)

    return {
        "original_samples": len(times),
        "cropped_samples": len(cropped_times),
        "time_range": [actual_start, actual_end],
        "output_file": str(output_file),
    }


def copy_reference_data(
    device_name: str,
    device_type: str,
    output_dir: Path,
) -> Dict:
    """复制参考设备数据到输出目录"""
    input_file = find_raw_data_file(device_name, device_type)

    if input_file is None:
        raise FileNotFoundError(f"找不到设备数据文件: {device_name}")

    output_dir.mkdir(parents=True, exist_ok=True)

    if device_type == "eeg":
        # EEG需要复制所有相关文件
        output_files = []
        for ext in [".vhdr", ".vmrk", ".eeg"]:
            src = input_file.parent / f"{device_name}{ext}"
            if src.exists():
                dst = output_dir / f"{device_name}{ext}"
                shutil.copy2(src, dst)
                output_files.append(str(dst))
        return {"output_files": output_files}

    elif device_type == "ecg":
        dst = output_dir / f"{device_name}_ecg.csv"
        shutil.copy2(input_file, dst)
        return {"output_file": str(dst)}

    elif device_type == "fnirs":
        dst = output_dir / f"{device_name}.snirf"
        shutil.copy2(input_file, dst)
        return {"output_file": str(dst)}

    return {}


def matchcrop(
    timeline_csv: Path,
    metadata_json: Path,
    reference_device: str,
    output_dir: Path,
    output_prefix: str = "matchcrop",
) -> Dict:
    """
    执行matchcrop操作：读取匹配后的timeline和metadata，
    以指定设备为参考，裁剪其他设备的原始数据

    Parameters:
    -----------
    timeline_csv : Path
        匹配后的timeline CSV文件路径
    metadata_json : Path
        匹配后的metadata JSON文件路径
    reference_device : str
        参考设备名称
    output_dir : Path
        输出目录路径
    output_prefix : str
        输出文件前缀

    Returns:
    --------
    Dict : 处理结果统计
    """
    # 读取metadata
    with open(metadata_json, "r") as f:
        metadata = json.load(f)

    # 获取设备信息
    device_info = metadata.get("device_info", [])

    # 查找参考设备的时间范围
    reference_info = None
    for dev in device_info:
        if dev["name"] == reference_device:
            reference_info = dev
            break

    if reference_info is None:
        raise ValueError(f"未找到参考设备: {reference_device}")

    reference_time_range = reference_info["time_range"]
    reference_start = reference_time_range[0]
    reference_end = reference_time_range[1]

    print(f"参考设备: {reference_device}")
    print(f"时间范围: {reference_start:.3f}s - {reference_end:.3f}s")

    # 处理结果
    results = {
        "reference_device": reference_device,
        "reference_time_range": reference_time_range,
        "cropped_devices": [],
        "output_files": {},
    }

    # 处理每个设备
    for dev in device_info:
        device_name = dev["name"]
        device_type = detect_device_type(device_name)

        if device_name == reference_device:
            # 复制参考设备数据
            print(f"  复制参考设备: {device_name} ({device_type})")
            try:
                copy_result = copy_reference_data(device_name, device_type, output_dir)
                results["output_files"][device_name] = copy_result
                print(f"    -> 已复制到 {output_dir}")
            except Exception as e:
                print(f"    -> 复制失败: {e}")
            continue

        # 裁剪其他设备数据
        print(f"  裁剪设备: {device_name} ({device_type})")

        # 获取设备的时间偏移（如果有漂移校正）
        drift = (
            metadata.get("timeline_metadata", {})
            .get("drift_corrections", {})
            .get(device_name, {})
        )
        device_offset = drift.get("offset", 0.0)

        # 查找原始数据文件
        input_file = find_raw_data_file(device_name, device_type)

        if input_file is None:
            print(f"    -> 警告: 找不到数据文件，跳过")
            continue

        print(f"    输入文件: {input_file}")

        try:
            if device_type == "ecg":
                output_file = output_dir / f"{device_name}_ecg.csv"
                crop_result = crop_ecg_data(
                    input_file,
                    output_file,
                    reference_start,
                    reference_end,
                    device_offset,
                )
                results["output_files"][device_name] = crop_result

            elif device_type == "fnirs":
                output_file = output_dir / f"{device_name}.snirf"
                crop_result = crop_fnirs_data(
                    input_file,
                    output_file,
                    reference_start,
                    reference_end,
                    device_offset,
                )
                results["output_files"][device_name] = crop_result

            elif device_type == "eeg":
                # EEG特殊处理：需要裁剪并保存
                crop_result = crop_eeg_data(
                    input_file,
                    output_dir,
                    reference_start,
                    reference_end,
                    device_offset,
                )
                results["output_files"][device_name] = crop_result

            results["cropped_devices"].append(device_name)
            print(f"    -> 裁剪完成")

        except Exception as e:
            print(f"    -> 裁剪失败: {e}")

    # 保存metadata
    output_metadata = output_dir / f"{output_prefix}_metadata.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_metadata, "w") as f:
        json.dump(
            {
                "reference_device": reference_device,
                "reference_time_range": reference_time_range,
                "devices": results["cropped_devices"],
                "processing_info": metadata,
            },
            f,
            indent=2,
        )

    results["output_files"]["metadata"] = str(output_metadata)

    return results


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="MatchCrop: 匹配后裁剪多设备原始数据")
    parser.add_argument(
        "--timeline-csv", "-t", required=True, help="匹配后的timeline CSV文件路径"
    )
    parser.add_argument(
        "--metadata-json", "-m", required=True, help="匹配后的metadata JSON文件路径"
    )
    parser.add_argument("--reference", "-r", required=True, help="参考设备名称")
    parser.add_argument("--output-dir", "-o", required=True, help="输出目录路径")
    parser.add_argument(
        "--output-prefix",
        "-p",
        default="matchcrop",
        help="输出文件前缀（默认：matchcrop）",
    )

    args = parser.parse_args()

    result = matchcrop(
        timeline_csv=Path(args.timeline_csv),
        metadata_json=Path(args.metadata_json),
        reference_device=args.reference,
        output_dir=Path(args.output_dir),
        output_prefix=args.output_prefix,
    )

    print(f"\n处理完成!")
    print(f"  参考设备: {result['reference_device']}")
    print(f"  裁剪设备数: {len(result['cropped_devices'])}")
    print(f"  输出目录: {args.output_dir}")


if __name__ == "__main__":
    main()
