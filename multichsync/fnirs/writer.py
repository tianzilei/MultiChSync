import numpy as np
import h5py
from typing import Any
from pathlib import Path
from .parser import ParsedTxt, _write_scalar_str, _write_scalar_int, _VLEN_STR, _infer_measurements_per_channel, _processed_label_map


def build_stim_from_mark(times: np.ndarray, marks: list[str], *, ignore_values: Any = ("", "0", "0Z")) -> dict[str, np.ndarray]:
    """
    Convert non-zero Mark entries into SNIRF stim groups.
    Each event becomes [starttime, duration, value] with duration=0 and value=1.
    """
    ignore = {str(x).strip() for x in ignore_values}
    out: dict[str, list[list[float]]] = {}

    for t, m in zip(times, marks):
        ms = str(m).strip()
        if ms in ignore:
            continue
        key = f"Mark_{ms}"
        out.setdefault(key, []).append([float(t), 0.0, 1.0])

    return {k: np.asarray(v, dtype=np.float64) for k, v in out.items()}


def build_aux_numeric_series(values: list[str]) -> np.ndarray | None:
    """
    Return Nx1 numeric aux array if all non-empty values can be converted to float.
    Otherwise return None.
    """
    nums = []
    for v in values:
        s = str(v).strip()
        if s == "":
            nums.append(np.nan)
            continue
        try:
            nums.append(float(s))
        except ValueError:
            return None
    arr = np.asarray(nums, dtype=np.float64).reshape(-1, 1)
    return arr


def write_snirf(output_path, meta, channel_pairs, times, data_matrix, sourcePos3D, detectorPos3D, src_map, det_map,
                coordinate_system: str = "Other",
                coordinate_system_description: str = "3D coordinates in millimeter units; exact standard template/system not declared in source export.",
                compress: bool = True,
                include_stim_from_mark: bool = True,
                include_aux_count: bool = True):
    """
    写入SNIRF文件
    
    参数:
        output_path: 输出文件路径
        meta: 元数据字典
        channel_pairs: 通道对列表 [(source, detector), ...]
        times: 时间数组
        data_matrix: 数据矩阵 (时间点 × 通道数)
        sourcePos3D: source坐标数组 (N×3)
        detectorPos3D: detector坐标数组 (M×3)
        src_map: source映射字典 {原始编号: SNIRF索引}
        det_map: detector映射字典 {原始编号: SNIRF索引}
        coordinate_system: 坐标系标识符
        coordinate_system_description: 坐标系描述
        compress: 是否压缩HDF5数据集
        include_stim_from_mark: 是否从Mark列创建stim组
        include_aux_count: 是否将Count列作为aux数据
    """
    # Create ParsedTxt object (some fields use placeholders)
    signal_labels = []
    measurements_per_channel = _infer_measurements_per_channel(signal_labels)
    # Since original signal labels unknown, assume HbO/HbR/HbT
    n_cols = data_matrix.shape[1]
    if measurements_per_channel == 0:
        # Infer
        if n_cols % 3 == 0:
            measurements_per_channel = 3
        else:
            measurements_per_channel = 1
    
    # Generate signal labels
    if measurements_per_channel == 3:
        signal_labels = ["oxyHb", "deoxyHb", "totalHb"] * (n_cols // 3)
    else:
        signal_labels = [f"ProcessedData{i+1}" for i in range(n_cols)]
    
    # Create ParsedTxt object
    parsed = ParsedTxt(
        meta=meta,
        channel_pairs=channel_pairs,
        times=times,
        data_matrix=data_matrix,
        signal_labels=signal_labels,
        task_values=[""] * len(times),
        mark_values=[""] * len(times),
        count_values=[""] * len(times),
    )
    
    # Call core writing function
    _write_snirf_core(
        output_path=output_path,
        parsed=parsed,
        source_pos_3d=sourcePos3D,
        detector_pos_3d=detectorPos3D,
        source_labels=[f"S{i}" for i in sorted(src_map.keys(), key=lambda x: src_map[x])],
        detector_labels=[f"D{i}" for i in sorted(det_map.keys(), key=lambda x: det_map[x])],
        source_map=src_map,
        detector_map=det_map,
        coordinate_system=coordinate_system,
        coordinate_system_description=coordinate_system_description,
        compress=compress,
        include_stim_from_mark=include_stim_from_mark,
        include_aux_count=include_aux_count,
    )
    
    print(f"SNIRF文件已保存: {output_path}")


def _write_snirf_core(
    output_path: str | Path,
    parsed: ParsedTxt,
    source_pos_3d: np.ndarray,
    detector_pos_3d: np.ndarray,
    source_labels: list[str],
    detector_labels: list[str],
    source_map: dict[int, int],
    detector_map: dict[int, int],
    *,
    coordinate_system: str = "Other",
    coordinate_system_description: str = "3D coordinates in millimeter units; exact standard template/system not declared in source export.",
    compress: bool = True,
    include_stim_from_mark: bool = True,
    include_aux_count: bool = True,
) -> Path:
    output_path = Path(output_path)

    times = parsed.times
    data_matrix = parsed.data_matrix
    signal_labels = parsed.signal_labels

    if times.ndim != 1:
        raise ValueError("times must be 1-D")
    if data_matrix.ndim != 2:
        raise ValueError("data_matrix must be 2-D")
    if data_matrix.shape[0] != times.shape[0]:
        raise ValueError("time length must equal number of data rows")

    n_cols = data_matrix.shape[1]
    measurements_per_channel = _infer_measurements_per_channel(signal_labels)
    if len(parsed.channel_pairs) * measurements_per_channel != n_cols:
        raise ValueError(
            f"Channel pair count ({len(parsed.channel_pairs)}) × measurements per channel ({measurements_per_channel}) "
            f"!= data columns ({n_cols})"
        )

    processed_labels = _processed_label_map(signal_labels[:measurements_per_channel])

    dset_kwargs: dict[str, Any] = {}
    time_kwargs: dict[str, Any] = {}
    main_chunks = (min(len(times), 2048), min(n_cols, 64))
    aux_chunks_1col = (min(len(times), 2048), 1)
    if compress:
        dset_kwargs = {
            "compression": "gzip",
            "compression_opts": 4,
            "shuffle": True,
            "chunks": main_chunks,
        }
        time_kwargs = {
            "compression": "gzip",
            "compression_opts": 4,
            "shuffle": True,
            "chunks": (min(len(times), 8192),),
        }

    with h5py.File(output_path, "w") as f:
        _write_scalar_str(f, "formatVersion", "1.1")

        nirs = f.create_group("nirs")

        # metaDataTags
        meta_grp = nirs.create_group("metaDataTags")
        meta = dict(parsed.meta)
        meta.setdefault("SubjectID", "unknown")
        meta["MeasurementDate"] = parsed.meta.get("MeasurementDate", "unknown")
        meta["MeasurementTime"] = parsed.meta.get("MeasurementTime", "unknown")
        meta.setdefault("LengthUnit", "mm")
        meta.setdefault("TimeUnit", "s")
        meta.setdefault("FrequencyUnit", "Hz")

        required_meta = {
            "SubjectID": meta["SubjectID"],
            "MeasurementDate": meta["MeasurementDate"],
            "MeasurementTime": meta["MeasurementTime"],
            "LengthUnit": meta.get("LengthUnit", "mm"),
            "TimeUnit": meta.get("TimeUnit", "s"),
            "FrequencyUnit": meta.get("FrequencyUnit", "Hz"),
        }
        for key, value in required_meta.items():
            _write_scalar_str(meta_grp, key, value)

        for key, value in meta.items():
            if key in required_meta:
                continue
            # store additional metadata as strings to keep writer simple and stable
            _write_scalar_str(meta_grp, key, str(value))

        # data1
        data_grp = nirs.create_group("data1")
        data_grp.create_dataset("dataTimeSeries", data=np.asarray(data_matrix, dtype=np.float64), dtype="f8", **dset_kwargs)

        # Use full time vector for compatibility.
        data_grp.create_dataset("time", data=np.asarray(times, dtype=np.float64), dtype="f8", **time_kwargs)

        ml_index = 1
        for pair_idx, (src_raw, det_raw) in enumerate(parsed.channel_pairs):
            if src_raw not in source_map:
                raise KeyError(f"Source index {src_raw} from TXT channel pairs not found in source CSV labels.")
            if det_raw not in detector_map:
                raise KeyError(f"Detector index {det_raw} from TXT channel pairs not found in detector CSV labels.")

            src_idx = source_map[src_raw]
            det_idx = detector_map[det_raw]

            if src_idx < 1 or det_idx < 1:
                raise ValueError("SNIRF indices must start at 1.")

            for m in range(measurements_per_channel):
                ml = data_grp.create_group(f"measurementList{ml_index}")
                _write_scalar_int(ml, "sourceIndex", src_idx)
                _write_scalar_int(ml, "detectorIndex", det_idx)

                # Processed data permit empty probe.wavelengths, but wavelengthIndex is still required.
                # Use 1 consistently for processed hemoglobin data.
                _write_scalar_int(ml, "wavelengthIndex", 1)
                _write_scalar_int(ml, "dataType", 99999)
                _write_scalar_int(ml, "dataTypeIndex", 1)
                _write_scalar_str(ml, "dataTypeLabel", processed_labels[m])

                ml_index += 1

        if (ml_index - 1) != n_cols:
            raise RuntimeError("measurementList count does not match dataTimeSeries column count.")

        # Optional stim
        if include_stim_from_mark and parsed.mark_values:
            stim_dict = build_stim_from_mark(times, parsed.mark_values)
            for i, (name, stim_data) in enumerate(stim_dict.items(), start=1):
                stim_grp = nirs.create_group(f"stim{i}")
                _write_scalar_str(stim_grp, "name", name)
                stim_grp.create_dataset("data", data=np.asarray(stim_data, dtype=np.float64), dtype="f8")

        # Optional aux for Count if numeric
        if include_aux_count and parsed.count_values:
            aux_count = build_aux_numeric_series(parsed.count_values)
            if aux_count is not None:
                aux_grp = nirs.create_group("aux1")
                _write_scalar_str(aux_grp, "name", "COUNT")
                aux_kwargs = dict(dset_kwargs)
                if compress:
                    aux_kwargs["chunks"] = aux_chunks_1col
                aux_grp.create_dataset("dataTimeSeries", data=aux_count, dtype="f8", **aux_kwargs)
                aux_grp.create_dataset("time", data=np.asarray(times, dtype=np.float64), dtype="f8", **time_kwargs)

        # probe
        probe = nirs.create_group("probe")
        # Processed Hb data: keep wavelengths present but empty because nominal wavelengths are not reliably recoverable here.
        probe.create_dataset("wavelengths", data=np.asarray([], dtype=np.float64), dtype="f8")
        probe.create_dataset("sourcePos3D", data=np.asarray(source_pos_3d, dtype=np.float64), dtype="f8")
        probe.create_dataset("detectorPos3D", data=np.asarray(detector_pos_3d, dtype=np.float64), dtype="f8")

        # sourceLabels must be 2-D according to spec; detectorLabels is string array.
        probe.create_dataset(
            "sourceLabels",
            data=np.asarray(source_labels, dtype=object).reshape(-1, 1),
            dtype=_VLEN_STR,
        )
        probe.create_dataset(
            "detectorLabels",
            data=np.asarray(detector_labels, dtype=object),
            dtype=_VLEN_STR,
        )
        _write_scalar_str(probe, "coordinateSystem", coordinate_system)
        if coordinate_system == "Other":
            _write_scalar_str(probe, "coordinateSystemDescription", coordinate_system_description)

    return output_path