#!/usr/bin/env python3
"""
多模态神经影像数据转换命令行工具
"""

import argparse
import sys
from pathlib import Path

from .fnirs import convert_fnirs_to_snirf, batch_convert_fnirs_to_snirf
from .ecg import convert_acq_to_csv, batch_convert_acq_to_csv
from .eeg import convert_eeg_format, batch_convert_eeg_format
from .marker import (
    extract_biopac_marker,
    extract_brainvision_marker,
    extract_fnirs_marker,
    clean_marker_csv,
    clean_marker_folder,
    extract_marker_info,
    clean_marker_folder,
)
from .marker.timeline_cropper import crop_timelines_to_shortest
from .marker.matchcrop import matchcrop
from .marker.matchcrop_aligned import matchcrop_aligned
from .quality import (
    process_one_snirf,
    batch_process_snirf_folder,
    batch_compute_resting_metrics,
    process_one_snirf_with_metadata,
    batch_process_snirf_folder_with_metadata,
    generate_all_visualizations,
)

# Mapping from CLI method names to internal method names
METHOD_NAME_MAPPING = {
    "hungarian": "hungarian",
    "mincostflow": "min_cost_flow",  # CLI uses no underscore, internal uses underscore
    "sinkhorn": "sinkhorn",
}


def fnirs_convert(args):
    """处理fNIRS转换命令"""
    try:
        output_path = convert_fnirs_to_snirf(
            txt_path=args.txt_path,
            src_coords_csv=args.src_coords,
            det_coords_csv=args.det_coords,
            output_path=args.output,
            patch_for_mne=not args.no_mne_patch,
        )
        print(f"转换成功: {output_path}")
    except Exception as e:
        print(f"转换失败: {e}")
        sys.exit(1)


def fnirs_batch(args):
    """处理fNIRS批量转换命令"""
    try:
        converted_files = batch_convert_fnirs_to_snirf(
            input_dir=args.input_dir,
            src_coords_csv=args.src_coords,
            det_coords_csv=args.det_coords,
            output_dir=args.output_dir,
            patch_for_mne=not args.no_mne_patch,
        )
        print(f"批量转换完成，共 {len(converted_files)} 个文件")
    except Exception as e:
        print(f"批量转换失败: {e}")
        sys.exit(1)


def fnirs_patch(args):
    """处理SNIRF文件MNE修复命令"""
    try:
        from multichsync.fnirs import patch_snirf_for_mne, patch_snirf_inplace

        if patch_snirf_for_mne is None:
            print("错误: MNE修复模块不可用，请确保h5py已安装")
            sys.exit(1)

        if args.inplace:
            # In-place patch
            if args.output:
                print("警告: --inplace参数已指定，--output参数将被忽略")

            patched_path = patch_snirf_inplace(
                snirf_path=args.input,
                dummy_wavelengths=args.dummy_wavelengths,
                move_hbt_to_aux=not args.no_move_hbt,
                aux_name="HbT",
            )
            print(f"原地修复完成: {patched_path}")
        else:
            # Create new file
            patched_path = patch_snirf_for_mne(
                input_snirf=args.input,
                output_snirf=args.output,
                dummy_wavelengths=args.dummy_wavelengths,
                move_hbt_to_aux=not args.no_move_hbt,
                aux_name="HbT",
            )
            print(f"修复完成，输出文件: {patched_path}")

    except Exception as e:
        print(f"修复失败: {e}")
        sys.exit(1)


def ecg_convert(args):
    """处理ECG转换命令"""
    try:
        if args.format != "csv":
            print(f"不支持的格式: {args.format}，仅支持csv格式")
            sys.exit(1)

        result = convert_acq_to_csv(
            acq_path=args.acq_path,
            output_path=args.output,
            sampling_rate=args.sampling_rate,
            group_by_type=not args.no_group,
            float_format=args.float_format,
        )

        if isinstance(result, dict):
            print("转换成功，输出文件:")
            for group, path in result.items():
                print(f"  {group}: {path}")
        else:
            print(f"转换成功: {result}")

    except Exception as e:
        print(f"转换失败: {e}")
        sys.exit(1)


def ecg_batch(args):
    """处理ECG批量转换命令"""
    try:
        if args.format != "csv":
            print(f"不支持的格式: {args.format}，仅支持csv格式")
            sys.exit(1)

        results = batch_convert_acq_to_csv(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            sampling_rate=args.sampling_rate,
            group_by_type=not args.no_group,
            float_format=args.float_format,
        )

        print(f"批量转换完成，共 {len(results)} 个文件")

    except Exception as e:
        print(f"批量转换失败: {e}")
        sys.exit(1)


def eeg_convert(args):
    """处理EEG转换命令"""
    try:
        raw, output_path = convert_eeg_format(
            file_path=args.file_path,
            export_format=args.format,
            output_path=args.output,
            preload=args.preload,
            overwrite=args.overwrite,
            verbose=args.verbose,
            sampling_rate=args.sampling_rate,
        )
        print(f"转换成功: {output_path}")
        print(f"通道数: {len(raw.ch_names)}, 采样率: {raw.info['sfreq']} Hz")

    except Exception as e:
        print(f"转换失败: {e}")
        sys.exit(1)


def eeg_batch(args):
    """处理EEG批量转换命令"""
    try:
        results = batch_convert_eeg_format(
            input_dir=args.input_dir,
            export_format=args.format,
            output_dir=args.output_dir,
            preload=args.preload,
            overwrite=args.overwrite,
            verbose=args.verbose,
            recursive=args.recursive,
            sampling_rate=args.sampling_rate,
        )

        print(f"批量转换完成，共 {len(results)} 个文件")

    except Exception as e:
        print(f"批量转换失败: {e}")
        sys.exit(1)


def marker_extract(args):
    """处理marker提取命令"""
    try:
        input_path = Path(args.input)
        output_path = (
            Path(args.output) if args.output else input_path.with_suffix(".marker.csv")
        )

        # Determine extraction type
        extract_type = args.type
        if not extract_type:
            # Guess based on file extension
            if input_path.suffix.lower() == ".vmrk":
                extract_type = "brainvision"
            elif input_path.suffix.lower() == ".csv":
                # Needs further content check, default to biopac for now
                extract_type = "biopac"
            elif input_path.suffix.lower() in [".txt", ".csv"]:
                # fNIRS files can be .txt or .csv
                extract_type = "fnirs"
            else:
                raise ValueError("无法自动检测文件类型，请使用--type参数指定")

        # Call corresponding extraction function
        if extract_type == "biopac":
            df = extract_biopac_marker(
                input_csv=input_path,
                output_csv=output_path,
                fs=args.fs,
                tolerance=args.tolerance,
            )
        elif extract_type == "brainvision":
            df = extract_brainvision_marker(
                vmrk_path=input_path, output_csv=output_path
            )
        elif extract_type == "fnirs":
            df = extract_fnirs_marker(input_csv=input_path, output_csv=output_path)
        else:
            raise ValueError(f"不支持的提取类型: {extract_type}")

        print(f"Marker提取成功: {output_path}")
        print(f"提取数量: {len(df)}")

    except Exception as e:
        print(f"Marker提取失败: {e}")
        sys.exit(1)


def marker_batch(args):
    """处理marker批量提取命令"""
    import glob
    import os

    try:
        # Determine types to process
        types = args.types.split(",") if args.types else ["fnirs", "ecg", "eeg"]

        stats = {"fnirs": 0, "ecg": 0, "eeg": 0, "failed": 0, "skipped": 0}

        # fNIRS: Data/raw/fnirs/*.csv -> Data/marker/fnirs/*.csv
        if "fnirs" in types:
            fnirs_input_dir = (
                Path(args.fnirs_input) if args.fnirs_input else Path("Data/raw/fnirs")
            )
            fnirs_output_dir = (
                Path(args.fnirs_output)
                if args.fnirs_output
                else Path("Data/marker/fnirs")
            )
            fnirs_output_dir.mkdir(parents=True, exist_ok=True)

            for csv_file in sorted(fnirs_input_dir.glob("*.csv")):
                if args.max_files and stats["fnirs"] >= args.max_files:
                    break
                # Output filename uses original name without _marker suffix
                output_file = fnirs_output_dir / csv_file.name
                if args.skip_existing and output_file.exists():
                    stats["skipped"] += 1
                    continue
                try:
                    df = extract_fnirs_marker(
                        input_csv=csv_file, output_csv=output_file
                    )
                    stats["fnirs"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  [失败] {csv_file.name}: {e}")

        # ECG: Data/convert/ecg/*_input.csv -> Data/marker/ecg/*.csv
        if "ecg" in types:
            ecg_input_dir = (
                Path(args.ecg_input) if args.ecg_input else Path("Data/convert/ecg")
            )
            ecg_output_dir = (
                Path(args.ecg_output) if args.ecg_output else Path("Data/marker/ecg")
            )
            ecg_output_dir.mkdir(parents=True, exist_ok=True)

            # Find all *_input.csv files (BIDS rule)
            for csv_file in sorted(ecg_input_dir.glob("*_input.csv")):
                if args.max_files and stats["ecg"] >= args.max_files:
                    break
                # Output filename without _marker suffix
                output_file = ecg_output_dir / csv_file.name
                if args.skip_existing and output_file.exists():
                    stats["skipped"] += 1
                    continue
                try:
                    df = extract_biopac_marker(
                        input_csv=csv_file,
                        output_csv=output_file,
                        fs=args.fs,
                        tolerance=args.tolerance,
                    )
                    stats["ecg"] += 1
                    # Delete successfully extracted input files (no longer needed after marker extraction)
                    csv_file.unlink(missing_ok=True)
                    print(f"  [已删除] {csv_file.name}")
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  [失败] {csv_file.name}: {e}")

        # EEG: Data/convert/eeg/**/*.vmrk -> Data/marker/eeg/**/*_marker.csv
        if "eeg" in types:
            eeg_input_dir = (
                Path(args.eeg_input) if args.eeg_input else Path("Data/convert/eeg")
            )
            eeg_output_dir = (
                Path(args.eeg_output) if args.eeg_output else Path("Data/marker/eeg")
            )
            eeg_output_dir.mkdir(parents=True, exist_ok=True)

            for vmrk_file in sorted(eeg_input_dir.rglob("*.vmrk")):
                if args.max_files and stats["eeg"] >= args.max_files:
                    break
                # Output filename uses original name without _marker suffix (remove .vmrk extension)
                output_file = eeg_output_dir / f"{vmrk_file.stem}.csv"
                if args.skip_existing and output_file.exists():
                    stats["skipped"] += 1
                    continue
                try:
                    df = extract_brainvision_marker(
                        vmrk_path=vmrk_file, output_csv=output_file
                    )
                    stats["eeg"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  [失败] {vmrk_file.name}: {e}")

        print(f"\n批量Marker提取完成:")
        print(f"  fNIRS: {stats['fnirs']} 文件")
        print(f"  ECG:   {stats['ecg']} 文件")
        print(f"  EEG:   {stats['eeg']} 文件")
        print(f"  失败:  {stats['failed']} 文件")
        print(f"  跳过:  {stats['skipped']} 文件 (已存在)")

    except Exception as e:
        print(f"批量Marker提取失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_clean(args):
    """处理marker清洗命令"""
    try:
        input_path = Path(args.input)

        if not input_path.exists():
            raise FileNotFoundError(f"输入路径不存在: {input_path}")

        # Determine cleaning mode
        if input_path.is_file():
            # Single file cleaning
            print(f"清洗单个文件: {input_path}")
            result = clean_marker_csv(
                csv_path=input_path,
                out_path=None
                if args.inplace
                else input_path.with_suffix(".cleaned.csv"),
                time_col=args.time_col,
                min_rows=args.min_rows,
                min_interval=args.min_interval,
                remove_start=args.remove_start,
            )
            print(f"清洗结果: {result}")

        elif input_path.is_dir():
            # Batch directory cleaning
            print(f"批量清洗目录: {input_path}")
            output_dir = (
                None
                if args.inplace
                else Path(args.output_dir)
                if args.output_dir
                else input_path / "cleaned"
            )

            summary = clean_marker_folder(
                input_dir=input_path,
                output_dir=output_dir,
                time_col=args.time_col,
                min_rows=args.min_rows,
                min_interval=args.min_interval,
                remove_start=args.remove_start,
            )

            print(f"清洗完成，处理文件统计:")
            for status, count in summary.items():
                if count > 0:
                    print(f"  {status}: {count}")
        else:
            raise ValueError(f"输入路径既不是文件也不是目录: {input_path}")

    except Exception as e:
        print(f"Marker清洗失败: {e}")
        sys.exit(1)


def marker_info(args):
    """处理marker信息提取命令"""
    try:
        from pathlib import Path

        input_dir = Path(args.input_dir) if args.input_dir else Path("Data/marker")
        output_dir = Path(args.output_dir) if args.output_dir else input_dir / "info"

        recursive = not args.no_recursive

        reports = extract_marker_info(
            input_dir=input_dir, output_dir=output_dir, recursive=recursive
        )

        print(f"Marker信息提取完成:")
        print(f"  输入目录: {input_dir}")
        print(f"  输出目录: {output_dir}")
        print(f"  递归搜索: {recursive}")
        print(f"  生成报告:")
        print(f"    错误报告: {reports['error_report']}")
        print(f"    受试者报告:")
        for subj_name, report_path in reports["subject_reports"].items():
            print(f"      受试者 {subj_name}: {report_path}")

    except Exception as e:
        print(f"Marker信息提取失败: {e}")
        sys.exit(1)


def marker_match(args):
    """处理多设备marker匹配命令"""
    try:
        from pathlib import Path
        from multichsync.marker import match_by_filename

        # Get filename
        if args.filename:
            # Use filename matching mode - auto load data from Data/convert
            filename = args.filename
            convert_dir = args.convert_dir if args.convert_dir else "Data/convert"

            print(f"正在匹配文件: {filename}")
            print(f"数据目录: {convert_dir}")

            # Map CLI method names to internal method names
            internal_method = METHOD_NAME_MAPPING[args.method]

            # Call filename matching function
            results = match_by_filename(
                filename=filename,
                convert_dir=convert_dir,
                method=internal_method,
                max_time_diff_s=args.max_time_diff,
                sigma_time_s=args.sigma_time,
                estimate_drift=not args.no_drift_correction,
                drift_method=args.drift_method,
                output_dir=args.output_dir if args.output_dir else "data/matching",
                output_prefix=args.output_prefix,
                save_json=not args.no_json,
                generate_plots=not args.no_plots,
            )

            # Print result summary
            print(f"匹配完成!")
            print(
                f"  输出目录: {args.output_dir if args.output_dir else 'data/matching'}"
            )
            print(
                f"  时间线CSV: {results.get('output_files', {}).get('timeline_csv', 'N/A')}"
            )
            print(f"  共识事件数: {results.get('n_consensus_events', 'N/A')}")
            print(f"  总匹配数: {results.get('total_matches', 'N/A')}")
            mean_conf = results.get("mean_confidence", "N/A")
            print(
                f"  平均置信度: {mean_conf if isinstance(mean_conf, str) else f'{mean_conf:.3f}'}"
            )

            # Print device statistics
            if "device_stats" in results:
                print(f"  设备统计:")
                for stat in results["device_stats"]:
                    dev_conf = stat.get("mean_confidence", "N/A")
                    print(
                        f"    {stat['device']}: {stat['n_matches']} 个匹配，置信度 {dev_conf if isinstance(dev_conf, str) else f'{dev_conf:.3f}'}"
                    )

            # Print drift correction
            if "drift_corrections" in results:
                print(f"  漂移校正:")
                for i, drift in enumerate(results["drift_corrections"]):
                    if drift:
                        print(
                            f"    设备{i + 1}: 偏移 {drift.get('offset', 0):.3f}s, 缩放 {drift.get('scale', 1):.5f}, R²={drift.get('r_squared', 0):.3f}"
                        )
        else:
            # Backward compatible mode: load from directory or file list
            from multichsync.marker import match_multiple_files_enhanced

            # Get file list
            if args.input_dir:
                # Read files from directory
                input_dir = Path(args.input_dir)
                if not input_dir.exists():
                    raise FileNotFoundError(f"输入目录不存在: {input_dir}")

                # Find CSV files
                csv_files = list(input_dir.glob("*.csv"))
                if len(csv_files) < 2:
                    raise ValueError(
                        f"需要至少2个CSV文件进行匹配，但只找到 {len(csv_files)} 个"
                    )

                # Sort for consistency
                csv_files.sort()
                file_paths = [str(f) for f in csv_files]
                print(f"从目录加载 {len(file_paths)} 个文件: {input_dir}")
            elif args.input_files:
                # Directly specify file list (support with or without extension)
                file_paths = []
                for f in args.input_files:
                    p = Path(f)
                    if p.exists():
                        file_paths.append(str(p))
                    else:
                        # Try adding .csv suffix
                        p_csv = p.with_suffix(".csv")
                        if p_csv.exists():
                            file_paths.append(str(p_csv))
                        else:
                            # Try finding in Data/marker subfolder
                            marker_dir = Path("Data/marker")
                            if marker_dir.exists():
                                # Smart matching: try multiple patterns (support simplified and full filenames)
                                input_name = p.name

                                # Determine base name of input file (remove common suffixes)
                                base_name = (
                                    input_name.replace("_ecg", "")
                                    .replace("_fnirs", "")
                                    .replace("_eeg", "")
                                    .replace("_input", "")
                                )

                                # Determine priority search subfolder based on input suffix
                                priority_subdirs = []
                                if "_input" in input_name:
                                    priority_subdirs = [
                                        "ecg"
                                    ]  # _input suffix prioritizes search in ecg folder
                                elif "_ecg" in input_name:
                                    priority_subdirs = ["ecg"]
                                elif "_fnirs" in input_name:
                                    priority_subdirs = ["fnirs"]
                                elif "_eeg" in input_name:
                                    priority_subdirs = ["eeg"]

                                # Build search patterns
                                search_patterns = [
                                    input_name,  # Original input
                                    f"{input_name}_marker",  # Add _marker suffix
                                    # Special handling: ecg -> input conversion
                                    input_name.replace("_ecg", "_input"),
                                    input_name.replace("_ecg", "") + "_input",
                                    # Special handling: fnirs/eeg stay as is
                                    input_name.replace("_fnirs", ""),
                                    input_name.replace("_eeg", ""),
                                    # If user already entered _input, also try other variants
                                    input_name.replace("_input", "_ecg"),
                                    input_name.replace("_input", ""),
                                    # Add base name patterns (after removing various suffixes)
                                    base_name,
                                    f"{base_name}_input",  # Add _input suffix
                                    f"{base_name}_ecg",  # Add _ecg suffix
                                    f"{base_name}_fnirs",  # Add _fnirs suffix
                                    f"{base_name}_eeg",  # Add _eeg suffix
                                ]

                                # Search priority subfolders first, then other subfolders
                                subdirs_to_search = priority_subdirs + [
                                    s
                                    for s in ["fnirs", "eeg", "ecg"]
                                    if s not in priority_subdirs
                                ]

                                for subdir in subdirs_to_search:
                                    search_dir = marker_dir / subdir
                                    if search_dir.exists():
                                        for pattern in search_patterns:
                                            found = list(
                                                search_dir.glob(f"{pattern}.csv")
                                            )
                                            if found:
                                                file_paths.append(str(found[0]))
                                                break
                                    if file_paths and any(
                                        Path(fp).stem.startswith(
                                            p.stem.rstrip("_ecg")
                                            .rstrip("_fnirs")
                                            .rstrip("_eeg")
                                            .rstrip("_input")
                                        )
                                        for fp in (
                                            [file_paths[-1]] if file_paths else []
                                        )
                                    ):
                                        break

                            # Smart matching: check if correct file was matched
                            matched = False
                            if file_paths:
                                input_stem = (
                                    p.stem.replace("_ecg", "_input")
                                    .replace("_fnirs", "")
                                    .replace("_eeg", "")
                                    .replace("_input", "")  # Handle case where _input suffix is already present
                                )
                                for fp in file_paths:
                                    fp_stem = (
                                        Path(fp)
                                        .stem.replace("_input", "")
                                        .replace("_marker", "")
                                        .replace("_fnirs", "")
                                        .replace("_eeg", "")
                                        .replace("_ecg", "")
                                    )
                                    if input_stem in fp_stem or fp_stem.startswith(
                                        p.stem.replace("_ecg", "")
                                        .replace("_fnirs", "")
                                        .replace("_eeg", "")
                                        .replace("_input", "")
                                    ):
                                        matched = True
                                        break
                            if not matched:
                                raise FileNotFoundError(f"找不到文件: {f}")

                print(f"加载 {len(file_paths)} 个指定文件")
            else:
                raise ValueError("必须提供 --filename 或 --input-dir 或 --input-files")

            # Device name (optional)
            device_names = args.device_names if args.device_names else None

            # Output directory
            output_dir = args.output_dir if args.output_dir else "data/matching"

            # Map CLI method names to internal method names
            internal_method = METHOD_NAME_MAPPING[args.method]

            # Call matching function
            results = match_multiple_files_enhanced(
                file_paths=file_paths,
                device_names=device_names,
                method=internal_method,
                max_time_diff_s=args.max_time_diff,
                sigma_time_s=args.sigma_time,
                estimate_drift=not args.no_drift_correction,
                drift_method=args.drift_method,
                output_dir=output_dir,
                output_prefix=args.output_prefix,
                save_json=not args.no_json,
                generate_plots=not args.no_plots,
            )

            # Print result summary
            print(f"匹配完成!")
            print(f"  输出目录: {output_dir}")
            print(f"  时间线CSV: {output_dir}/{args.output_prefix}_timeline.csv")
            print(f"  元数据JSON: {output_dir}/{args.output_prefix}_metadata.json")
            print(f"  共识事件数: {results.get('n_consensus_events', 'N/A')}")
            print(f"  总匹配数: {results.get('total_matches', 'N/A')}")
            mean_conf = results.get("mean_confidence", "N/A")
            print(
                f"  平均置信度: {mean_conf if isinstance(mean_conf, str) else f'{mean_conf:.3f}'}"
            )

            # Print device statistics
            if "device_stats" in results:
                print(f"  设备统计:")
                for stat in results["device_stats"]:
                    dev_conf = stat.get("mean_confidence", "N/A")
                    print(
                        f"    {stat['device']}: {stat['n_matches']} 个匹配，置信度 {dev_conf if isinstance(dev_conf, str) else f'{dev_conf:.3f}'}"
                    )

            # Print drift correction
            if "drift_corrections" in results:
                print(f"  漂移校正:")
                for i, drift in enumerate(results["drift_corrections"]):
                    if drift:
                        print(
                            f"    设备{i + 1}: 偏移 {drift.get('offset', 0):.3f}s, 缩放 {drift.get('scale', 1):.5f}, R²={drift.get('r_squared', 0):.3f}"
                        )

    except Exception as e:
        print(f"Marker匹配失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_crop(args):
    """处理timeline裁剪命令"""
    try:
        timeline_csv = Path(args.timeline_csv)
        metadata_json = Path(args.metadata_json)

        if not timeline_csv.exists():
            raise FileNotFoundError(f"Timeline CSV文件不存在: {timeline_csv}")
        if not metadata_json.exists():
            raise FileNotFoundError(f"Metadata JSON文件不存在: {metadata_json}")

        output_dir = Path(args.output_dir) if args.output_dir else timeline_csv.parent

        result = crop_timelines_to_shortest(
            timeline_csv=timeline_csv,
            metadata_json=metadata_json,
            output_dir=output_dir,
            output_prefix=args.output_prefix,
            include_metadata=not args.no_metadata,
        )

        print(f"Timeline裁剪完成!")
        print(f"  参照设备: {result['crop_info']['reference_device']}")
        print(
            f"  时间范围: {result['crop_info']['reference_start']:.3f}s - {result['crop_info']['reference_end']:.3f}s"
        )
        print(f"  裁剪设备数: {len(result['crop_info']['cropped_devices'])}")
        print(f"  输出目录: {output_dir}")
        print(f"  输出文件:")
        for name, path in result["output_files"].items():
            print(f"    {name}: {path}")

    except Exception as e:
        print(f"Timeline裁剪失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_matchcrop(args):
    """处理matchcrop命令 - 裁剪多设备原始数据"""
    try:
        timeline_csv = Path(args.timeline_csv)
        metadata_json = Path(args.metadata_json)

        if not timeline_csv.exists():
            raise FileNotFoundError(f"Timeline CSV文件不存在: {timeline_csv}")
        if not metadata_json.exists():
            raise FileNotFoundError(f"Metadata JSON文件不存在: {metadata_json}")

        output_dir = Path(args.output_dir) if args.output_dir else timeline_csv.parent

        result = matchcrop(
            timeline_csv=timeline_csv,
            metadata_json=metadata_json,
            reference_device=args.reference,
            output_dir=output_dir,
            output_prefix=args.output_prefix,
        )

        print(f"MatchCrop完成!")
        print(f"  参考设备: {result['reference_device']}")
        print(f"  裁剪设备数: {len(result['cropped_devices'])}")
        print(f"  输出目录: {output_dir}")
        print(f"  输出文件:")
        for name, path in result["output_files"].items():
            print(f"    {name}: {path}")

    except Exception as e:
        print(f"MatchCrop失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_matchcrop_aligned(args):
    """处理matchcrop-aligned命令 - 基于对齐的时间线裁剪"""
    from pathlib import Path
    from multichsync.marker import matchcrop_aligned

    try:
        json_path = Path(args.json_path)

        if not json_path.exists():
            raise FileNotFoundError(f"Metadata JSON文件不存在: {json_path}")

        result = matchcrop_aligned(
            json_path=json_path,
            start_time=args.start_time,
            end_time=args.end_time,
            taskname=args.taskname,
        )

        print(f"MatchCrop-Aligned完成!")
        print(
            f"  裁剪时间范围: {result['crop_time_range'][0]:.3f}s - {result['crop_time_range'][1]:.3f}s"
        )
        print(f"  Task名称: {result['old_taskname']} -> {result['new_taskname']}")
        print(f"  输出目录: {result['output_dir']}")
        print(f"  成功处理设备: {len(result['cropped_devices'])}")

        if result["errors"]:
            print(f"  错误数: {len(result['errors'])}")
            for err in result["errors"]:
                print(f"    - {err}")

    except Exception as e:
        print(f"MatchCrop-Aligned失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_manual_match(args):
    """处理manual-match命令 - 手动调整设备偏移量并重新生成匹配时间线"""
    from pathlib import Path
    from multichsync.marker.adjust_offsets import adjust_offsets, parse_offset_list
    
    try:
        json_path = Path(args.json_path)
        
        if not json_path.exists():
            raise FileNotFoundError(f"Metadata JSON文件不存在: {json_path}")
        
        # 解析偏移量列表（基于JSON中device_info顺序）
        offset_list = parse_offset_list(args.offsets)
        
        if not offset_list:
            print("警告: 未指定任何偏移量，将使用原始偏移量")
        
        # 输出目录为JSON文件所在目录
        output_dir = json_path.parent
        
        # 运行调整
        result = adjust_offsets(
            json_path=json_path,
            offsets=offset_list,
            output_dir=output_dir,
            output_prefix=args.prefix,
            add_to_existing=args.add,
            method=args.method,
            sigma_time_s=args.sigma_time,
            max_time_diff_s=args.max_time_diff
        )
        
        print(f"手动匹配完成!")
        print(f"  输出目录: {output_dir}")
        print(f"  时间线文件: {result['output_files']['timeline_csv']}")
        print(f"  元数据文件: {result['output_files']['metadata_json']}")
        if result['output_files']['diff_report']:
            print(f"  差异报告: {result['output_files']['diff_report']}")
        print(f"  调整的设备数: {len(result['adjusted_devices'])}")
        
    except Exception as e:
        print(f"手动匹配失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def quality_assess(args):
    """处理SNIRF文件质量评估命令"""
    try:
        from pathlib import Path

        comprehensive = not args.no_comprehensive
        args.comprehensive = comprehensive

        input_path = Path(args.input)
        output_dir = (
            Path(args.output_dir) if args.output_dir else input_path.parent / "quality"
        )

        resample_sfreq = args.resample_sfreq if args.resample_sfreq > 0 else None

        summary = process_one_snirf(
            snirf_path=input_path,
            out_dir=output_dir,
            l_freq=args.l_freq,
            h_freq=args.h_freq,
            resample_sfreq=resample_sfreq,
            apply_tddr=not args.no_tddr,
            signal_band=(args.signal_band_min, args.signal_band_max),
            noise_band=(args.noise_band_min, args.noise_band_max),
            comprehensive=args.comprehensive,
            paradigm=args.paradigm,
            events=None,
        )

        print(f"质量评估完成:")
        print(f"  输出目录: {output_dir}")
        print(f"  HbO通道数: {summary['n_hbo_channels']}")
        print(f"  HbR通道数: {summary['n_hbr_channels']}")
        print(f"  滤波前坏通道数: {summary['n_bad_prefilter']}")
        print(f"  滤波后坏通道数: {summary['n_bad_postfilter']}")
        print(f"  滤波前平均时域SNR: {summary['Pre-filter mean time SNR (dB)']:.2f} dB")
        print(
            f"  滤波后平均时域SNR: {summary['Post-filter mean time SNR (dB)']:.2f} dB"
        )

    except Exception as e:
        print(f"质量评估失败: {e}")
        sys.exit(1)


def quality_batch(args):
    """处理SNIRF文件批量质量评估命令"""
    try:
        from pathlib import Path

        comprehensive = not args.no_comprehensive
        args.comprehensive = comprehensive

        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir) if args.output_dir else input_dir / "quality"

        resample_sfreq = args.resample_sfreq if args.resample_sfreq > 0 else None

        summary_df, failed = batch_process_snirf_folder(
            in_dir=input_dir,
            out_dir=output_dir,
            l_freq=args.l_freq,
            h_freq=args.h_freq,
            resample_sfreq=resample_sfreq,
            apply_tddr=not args.no_tddr,
            signal_band=(args.signal_band_min, args.signal_band_max),
            noise_band=(args.noise_band_min, args.noise_band_max),
            comprehensive=args.comprehensive,
            paradigm=args.paradigm,
            events=None,
        )

        print(f"批量质量评估完成:")
        print(f"  输出目录: {output_dir}")
        print(f"  处理文件数: {len(summary_df)}")
        print(f"  失败文件数: {len(failed)}")

        if len(failed) > 0:
            print(f"  失败文件详情: {output_dir / 'snirf_batch_failed.csv'}")

        print(f"  汇总文件: {output_dir / 'snirf_batch_summary.csv'}")

    except Exception as e:
        print(f"批量质量评估失败: {e}")
        sys.exit(1)


def quality_assess_with_metadata(args):
    """处理SNIRF文件质量评估命令，并将结果写入SNIRF文件元数据"""
    try:
        from pathlib import Path

        input_path = Path(args.input)
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else input_path.parent / "quality_with_metadata"
        )

        resample_sfreq = args.resample_sfreq if args.resample_sfreq > 0 else None

        summary = process_one_snirf_with_metadata(
            snirf_path=input_path,
            out_dir=output_dir,
            l_freq=args.l_freq,
            h_freq=args.h_freq,
            resample_sfreq=resample_sfreq,
            apply_tddr=not args.no_tddr,
            signal_band=(args.signal_band_min, args.signal_band_max),
            noise_band=(args.noise_band_min, args.noise_band_max),
            comprehensive=not args.no_comprehensive,
            paradigm=args.paradigm,
            events=None,
            write_metadata=not args.no_metadata,
            output_snirf_path=args.output_snirf,
            write_report_csv=not args.no_report_csv,
            overwrite=args.overwrite,
        )

        print(f"质量评估完成（带元数据写入）:")
        print(f"  输出目录: {output_dir}")
        print(f"  HbO通道数: {summary['n_hbo_channels']}")
        print(f"  HbR通道数: {summary['n_hbr_channels']}")
        print(f"  坏通道数: {summary['n_bad_channels']}")
        print(f"  整体质量分数: {summary['overall_score']:.3f}")

        if summary["metadata_written"]:
            print(f"  元数据已写入: {summary['output_snirf_file']}")
        else:
            print(f"  警告: 元数据未写入")

        if summary["report_csv_file"]:
            print(f"  单行报告CSV: {summary['report_csv_file']}")

    except Exception as e:
        print(f"质量评估失败: {e}")
        sys.exit(1)


def quality_batch_with_metadata(args):
    """处理SNIRF文件批量质量评估命令，并将结果写入SNIRF文件元数据"""
    try:
        from pathlib import Path

        input_dir = Path(args.input_dir)
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else input_dir / "quality_with_metadata"
        )

        resample_sfreq = args.resample_sfreq if args.resample_sfreq > 0 else None

        summary_df, failed = batch_process_snirf_folder_with_metadata(
            in_dir=input_dir,
            out_dir=output_dir,
            l_freq=args.l_freq,
            h_freq=args.h_freq,
            resample_sfreq=resample_sfreq,
            apply_tddr=not args.no_tddr,
            signal_band=(args.signal_band_min, args.signal_band_max),
            noise_band=(args.noise_band_min, args.noise_band_max),
            comprehensive=not args.no_comprehensive,
            paradigm=args.paradigm,
            events=None,
            write_metadata=not args.no_metadata,
            write_report_csv=not args.no_report_csv,
            overwrite=args.overwrite,
        )

        print(f"批量质量评估完成（带元数据写入）:")
        print(f"  输出目录: {output_dir}")
        print(f"  处理文件数: {len(summary_df)}")
        print(f"  失败文件数: {len(failed)}")

        if len(failed) > 0:
            print(f"  失败文件详情: {output_dir / 'snirf_batch_failed.csv'}")

        print(f"  汇总文件: {output_dir / 'snirf_batch_summary_with_metadata.csv'}")

        # Count metadata write status
        n_with_metadata = (
            summary_df["metadata_written"].sum()
            if "metadata_written" in summary_df.columns
            else 0
        )
        print(f"  成功写入元数据的文件数: {n_with_metadata}/{len(summary_df)}")

    except Exception as e:
        print(f"批量质量评估失败: {e}")
        sys.exit(1)


def quality_resting_metrics(args):
    """批量计算fNIRS文件的静息态指标"""
    try:
        from pathlib import Path

        input_dir = Path(args.input_dir)
        output_dir = (
            Path(args.output_dir) if args.output_dir else input_dir / "resting_metrics"
        )

        summary_df, failed = batch_compute_resting_metrics(
            input_dir=input_dir,
            output_dir=output_dir,
            temp_dir=args.temp_dir,
        )

        print(f"静息态指标计算完成:")
        print(f"  输入目录: {input_dir}")
        print(f"  输出目录: {output_dir}")
        print(f"  处理文件数: {len(summary_df)}")
        print(f"  失败文件数: {len(failed)}")

        if len(summary_df) > 0 and "mean_reliability" in summary_df.columns:
            valid_rel = summary_df["mean_reliability"].dropna()
            if len(valid_rel) > 0:
                print(f"  平均可靠性统计:")
                print(f"    最小值: {valid_rel.min():.3f}")
                print(f"    最大值: {valid_rel.max():.3f}")
                print(f"    中位数: {valid_rel.median():.3f}")
                print(f"    平均值: {valid_rel.mean():.3f}")

        if len(failed) > 0:
            print(f"  失败文件详情: {output_dir / 'failed_files.csv'}")

        print(f"  汇总文件: {output_dir / 'resting_metrics_summary.csv'}")

    except Exception as e:
        print(f"静息态指标计算失败: {e}")
        sys.exit(1)


def quality_visualize(args):
    """处理质量评估可视化命令"""
    try:
        from pathlib import Path
        from multichsync.quality.visualization import generate_all_visualizations

        input_path = Path(args.input)
        output_dir = Path(args.output_dir) if args.output_dir else input_path.parent

        # Determine visualization types to generate
        generate_heatmap = not args.no_heatmap
        generate_snr = not args.no_snr
        generate_corr = not args.no_correlation

        # Call visualization function
        results = generate_all_visualizations(
            input_snirf_path=input_path,
            output_dir=output_dir,
            generate_heatmap=generate_heatmap,
            generate_snr=generate_snr,
            generate_correlation=generate_corr,
            dpi=args.dpi,
        )

        print(f"质量评估可视化完成:")
        print(f"  输出目录: {output_dir}")

        for viz_type, path in results.items():
            if path:
                print(f"  {viz_type}: {path.name}")
            else:
                print(f"  {viz_type}: 生成失败")

    except Exception as e:
        print(f"质量评估可视化失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def quality_visualize_batch(args):
    """批量生成质量评估可视化"""
    try:
        from pathlib import Path
        from multichsync.quality.visualization import generate_all_visualizations
        import glob

        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir) if args.output_dir else input_dir

        # Find all quality assessment output files (directories containing _postfilter_detail.csv)
        # Here we assume user has already run quality assessment
        detail_files = list(output_dir.rglob("*_postfilter_detail.csv"))

        if not detail_files:
            print(f"警告: 在 {output_dir} 中未找到质量评估数据")
            print(
                f"请先运行质量评估: multichsync quality batch --input-dir <dir> --output-dir {output_dir}"
            )
            return

        print(f"找到 {len(detail_files)} 个质量评估数据文件")

        # Batch generate visualizations
        success_count = 0
        failed_files = []

        # Group by file (same file has _postfilter_detail.csv and _comprehensive_detail.csv)
        processed_stems = set()

        for detail_file in detail_files:
            stem = detail_file.stem.replace("_postfilter_detail", "")

            if stem in processed_stems:
                continue
            processed_stems.add(stem)

            # Find corresponding SNIRF file
            snirf_files = list(input_dir.glob(f"{stem}.snirf"))
            if not snirf_files:
                # Try finding in parent directory
                snirf_files = list(input_dir.rglob(f"{stem}.snirf"))

            if not snirf_files:
                print(f"  跳过 {stem}: 未找到 SNIRF 文件")
                continue

            snirf_path = snirf_files[0]

            try:
                results = generate_all_visualizations(
                    input_snirf_path=snirf_path,
                    output_dir=output_dir,
                    generate_heatmap=not args.no_heatmap,
                    generate_snr=not args.no_snr,
                    generate_correlation=not args.no_correlation,
                    dpi=args.dpi,
                )

                if any(results.values()):
                    success_count += 1
                    print(f"  完成: {stem}")
                else:
                    failed_files.append(stem)
                    print(f"  失败: {stem}")

            except Exception as e:
                failed_files.append(stem)
                print(f"  错误 {stem}: {e}")

        print(f"\n批量可视化完成:")
        print(f"  成功: {success_count}")
        print(f"  失败: {len(failed_files)}")

        if failed_files:
            print(
                f"  失败文件: {', '.join(failed_files[:5])}{'...' if len(failed_files) > 5 else ''}"
            )

    except Exception as e:
        print(f"批量可视化失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="多模态神经影像数据转换工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s fnirs convert --txt data.TXT --src-coords sources.csv --det-coords detectors.csv
  %(prog)s fnirs convert --txt data.TXT --src-coords sources.csv --det-coords detectors.csv --no-mne-patch
  %(prog)s fnirs batch --input-dir ./raw --src-coords sources.csv --det-coords detectors.csv --output-dir ./snirf
  %(prog)s fnirs patch --input existing.snirf --inplace --dummy-wavelengths 760.0 850.0
  %(prog)s fnirs patch --input existing.snirf --output fixed.snirf --no-move-hbt
  %(prog)s ecg convert --acq data.acq --format csv --sampling-rate 250
  %(prog)s ecg batch --input-dir ./raw/ecg --format csv --output-dir ./convert/ecg
  %(prog)s eeg convert --file data.set --format BrainVision
  %(prog)s eeg batch --input-dir ./raw/eeg --format BrainVision --output-dir ./convert/eeg
  %(prog)s marker extract --input marker.vmrk --type brainvision
  %(prog)s marker extract --input biopac.csv --type biopac --fs 500
  %(prog)s marker extract --input fnirs.csv --type fnirs
  %(prog)s marker clean --input marker.csv --inplace --min-interval 0.5
  %(prog)s marker clean --input ./marker_folder --output-dir ./cleaned --min-rows 3
  %(prog)s marker info --input-dir Data/marker --output-dir Data/marker/info
  %(prog)s quality assess --input data.snirf --output-dir ./quality
  %(prog)s quality batch --input-dir ./snirf_folder --output-dir ./quality
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # fnirs subcommand
    fnirs_parser = subparsers.add_parser("fnirs", help="fNIRS相关操作")
    fnirs_subparsers = fnirs_parser.add_subparsers(
        dest="fnirs_command", help="fNIRS子命令"
    )

    # fnirs convert
    convert_parser = fnirs_subparsers.add_parser("convert", help="转换单个fNIRS文件")
    convert_parser.add_argument(
        "--txt-path", "--txt", required=True, help="fNIRS TXT文件路径"
    )
    convert_parser.add_argument(
        "--src-coords", required=True, help="source坐标CSV文件路径"
    )
    convert_parser.add_argument(
        "--det-coords", required=True, help="detector坐标CSV文件路径"
    )
    convert_parser.add_argument(
        "--output", "-o", help="输出SNIRF文件路径（默认：同名.snirf）"
    )
    convert_parser.add_argument(
        "--no-mne-patch", action="store_true", help="禁用MNE兼容性修复（默认启用）"
    )
    convert_parser.set_defaults(func=fnirs_convert)

    # fnirs batch
    batch_parser = fnirs_subparsers.add_parser("batch", help="批量转换fNIRS文件")
    batch_parser.add_argument("--input-dir", "-i", required=True, help="输入目录路径")
    batch_parser.add_argument(
        "--src-coords", required=True, help="source坐标CSV文件路径"
    )
    batch_parser.add_argument(
        "--det-coords", required=True, help="detector坐标CSV文件路径"
    )
    batch_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：输入目录）"
    )
    batch_parser.add_argument(
        "--no-mne-patch", action="store_true", help="禁用MNE兼容性修复（默认启用）"
    )
    batch_parser.set_defaults(func=fnirs_batch)

    # fnirs patch
    patch_parser = fnirs_subparsers.add_parser(
        "patch", help="修复已存在的SNIRF文件以便MNE读取"
    )
    patch_parser.add_argument("--input", "-i", required=True, help="输入SNIRF文件路径")
    patch_parser.add_argument(
        "--output", "-o", help="输出SNIRF文件路径（默认：输入文件名_mne_fixed.snirf）"
    )
    patch_parser.add_argument(
        "--inplace", action="store_true", help="原地修复（覆盖原文件）"
    )
    patch_parser.add_argument(
        "--dummy-wavelengths",
        type=float,
        nargs="+",
        default=[760.0, 850.0],
        help="虚拟波长值（默认：760.0 850.0）",
    )
    patch_parser.add_argument(
        "--no-move-hbt", action="store_true", help="不移除HbT通道到aux（默认移除）"
    )
    patch_parser.set_defaults(func=fnirs_patch)

    # ecg subcommand
    ecg_parser = subparsers.add_parser("ecg", help="ECG相关操作")
    ecg_subparsers = ecg_parser.add_subparsers(dest="ecg_command", help="ECG子命令")

    # ecg convert
    ecg_convert_parser = ecg_subparsers.add_parser("convert", help="转换单个ECG文件")
    ecg_convert_parser.add_argument(
        "--acq-path", "--acq", required=True, help="ACQ文件路径"
    )
    ecg_convert_parser.add_argument(
        "--format",
        "-f",
        choices=["csv"],
        default="csv",
        help="输出格式（仅支持csv，默认：csv）",
    )
    ecg_convert_parser.add_argument(
        "--output", "-o", help="输出文件路径（默认：自动生成）"
    )
    ecg_convert_parser.add_argument(
        "--sampling-rate",
        "-r",
        type=int,
        default=250,
        help="目标采样率（Hz，默认：250）",
    )
    ecg_convert_parser.add_argument(
        "--no-group", action="store_true", help="不按通道类型分组输出（仅CSV格式）"
    )
    ecg_convert_parser.add_argument(
        "--float-format", default="%.6f", help="浮点数格式（默认：%%.6f）"
    )
    ecg_convert_parser.set_defaults(func=ecg_convert)

    # ecg batch
    ecg_batch_parser = ecg_subparsers.add_parser("batch", help="批量转换ECG文件")
    ecg_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="输入目录路径"
    )
    ecg_batch_parser.add_argument(
        "--format",
        "-f",
        choices=["csv"],
        default="csv",
        help="输出格式（仅支持csv，默认：csv）",
    )
    ecg_batch_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：自动生成）"
    )
    ecg_batch_parser.add_argument(
        "--sampling-rate",
        "-r",
        type=int,
        default=250,
        help="目标采样率（Hz，默认：250）",
    )
    ecg_batch_parser.add_argument(
        "--no-group", action="store_true", help="不按通道类型分组输出（仅CSV格式）"
    )
    ecg_batch_parser.add_argument(
        "--float-format", default="%.6f", help="浮点数格式（默认：%%.6f）"
    )
    ecg_batch_parser.set_defaults(func=ecg_batch)

    # eeg subcommand
    eeg_parser = subparsers.add_parser("eeg", help="EEG相关操作")
    eeg_subparsers = eeg_parser.add_subparsers(dest="eeg_command", help="EEG子命令")

    # eeg convert
    eeg_convert_parser = eeg_subparsers.add_parser("convert", help="转换单个EEG文件")
    eeg_convert_parser.add_argument(
        "--file-path",
        "--file",
        required=True,
        help="EEG文件路径（支持.set, .cdt等格式）",
    )
    eeg_convert_parser.add_argument(
        "--format",
        "-f",
        choices=["BrainVision", "EEGLAB", "EDF"],
        default="BrainVision",
        help="输出格式（默认：BrainVision）",
    )
    eeg_convert_parser.add_argument(
        "--output", "-o", help="输出文件路径（默认：自动生成）"
    )
    eeg_convert_parser.add_argument(
        "--preload", action="store_true", help="预加载数据到内存"
    )
    eeg_convert_parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的文件"
    )
    eeg_convert_parser.add_argument(
        "--verbose", action="store_true", help="显示详细输出"
    )
    eeg_convert_parser.add_argument(
        "--sampling-rate",
        "-s",
        nargs="?",
        const=250.0,
        default=None,
        type=float,
        help="目标采样率（Hz，默认：None（保持原采样率），使用--sampling-rate不带参数时默认为250Hz）",
    )
    eeg_convert_parser.set_defaults(func=eeg_convert)

    # eeg batch
    eeg_batch_parser = eeg_subparsers.add_parser("batch", help="批量转换EEG文件")
    eeg_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="输入目录路径"
    )
    eeg_batch_parser.add_argument(
        "--format",
        "-f",
        choices=["BrainVision", "EEGLAB", "EDF"],
        default="BrainVision",
        help="输出格式（默认：BrainVision）",
    )
    eeg_batch_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：自动生成）"
    )
    eeg_batch_parser.add_argument(
        "--preload", action="store_true", help="预加载数据到内存"
    )
    eeg_batch_parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的文件"
    )
    eeg_batch_parser.add_argument("--verbose", action="store_true", help="显示详细输出")
    eeg_batch_parser.add_argument(
        "--recursive", "-r", action="store_true", help="递归搜索子目录"
    )
    eeg_batch_parser.add_argument(
        "--sampling-rate",
        "-s",
        nargs="?",
        const=250.0,
        default=None,
        type=float,
        help="目标采样率（Hz，默认：None（保持原采样率），使用--sampling-rate不带参数时默认为250Hz）",
    )
    eeg_batch_parser.set_defaults(func=eeg_batch)

    # marker subcommand
    marker_parser = subparsers.add_parser("marker", help="Marker提取相关操作")
    marker_subparsers = marker_parser.add_subparsers(
        dest="marker_command", help="Marker子命令"
    )

    # marker extract
    marker_extract_parser = marker_subparsers.add_parser(
        "extract", help="提取marker信息"
    )
    marker_extract_parser.add_argument(
        "--input", "-i", required=True, help="输入文件路径"
    )
    marker_extract_parser.add_argument(
        "--output", "-o", help="输出CSV文件路径（默认：输入文件名.marker.csv）"
    )
    marker_extract_parser.add_argument(
        "--type",
        choices=["biopac", "brainvision", "fnirs"],
        help="文件类型（可选，默认根据扩展名猜测）",
    )
    marker_extract_parser.add_argument(
        "--fs", type=float, default=500, help="Biopac采样率（Hz，默认：500）"
    )
    marker_extract_parser.add_argument(
        "--tolerance", type=float, default=0.2, help="Biopac电压容差（默认：0.2）"
    )
    marker_extract_parser.set_defaults(func=marker_extract)

    # marker batch
    marker_batch_parser = marker_subparsers.add_parser(
        "batch", help="批量提取marker信息"
    )
    marker_batch_parser.add_argument(
        "--types",
        "-t",
        help="要处理的类型，逗号分隔（默认：fnirs,ecg,eeg，如：fnirs,ecg）",
    )
    marker_batch_parser.add_argument(
        "--fnirs-input",
        help="fNIRS输入目录（默认：Data/raw/fnirs）",
    )
    marker_batch_parser.add_argument(
        "--fnirs-output",
        help="fNIRS输出目录（默认：Data/marker/fnirs）",
    )
    marker_batch_parser.add_argument(
        "--ecg-input",
        help="ECG输入目录（默认：Data/convert/ecg）",
    )
    marker_batch_parser.add_argument(
        "--ecg-output",
        help="ECG输出目录（默认：Data/marker/ecg）",
    )
    marker_batch_parser.add_argument(
        "--eeg-input",
        help="EEG输入目录（默认：Data/convert/eeg）",
    )
    marker_batch_parser.add_argument(
        "--eeg-output",
        help="EEG输出目录（默认：Data/marker/eeg）",
    )
    marker_batch_parser.add_argument(
        "--fs",
        type=float,
        default=500,
        help="ECG采样率（Hz，默认：500）",
    )
    marker_batch_parser.add_argument(
        "--tolerance",
        type=float,
        default=0.2,
        help="ECG电压容差（默认：0.2）",
    )
    marker_batch_parser.add_argument(
        "--skip-existing", action="store_true", help="跳过已存在的输出文件"
    )
    marker_batch_parser.add_argument(
        "--max-files",
        type=int,
        help="每种类型最多处理的文件数（默认：全部）",
    )
    marker_batch_parser.set_defaults(func=marker_batch)

    # marker clean
    marker_clean_parser = marker_subparsers.add_parser("clean", help="清洗marker文件")
    marker_clean_parser.add_argument(
        "--input", "-i", required=True, help="输入文件或目录路径"
    )
    marker_clean_parser.add_argument(
        "--output-dir", help="输出目录路径（仅目录模式有效，默认：输入目录/cleaned）"
    )
    marker_clean_parser.add_argument(
        "--inplace", action="store_true", help="原地清洗（覆盖原文件）"
    )
    marker_clean_parser.add_argument(
        "--time-col",
        help="时间列名（默认自动检测：Time(sec)/reference_time/time/Time）",
    )
    marker_clean_parser.add_argument(
        "--min-rows", type=int, default=2, help="最小行数要求（默认：2）"
    )
    marker_clean_parser.add_argument(
        "--min-interval", type=float, default=1.0, help="最小时间间隔（秒，默认：1.0）"
    )
    marker_clean_parser.add_argument(
        "--remove-start", action="store_true", help="删除第一个marker时间为0的记录"
    )
    marker_clean_parser.set_defaults(func=marker_clean)

    # marker info
    marker_info_parser = marker_subparsers.add_parser(
        "info", help="提取marker信息并生成报告"
    )
    marker_info_parser.add_argument(
        "--input-dir", "-i", help="输入目录路径（默认：Data/marker）"
    )
    marker_info_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：输入目录/info）"
    )
    marker_info_parser.add_argument(
        "--no-recursive", action="store_true", help="不递归搜索子目录（默认递归）"
    )
    marker_info_parser.set_defaults(func=marker_info)

    # marker match
    marker_match_parser = marker_subparsers.add_parser(
        "match", help="匹配多设备marker事件，生成共识时间线"
    )
    marker_match_parser.add_argument(
        "--filename", "-f", help="文件名（不含后缀），自动从Data/convert加载数据"
    )
    marker_match_parser.add_argument(
        "--convert-dir", help="数据目录（默认：Data/convert）"
    )
    input_group = marker_match_parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument("--input-dir", help="包含CSV文件的输入目录")
    input_group.add_argument("--input-files", nargs="+", help="CSV文件路径列表")
    marker_match_parser.add_argument(
        "--device-names", nargs="+", help="设备名称列表（与文件顺序对应）"
    )
    marker_match_parser.add_argument(
        "--output-dir",
        default="data/matching",
        help="输出目录路径（默认：data/matching）",
    )
    marker_match_parser.add_argument(
        "--output-prefix", default="matched", help="输出文件前缀（默认：matched）"
    )
    marker_match_parser.add_argument(
        "--method",
        choices=["hungarian", "mincostflow", "sinkhorn"],
        default="hungarian",
        help="匹配算法（默认：hungarian，可选：hungarian/mincostflow/sinkhorn）",
    )
    marker_match_parser.add_argument(
        "--max-time-diff",
        type=float,
        default=3.0,
        help="最大时间差（秒）用于匹配（默认：3.0）",
    )
    marker_match_parser.add_argument(
        "--sigma-time",
        type=float,
        default=0.75,
        help="时间标准差（秒）用于置信度计算（默认：0.75）",
    )
    marker_match_parser.add_argument(
        "--no-drift-correction", action="store_true", help="禁用漂移校正（默认启用）"
    )
    marker_match_parser.add_argument(
        "--drift-method",
        choices=["linear", "theilsen"],
        default="linear",
        help="漂移校正方法（默认：linear）",
    )
    marker_match_parser.add_argument(
        "--no-json", action="store_true", help="不保存JSON元数据文件（默认保存）"
    )
    marker_match_parser.add_argument(
        "--no-plots", action="store_true", help="不生成可视化图表（默认生成）"
    )
    marker_match_parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的输出文件"
    )
    marker_match_parser.set_defaults(func=marker_match)

    # marker crop subcommand - added to marker subparser
    marker_crop_parser = marker_subparsers.add_parser(
        "crop", help="裁剪多设备timeline到统一时间范围"
    )
    marker_crop_parser.add_argument(
        "--timeline-csv", "-t", required=True, help="匹配后的timeline CSV文件路径"
    )
    marker_crop_parser.add_argument(
        "--metadata-json", "-m", required=True, help="匹配后的metadata JSON文件路径"
    )
    marker_crop_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：与timeline CSV同目录）"
    )
    marker_crop_parser.add_argument(
        "--output-prefix", "-p", default="cropped", help="输出文件前缀（默认：cropped）"
    )
    marker_crop_parser.add_argument(
        "--no-metadata", action="store_true", help="不保存裁剪后的metadata JSON文件"
    )
    marker_crop_parser.set_defaults(func=marker_crop)

    # marker matchcrop subcommand - added to marker subparser
    marker_matchcrop_parser = marker_subparsers.add_parser(
        "matchcrop", help="裁剪多设备原始数据（基于匹配后的timeline）"
    )
    marker_matchcrop_parser.add_argument(
        "--timeline-csv", "-t", required=True, help="匹配后的timeline CSV文件路径"
    )
    marker_matchcrop_parser.add_argument(
        "--metadata-json", "-m", required=True, help="匹配后的metadata JSON文件路径"
    )
    marker_matchcrop_parser.add_argument(
        "--reference", "-r", required=True, help="参考设备名称"
    )
    marker_matchcrop_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：与timeline CSV同目录）"
    )
    marker_matchcrop_parser.add_argument(
        "--output-prefix",
        "-p",
        default="matchcrop",
        help="输出文件前缀（默认：matchcrop）",
    )
    marker_matchcrop_parser.set_defaults(func=marker_matchcrop)

    # marker matchcrop-aligned subcommand - added to marker subparser
    marker_matchcrop_aligned_parser = marker_subparsers.add_parser(
        "matchcrop-aligned",
        help="基于对齐的时间线裁剪多设备原始数据（使用共识时间范围）",
    )
    marker_matchcrop_aligned_parser.add_argument(
        "--json-path", "-j", required=True, help="matched_metadata.json文件路径"
    )
    marker_matchcrop_aligned_parser.add_argument(
        "--start-time",
        "-s",
        type=float,
        required=True,
        help="裁剪起始时间（共识时间轴，必填，例如：0.0）",
    )
    marker_matchcrop_aligned_parser.add_argument(
        "--end-time",
        "-e",
        type=float,
        required=True,
        help="裁剪结束时间（共识时间轴，必填，例如：300.0）",
    )
    marker_matchcrop_aligned_parser.add_argument(
        "--taskname", "-t", required=True, help="输出文件的新task名称（必填）"
    )
    marker_matchcrop_aligned_parser.set_defaults(func=marker_matchcrop_aligned)

    # marker manual-match subcommand - added to marker subparser
    marker_manual_match_parser = marker_subparsers.add_parser(
        "manual-match",
        help="手动调整设备偏移量并重新生成匹配时间线"
    )
    marker_manual_match_parser.add_argument(
        "--json-path", "-j", required=True,
        help="matched_metadata.json文件路径"
    )
    marker_manual_match_parser.add_argument(
        "--offsets", "-o", required=True,
        help="偏移量列表（基于JSON中device_info顺序）：例如 '[1.5, -0.3]' 或 JSON文件路径"
    )
    marker_manual_match_parser.add_argument(
        "--prefix", "-p", default="manual",
        help="输出文件前缀（默认：manual）"
    )
    marker_manual_match_parser.add_argument(
        "--add", action="store_true",
        help="将偏移量添加到现有偏移量而不是替换"
    )
    marker_manual_match_parser.add_argument(
        "--method", "-m", default="hungarian",
        choices=["hungarian", "mincostflow", "sinkhorn"],
        help="匹配方法（默认：hungarian）"
    )
    marker_manual_match_parser.add_argument(
        "--sigma-time", type=float, default=0.75,
        help="置信度计算的高斯sigma（默认：0.75）"
    )
    marker_manual_match_parser.add_argument(
        "--max-time-diff", type=float, default=3.0,
        help="匹配的最大时间差（默认：3.0）"
    )
    marker_manual_match_parser.set_defaults(func=marker_manual_match)

    # quality subcommand
    quality_parser = subparsers.add_parser("quality", help="fNIRS数据质量评估相关操作")
    quality_subparsers = quality_parser.add_subparsers(
        dest="quality_command", help="Quality子命令"
    )

    # quality assess
    quality_assess_parser = quality_subparsers.add_parser(
        "assess", help="评估单个SNIRF文件质量"
    )
    quality_assess_parser.add_argument(
        "--input", "-i", required=True, help="SNIRF文件路径"
    )
    quality_assess_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：输入文件所在目录/quality）"
    )
    quality_assess_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="低通滤波频率（Hz，默认：0.01）"
    )
    quality_assess_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="高通滤波频率（Hz，默认：0.2）"
    )
    quality_assess_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="重采样频率（Hz，默认：4.0，设为0表示不重采样）",
    )
    quality_assess_parser.add_argument(
        "--no-tddr", action="store_true", help="不应用TDDR（默认启用）"
    )
    quality_assess_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="信号频带下限（Hz，默认：0.01）",
    )
    quality_assess_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="信号频带上限（Hz，默认：0.2）",
    )
    quality_assess_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="噪声频带下限（Hz，默认：0.2）",
    )
    quality_assess_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="噪声频带上限（Hz，默认：0.5）",
    )
    quality_assess_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="禁用基于信号水平的综合质量评估（默认启用）",
    )
    quality_assess_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="实验范式（默认：resting）",
    )
    quality_assess_parser.set_defaults(func=quality_assess)

    # quality batch
    quality_batch_parser = quality_subparsers.add_parser(
        "batch", help="批量评估SNIRF文件质量"
    )
    quality_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF文件目录路径"
    )
    quality_batch_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：输入目录/quality）"
    )
    quality_batch_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="低通滤波频率（Hz，默认：0.01）"
    )
    quality_batch_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="高通滤波频率（Hz，默认：0.2）"
    )
    quality_batch_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="重采样频率（Hz，默认：4.0，设为0表示不重采样）",
    )
    quality_batch_parser.add_argument(
        "--no-tddr", action="store_true", help="不应用TDDR（默认启用）"
    )
    quality_batch_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="信号频带下限（Hz，默认：0.01）",
    )
    quality_batch_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="信号频带上限（Hz，默认：0.2）",
    )
    quality_batch_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="噪声频带下限（Hz，默认：0.2）",
    )
    quality_batch_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="噪声频带上限（Hz，默认：0.5）",
    )
    quality_batch_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="禁用基于信号水平的综合质量评估（默认启用）",
    )
    quality_batch_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="实验范式（默认：resting）",
    )
    quality_batch_parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的输出文件"
    )
    quality_batch_parser.set_defaults(func=quality_batch)

    # quality assess-with-metadata
    quality_assess_metadata_parser = quality_subparsers.add_parser(
        "assess-with-metadata", help="评估单个SNIRF文件质量并将结果写入元数据"
    )
    quality_assess_metadata_parser.add_argument(
        "--input", "-i", required=True, help="SNIRF文件路径"
    )
    quality_assess_metadata_parser.add_argument(
        "--output-dir",
        "-o",
        help="输出目录路径（默认：输入文件所在目录/quality_with_metadata）",
    )
    quality_assess_metadata_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="低通滤波频率（Hz，默认：0.01）"
    )
    quality_assess_metadata_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="高通滤波频率（Hz，默认：0.2）"
    )
    quality_assess_metadata_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="重采样频率（Hz，默认：4.0，设为0表示不重采样）",
    )
    quality_assess_metadata_parser.add_argument(
        "--no-tddr", action="store_true", help="不应用TDDR（默认启用）"
    )
    quality_assess_metadata_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="信号频带下限（Hz，默认：0.01）",
    )
    quality_assess_metadata_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="信号频带上限（Hz，默认：0.2）",
    )
    quality_assess_metadata_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="噪声频带下限（Hz，默认：0.2）",
    )
    quality_assess_metadata_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="噪声频带上限（Hz，默认：0.5）",
    )
    quality_assess_metadata_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="禁用基于信号水平的综合质量评估（默认启用）",
    )
    quality_assess_metadata_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="实验范式（默认：resting）",
    )
    quality_assess_metadata_parser.add_argument(
        "--no-metadata", action="store_true", help="不将元数据写入SNIRF文件（默认写入）"
    )
    quality_assess_metadata_parser.add_argument(
        "--output-snirf", help="输出SNIRF文件路径（默认：自动生成_processed.snirf）"
    )
    quality_assess_metadata_parser.add_argument(
        "--no-report-csv", action="store_true", help="不生成单行CSV报告（默认生成）"
    )
    quality_assess_metadata_parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的输出文件"
    )
    quality_assess_metadata_parser.set_defaults(func=quality_assess_with_metadata)

    # quality batch-with-metadata
    quality_batch_metadata_parser = quality_subparsers.add_parser(
        "batch-with-metadata", help="批量评估SNIRF文件质量并将结果写入元数据"
    )
    quality_batch_metadata_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF文件目录路径"
    )
    quality_batch_metadata_parser.add_argument(
        "--output-dir",
        "-o",
        help="输出目录路径（默认：输入目录/quality_with_metadata）",
    )
    quality_batch_metadata_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="低通滤波频率（Hz，默认：0.01）"
    )
    quality_batch_metadata_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="高通滤波频率（Hz，默认：0.2）"
    )
    quality_batch_metadata_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="重采样频率（Hz，默认：4.0，设为0表示不重采样）",
    )
    quality_batch_metadata_parser.add_argument(
        "--no-tddr", action="store_true", help="不应用TDDR（默认启用）"
    )
    quality_batch_metadata_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="信号频带下限（Hz，默认：0.01）",
    )
    quality_batch_metadata_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="信号频带上限（Hz，默认：0.2）",
    )
    quality_batch_metadata_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="噪声频带下限（Hz，默认：0.2）",
    )
    quality_batch_metadata_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="噪声频带上限（Hz，默认：0.5）",
    )
    quality_batch_metadata_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="禁用基于信号水平的综合质量评估（默认启用）",
    )
    quality_batch_metadata_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="实验范式（默认：resting）",
    )
    quality_batch_metadata_parser.add_argument(
        "--no-metadata", action="store_true", help="不将元数据写入SNIRF文件（默认写入）"
    )
    quality_batch_metadata_parser.add_argument(
        "--no-report-csv", action="store_true", help="不生成单行CSV报告（默认生成）"
    )
    quality_batch_metadata_parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的输出文件"
    )
    quality_batch_metadata_parser.set_defaults(func=quality_batch_with_metadata)

    # quality resting-metrics
    quality_resting_metrics_parser = quality_subparsers.add_parser(
        "resting-metrics", help="批量计算fNIRS文件的静息态指标"
    )
    quality_resting_metrics_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF文件目录路径"
    )
    quality_resting_metrics_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：输入目录/resting_metrics）"
    )
    quality_resting_metrics_parser.add_argument(
        "--temp-dir",
        help="临时目录路径（用于存储补丁后的文件，默认：输出目录/temp_patched）",
    )
    quality_resting_metrics_parser.set_defaults(func=quality_resting_metrics)

    # quality visualize
    quality_visualize_parser = quality_subparsers.add_parser(
        "visualize", help="生成质量评估可视化图表"
    )
    quality_visualize_parser.add_argument(
        "--input", "-i", required=True, help="SNIRF文件路径"
    )
    quality_visualize_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：与输入文件相同目录）"
    )
    quality_visualize_parser.add_argument(
        "--no-heatmap", action="store_true", help="不生成通道质量热图"
    )
    quality_visualize_parser.add_argument(
        "--no-snr", action="store_true", help="不生成信噪比分布图"
    )
    quality_visualize_parser.add_argument(
        "--no-correlation", action="store_true", help="不生成HbO-HbR相关性图"
    )
    quality_visualize_parser.add_argument(
        "--dpi", type=int, default=150, help="图像分辨率（默认：150）"
    )
    quality_visualize_parser.set_defaults(func=quality_visualize)

    # quality visualize-batch
    quality_visualize_batch_parser = quality_subparsers.add_parser(
        "visualize-batch", help="批量生成质量评估可视化图表"
    )
    quality_visualize_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF文件目录路径"
    )
    quality_visualize_batch_parser.add_argument(
        "--output-dir", "-o", help="输出目录路径（默认：与输入目录相同）"
    )
    quality_visualize_batch_parser.add_argument(
        "--no-heatmap", action="store_true", help="不生成通道质量热图"
    )
    quality_visualize_batch_parser.add_argument(
        "--no-snr", action="store_true", help="不生成信噪比分布图"
    )
    quality_visualize_batch_parser.add_argument(
        "--no-correlation", action="store_true", help="不生成HbO-HbR相关性图"
    )
    quality_visualize_batch_parser.add_argument(
        "--dpi", type=int, default=150, help="图像分辨率（默认：150）"
    )
    quality_visualize_batch_parser.set_defaults(func=quality_visualize_batch)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "fnirs" and not args.fnirs_command:
        fnirs_parser.print_help()
        sys.exit(1)

    if args.command == "ecg" and not args.ecg_command:
        ecg_parser.print_help()
        sys.exit(1)

    if args.command == "eeg" and not args.eeg_command:
        eeg_parser.print_help()
        sys.exit(1)

    if args.command == "marker" and not args.marker_command:
        marker_parser.print_help()
        sys.exit(1)

    if args.command == "quality" and not args.quality_command:
        quality_parser.print_help()
        sys.exit(1)

    # Call corresponding processing function
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
