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

    # ---------- 读取 ----------
    df = pd.read_csv(input_csv)

    if df.shape[1] != 1:
        raise ValueError("CSV必须只有1列")

    col = df.columns[0]
    s = pd.to_numeric(df[col], errors="coerce")

    # ---------- 映射到 0 / 5 ----------
    s_clean = s.copy()
    s_clean[(s - 0).abs() <= tolerance] = 0
    s_clean[(s - 5).abs() <= tolerance] = 5
    s_clean[~((s_clean == 0) | (s_clean == 5))] = pd.NA

    # ---------- 时间轴 ----------
    step = 1 / fs
    time = [i * step for i in range(len(s_clean))]

    # ---------- 边沿检测 ----------
    mask = s_clean != s_clean.shift(1)
    mask.iloc[0] = True

    # ---------- 构建输出 ----------
    df_out = pd.DataFrame({"Time(sec)": time})

    df_out = df_out[mask].copy()

    # 重置 index（作为 marker 编号）
    df_out.reset_index(drop=True, inplace=True)

    # 时间精度
    df_out["Time(sec)"] = df_out["Time(sec)"].round(4)

    # ---------- 保存 ----------
    df_out.to_csv(
        output_csv,
        index=True,  # 保留 index = marker编号
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

    # ---------- 读取 SamplingInterval（单位：µs） ----------
    sampling_interval_us = None

    with open(vhdr_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("SamplingInterval="):
                sampling_interval_us = float(line.split("=")[1].strip())
                break

    if sampling_interval_us is None:
        raise ValueError("SamplingInterval not found")

    # ---------- 转换为秒 ----------
    step_sec = sampling_interval_us / 1_000_000.0  # µs → sec

    # ---------- 解析 vmrk ----------
    rows = []

    with open(vmrk_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()

            if not line.startswith("Mk"):
                continue

            if line.startswith("Mk1="):  # 忽略起始marker
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

            # ⚠️ BrainVision 是 1-based index
            time_sec = (pos - 1) * step_sec

            rows.append({"reference_time": round(time_sec, 6), "value": desc})

    # ---------- DataFrame ----------
    df_out = pd.DataFrame(rows)
    df_out.reset_index(drop=True, inplace=True)

    # ---------- 保存 ----------
    df_out.to_csv(
        output_csv,
        index=True,  # marker编号
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

    # ---------- 找到表头行 ----------
    header_idx = None
    # 尝试多种编码
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

    # ---------- 从表头行开始读 ----------
    # 尝试多种编码读取CSV
    df = None
    for enc in encodings_to_try:
        try:
            df = pd.read_csv(
                input_csv, skiprows=header_idx, encoding=enc, engine="python"
            )
            # 检查是否有必需的列
            if "Start Time" in df.columns or "Start Time" in [
                str(c).strip() for c in df.columns
            ]:
                break
        except:
            continue

    if df is None:
        raise ValueError(f"无法读取CSV文件，尝试了编码: {encodings_to_try}")

    # 去掉列名首尾空格
    df.columns = [str(c).strip() for c in df.columns]

    required_cols = ["Start Time", "Protocol Type"]
    for c in required_cols:
        if c not in df.columns:
            raise KeyError(f"Column '{c}' not found in file: {input_csv}")

    # ---------- 转换 ----------
    df_out = pd.DataFrame(
        {
            "reference_time": df["Start Time"].apply(hms_to_sec).round(4),
            "value": df["Protocol Type"],
        }
    )

    # 可选：去掉空行
    df_out = df_out.dropna(subset=["reference_time", "value"]).copy()

    # 重置 index，作为 marker 编号
    df_out.reset_index(drop=True, inplace=True)

    # ---------- 保存 ----------
    df_out.to_csv(
        output_csv,
        index=True,  # 保留 index 以计数 marker
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

    # ---------- 1. 删除无效文件 ----------
    # 只有header / 没有数据
    if df.empty:
        print(f"[删除空文件] {csv_path.name}")
        csv_path.unlink(missing_ok=True)
        return "deleted_empty"

    # 小于min_rows行数据
    if len(df) < min_rows:
        print(f"[删除数据过少文件] {csv_path.name} | 行数={len(df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_too_few_rows"

    # ---------- 2. 检查时间列 ----------
    # 自动检测时间列名
    if time_col is None:
        # 常见的时间列名
        possible_time_cols = ["Time(sec)", "reference_time", "time", "Time"]
        for col in possible_time_cols:
            if col in df.columns:
                time_col = col
                break

        if time_col is None:
            # 尝试查找包含"time"的列名（不区分大小写）
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

    # 转成数值，无法转换的设为 NaN
    df[time_col] = pd.to_numeric(df[time_col], errors="coerce")

    # 删除时间为空的行
    df = df.dropna(subset=[time_col]).copy()

    # 如果删完后不足最小行数，直接删文件
    if len(df) < min_rows:
        print(f"[删除无效时间文件] {csv_path.name} | 有效时间行数={len(df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_invalid_time"

    # ---------- 3. 排序 ----------
    df = df.sort_values(by=time_col).reset_index(drop=True)

    # ---------- 3.1 (可选) 删除所有Time=0的记录 ----------
    if remove_start and len(df) > 0:
        zero_mask = df[time_col] == 0
        zero_count = zero_mask.sum()
        if zero_count > 0:
            df = df[~zero_mask].reset_index(drop=True)
            print(f"[删除首点为0] {csv_path.name} | 删除{zero_count}行，时间=0")

    # 如果删除后不足最小行数，直接删文件
    if len(df) < min_rows:
        print(f"[删除首点为0后] {csv_path.name} | 行数不足={len(df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_invalid_time"

    # ---------- 4. 去除过近 marker ----------
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
                # 时间过近，丢弃当前行
                pass

    cleaned_df = df.loc[keep_indices].copy().reset_index(drop=True)

    # 清洗后如果不足min_rows行，也可以删掉
    if len(cleaned_df) < min_rows:
        print(f"[清洗后删除文件] {csv_path.name} | 清洗后行数={len(cleaned_df)}")
        csv_path.unlink(missing_ok=True)
        return "deleted_after_clean"

    # ---------- 5. 保存 ----------
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

    # 递归搜索所有CSV文件（支持二级目录结构）
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

    # 计算相对路径以保留目录结构
    def get_output_path(csv_file: Path) -> Optional[Path]:
        if output_dir is None:
            return None  # 原地覆盖
        # 计算相对路径并保留目录结构
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

        # 确保输出目录存在
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
