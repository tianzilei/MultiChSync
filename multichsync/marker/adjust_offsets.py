"""
adjust_offsets: Adjust device offsets and regenerate matched timeline
Allows users to manually specify time offsets for each device and generate new matched timelines.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from .matcher import (
    DriftResult,
    DeviceInfo,
    EnhancedTimeline,
    apply_drift_correction,
    load_marker_csv_enhanced,
)


def parse_offset_spec(spec: str) -> Dict[str, float]:
    """
    Parse offset specification string into dictionary.
    
    Format: "device1:1.5,device2:-0.3" or JSON file path
    
    Parameters:
    -----------
    spec : str
        Offset specification string or path to JSON file
        
    Returns:
    --------
    Dict[str, float]: Device name -> offset mapping
    """
    offsets = {}
    
    # Check if it's a JSON file path
    if spec.endswith('.json'):
        try:
            with open(spec, 'r') as f:
                json_data = json.load(f)
                # Expect either dict or list of dicts
                if isinstance(json_data, dict):
                    offsets = {k: float(v) for k, v in json_data.items()}
                elif isinstance(json_data, list):
                    for item in json_data:
                        if isinstance(item, dict) and 'device' in item and 'offset' in item:
                            offsets[item['device']] = float(item['offset'])
                return offsets
        except Exception as e:
            raise ValueError(f"Failed to parse JSON offset file {spec}: {e}")
    
    # Parse string format: "device1:1.5,device2:-0.3"
    parts = spec.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        # Try to split by colon
        if ':' in part:
            device, offset_str = part.split(':', 1)
            device = device.strip()
            offset_str = offset_str.strip()
            
            try:
                offset = float(offset_str)
                offsets[device] = offset
            except ValueError:
                raise ValueError(f"Invalid offset value for device {device}: {offset_str}")
        else:
            raise ValueError(f"Invalid offset specification format: {part}. Expected 'device:offset'")
    
    return offsets


def load_and_adjust_metadata(
    json_path: Path,
    offsets: Dict[str, float],
    add_to_existing: bool = False
) -> Tuple[Dict, List[DeviceInfo]]:
    """
    Load existing matched_metadata.json and apply offset adjustments.
    
    Parameters:
    -----------
    json_path : Path
        Path to existing matched_metadata.json
    offsets : Dict[str, float]
        Device name -> offset mapping
    add_to_existing : bool
        If True, add offsets to existing offsets. If False, replace.
        
    Returns:
    --------
    Tuple[Dict, List[DeviceInfo]]: (updated metadata, list of adjusted DeviceInfo objects)
    """
    # Load existing metadata
    with open(json_path, 'r') as f:
        metadata = json.load(f)
    
    device_info_list = metadata.get('device_info', [])
    if not device_info_list:
        raise ValueError(f"No device_info found in {json_path}")
    
    # Get original marker files to load timestamps
    adjusted_devices = []
    
    for device_data in device_info_list:
        device_name = device_data['name']
        file_path = device_data.get('file_path')
        
        if not file_path:
            raise ValueError(f"No file_path for device {device_name}")
        
        # Load original timestamps
        device = load_marker_csv_enhanced(file_path, device_name)
        
        # Get existing drift correction
        old_drift_dict = device_data.get('drift_correction')
        if old_drift_dict:
            old_drift = DriftResult(
                offset=old_drift_dict.get('offset', 0.0),
                scale=old_drift_dict.get('scale', 1.0),
                r_squared=old_drift_dict.get('r_squared', 0.0),
                n_matches=old_drift_dict.get('n_matches', 0),
                method=old_drift_dict.get('method', 'unknown')
            )
        else:
            # Create default drift correction
            old_drift = DriftResult(
                offset=0.0,
                scale=1.0,
                r_squared=0.0,
                n_matches=0,
                method='no_correction'
            )
        
        # Calculate new offset
        if device_name in offsets:
            if add_to_existing:
                new_offset = old_drift.offset + offsets[device_name]
            else:
                new_offset = offsets[device_name]
        else:
            new_offset = old_drift.offset
        
        # Create new drift correction
        new_drift = DriftResult(
            offset=new_offset,
            scale=old_drift.scale,  # Keep scale unchanged
            r_squared=old_drift.r_squared,
            n_matches=old_drift.n_matches,
            method=old_drift.method + '_manual_adjust'
        )
        
        # Apply drift correction
        device.drift_result = new_drift
        device.timestamps_corrected = apply_drift_correction(
            device.timestamps_raw, new_drift
        )
        
        adjusted_devices.append(device)
    
    return metadata, adjusted_devices


def rebuild_timeline(
    adjusted_devices: List[DeviceInfo],
    method: str = "hungarian",
    sigma_time_s: float = 0.75,
    max_time_diff_s: float = 3.0
) -> EnhancedTimeline:
    """
    Rebuild consensus timeline using adjusted devices.
    
    Parameters:
    -----------
    adjusted_devices : List[DeviceInfo]
        List of DeviceInfo objects with adjusted offsets
    method : str
        Matching method (default: "hungarian")
    sigma_time_s : float
        Gaussian sigma for confidence calculation
    max_time_diff_s : float
        Maximum time difference for matching
        
    Returns:
    --------
    EnhancedTimeline: Rebuilt timeline with adjusted offsets
    """
    if not adjusted_devices:
        raise ValueError("No devices provided")
    
    # Use first device as reference
    timeline = EnhancedTimeline(adjusted_devices[0])
    
    # Add remaining devices without re-estimating drift
    for device in adjusted_devices[1:]:
        timeline.add_device(
            device,
            method=method,
            estimate_drift=False,  # Don't re-estimate drift
            drift_method="theil_sen",  # Not used when estimate_drift=False
            sigma_time_s=sigma_time_s,
            max_time_diff_s=max_time_diff_s
        )
    
    return timeline


def adjust_offsets(
    json_path: Path,
    offsets: Dict[str, float],
    output_dir: Path,
    output_prefix: str = "adjusted",
    add_to_existing: bool = False,
    method: str = "hungarian",
    sigma_time_s: float = 0.75,
    max_time_diff_s: float = 3.0
) -> Dict[str, Any]:
    """
    Main function: adjust offsets and generate new timeline and metadata.
    
    Parameters:
    -----------
    json_path : Path
        Path to existing matched_metadata.json
    offsets : Dict[str, float]
        Device name -> offset mapping
    output_dir : Path
        Output directory for new files
    output_prefix : str
        Prefix for output files (default: "adjusted")
    add_to_existing : bool
        If True, add offsets to existing offsets. If False, replace.
    method : str
        Matching method (default: "hungarian")
    sigma_time_s : float
        Gaussian sigma for confidence calculation
    max_time_diff_s : float
        
    Returns:
    --------
    Dict[str, Any]: Processing results including output file paths
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Adjusting offsets for devices: {list(offsets.keys())}")
    print(f"Output directory: {output_dir}")
    print(f"Add to existing: {add_to_existing}")
    
    # Load and adjust metadata
    metadata, adjusted_devices = load_and_adjust_metadata(
        json_path, offsets, add_to_existing
    )
    
    # Rebuild timeline
    print("Rebuilding consensus timeline...")
    timeline = rebuild_timeline(
        adjusted_devices,
        method=method,
        sigma_time_s=sigma_time_s,
        max_time_diff_s=max_time_diff_s
    )
    
    # Get merged DataFrame
    merged_df = timeline.get_merged_dataframe()
    
    # Save new timeline CSV
    csv_path = output_dir / f"{output_prefix}_timeline.csv"
    merged_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved new timeline to {csv_path}")
    
    # Update metadata with new drift corrections
    updated_device_info = []
    for device, adjusted_device in zip(metadata['device_info'], adjusted_devices):
        updated_info = device.copy()
        if adjusted_device.drift_result:
            updated_info['drift_correction'] = adjusted_device.drift_result.to_dict()
        updated_device_info.append(updated_info)
    
    metadata['device_info'] = updated_device_info
    
    # Update timeline metadata
    timeline_metadata = timeline.get_metadata()
    metadata['timeline_metadata'] = timeline_metadata
    
    # Add adjustment information
    metadata['adjustment_info'] = {
        'original_json': str(json_path),
        'offsets_applied': offsets,
        'add_to_existing': add_to_existing,
        'output_prefix': output_prefix,
        'adjustment_timestamp': pd.Timestamp.now().isoformat()
    }
    
    # Save new metadata JSON
    json_output_path = output_dir / f"{output_prefix}_metadata.json"
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"Saved new metadata to {json_output_path}")
    
    # Generate diff report (optional)
    diff_report = generate_diff_report(json_path, json_output_path)
    if diff_report:
        diff_path = output_dir / f"{output_prefix}_diff_report.txt"
        with open(diff_path, 'w') as f:
            f.write(diff_report)
        print(f"Saved diff report to {diff_path}")
    
    return {
        'output_files': {
            'timeline_csv': str(csv_path),
            'metadata_json': str(json_output_path),
            'diff_report': str(diff_path) if diff_report else None
        },
        'adjusted_devices': [d.name for d in adjusted_devices],
        'offsets_applied': offsets,
        'timeline_statistics': timeline_metadata
    }


def generate_diff_report(original_json: Path, adjusted_json: Path) -> Optional[str]:
    """
    Generate diff report comparing original and adjusted metadata.
    
    Parameters:
    -----------
    original_json : Path
        Path to original metadata JSON
    adjusted_json : Path
        Path to adjusted metadata JSON
        
    Returns:
    --------
    Optional[str]: Diff report text, or None if comparison fails
    """
    try:
        with open(original_json, 'r') as f:
            original = json.load(f)
        with open(adjusted_json, 'r') as f:
            adjusted = json.load(f)
        
        report_lines = ["Offset Adjustment Diff Report", "=" * 40, ""]
        
        # Compare device offsets
        original_devices = {d['name']: d for d in original.get('device_info', [])}
        adjusted_devices = {d['name']: d for d in adjusted.get('device_info', [])}
        
        for device_name in sorted(set(original_devices.keys()) | set(adjusted_devices.keys())):
            report_lines.append(f"Device: {device_name}")
            
            orig_drift = original_devices.get(device_name, {}).get('drift_correction', {})
            adj_drift = adjusted_devices.get(device_name, {}).get('drift_correction', {})
            
            if orig_drift and adj_drift:
                orig_offset = orig_drift.get('offset', 0.0)
                adj_offset = adj_drift.get('offset', 0.0)
                offset_diff = adj_offset - orig_offset
                
                report_lines.append(f"  Offset: {orig_offset:.3f}s -> {adj_offset:.3f}s (Δ={offset_diff:+.3f}s)")
                report_lines.append(f"  Scale: {orig_drift.get('scale', 1.0):.6f} -> {adj_drift.get('scale', 1.0):.6f}")
            elif adj_drift:
                report_lines.append(f"  Offset: (no original) -> {adj_drift.get('offset', 0.0):.3f}s")
            elif orig_drift:
                report_lines.append(f"  Offset: {orig_drift.get('offset', 0.0):.3f}s -> (no adjustment)")
            
            report_lines.append("")
        
        # Compare timeline ranges
        orig_range = original.get('timeline_metadata', {}).get('consensus_time_range', [0, 0])
        adj_range = adjusted.get('timeline_metadata', {}).get('consensus_time_range', [0, 0])
        
        if orig_range and adj_range:
            report_lines.append("Timeline Range Comparison:")
            report_lines.append(f"  Original: {orig_range[0]:.3f}s - {orig_range[1]:.3f}s (duration: {orig_range[1]-orig_range[0]:.3f}s)")
            report_lines.append(f"  Adjusted: {adj_range[0]:.3f}s - {adj_range[1]:.3f}s (duration: {adj_range[1]-adj_range[0]:.3f}s)")
            report_lines.append("")
        
        return "\n".join(report_lines)
    
    except Exception as e:
        print(f"Warning: Could not generate diff report: {e}")
        return None


def main():
    """Command-line entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Adjust device offsets and regenerate matched timeline"
    )
    parser.add_argument(
        "--json-path", "-j", required=True,
        help="Path to existing matched_metadata.json"
    )
    parser.add_argument(
        "--offsets", "-o", required=True,
        help="Offset specification: 'device1:1.5,device2:-0.3' or path to JSON file"
    )
    parser.add_argument(
        "--output-dir", "-d", required=True,
        help="Output directory for new files"
    )
    parser.add_argument(
        "--prefix", "-p", default="adjusted",
        help="Prefix for output files (default: adjusted)"
    )
    parser.add_argument(
        "--add", action="store_true",
        help="Add offsets to existing offsets instead of replacing"
    )
    parser.add_argument(
        "--method", "-m", default="hungarian",
        choices=["hungarian", "mincostflow", "sinkhorn"],
        help="Matching method (default: hungarian)"
    )
    parser.add_argument(
        "--sigma-time", type=float, default=0.75,
        help="Gaussian sigma for confidence calculation (default: 0.75)"
    )
    parser.add_argument(
        "--max-time-diff", type=float, default=3.0,
        help="Maximum time difference for matching (default: 3.0)"
    )
    
    args = parser.parse_args()
    
    try:
        # Parse offsets
        offsets = parse_offset_spec(args.offsets)
        
        # Run adjustment
        result = adjust_offsets(
            json_path=Path(args.json_path),
            offsets=offsets,
            output_dir=Path(args.output_dir),
            output_prefix=args.prefix,
            add_to_existing=args.add,
            method=args.method,
            sigma_time_s=args.sigma_time,
            max_time_diff_s=args.max_time_diff
        )
        
        print(f"\nAdjustment complete!")
        print(f"  Output directory: {args.output_dir}")
        print(f"  Timeline file: {result['output_files']['timeline_csv']}")
        print(f"  Metadata file: {result['output_files']['metadata_json']}")
        if result['output_files']['diff_report']:
            print(f"  Diff report: {result['output_files']['diff_report']}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()