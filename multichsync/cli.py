#!/usr/bin/env python3
"""
多模态神经影像数据转换命令行工具
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

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
    generate_timeline_figures,
    clean_marker_folder,
)
from .marker.timeline_cropper import crop_timelines_to_shortest
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
        print(f"Conversion successful: {output_path}")
    except Exception as e:
        print(f"Conversion failed: {e}")
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
        print(f"Batch conversion complete, {len(converted_files)} files total")
    except Exception as e:
        print(f"Batch conversion failed: {e}")
        sys.exit(1)


def fnirs_patch(args):
    """处理SNIRF文件MNE修复命令"""
    try:
        from multichsync.fnirs import patch_snirf_for_mne, patch_snirf_inplace

        if patch_snirf_for_mne is None:
            print("Error: MNE patch module unavailable, ensure h5py is installed")
            sys.exit(1)

        if args.inplace:
            # In-place patch
            if args.output:
                print("Warning: --inplace specified, --output will be ignored")

            patched_path = patch_snirf_inplace(
                snirf_path=args.input,
                dummy_wavelengths=args.dummy_wavelengths,
                move_hbt_to_aux=not args.no_move_hbt,
                aux_name="HbT",
            )
            print(f"In-place patch complete: {patched_path}")
        else:
            # Create new file
            patched_path = patch_snirf_for_mne(
                input_snirf=args.input,
                output_snirf=args.output,
                dummy_wavelengths=args.dummy_wavelengths,
                move_hbt_to_aux=not args.no_move_hbt,
                aux_name="HbT",
            )
            print(f"Patch complete, output file: {patched_path}")

    except Exception as e:
        print(f"Patch failed: {e}")
        sys.exit(1)


def ecg_convert(args):
    """处理ECG转换命令"""
    try:
        if args.format != "csv":
            print(f"Unsupported format: {args.format}, only csv format supported")
            sys.exit(1)

        result = convert_acq_to_csv(
            acq_path=args.acq_path,
            output_path=args.output,
            sampling_rate=args.sampling_rate,
            group_by_type=not args.no_group,
            float_format=args.float_format,
        )

        if isinstance(result, dict):
            print("Conversion successful, output files:")
            for group, path in result.items():
                print(f"  {group}: {path}")
        else:
            print(f"Conversion successful: {result}")

    except Exception as e:
        print(f"Conversion failed: {e}")
        sys.exit(1)


def ecg_batch(args):
    """处理ECG批量转换命令"""
    try:
        if args.format != "csv":
            print(f"Unsupported format: {args.format}, only csv format supported")
            sys.exit(1)

        results = batch_convert_acq_to_csv(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            sampling_rate=args.sampling_rate,
            group_by_type=not args.no_group,
            float_format=args.float_format,
        )

        print(f"Batch conversion complete, {len(results)} files total")

    except Exception as e:
        print(f"Batch conversion failed: {e}")
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
        print(f"Conversion successful: {output_path}")
        print(f"Channels: {len(raw.ch_names)}, Sampling rate: {raw.info['sfreq']} Hz")

    except Exception as e:
        print(f"Conversion failed: {e}")
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

        print(f"Batch conversion complete, {len(results)} files total")

    except Exception as e:
        print(f"Batch conversion failed: {e}")
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
                raise ValueError("Cannot auto-detect file type, use the --type parameter")

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
                raise ValueError(f"Unsupported extraction type: {extract_type}")

        print(f"Marker extraction successful: {output_path}")
        print(f"Extracted count: {len(df)}")

    except Exception as e:
        print(f"Marker extraction failed: {e}")
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
                    print(f"  [FAILED] {csv_file.name}: {e}")

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
                    print(f"  [DELETED] {csv_file.name}")
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  [FAILED] {csv_file.name}: {e}")

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
                    print(f"  [FAILED] {vmrk_file.name}: {e}")

        print(f"\nBatch marker extraction complete:")
        print(f"  fNIRS: {stats['fnirs']} files")
        print(f"  ECG:   {stats['ecg']} files")
        print(f"  EEG:   {stats['eeg']} files")
        print(f"  Failed:  {stats['failed']} files")
        print(f"  Skipped:  {stats['skipped']} files (already exist)")

    except Exception as e:
        print(f"Batch marker extraction failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_clean(args):
    """处理marker清洗命令"""
    try:
        input_path = Path(args.input)

        if not input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")

        # Determine cleaning mode
        if input_path.is_file():
            # Single file cleaning
            print(f"Cleaning single file: {input_path}")
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
            print(f"Cleaning result: {result}")

        elif input_path.is_dir():
            # Batch directory cleaning
            print(f"Batch cleaning directory: {input_path}")
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

            print(f"Cleaning complete, file statistics:")
            for status, count in summary.items():
                if count > 0:
                    print(f"  {status}: {count}")
        else:
            raise ValueError(f"Input path is neither a file nor a directory: {input_path}")

    except Exception as e:
        print(f"Marker cleaning failed: {e}")
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

        print(f"Marker info extraction complete:")
        print(f"  Input directory: {input_dir}")
        print(f"  Output directory: {output_dir}")
        print(f"  Recursive: {recursive}")
        print(f"  Reports generated:")
        print(f"    Error report: {reports['error_report']}")
        print(f"    Subject reports:")
        for subj_name, report_path in reports["subject_reports"].items():
            print(f"      Subject {subj_name}: {report_path}")

    except Exception as e:
        print(f"Marker info extraction failed: {e}")
        sys.exit(1)


def marker_timeline(args):
    """处理marker timeline可视化生成命令"""
    try:
        from pathlib import Path

        input_dir = Path(args.input_dir) if args.input_dir else Path("Data/marker/info")
        output_dir = Path(args.output_dir) if args.output_dir else Path("Data/marker/timeline")

        saved = generate_timeline_figures(
            input_dir=input_dir,
            output_dir=output_dir,
            dpi=args.dpi,
            stack=args.stack,
        )

        print(f"Timeline visualization generation complete:")
        print(f"  Input directory: {input_dir}")
        print(f"  Output directory: {output_dir}")
        print(f"  Files generated: {len(saved)}")
        print(f"  Mode: {'stack (per-device)' if args.stack else 'combined'}")
        for subj, path in sorted(saved.items()):
            print(f"    {subj}: {path.name}")

    except Exception as e:
        print(f"Timeline visualization generation failed: {e}")
        sys.exit(1)


def marker_match(args):
    """处理多设备marker匹配命令"""
    try:
        from pathlib import Path
        from multichsync.marker import match_multiple_files_enhanced

        # Get file list
        if args.input_dir:
            # Read files from directory
            input_dir = Path(args.input_dir)
            if not input_dir.exists():
                raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

            # Find CSV files
            csv_files = list(input_dir.glob("*.csv"))
            if len(csv_files) < 2:
                raise ValueError(
                    f"At least 2 CSV files required for matching, but only {len(csv_files)} found"
                )

            # Sort for consistency
            csv_files.sort()
            file_paths = [str(f) for f in csv_files]
            print(f"Loading {len(file_paths)} files from directory: {input_dir}")
        elif args.input_files:
            # Directly specify file list
            file_paths = []
            for f in args.input_files:
                p = Path(f)
                if p.exists():
                    file_paths.append(str(p))
                else:
                    raise FileNotFoundError(f"File not found: {f}")

            print(f"Loading {len(file_paths)} specified files")
        else:
            raise ValueError("Must provide --input-dir or --input-files")

        # Device name (optional)
        device_names = args.device_names if args.device_names else None

        # Output directory
        output_dir = args.output_dir if args.output_dir else "Data/matching"

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
        print(f"Matching complete!")
        print(f"  Output directory: {output_dir}")
        print(f"  Timeline CSV: {output_dir}/{args.output_prefix}_timeline.csv")
        print(f"  Metadata JSON: {output_dir}/{args.output_prefix}_metadata.json")
        print(f"  Consensus events: {results.get('n_consensus_events', 'N/A')}")
        print(f"  Total matches: {results.get('total_matches', 'N/A')}")
        mean_conf = results.get("mean_confidence", "N/A")
        print(
            f"  Mean confidence: {mean_conf if isinstance(mean_conf, str) else f'{mean_conf:.3f}'}"
        )

        # Print device statistics
        if "device_stats" in results:
            print(f"  Device statistics:")
            for stat in results["device_stats"]:
                dev_conf = stat.get("mean_confidence", "N/A")
                print(
                    f"    {stat['device']}: {stat['n_matches']} matches, confidence {dev_conf if isinstance(dev_conf, str) else f'{dev_conf:.3f}'}"
                )

        # Print drift correction
        if "drift_corrections" in results:
            print(f"  Drift correction:")
            for i, drift in enumerate(results["drift_corrections"]):
                if drift:
                    print(
                        f"    Device {i + 1}: offset {drift.get('offset', 0):.3f}s, scale {drift.get('scale', 1):.5f}, R^2={drift.get('r_squared', 0):.3f}"
                    )

    except Exception as e:
        print(f"Marker matching failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_crop(args):
    """处理timeline裁剪命令"""
    try:
        timeline_csv = Path(args.timeline_csv)
        metadata_json = Path(args.metadata_json)

        if not timeline_csv.exists():
            raise FileNotFoundError(f"Timeline CSV file not found: {timeline_csv}")
        if not metadata_json.exists():
            raise FileNotFoundError(f"Metadata JSON file not found: {metadata_json}")

        output_dir = Path(args.output_dir) if args.output_dir else timeline_csv.parent

        result = crop_timelines_to_shortest(
            timeline_csv=timeline_csv,
            metadata_json=metadata_json,
            output_dir=output_dir,
            output_prefix=args.output_prefix,
            include_metadata=not args.no_metadata,
        )

        print(f"Timeline crop complete!")
        print(f"  Reference device: {result['crop_info']['reference_device']}")
        print(
            f"  Time range: {result['crop_info']['reference_start']:.3f}s - {result['crop_info']['reference_end']:.3f}s"
        )
        print(f"  Cropped devices: {len(result['crop_info']['cropped_devices'])}")
        print(f"  Output directory: {output_dir}")
        print(f"  Output files:")
        for name, path in result["output_files"].items():
            print(f"    {name}: {path}")

    except Exception as e:
        print(f"Timeline crop failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_matchcrop(args):
    """处理matchcrop命令 - 基于对齐的时间线按session裁剪多设备数据

    支持三种模式:
      1. 批处理(--input-dir): 扫描matching目录, 按session裁剪所有subject
      2. 单subject按session(--json-path, 无start/end): 自动按session切分
      3. 传统连续裁剪(--json-path + --start-time + --end-time): 保留向后兼容
    """
    from pathlib import Path
    from multichsync.marker.matchcrop_aligned import (
        matchcrop_aligned,
        matchcrop_by_sessions,
        batch_matchcrop_from_matching_dir,
    )

    try:
        # ── Mode 1: Batch from input-dir ──────────────────────────────
        if args.input_dir:
            result = batch_matchcrop_from_matching_dir(
                matching_dir=args.input_dir,
                output_dir=args.output_dir or "Data/matchcrop",
                convert_base_dir="Data/convert",
            )
            print(f"\nBatch matchcrop complete!")
            print(f"  Subjects processed: {len(result)}")
            return

        # ── Single JSON path modes ────────────────────────────────────
        json_path = Path(args.json_path)
        if not json_path.exists():
            raise FileNotFoundError(f"Metadata JSON file not found: {json_path}")

        # ── Mode 2: Session-based (no start/end provided) ─────────────
        if args.start_time is None and args.end_time is None:
            output_dir = (
                Path(args.output_dir) if args.output_dir else
                json_path.parent.parent / "matchcrop" / json_path.stem.replace("_metadata", "")
            )
            result = matchcrop_by_sessions(
                json_path=json_path,
                output_dir=output_dir,
                convert_base_dir="Data/convert",
            )
            print(f"\nMatchCrop complete!")
            print(f"  Subject: {result.get('subject_id', '?')}")
            print(f"  Reference device: {result.get('reference_device', '?')}")
            print(f"  Task: {result.get('taskname', '?')}")
            n_ok = sum(
                1 for s in result.get("sessions", {}).values()
                for d in s.get("devices", {}).values()
                if d.get("status") == "ok"
            )
            n_err = len(result.get("errors", []))
            print(f"  Successfully cropped: {n_ok} files")
            if n_err:
                print(f"  Errors: {n_err}")
            return

        # ── Mode 3: Legacy continuous crop (start/end required) ───────
        if args.start_time is None or args.end_time is None:
            raise ValueError("--start-time and --end-time are required for continuous crop mode")

        result = matchcrop_aligned(
            json_path=json_path,
            start_time=args.start_time,
            end_time=args.end_time,
            taskname=None,
        )

        print(f"MatchCrop complete!")
        print(
            f"  Crop time range: {result['crop_time_range'][0]:.3f}s - {result['crop_time_range'][1]:.3f}s"
        )
        print(f"  Task name: {result['old_taskname']} -> {result['new_taskname']}")
        print(f"  Output directory: {result['output_dir']}")
        print(f"  Devices processed: {len(result['cropped_devices'])}")

        if result["errors"]:
            print(f"  Errors: {len(result['errors'])}")
            for err in result["errors"]:
                print(f"    - {err}")

    except Exception as e:
        print(f"MatchCrop failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def marker_manual_match(args):
    """处理manual-match命令 - 从BIDS文件直接匹配并应用手动偏移量"""
    from pathlib import Path
    import json as json_mod
    from multichsync.marker.adjust_offsets import parse_offset_list, rebuild_timeline
    from multichsync.marker.matcher import load_marker_csv_enhanced, DriftResult
    from multichsync.marker import apply_drift_correction
    
    try:
        output_dir = Path(args.output_dir) if args.output_dir else Path("Data/matching")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load marker files
        file_paths = []
        for f in args.input_files:
            p = Path(f)
            if p.exists():
                file_paths.append(str(p))
            else:
                raise FileNotFoundError(f"File not found: {f}")
        
        device_names_specified = args.device_names if args.device_names else None
        internal_method = METHOD_NAME_MAPPING.get(args.method, "hungarian")
        
        # Load devices
        devices = []
        for i, fpath in enumerate(file_paths):
            name = device_names_specified[i] if (device_names_specified and i < len(device_names_specified)) else None
            dev = load_marker_csv_enhanced(fpath, name)
            devices.append(dev)
        
        # Parse offsets
        offset_list = parse_offset_list(args.offsets)
        
        # Build device -> offset map
        if device_names_specified:
            offset_map = dict(zip(device_names_specified, offset_list))
        else:
            offset_map = {dev.name: offset_list[i] if i < len(offset_list) else 0.0 for i, dev in enumerate(devices)}
        
        # Apply offsets to each device
        adjusted_devices = []
        for dev in devices:
            offset = offset_map.get(dev.name, 0.0)
            manual_drift = DriftResult(
                offset=offset,
                scale=1.0,
                r_squared=0.0,
                n_matches=0,
                method='manual_input'
            )
            dev.drift_result = manual_drift
            dev.timestamps_corrected = apply_drift_correction(dev.timestamps_raw, manual_drift)
            adjusted_devices.append(dev)
            print(f"  Device {dev.name}: offset {offset:+.3f}s ({len(dev.timestamps_raw)} markers)")
        
        # Rebuild consensus timeline with applied offsets
        print("Rebuilding consensus timeline...")
        timeline = rebuild_timeline(
            adjusted_devices,
            method=internal_method,
            sigma_time_s=args.sigma_time,
            max_time_diff_s=args.max_time_diff
        )
        
        # Save timeline CSV
        merged_df = timeline.get_merged_dataframe()
        csv_path = output_dir / f"{args.prefix}_timeline.csv"
        merged_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"Timeline saved: {csv_path}")
        
        # Build and save metadata JSON
        timeline_meta = timeline.get_metadata()
        device_info_list = []
        for dev in adjusted_devices:
            device_info_list.append({
                "name": dev.name,
                "file_path": dev.file_path,
                "converted_data_file_path": "",
                "n_events": dev.n_events,
                "time_range": list(dev.time_range) if dev.time_range else [0.0, 0.0],
                "drift_correction": dev.drift_result.to_dict() if dev.drift_result else None,
            })
        
        metadata = {
            "algorithm": f"manual_match_{internal_method}",
            "offsets_applied": offset_map,
            "add_to_existing": args.add,
            "adjustment_timestamp": pd.Timestamp.now().isoformat(),
            "device_info": device_info_list,
            "matching_statistics": {
                "n_consensus_events": timeline_meta.get("n_matched_groups", len(merged_df)),
                "total_matches": timeline_meta.get("total_matches", 0),
                "mean_confidence": timeline_meta.get("mean_confidence", 0.0),
            },
            "timeline_metadata": timeline_meta,
            "output_files": {"timeline_csv": str(csv_path)},
        }
        
        json_path_out = output_dir / f"{args.prefix}_metadata.json"
        with open(json_path_out, 'w', encoding='utf-8') as f:
            json_mod.dump(metadata, f, indent=2, default=str)
        print(f"Metadata saved: {json_path_out}")
        
        # Print summary
        print(f"\nManual matching complete!")
        print(f"  Output directory: {output_dir}")
        print(f"  Timeline file: {csv_path}")
        print(f"  Metadata file: {json_path_out}")
        print(f"  Consensus events: {timeline_meta.get('n_matched_groups', 'N/A')}")
        print(f"  Adjusted devices: {len(adjusted_devices)}")
        for dev in adjusted_devices:
            print(f"    {dev.name}: offset {dev.drift_result.offset:+.3f}s")
        
    except Exception as e:
        print(f"Manual matching failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def marker_traversal_match(args):
    """Traversal shift-search matching handler."""
    try:
        from multichsync.marker.traversal_matcher import match_traversal_cli
        match_traversal_cli(args)
    except Exception as e:
        print(f"Traversal matching failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def marker_basematch(args):
    """Base matching handler — length-first, marker-second alignment."""
    try:
        from multichsync.marker.traversal_matcher import match_baseline_cli
        match_baseline_cli(args)
    except Exception as e:
        print(f"Base matching failed: {e}")
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

        print(f"Quality assessment complete:")
        print(f"  Output directory: {output_dir}")
        print(f"  HbO channels: {summary['n_hbo_channels']}")
        print(f"  HbR channels: {summary['n_hbr_channels']}")
        print(f"  Bad channels (pre-filter): {summary['n_bad_prefilter']}")
        print(f"  Bad channels (post-filter): {summary['n_bad_postfilter']}")
        print(f"  Pre-filter mean time SNR: {summary['Pre-filter mean time SNR (dB)']:.2f} dB")
        print(
            f"  Post-filter mean time SNR: {summary['Post-filter mean time SNR (dB)']:.2f} dB"
        )

    except Exception as e:
        print(f"Quality assessment failed: {e}")
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

        print(f"Batch quality assessment complete:")
        print(f"  Output directory: {output_dir}")
        print(f"  Files processed: {len(summary_df)}")
        print(f"  Failed files: {len(failed)}")

        if len(failed) > 0:
            print(f"  Failed file details: {output_dir / 'snirf_batch_failed.csv'}")

        print(f"  Summary file: {output_dir / 'snirf_batch_summary.csv'}")

    except Exception as e:
        print(f"Batch quality assessment failed: {e}")
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

        print(f"Quality assessment complete (with metadata write):")
        print(f"  Output directory: {output_dir}")
        print(f"  HbO channels: {summary['n_hbo_channels']}")
        print(f"  HbR channels: {summary['n_hbr_channels']}")
        print(f"  Bad channels: {summary['n_bad_channels']}")
        print(f"  Overall quality score: {summary['overall_score']:.3f}")

        if summary["metadata_written"]:
            print(f"  Metadata written to: {summary['output_snirf_file']}")
        else:
            print(f"  Warning: metadata not written")

        if summary["report_csv_file"]:
            print(f"  Single-row report CSV: {summary['report_csv_file']}")

    except Exception as e:
        print(f"Quality assessment failed: {e}")
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

        print(f"Batch quality assessment complete (with metadata write):")
        print(f"  Output directory: {output_dir}")
        print(f"  Files processed: {len(summary_df)}")
        print(f"  Failed files: {len(failed)}")

        if len(failed) > 0:
            print(f"  Failed file details: {output_dir / 'snirf_batch_failed.csv'}")

        print(f"  Summary file: {output_dir / 'snirf_batch_summary_with_metadata.csv'}")

        # Count metadata write status
        n_with_metadata = (
            summary_df["metadata_written"].sum()
            if "metadata_written" in summary_df.columns
            else 0
        )
        print(f"  Files with metadata written: {n_with_metadata}/{len(summary_df)}")

    except Exception as e:
        print(f"Batch quality assessment failed: {e}")
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

        print(f"Resting-state metrics computation complete:")
        print(f"  Input directory: {input_dir}")
        print(f"  Output directory: {output_dir}")
        print(f"  Files processed: {len(summary_df)}")
        print(f"  Failed files: {len(failed)}")

        if len(summary_df) > 0 and "mean_reliability" in summary_df.columns:
            valid_rel = summary_df["mean_reliability"].dropna()
            if len(valid_rel) > 0:
                print(f"  Mean reliability statistics:")
                print(f"    Min: {valid_rel.min():.3f}")
                print(f"    Max: {valid_rel.max():.3f}")
                print(f"    Median: {valid_rel.median():.3f}")
                print(f"    Mean: {valid_rel.mean():.3f}")

        if len(failed) > 0:
            print(f"  Failed file details: {output_dir / 'failed_files.csv'}")

        print(f"  Summary file: {output_dir / 'resting_metrics_summary.csv'}")

    except Exception as e:
        print(f"Resting-state metrics computation failed: {e}")
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

        print(f"Quality assessment visualization complete:")
        print(f"  Output directory: {output_dir}")

        for viz_type, path in results.items():
            if path:
                print(f"  {viz_type}: {path.name}")
            else:
                print(f"  {viz_type}: generation failed")

    except Exception as e:
        print(f"Quality assessment visualization failed: {e}")
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
            print(f"Warning: no quality assessment data found in {output_dir}")
            print(
                f"Please run quality assessment first: multichsync quality batch --input-dir <dir> --output-dir {output_dir}"
            )
            return

        print(f"Found {len(detail_files)} quality assessment data files")

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
                print(f"  Skipping {stem}: SNIRF file not found")
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
                    print(f"  Done: {stem}")
                else:
                    failed_files.append(stem)
                    print(f"  Failed: {stem}")

            except Exception as e:
                failed_files.append(stem)
                print(f"  Error {stem}: {e}")

        print(f"\nBatch visualization complete:")
        print(f"  Succeeded: {success_count}")
        print(f"  Failed: {len(failed_files)}")

        if failed_files:
            print(
                f"  Failed files: {', '.join(failed_files[:5])}{'...' if len(failed_files) > 5 else ''}"
            )

    except Exception as e:
        print(f"Batch visualization failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Multi-modal neuroimaging data conversion tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
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

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # fnirs subcommand
    fnirs_parser = subparsers.add_parser("fnirs", help="fNIRS operations")
    fnirs_subparsers = fnirs_parser.add_subparsers(
        dest="fnirs_command", help="fNIRS subcommands"
    )

    # fnirs convert
    convert_parser = fnirs_subparsers.add_parser("convert", help="Convert a single fNIRS file")
    convert_parser.add_argument(
        "--txt-path", "--txt", required=True, help="Path to fNIRS TXT file"
    )
    convert_parser.add_argument(
        "--src-coords", required=True, help="Path to source coordinates CSV"
    )
    convert_parser.add_argument(
        "--det-coords", required=True, help="Path to detector coordinates CSV"
    )
    convert_parser.add_argument(
        "--output", "-o", help="Output SNIRF file path (default: same name .snirf)"
    )
    convert_parser.add_argument(
        "--no-mne-patch", action="store_true", help="Disable MNE compatibility patch (default: enabled)"
    )
    convert_parser.set_defaults(func=fnirs_convert)

    # fnirs batch
    batch_parser = fnirs_subparsers.add_parser("batch", help="Batch convert fNIRS files")
    batch_parser.add_argument("--input-dir", "-i", required=True, help="Input directory path")
    batch_parser.add_argument(
        "--src-coords", required=True, help="Path to source coordinates CSV"
    )
    batch_parser.add_argument(
        "--det-coords", required=True, help="Path to detector coordinates CSV"
    )
    batch_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: input directory)"
    )
    batch_parser.add_argument(
        "--no-mne-patch", action="store_true", help="Disable MNE compatibility patch (default: enabled)"
    )
    batch_parser.set_defaults(func=fnirs_batch)

    # fnirs patch
    patch_parser = fnirs_subparsers.add_parser(
        "patch", help="Patch existing SNIRF files for MNE compatibility"
    )
    patch_parser.add_argument("--input", "-i", required=True, help="Input SNIRF file path")
    patch_parser.add_argument(
        "--output", "-o", help="Output SNIRF file path (default: input filename_mne_fixed.snirf)"
    )
    patch_parser.add_argument(
        "--inplace", action="store_true", help="Patch in-place (overwrite original)"
    )
    patch_parser.add_argument(
        "--dummy-wavelengths",
        type=float,
        nargs="+",
        default=[760.0, 850.0],
        help="Dummy wavelength values (default: 760.0 850.0)",
    )
    patch_parser.add_argument(
        "--no-move-hbt", action="store_true", help="Do not move HbT channel to aux (default: move)"
    )
    patch_parser.set_defaults(func=fnirs_patch)

    # ecg subcommand
    ecg_parser = subparsers.add_parser("ecg", help="ECG operations")
    ecg_subparsers = ecg_parser.add_subparsers(dest="ecg_command", help="ECG subcommands")

    # ecg convert
    ecg_convert_parser = ecg_subparsers.add_parser("convert", help="Convert a single ECG file")
    ecg_convert_parser.add_argument(
        "--acq-path", "--acq", required=True, help="Path to ACQ file"
    )
    ecg_convert_parser.add_argument(
        "--format",
        "-f",
        choices=["csv"],
        default="csv",
        help="Output format (only csv supported, default: csv)",
    )
    ecg_convert_parser.add_argument(
        "--output", "-o", help="Output file path (default: auto-generated)"
    )
    ecg_convert_parser.add_argument(
        "--sampling-rate",
        "-r",
        type=int,
        default=250,
        help="Target sampling rate (Hz, default: 250)",
    )
    ecg_convert_parser.add_argument(
        "--no-group", action="store_true", help="Do not group output by channel type (CSV only)"
    )
    ecg_convert_parser.add_argument(
        "--float-format", default="%.6f", help="Float format string (default: %%.6f)"
    )
    ecg_convert_parser.set_defaults(func=ecg_convert)

    # ecg batch
    ecg_batch_parser = ecg_subparsers.add_parser("batch", help="Batch convert ECG files")
    ecg_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="Input directory path"
    )
    ecg_batch_parser.add_argument(
        "--format",
        "-f",
        choices=["csv"],
        default="csv",
        help="Output format (only csv supported, default: csv)",
    )
    ecg_batch_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: auto-generated)"
    )
    ecg_batch_parser.add_argument(
        "--sampling-rate",
        "-r",
        type=int,
        default=250,
        help="Target sampling rate (Hz, default: 250)",
    )
    ecg_batch_parser.add_argument(
        "--no-group", action="store_true", help="Do not group output by channel type (CSV only)"
    )
    ecg_batch_parser.add_argument(
        "--float-format", default="%.6f", help="Float format string (default: %%.6f)"
    )
    ecg_batch_parser.set_defaults(func=ecg_batch)

    # eeg subcommand
    eeg_parser = subparsers.add_parser("eeg", help="EEG operations")
    eeg_subparsers = eeg_parser.add_subparsers(dest="eeg_command", help="EEG subcommands")

    # eeg convert
    eeg_convert_parser = eeg_subparsers.add_parser("convert", help="Convert a single EEG file")
    eeg_convert_parser.add_argument(
        "--file-path",
        "--file",
        required=True,
        help="EEG file path (supports .set, .cdt, etc.)",
    )
    eeg_convert_parser.add_argument(
        "--format",
        "-f",
        choices=["BrainVision", "EEGLAB", "EDF"],
        default="BrainVision",
        help="Output format (default: BrainVision)",
    )
    eeg_convert_parser.add_argument(
        "--output", "-o", help="Output file path (default: auto-generated)"
    )
    eeg_convert_parser.add_argument(
        "--preload", action="store_true", help="Preload data into memory"
    )
    eeg_convert_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing files"
    )
    eeg_convert_parser.add_argument(
        "--verbose", action="store_true", help="Show verbose output"
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
    eeg_batch_parser = eeg_subparsers.add_parser("batch", help="Batch convert EEG files")
    eeg_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="Input directory path"
    )
    eeg_batch_parser.add_argument(
        "--format",
        "-f",
        choices=["BrainVision", "EEGLAB", "EDF"],
        default="BrainVision",
        help="Output format (default: BrainVision)",
    )
    eeg_batch_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: auto-generated)"
    )
    eeg_batch_parser.add_argument(
        "--preload", action="store_true", help="Preload data into memory"
    )
    eeg_batch_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing files"
    )
    eeg_batch_parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    eeg_batch_parser.add_argument(
        "--recursive", "-r", action="store_true", help="Recursively search subdirectories"
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
    marker_parser = subparsers.add_parser("marker", help="Marker extraction operations")
    marker_subparsers = marker_parser.add_subparsers(
        dest="marker_command", help="Marker subcommands"
    )

    # marker extract
    marker_extract_parser = marker_subparsers.add_parser(
        "extract", help="Extract marker information"
    )
    marker_extract_parser.add_argument(
        "--input", "-i", required=True, help="Input file path"
    )
    marker_extract_parser.add_argument(
        "--output", "-o", help="Output CSV file path (default: input filename.marker.csv)"
    )
    marker_extract_parser.add_argument(
        "--type",
        choices=["biopac", "brainvision", "fnirs"],
        help="File type (optional, auto-detected from extension by default)",
    )
    marker_extract_parser.add_argument(
        "--fs", type=float, default=500, help="Biopac sampling rate (Hz, default: 500)"
    )
    marker_extract_parser.add_argument(
        "--tolerance", type=float, default=0.2, help="Biopac voltage tolerance (default: 0.2)"
    )
    marker_extract_parser.set_defaults(func=marker_extract)

    # marker batch
    marker_batch_parser = marker_subparsers.add_parser(
        "batch", help="Batch extract marker information"
    )
    marker_batch_parser.add_argument(
        "--types",
        "-t",
        help="Types to process, comma separated (default: fnirs,ecg,eeg, e.g.: fnirs,ecg)",
    )
    marker_batch_parser.add_argument(
        "--fnirs-input",
        help="fNIRS input directory (default: Data/raw/fnirs)",
    )
    marker_batch_parser.add_argument(
        "--fnirs-output",
        help="fNIRS output directory (default: Data/marker/fnirs)",
    )
    marker_batch_parser.add_argument(
        "--ecg-input",
        help="ECG input directory (default: Data/convert/ecg)",
    )
    marker_batch_parser.add_argument(
        "--ecg-output",
        help="ECG output directory (default: Data/marker/ecg)",
    )
    marker_batch_parser.add_argument(
        "--eeg-input",
        help="EEG input directory (default: Data/convert/eeg)",
    )
    marker_batch_parser.add_argument(
        "--eeg-output",
        help="EEG output directory (default: Data/marker/eeg)",
    )
    marker_batch_parser.add_argument(
        "--fs",
        type=float,
        default=500,
        help="ECG sampling rate (Hz, default: 500)",
    )
    marker_batch_parser.add_argument(
        "--tolerance",
        type=float,
        default=0.2,
        help="ECG voltage tolerance (default: 0.2)",
    )
    marker_batch_parser.add_argument(
        "--skip-existing", action="store_true", help="Skip existing output files"
    )
    marker_batch_parser.add_argument(
        "--max-files",
        type=int,
        help="Max files per type (default: all)",
    )
    marker_batch_parser.set_defaults(func=marker_batch)

    # marker clean
    marker_clean_parser = marker_subparsers.add_parser("clean", help="Clean marker files")
    marker_clean_parser.add_argument(
        "--input", "-i", required=True, help="Input file or directory path"
    )
    marker_clean_parser.add_argument(
        "--output-dir", help="Output directory path (directory mode only, default: input dir/cleaned)"
    )
    marker_clean_parser.add_argument(
        "--inplace", action="store_true", help="Clean in-place (overwrite original)"
    )
    marker_clean_parser.add_argument(
        "--time-col",
        help="Time column name (auto-detected: Time(sec)/reference_time/time/Time)",
    )
    marker_clean_parser.add_argument(
        "--min-rows", type=int, default=2, help="Minimum row count (default: 2)"
    )
    marker_clean_parser.add_argument(
        "--min-interval", type=float, default=1.0, help="Minimum time interval (seconds, default: 1.0)"
    )
    marker_clean_parser.add_argument(
        "--remove-start", action="store_true", help="Remove records where first marker time is 0"
    )
    marker_clean_parser.set_defaults(func=marker_clean)

    # marker info
    marker_info_parser = marker_subparsers.add_parser(
        "info", help="Extract marker information and generate reports"
    )
    marker_info_parser.add_argument(
        "--input-dir", "-i", help="Input directory path (default: Data/marker)"
    )
    marker_info_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: input dir/info)"
    )
    marker_info_parser.add_argument(
        "--no-recursive", action="store_true", help="Do not recursively search subdirectories (default: recursive)"
    )
    marker_info_parser.set_defaults(func=marker_info)

    # marker timeline
    marker_timeline_parser = marker_subparsers.add_parser(
        "timeline", help="Generate multi-device timeline visualization from marker info reports"
    )
    marker_timeline_parser.add_argument(
        "--input-dir", "-i", help="Input directory (with subject_*_marker_report.csv, default: Data/marker/info)"
    )
    marker_timeline_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: Data/marker/timeline)"
    )
    marker_timeline_parser.add_argument(
        "--dpi", type=int, default=150, help="Image resolution (DPI, default: 150)"
    )
    marker_timeline_parser.add_argument(
        "--stack", action="store_true",
        help="每个设备只显示一条分段timeline，各session按文件名升序首尾相接排列（默认：每个session显示独立条形）"
    )
    marker_timeline_parser.set_defaults(func=marker_timeline)

    # marker match
    marker_match_parser = marker_subparsers.add_parser(
        "match", help="Match multi-device marker events, generate consensus timeline"
    )
    input_group = marker_match_parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input-dir", help="Input directory containing CSV files")
    input_group.add_argument("--input-files", nargs="+", help="CSV file paths list, supports BIDS wildcards (e.g. *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg)")
    marker_match_parser.add_argument(
        "--device-names", nargs="+", help="Device names list (corresponding to file order)"
    )
    marker_match_parser.add_argument(
        "--output-dir",
        default="Data/matching",
        help="Output directory path (default: Data/matching)",
    )
    marker_match_parser.add_argument(
        "--output-prefix", default="matched", help="Output file prefix (default: matched)"
    )
    marker_match_parser.add_argument(
        "--method",
        choices=["hungarian", "mincostflow", "sinkhorn"],
        default="hungarian",
        help="Matching algorithm (default: hungarian, options: hungarian/mincostflow/sinkhorn)",
    )
    marker_match_parser.add_argument(
        "--max-time-diff",
        type=float,
        default=3.0,
        help="Max time difference (seconds) for matching (default: 3.0)",
    )
    marker_match_parser.add_argument(
        "--sigma-time",
        type=float,
        default=0.75,
        help="Time sigma (seconds) for confidence calculation (default: 0.75)",
    )
    marker_match_parser.add_argument(
        "--no-drift-correction", action="store_true", help="Disable drift correction (default: enabled)"
    )
    marker_match_parser.add_argument(
        "--drift-method",
        choices=["linear", "theilsen"],
        default="linear",
        help="Drift correction method (default: linear)",
    )
    marker_match_parser.add_argument(
        "--no-json", action="store_true", help="Do not save JSON metadata file (default: save)"
    )
    marker_match_parser.add_argument(
        "--no-plots", action="store_true", help="Do not generate visualization charts (default: generate)"
    )
    marker_match_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing output files"
    )
    marker_match_parser.set_defaults(func=marker_match)

    # marker crop subcommand - added to marker subparser
    marker_crop_parser = marker_subparsers.add_parser(
        "crop", help="Crop multi-device timeline to unified time range"
    )
    marker_crop_parser.add_argument(
        "--timeline-csv", "-t", required=True, help="Path to matched timeline CSV file"
    )
    marker_crop_parser.add_argument(
        "--metadata-json", "-m", required=True, help="Path to matched metadata JSON file"
    )
    marker_crop_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: same directory as timeline CSV)"
    )
    marker_crop_parser.add_argument(
        "--output-prefix", "-p", default="cropped", help="Output file prefix (default: cropped)"
    )
    marker_crop_parser.add_argument(
        "--no-metadata", action="store_true", help="Do not save cropped metadata JSON file"
    )
    marker_crop_parser.set_defaults(func=marker_crop)

    # marker matchcrop subcommand - replaces both old matchcrop and matchcrop-aligned
    marker_matchcrop_parser = marker_subparsers.add_parser(
        "matchcrop",
        help="Crop multi-device raw data by session (auto-detect taskname and reference device)",
    )
    # Input: mutually exclusive batch vs single
    input_group_mc = marker_matchcrop_parser.add_mutually_exclusive_group()
    input_group_mc.add_argument(
        "--input-dir", "-i",
        help="Matching directory path (batch mode, scans all *_metadata.json)"
    )
    input_group_mc.add_argument(
        "--json-path", "-j",
        help="Single matched_metadata.json file path (single subject mode)"
    )
    marker_matchcrop_parser.add_argument(
        "--output-dir", "-o",
        help="Output directory path (batch default: Data/matchcrop, single subject default: matching/../matchcrop/subject-{id}/)"
    )
    marker_matchcrop_parser.add_argument(
        "--stacked-csv",
        help="Stacked timeline CSV path (optional, auto-detected from metadata directory)"
    )
    marker_matchcrop_parser.add_argument(
        "--start-time",
        "-s",
        type=float,
        default=None,
        help="裁剪起始时间（共识时间轴，不指定时自动按session切分）",
    )
    marker_matchcrop_parser.add_argument(
        "--end-time",
        "-e",
        type=float,
        default=None,
        help="裁剪结束时间（共识时间轴，不指定时自动按session切分）",
    )
    marker_matchcrop_parser.set_defaults(func=marker_matchcrop)

    # marker manual-match subcommand - added to marker subparser
    marker_manual_match_parser = marker_subparsers.add_parser(
        "manual-match",
        help="Match directly from BIDS files and apply manual offsets"
    )
    marker_manual_match_parser.add_argument(
        "--input-files", nargs="+", required=True,
        help="CSV file paths list, supports BIDS wildcards (e.g. *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg), match directly and apply offsets"
    )
    marker_manual_match_parser.add_argument(
        "--offsets", "-o", required=True,
        help="Offset list (based on file order): e.g. '[1.5, -0.3]' or JSON file path"
    )
    marker_manual_match_parser.add_argument(
        "--device-names", nargs="+",
        help="Device names list (corresponding to --input-files order)"
    )
    marker_manual_match_parser.add_argument(
        "--output-dir",
        default="Data/matching",
        help="Output directory path (default: Data/matching)"
    )
    marker_manual_match_parser.add_argument(
        "--prefix", "-p", default="manual",
        help="Output file prefix (default: manual)"
    )
    marker_manual_match_parser.add_argument(
        "--add", action="store_true",
        help="Add offsets to existing offsets instead of replacing"
    )
    marker_manual_match_parser.add_argument(
        "--method", "-m", default="hungarian",
        choices=["hungarian", "mincostflow", "sinkhorn"],
        help="Matching method (default: hungarian)"
    )
    marker_manual_match_parser.add_argument(
        "--sigma-time", type=float, default=0.75,
        help="Gaussian sigma for confidence calculation (default: 0.75)"
    )
    marker_manual_match_parser.add_argument(
        "--max-time-diff", type=float, default=3.0,
        help="Max matching time difference (s, default: 3.0)"
    )
    marker_manual_match_parser.set_defaults(func=marker_manual_match)

    # marker traversal-match
    marker_traversal_parser = marker_subparsers.add_parser(
        "traversal-match",
        help="Brute-force shift traversal matching to minimise mean per-marker distance"
    )
    input_group_trav = marker_traversal_parser.add_mutually_exclusive_group(required=True)
    input_group_trav.add_argument(
        "--info-dir",
        help="Directory containing subject_*_marker_report.csv (output of `marker info`).  "
             "Enables stacked-timeline matching: sessions per device are concatenated with "
             "time offsets, the longest-duration device is the reference (±10 s tolerance), "
             "and each shorter device is matched via iterative shift refinement."
    )
    input_group_trav.add_argument(
        "--input-dir",
        help="Directory containing marker CSV files (legacy mode)"
    )
    input_group_trav.add_argument(
        "--input-files",
        nargs="+",
        help="Explicit list of marker CSV file paths, supports BIDS wildcards (e.g. *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg) (legacy mode)"
    )
    marker_traversal_parser.add_argument(
        "--device-names",
        nargs="+",
        help="Device names matching the order of --input-files (legacy mode)"
    )
    marker_traversal_parser.add_argument(
        "--marker-base-dir",
        default="Data/marker",
        help="Marker CSV base directory, used with --info-dir (default: Data/marker)"
    )
    marker_traversal_parser.add_argument(
        "--convert-base-dir",
        default="Data/convert",
        help="Converted data base directory, used with --info-dir (default: Data/convert)"
    )
    marker_traversal_parser.add_argument(
        "--output-dir",
        default="Data/matching",
        help="Output directory (default: Data/matching)"
    )
    marker_traversal_parser.add_argument(
        "--output-prefix",
        help="Output file prefix (default: filename or 'traversal_matched')"
    )
    marker_traversal_parser.add_argument(
        "--max-time-diff",
        type=float,
        default=10.0,
        help="Max time difference (s) for a valid match; also sets the ± tolerance "
             "for the reference duration window (default: 10.0)"
    )
    marker_traversal_parser.add_argument(
        "--gap-penalty",
        type=float,
        default=1e6,
        help="Penalty cost for gaps (default: 1e6)"
    )
    marker_traversal_parser.add_argument(
        "--random-restarts",
        type=int,
        default=5,
        help="Random restarts for robustness (default: 5)"
    )
    marker_traversal_parser.add_argument(
        "--rng-seed",
        type=int,
        default=42,
        help="Random seed (default: 42)"
    )
    marker_traversal_parser.add_argument(
        "--no-json",
        action="store_true",
        help="Skip saving metadata JSON"
    )
    marker_traversal_parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip saving timeline CSV"
    )
    marker_traversal_parser.add_argument(
        "--no-fig",
        action="store_true",
        help="Skip saving matched timeline figure (PNG)"
    )
    marker_traversal_parser.add_argument(
        "--no-merge-sessions",
        action="store_true",
        help="Disable session merging; treat each file as a separate device (legacy mode, default: merge sessions per device type)"
    )
    marker_traversal_parser.set_defaults(func=marker_traversal_match)

    # marker basematch
    marker_basematch_parser = marker_subparsers.add_parser(
        "basematch",
        help="Match markers by session-length alignment first, then by markers. "
             "Groups sessions across devices to align start/end times, distributes "
             "duration differences as gaps between sessions, then fine-tunes middle "
             "sessions with traversal search."
    )
    bg = marker_basematch_parser.add_mutually_exclusive_group(required=True)
    bg.add_argument(
        "--info-dir",
        help="Directory containing subject_*_marker_report.csv (output of `marker info`)."
    )
    bg.add_argument(
        "--input-dir",
        help="Directory containing marker CSV files"
    )
    bg.add_argument(
        "--input-files",
        nargs="+",
        help="Explicit list of marker CSV file paths"
    )
    marker_basematch_parser.add_argument(
        "--device-names", nargs="+",
        help="Device names matching the order of --input-files"
    )
    marker_basematch_parser.add_argument(
        "--marker-base-dir", default="Data/marker",
        help="Marker CSV base directory, used with --info-dir (default: Data/marker)"
    )
    marker_basematch_parser.add_argument(
        "--convert-base-dir", default="Data/convert",
        help="Converted data base directory, used with --info-dir (default: Data/convert)"
    )
    marker_basematch_parser.add_argument(
        "--output-dir", default="Data/matching",
        help="Output directory (default: Data/matching)"
    )
    marker_basematch_parser.add_argument(
        "--output-prefix", default="basematched",
        help="Output file prefix (default: basematched)"
    )
    marker_basematch_parser.add_argument(
        "--max-time-diff", type=float, default=10.0,
        help="Max time difference (s) for a valid match (default: 10.0)"
    )
    marker_basematch_parser.add_argument(
        "--gap-penalty", type=float, default=1e6,
        help="Penalty cost for gaps (default: 1e6)"
    )
    marker_basematch_parser.add_argument(
        "--rng-seed", type=int, default=42,
        help="Random seed (default: 42)"
    )
    marker_basematch_parser.add_argument(
        "--no-json", action="store_true",
        help="Skip saving metadata JSON"
    )
    marker_basematch_parser.add_argument(
        "--no-csv", action="store_true",
        help="Skip saving timeline CSV"
    )
    marker_basematch_parser.add_argument(
        "--no-fig", action="store_true",
        help="Skip saving matched timeline figure"
    )
    marker_basematch_parser.set_defaults(func=marker_basematch)

    # quality subcommand
    quality_parser = subparsers.add_parser("quality", help="fNIRS data quality assessment operations")
    quality_subparsers = quality_parser.add_subparsers(
        dest="quality_command", help="Quality subcommands"
    )

    # quality assess
    quality_assess_parser = quality_subparsers.add_parser(
        "assess", help="Assess quality of a single SNIRF file"
    )
    quality_assess_parser.add_argument(
        "--input", "-i", required=True, help="SNIRF file path"
    )
    quality_assess_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: input file directory/quality)"
    )
    quality_assess_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="Low-pass filter frequency (Hz, default: 0.01)"
    )
    quality_assess_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="High-pass filter frequency (Hz, default: 0.2)"
    )
    quality_assess_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="Resampling frequency (Hz, default: 4.0, set to 0 to disable resampling)",
    )
    quality_assess_parser.add_argument(
        "--no-tddr", action="store_true", help="Disable TDDR (default: enabled)"
    )
    quality_assess_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="Signal band lower limit (Hz, default: 0.01)",
    )
    quality_assess_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="Signal band upper limit (Hz, default: 0.2)",
    )
    quality_assess_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="Noise band lower limit (Hz, default: 0.2)",
    )
    quality_assess_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="Noise band upper limit (Hz, default: 0.5)",
    )
    quality_assess_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="Disable signal-level comprehensive quality assessment (default: enabled)",
    )
    quality_assess_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="Experimental paradigm (default: resting)",
    )
    quality_assess_parser.set_defaults(func=quality_assess)

    # quality batch
    quality_batch_parser = quality_subparsers.add_parser(
        "batch", help="Batch assess SNIRF file quality"
    )
    quality_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF file directory path"
    )
    quality_batch_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: input directory/quality)"
    )
    quality_batch_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="Low-pass filter frequency (Hz, default: 0.01)"
    )
    quality_batch_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="High-pass filter frequency (Hz, default: 0.2)"
    )
    quality_batch_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="Resampling frequency (Hz, default: 4.0, set to 0 to disable resampling)",
    )
    quality_batch_parser.add_argument(
        "--no-tddr", action="store_true", help="Disable TDDR (default: enabled)"
    )
    quality_batch_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="Signal band lower limit (Hz, default: 0.01)",
    )
    quality_batch_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="Signal band upper limit (Hz, default: 0.2)",
    )
    quality_batch_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="Noise band lower limit (Hz, default: 0.2)",
    )
    quality_batch_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="Noise band upper limit (Hz, default: 0.5)",
    )
    quality_batch_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="Disable signal-level comprehensive quality assessment (default: enabled)",
    )
    quality_batch_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="Experimental paradigm (default: resting)",
    )
    quality_batch_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing output files"
    )
    quality_batch_parser.set_defaults(func=quality_batch)

    # quality assess-with-metadata
    quality_assess_metadata_parser = quality_subparsers.add_parser(
        "assess-with-metadata", help="Assess single SNIRF file quality and write results to metadata"
    )
    quality_assess_metadata_parser.add_argument(
        "--input", "-i", required=True, help="SNIRF file path"
    )
    quality_assess_metadata_parser.add_argument(
        "--output-dir",
        "-o",
        help="Output directory path (default: input file directory/quality_with_metadata)",
    )
    quality_assess_metadata_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="Low-pass filter frequency (Hz, default: 0.01)"
    )
    quality_assess_metadata_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="High-pass filter frequency (Hz, default: 0.2)"
    )
    quality_assess_metadata_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="Resampling frequency (Hz, default: 4.0, set to 0 to disable resampling)",
    )
    quality_assess_metadata_parser.add_argument(
        "--no-tddr", action="store_true", help="Disable TDDR (default: enabled)"
    )
    quality_assess_metadata_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="Signal band lower limit (Hz, default: 0.01)",
    )
    quality_assess_metadata_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="Signal band upper limit (Hz, default: 0.2)",
    )
    quality_assess_metadata_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="Noise band lower limit (Hz, default: 0.2)",
    )
    quality_assess_metadata_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="Noise band upper limit (Hz, default: 0.5)",
    )
    quality_assess_metadata_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="Disable signal-level comprehensive quality assessment (default: enabled)",
    )
    quality_assess_metadata_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="Experimental paradigm (default: resting)",
    )
    quality_assess_metadata_parser.add_argument(
        "--no-metadata", action="store_true", help="Do not write metadata to SNIRF file (default: write)"
    )
    quality_assess_metadata_parser.add_argument(
        "--output-snirf", help="Output SNIRF file path (default: auto-generated _processed.snirf)"
    )
    quality_assess_metadata_parser.add_argument(
        "--no-report-csv", action="store_true", help="Do not generate single-row CSV report (default: generate)"
    )
    quality_assess_metadata_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing output files"
    )
    quality_assess_metadata_parser.set_defaults(func=quality_assess_with_metadata)

    # quality batch-with-metadata
    quality_batch_metadata_parser = quality_subparsers.add_parser(
        "batch-with-metadata", help="Batch assess SNIRF file quality and write results to metadata"
    )
    quality_batch_metadata_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF file directory path"
    )
    quality_batch_metadata_parser.add_argument(
        "--output-dir",
        "-o",
        help="Output directory path (default: input directory/quality_with_metadata)",
    )
    quality_batch_metadata_parser.add_argument(
        "--l-freq", type=float, default=0.01, help="Low-pass filter frequency (Hz, default: 0.01)"
    )
    quality_batch_metadata_parser.add_argument(
        "--h-freq", type=float, default=0.2, help="High-pass filter frequency (Hz, default: 0.2)"
    )
    quality_batch_metadata_parser.add_argument(
        "--resample-sfreq",
        type=float,
        default=4.0,
        help="Resampling frequency (Hz, default: 4.0, set to 0 to disable resampling)",
    )
    quality_batch_metadata_parser.add_argument(
        "--no-tddr", action="store_true", help="Disable TDDR (default: enabled)"
    )
    quality_batch_metadata_parser.add_argument(
        "--signal-band-min",
        type=float,
        default=0.01,
        help="Signal band lower limit (Hz, default: 0.01)",
    )
    quality_batch_metadata_parser.add_argument(
        "--signal-band-max",
        type=float,
        default=0.2,
        help="Signal band upper limit (Hz, default: 0.2)",
    )
    quality_batch_metadata_parser.add_argument(
        "--noise-band-min",
        type=float,
        default=0.2,
        help="Noise band lower limit (Hz, default: 0.2)",
    )
    quality_batch_metadata_parser.add_argument(
        "--noise-band-max",
        type=float,
        default=0.5,
        help="Noise band upper limit (Hz, default: 0.5)",
    )
    quality_batch_metadata_parser.add_argument(
        "--no-comprehensive",
        action="store_true",
        help="Disable signal-level comprehensive quality assessment (default: enabled)",
    )
    quality_batch_metadata_parser.add_argument(
        "--paradigm",
        choices=["task", "resting"],
        default="resting",
        help="Experimental paradigm (default: resting)",
    )
    quality_batch_metadata_parser.add_argument(
        "--no-metadata", action="store_true", help="Do not write metadata to SNIRF file (default: write)"
    )
    quality_batch_metadata_parser.add_argument(
        "--no-report-csv", action="store_true", help="Do not generate single-row CSV report (default: generate)"
    )
    quality_batch_metadata_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing output files"
    )
    quality_batch_metadata_parser.set_defaults(func=quality_batch_with_metadata)

    # quality resting-metrics
    quality_resting_metrics_parser = quality_subparsers.add_parser(
        "resting-metrics", help="Batch compute resting-state metrics for fNIRS files"
    )
    quality_resting_metrics_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF file directory path"
    )
    quality_resting_metrics_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: input dir/resting_metrics)"
    )
    quality_resting_metrics_parser.add_argument(
        "--temp-dir",
        help="Temporary directory (for storing patched files, default: output dir/temp_patched)",
    )
    quality_resting_metrics_parser.set_defaults(func=quality_resting_metrics)

    # quality visualize
    quality_visualize_parser = quality_subparsers.add_parser(
        "visualize", help="Generate quality assessment visualization charts"
    )
    quality_visualize_parser.add_argument(
        "--input", "-i", required=True, help="SNIRF file path"
    )
    quality_visualize_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: same directory as input file)"
    )
    quality_visualize_parser.add_argument(
        "--no-heatmap", action="store_true", help="Do not generate channel quality heatmap"
    )
    quality_visualize_parser.add_argument(
        "--no-snr", action="store_true", help="Do not generate SNR distribution plot"
    )
    quality_visualize_parser.add_argument(
        "--no-correlation", action="store_true", help="Do not generate HbO-HbR correlation plot"
    )
    quality_visualize_parser.add_argument(
        "--dpi", type=int, default=150, help="Image resolution (DPI, default: 150)"
    )
    quality_visualize_parser.set_defaults(func=quality_visualize)

    # quality visualize-batch
    quality_visualize_batch_parser = quality_subparsers.add_parser(
        "visualize-batch", help="批量Generate quality assessment visualization charts"
    )
    quality_visualize_batch_parser.add_argument(
        "--input-dir", "-i", required=True, help="SNIRF file directory path"
    )
    quality_visualize_batch_parser.add_argument(
        "--output-dir", "-o", help="Output directory path (default: same as input directory)"
    )
    quality_visualize_batch_parser.add_argument(
        "--no-heatmap", action="store_true", help="Do not generate channel quality heatmap"
    )
    quality_visualize_batch_parser.add_argument(
        "--no-snr", action="store_true", help="Do not generate SNR distribution plot"
    )
    quality_visualize_batch_parser.add_argument(
        "--no-correlation", action="store_true", help="Do not generate HbO-HbR correlation plot"
    )
    quality_visualize_batch_parser.add_argument(
        "--dpi", type=int, default=150, help="Image resolution (DPI, default: 150)"
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
