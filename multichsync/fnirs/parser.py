import re
import math
import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import h5py


_VLEN_STR = h5py.string_dtype(encoding="utf-8")


@dataclass
class ParsedTxt:
    meta: dict[str, Any]
    channel_pairs: list[tuple[int, int]]
    times: np.ndarray
    data_matrix: np.ndarray
    signal_labels: list[str]
    task_values: list[str]
    mark_values: list[str]
    count_values: list[str]


def _overwrite_if_exists(group: h5py.Group | h5py.File, name: str) -> None:
    if name in group:
        del group[name]


def _write_scalar_str(group: h5py.Group | h5py.File, name: str, value: str) -> None:
    _overwrite_if_exists(group, name)
    group.create_dataset(name, data=str(value), dtype=_VLEN_STR)


def _write_scalar_int(group: h5py.Group | h5py.File, name: str, value: int) -> None:
    _overwrite_if_exists(group, name)
    group.create_dataset(name, data=np.int32(value), dtype="i4")


def _write_scalar_float(group: h5py.Group | h5py.File, name: str, value: float) -> None:
    _overwrite_if_exists(group, name)
    group.create_dataset(name, data=np.float64(value), dtype="f8")


def _normalize_date(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    s = str(raw).strip()
    if not s or "*" in s:
        return "unknown"

    m = re.search(r"(?P<y>\d{4})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})", s)
    if not m:
        return "unknown"

    try:
        dt = _dt.date(int(m["y"]), int(m["m"]), int(m["d"]))
    except ValueError:
        return "unknown"
    return dt.strftime("%Y-%m-%d")


def _normalize_time(raw: str | None, default_tz: str = "Z") -> str:
    """
    SNIRF requires either "unknown" or ISO 8601 time string hh:mm:ss.sTZD.
    """
    if raw is None:
        return "unknown"
    s = str(raw).strip()
    if not s or "*" in s:
        return "unknown"

    # hh:mm:ss(.frac)?(Z|+hh:mm|-hh:mm)?
    m = re.fullmatch(
        r"(?P<h>\d{1,2}):(?P<m>\d{1,2}):(?P<s>\d{1,2})(?P<f>\.\d+)?(?P<tz>Z|[+-]\d{2}:\d{2})?",
        s,
    )
    if m:
        hh = int(m["h"])
        mm = int(m["m"])
        ss = int(m["s"])
        frac = m["f"] or ""
        tz = m["tz"] or default_tz
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
            return f"{hh:02d}:{mm:02d}:{ss:02d}{frac}{tz}"
        return "unknown"

    # hhmmss(.frac)?
    m = re.fullmatch(r"(?P<h>\d{2})(?P<m>\d{2})(?P<s>\d{2})(?P<f>\.\d+)?", s)
    if m:
        hh = int(m["h"])
        mm = int(m["m"])
        ss = int(m["s"])
        frac = m["f"] or ""
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
            return f"{hh:02d}:{mm:02d}:{ss:02d}{frac}{default_tz}"

    return "unknown"


def _safe_subject_id(lines: list[str]) -> str:
    id_value = ""
    name_value = ""
    for ln in lines:
        if ln.startswith("ID"):
            parts = re.split(r"\t+", ln)
            if len(parts) >= 2:
                id_value = parts[1].strip()
        elif ln.startswith("Name"):
            parts = re.split(r"\t+", ln)
            if len(parts) >= 2:
                name_value = parts[1].strip()

    candidate = id_value if len(id_value) >= len(name_value) else name_value
    return candidate or "unknown"


def _find_data_start(lines: list[str]) -> int:
    # Preferred route: [Data Line] N
    first_line = lines[0] if lines else ""
    m = re.search(r"\[Data Line\]\s*(\d+)", first_line)
    if m:
        return max(int(m.group(1)) - 1, 0)

    # Fallback: first line after the column header
    for i, ln in enumerate(lines):
        if ln.strip().startswith("Time(sec)"):
            return i + 1

    raise ValueError("Could not locate data start line.")


def _extract_channel_pairs(header_lines: list[str]) -> list[tuple[int, int]]:
    channel_pairs: list[tuple[int, int]] = []
    in_text_info = False
    pair_pattern = re.compile(r"\((\d+),(\d+)\)")

    for ln in header_lines:
        if ln.strip().startswith("[Text Info.]"):
            in_text_info = True
            continue
        if in_text_info and ln.strip().startswith("Time(sec)"):
            break
        if in_text_info:
            for a, b in pair_pattern.findall(ln):
                channel_pairs.append((int(a), int(b)))

    return channel_pairs


def _extract_data_type(header_lines: list[str]) -> str:
    for ln in header_lines:
        if ln.strip().startswith("Output Mode"):
            # e.g. Output Mode  Continious   Task No.   Data Type Hb
            m = re.search(r"Data Type\s+([A-Za-z]+)", ln)
            if m:
                return m.group(1).strip()
    return "Unknown"


def _extract_time_range(header_lines: list[str]) -> tuple[float | None, float | None]:
    for ln in header_lines:
        if ln.strip().startswith("Time Range"):
            nums = re.findall(r"-?\d+(?:\.\d+)?", ln)
            if len(nums) >= 2:
                return float(nums[0]), float(nums[1])
    return None, None


def _read_data_table(lines: list[str], data_start_idx: int) -> tuple[np.ndarray, np.ndarray, list[str], list[str], list[str], list[str]]:
    # Column header is directly above the first data row.
    if data_start_idx < 1:
        raise ValueError("data_start_idx must be >= 1")

    column_line = lines[data_start_idx - 1]
    columns = [c.strip() for c in column_line.split("\t")]
    if len(columns) < 5:
        raise ValueError("Could not parse tab-delimited column header.")

    expected_prefix = ["Time(sec)", "Task", "Mark", "Count"]
    if columns[:4] != expected_prefix:
        raise ValueError(f"Unexpected first columns: {columns[:4]}")

    signal_labels = columns[4:]

    times: list[float] = []
    task_values: list[str] = []
    mark_values: list[str] = []
    count_values: list[str] = []
    data_rows: list[list[float]] = []

    n_signal_cols = len(signal_labels)

    for ln in lines[data_start_idx:]:
        if not ln.strip():
            continue

        parts = [p.strip() for p in ln.split("\t")]
        if len(parts) < 4:
            continue

        try:
            t = float(parts[0])
        except ValueError:
            continue

        task = parts[1] if len(parts) > 1 else ""
        mark = parts[2] if len(parts) > 2 else ""
        count = parts[3] if len(parts) > 3 else ""

        signal_parts = parts[4:]
        if len(signal_parts) < n_signal_cols:
            signal_parts += [""] * (n_signal_cols - len(signal_parts))
        elif len(signal_parts) > n_signal_cols:
            signal_parts = signal_parts[:n_signal_cols]

        row: list[float] = []
        for val in signal_parts:
            try:
                row.append(float(val))
            except ValueError:
                row.append(np.nan)

        times.append(t)
        task_values.append(task)
        mark_values.append(mark)
        count_values.append(count)
        data_rows.append(row)

    if not times:
        raise ValueError("No numeric data rows were parsed.")

    return (
        np.asarray(times, dtype=np.float64),
        np.asarray(data_rows, dtype=np.float64),
        signal_labels,
        task_values,
        mark_values,
        count_values,
    )


def parse_fnirs_header(txt_path):
    """
    解析fNIRS TXT文件头部信息
    
    参数:
        txt_path: TXT文件路径
        
    返回:
        meta: 元数据字典
        channel_pairs: 通道对列表 [(source, detector), ...]
        times: 时间数组
        data_matrix: 数据矩阵 (时间点 × 通道数)
    """
    parsed = parse_shimadzu_txt(txt_path)
    
    # Convert to old interface format
    meta = parsed.meta
    channel_pairs = parsed.channel_pairs
    times = parsed.times
    data_matrix = parsed.data_matrix
    
    return meta, channel_pairs, times, data_matrix


def parse_shimadzu_txt(txt_path: str | Path) -> ParsedTxt:
    txt_path = Path(txt_path)
    lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise FileNotFoundError(f"Input file is empty: {txt_path}")

    data_start_idx = _find_data_start(lines)
    header_lines = lines[:data_start_idx]

    # Metadata
    measured_date_raw = None
    total_points = None
    for ln in lines:
        if ln.startswith("Measured Date"):
            parts = re.split(r"\t+", ln, maxsplit=1)
            measured_date_raw = parts[1].strip() if len(parts) > 1 else ""
        elif ln.strip().startswith("Total Points"):
            nums = re.findall(r"\d+", ln)
            if nums:
                total_points = int(nums[-1])

    mdate = "unknown"
    mtime = "unknown"
    if measured_date_raw:
        if " " in measured_date_raw.strip():
            date_part, time_part = measured_date_raw.strip().split(" ", 1)
        else:
            date_part, time_part = measured_date_raw.strip(), ""
        mdate = _normalize_date(date_part)
        mtime = _normalize_time(time_part)

    channel_pairs = _extract_channel_pairs(header_lines)
    data_type_header = _extract_data_type(header_lines)
    time_range_start, time_range_end = _extract_time_range(header_lines)

    times, data_matrix, signal_labels, task_values, mark_values, count_values = _read_data_table(lines, data_start_idx)

    if total_points is not None and total_points != len(times):
        print(f"Warning: header Total Points={total_points}, parsed rows={len(times)}")

    if time_range_start is not None and len(times) > 0:
        # soft sanity check only
        if not math.isclose(times[0], time_range_start, rel_tol=0, abs_tol=1e-3):
            print(f"Warning: first time {times[0]} differs from header start {time_range_start}")
    if time_range_end is not None and len(times) > 0:
        if abs(times[-1] - time_range_end) > 1.0:
            print(f"Warning: last time {times[-1]} differs from header end {time_range_end}")

    # If channel pairs missing, infer count only; use identity mapping fallback.
    n_measurements = data_matrix.shape[1]
    measurements_per_channel = _infer_measurements_per_channel(signal_labels)
    if not channel_pairs:
        if n_measurements % measurements_per_channel != 0:
            raise ValueError("Cannot infer channel count from data columns.")
        n_channels = n_measurements // measurements_per_channel
        channel_pairs = [(i, i) for i in range(1, n_channels + 1)]

    meta = {
        "SubjectID": _safe_subject_id(lines),
        "MeasurementDate": mdate,
        "MeasurementTime": mtime,
        "LengthUnit": "mm",
        "TimeUnit": "s",
        "FrequencyUnit": "Hz",
        "OriginalDataType": data_type_header,
        "SourceFileName": txt_path.name,
    }

    return ParsedTxt(
        meta=meta,
        channel_pairs=channel_pairs,
        times=times,
        data_matrix=data_matrix,
        signal_labels=signal_labels,
        task_values=task_values,
        mark_values=mark_values,
        count_values=count_values,
    )


def _infer_measurements_per_channel(signal_labels: list[str]) -> int:
    labels = [s.strip() for s in signal_labels]
    unique = []
    for s in labels:
        if s not in unique:
            unique.append(s)

    # Typical processed Hb export
    hb_triplet = ["oxyHb", "deoxyHb", "totalHb"]
    if labels[:3] == hb_triplet or unique == hb_triplet:
        return 3

    # Generic fallback: detect repeating block
    for size in range(1, min(8, len(labels)) + 1):
        if len(labels) % size != 0:
            continue
        block = labels[:size]
        if block * (len(labels) // size) == labels:
            return size

    return 1


def _processed_label_map(signal_labels: list[str]) -> list[str]:
    mapping = {
        "oxyhb": "HbO",
        "deoxyhb": "HbR",
        "totalhb": "HbT",
        "dod": "dOD",
    }
    result = []
    for s in signal_labels:
        key = s.strip().lower()
        result.append(mapping.get(key, s.strip() or "ProcessedData"))
    return result


def load_coordinates(src_coords_csv, det_coords_csv):
    """
    加载source和detector坐标
    
    参数:
        src_coords_csv: source坐标CSV文件路径
        det_coords_csv: detector坐标CSV文件路径
        
    返回:
        sourcePos3D: source坐标数组 (N×3)
        detectorPos3D: detector坐标数组 (M×3)
        src_labels: source标签列表
        det_labels: detector标签列表
    """
    # Call new load_coordinates function, assuming prefixes T and R
    source_pos_3d, source_labels, source_map = _load_coordinates_with_map(src_coords_csv, expected_prefix="T")
    detector_pos_3d, detector_labels, detector_map = _load_coordinates_with_map(det_coords_csv, expected_prefix="R")
    
    return source_pos_3d, detector_pos_3d, source_labels, detector_labels


def _load_coordinates_with_map(csv_path: str | Path, expected_prefix: str) -> tuple[np.ndarray, list[str], dict[int, int]]:
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)

    missing = {"Label", "X", "Y", "Z"} - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name} missing required columns: {sorted(missing)}")

    labels = df["Label"].astype(str).tolist()
    coords = df[["X", "Y", "Z"]].to_numpy(dtype=np.float64)

    numeric_map: dict[int, int] = {}
    for idx, label in enumerate(labels, start=1):
        m = re.fullmatch(rf"{re.escape(expected_prefix)}(\d+)", label.strip(), flags=re.IGNORECASE)
        if not m:
            raise ValueError(
                f"{csv_path.name}: label '{label}' does not match expected pattern "
                f"'{expected_prefix}<number>'"
            )
        numeric_map[int(m.group(1))] = idx

    return coords, labels, numeric_map