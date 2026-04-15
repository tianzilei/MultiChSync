"""
Marker extraction functions for various data formats
"""

import pandas as pd
from pathlib import Path
from typing import Union, Optional, Dict


def hms_to_sec(x: Union[str, float]) -> float:
    """
    将 hh:mm:ss.ss 转换为秒
    例如:
        00:05:54.00 -> 354.00
    """
    if pd.isna(x):
        return pd.NA

    x = str(x).strip()
    parts = x.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid time format: {x}")

    h = float(parts[0])
    m = float(parts[1])
    s = float(parts[2])

    return h * 3600 + m * 60 + s


def extract_marker_time_only(
    input_csv: Union[str, Path],
    output_csv: Union[str, Path],
    fs: float = 500,
    tolerance: float = 0.2,
) -> pd.DataFrame:
    """
    功能：
        1. 单列电压 → 0/5
        2. 去连续重复（只保留第一个）
        3. 添加 Time(sec)
        4. 输出仅包含 index + Time(sec)

    输入：
        input_csv: 输入路径
        output_csv: 输出路径
        fs: 采样率（Hz）
        tolerance: 电压容差

    输出：
        index（marker id）, Time(sec)
    """

    input_csv = Path(input_csv)
    output_csv = Path(output_csv)

    # ---------- Read ----------
    df = pd.read_csv(input_csv)

    if df.shape[1] != 1:
        raise ValueError("CSV必须只有1列")

    col = df.columns[0]
    s = pd.to_numeric(df[col], errors="coerce")

    # ---------- Map to 0 / 5 ----------
    s_clean = s.copy()
    s_clean[(s - 0).abs() <= tolerance] = 0
    s_clean[(s - 5).abs() <= tolerance] = 5
    s_clean[~((s_clean == 0) | (s_clean == 5))] = pd.NA

    # ---------- Timeline ----------
    step = 1 / fs
    time = [i * step for i in range(len(s_clean))]

    # ---------- Edge Detection ----------
    mask = s_clean != s_clean.shift(1)
    mask.iloc[0] = True

    # ---------- Build Output ----------
    df_out = pd.DataFrame({"Time(sec)": time})

    df_out = df_out[mask].copy()

    # Reset index (as marker number)
    df_out.reset_index(drop=True, inplace=True)

    # Time precision
    df_out["Time(sec)"] = df_out["Time(sec)"].round(4)

    # ---------- Save ----------
    df_out.to_csv(
        output_csv,
        index=True,  # keep index = marker number
        encoding="utf-8-sig",
        float_format="%.6f",
    )

    print(f"输出文件: {output_csv}")
    print(f"marker数量: {len(df_out)}")

    return df_out


def extract_brainvision_marker(
    vmrk_path: Union[str, Path], output_csv: Union[str, Path]
) -> pd.DataFrame:
    """
    BrainVision marker 提取（严格单位处理）

    输出：
        index, reference_time(sec), value
    """

    vmrk_path = Path(vmrk_path)
    output_csv = Path(output_csv)

    vhdr_path = vmrk_path.with_suffix(".vhdr")
    if not vhdr_path.exists():
        raise FileNotFoundError(f"vhdr not found: {vhdr_path}")

    # ---------- Read SamplingInterval (unit: µs) ----------
    sampling_interval_us = None

    with open(vhdr_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("SamplingInterval="):
                sampling_interval_us = float(line.split("=")[1].strip())
                break

    if sampling_interval_us is None:
        raise ValueError("SamplingInterval not found")

    # ---------- Convert to seconds ----------
    step_sec = sampling_interval_us / 1_000_000.0  # µs → sec

    # ---------- Parse vmrk ----------
    rows = []

    with open(vmrk_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()

            if not line.startswith("Mk"):
                continue

            if line.startswith("Mk1="):  # ignore start marker
                continue

            try:
                _, val = line.split("=", 1)
                parts = [x.strip() for x in val.split(",")]
            except:
                continue

            if len(parts) < 3:
                continue

            desc = parts[1]

            try:
                pos = int(parts[2])
            except:
                continue

            # BrainVision uses 1-based index
            time_sec = (pos - 1) * step_sec

            rows.append({"reference_time": round(time_sec, 6), "value": desc})

    # ---------- DataFrame ----------
    df_out = pd.DataFrame(rows)
    df_out.reset_index(drop=True, inplace=True)

    # ---------- Save ----------
    df_out.to_csv(
        output_csv,
        index=True,  # marker number
        encoding="utf-8-sig",
        float_format="%.6f",
    )

    print(f"SamplingInterval: {sampling_interval_us} µs")
    print(f"Sampling rate: {1 / step_sec:.2f} Hz")
    print(f"Marker count: {len(df_out)}")
    print(f"Saved to: {output_csv}")

    return df_out


def extract_fnirs_marker(
    input_csv: Union[str, Path], output_csv: Union[str, Path]
) -> pd.DataFrame:
    """
    从非标准 fNIRS csv 中提取 marker

    输入:
        input_csv: 原始 csv 路径
        output_csv: 输出 csv 路径

    输出列:
        index, reference_time, value
    """
    input_csv = Path(input_csv)
    output_csv = Path(output_csv)

    # ---------- Find header row ----------
    header_idx = None
    # Try multiple encodings
    encodings_to_try = ["gbk", "utf-8-sig", "latin1"]
    for enc in encodings_to_try:
        try:
            with open(input_csv, "r", encoding=enc, errors="ignore") as f:
                for i, line in enumerate(f):
                    if line.strip().startswith("Start Time"):
                        header_idx = i
                        break
            if header_idx is not None:
                break
        except:
            continue

    if header_idx is None:
        raise ValueError(f"'Start Time' header row not found in: {input_csv}")

    # ---------- Read from header row ----------
    # Try multiple encodings to read CSV
    df = None
    for enc in encodings_to_try:
        try:
            df = pd.read_csv(
                input_csv, skiprows=header_idx, encoding=enc, engine="python"
            )
            # Check if required columns exist
            if "Start Time" in df.columns or "Start Time" in [
                str(c).strip() for c in df.columns
            ]:
                break
        except:
            continue

    if df is None:
        raise ValueError(f"无法读取CSV文件，尝试了编码: {encodings_to_try}")

    # Strip column name whitespace
    df.columns = [str(c).strip() for c in df.columns]

    required_cols = ["Start Time", "Protocol Type"]
    for c in required_cols:
        if c not in df.columns:
            raise KeyError(f"Column '{c}' not found in file: {input_csv}")

    # ---------- Convert ----------
    df_out = pd.DataFrame(
        {
            "reference_time": df["Start Time"].apply(hms_to_sec).round(4),
            "value": df["Protocol Type"],
        }
    )

    # Optional: remove empty rows
    df_out = df_out.dropna(subset=["reference_time", "value"]).copy()

    # Reset index, as marker number
    df_out.reset_index(drop=True, inplace=True)

    # ---------- Save ----------
    df_out.to_csv(
        output_csv,
        index=True,  # keep index to count markers
        encoding="utf-8-sig",
        float_format="%.4f",
    )

    print(f"Saved to: {output_csv}")
    print(f"Marker count: {len(df_out)}")

    return df_out


def extract_biopac_marker(
    input_csv: Union[str, Path],
    output_csv: Union[str, Path],
    fs: float = 500,
    tolerance: float = 0.2,
) -> pd.DataFrame:
    """
    别名：Biopac marker提取（与extract_marker_time_only相同）
    """
    return extract_marker_time_only(input_csv, output_csv, fs, tolerance)


def clean_marker_csv(
    csv_path: Union[str, Path],
    out_path: Optional[Union[str, Path]] = None,
    time_col: Optional[str] = None,
    min_rows: int = 2,
    min_interval: float = 1.0,
    remove_start: bool = False,
) -> str:
    """
    清洗单个 marker csv:
    1) 删除空csv或数据行少于 min_rows 的csv
    2) 对有效csv按时间排序
    3) (可选) 删除第一个marker时间为0的记录
    4) 去除过近marker：相邻保留事件时间差必须 >= min_interval

    参数:
        csv_path: 输入CSV文件路径
        out_path: 输出CSV文件路径（None=原地覆盖）
        time_col: 时间列名（None=自动检测）
        min_rows: 最小行数要求
        min_interval: 最小时间间隔（秒）
        remove_start: 是否删除第一个marker时间为0的记录（默认False）

    返回:
        状态字符串: "cleaned", "deleted_empty", "deleted_too_few_rows",
                  "deleted_invalid_time", "deleted_after_clean",
                  "missing_time_col", "read_error"
    """
    csv_path = Path(csv_path)

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"[读取失败] {csv_path.name}: {e}")
        return "read_error"

    # ---------- 1. Delete invalid files ----------
    # Only header / no data
    if df.empty:
        print(f"[删除空文件] {csv_path.name}")
        csv_path.unlink(missing_ok=True)
        return "deleted_empty"

    # Less than min_rows rows of data
    if len(df) < min_rows:
        print(f"[删除数据过少文件] {csv_path.name} | 行数={len(df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_too_few_rows"

    # ---------- 2. Check time column ----------
    # Auto-detect time column name
    if time_col is None:
        # Common time column names
        possible_time_cols = ["Time(sec)", "reference_time", "time", "Time"]
        for col in possible_time_cols:
            if col in df.columns:
                time_col = col
                break

        if time_col is None:
            # Try to find column name containing "time" (case insensitive)
            for col in df.columns:
                if "time" in col.lower():
                    time_col = col
                    break

        if time_col is None:
            print(f"[缺少时间列] {csv_path.name} | 未找到时间列")
            return "missing_time_col"

    if time_col not in df.columns:
        print(f"[缺少时间列] {csv_path.name} | 未找到列: {time_col}")
        return "missing_time_col"

    # Convert to numeric, set NaN if conversion fails
    df[time_col] = pd.to_numeric(df[time_col], errors="coerce")

    # Delete rows with empty time
    df = df.dropna(subset=[time_col]).copy()

    # If after deletion less than min_rows, delete file
    if len(df) < min_rows:
        print(f"[删除无效时间文件] {csv_path.name} | 有效时间行数={len(df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_invalid_time"

    # ---------- 3. Sort ----------
    df = df.sort_values(by=time_col).reset_index(drop=True)

    # ---------- 3.1 (Optional) Delete all Time=0 records ----------
    if remove_start and len(df) > 0:
        zero_mask = df[time_col] == 0
        zero_count = zero_mask.sum()
        if zero_count > 0:
            df = df[~zero_mask].reset_index(drop=True)
            print(f"[删除首点为0] {csv_path.name} | 删除{zero_count}行，时间=0")

    # If after deletion less than min_rows, delete file
    if len(df) < min_rows:
        print(f"[删除首点为0后] {csv_path.name} | 行数不足={len(df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_invalid_time"

    # ---------- 4. Remove too-close markers ----------
    keep_indices = []
    last_kept_time = None

    for idx, row in df.iterrows():
        current_time = row[time_col]

        if last_kept_time is None:
            keep_indices.append(idx)
            last_kept_time = current_time
        else:
            if current_time - last_kept_time >= min_interval:
                keep_indices.append(idx)
                last_kept_time = current_time
            else:
                # Time too close, discard current row
                pass

    cleaned_df = df.loc[keep_indices].copy().reset_index(drop=True)

    # After cleaning if less than min_rows, can also delete
    if len(cleaned_df) < min_rows:
        print(f"[清洗后删除文件] {csv_path.name} | 清洗后行数={len(cleaned_df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_after_clean"

    # ---------- 5. Save ----------
    if out_path is None:
        out_path = csv_path
    else:
        out_path = Path(out_path)

    cleaned_df.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"[已清洗] {csv_path.name} | 原始行数={len(df)} | 保留行数={len(cleaned_df)}")
    return "cleaned"


def clean_marker_folder(
    input_dir: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    time_col: Optional[str] = None,
    min_rows: int = 2,
    min_interval: float = 1.0,
    remove_start: bool = False,
) -> Dict[str, int]:
    """
    批量清洗文件夹中所有csv（支持二级目录结构）
    - 若 output_dir=None，则原地覆盖
    - 若指定 output_dir，则保存到新文件夹，保留二级目录结构

    参数:
        input_dir: 输入目录（支持一级或二级目录结构）
                   例如: Data/marker/fnirs/ (一级) 或 Data/marker/ (二级，含fnirs/ecg/eeg子目录)
        output_dir: 输出目录（None=原地覆盖）
        time_col: 时间列名（None=自动检测）
        min_rows: 最小行数要求
        min_interval: 最小时间间隔（秒）
        remove_start: 是否删除第一个marker时间为0的记录（默认False）

    返回:
        统计字典: 各状态的文件计数
    """
    input_dir = Path(input_dir)

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Recursively search all CSV files (supports two-level directory structure)
    csv_files = list(input_dir.rglob("*.csv"))
    # Filter out hidden files (macOS ._ files) and system files
    csv_files = [
        f
        for f in csv_files
        if not any(part.startswith(".") or part == "__MACOSX" for part in f.parts)
    ]
    if not csv_files:
        print("未找到 csv 文件")
        return {}

    # Calculate relative path to preserve directory structure
    def get_output_path(csv_file: Path) -> Optional[Path]:
        if output_dir is None:
            return None  # overwrite in place
        # Calculate relative path and preserve directory structure
        rel_path = csv_file.relative_to(input_dir)
        return output_dir / rel_path

    summary = {
        "cleaned": 0,
        "deleted_empty": 0,
        "deleted_too_few_rows": 0,
        "deleted_invalid_time": 0,
        "deleted_after_clean": 0,
        "missing_time_col": 0,
        "read_error": 0,
    }

    for csv_file in csv_files:
        out_path = get_output_path(csv_file)

        # Ensure output directory exists
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)

        result = clean_marker_csv(
            csv_path=csv_file,
            out_path=out_path,
            time_col=time_col,
            min_rows=min_rows,
            min_interval=min_interval,
            remove_start=remove_start,
        )

        if result in summary:
            summary[result] += 1

    print("\n=== 清洗完成 ===")
    for k, v in summary.items():
        if v > 0:
            print(f"{k}: {v}")

    return summary
