"""
Unit tests for matchcrop_aligned module
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from multichsync.marker.matchcrop_aligned import (
    calculate_aligned_time_range,
    apply_drift_correction,
    extract_taskname_from_filename,
    rename_bids_task,
)


class TestCalculateAlignedTimeRange(unittest.TestCase):
    """Test calculate_aligned_time_range function"""

    def test_with_consensus_time_range(self):
        """Test when consensus_time_range exists in metadata"""
        metadata = {
            "timeline_metadata": {"consensus_time_range": [-100.0, 500.0]},
            "device_info": [
                {"name": "device1", "time_range": [0, 400]},
                {"name": "device2", "time_range": [50, 600]},
            ],
        }

        start, end = calculate_aligned_time_range(metadata)
        self.assertEqual(start, -100.0)
        self.assertEqual(end, 500.0)

    def test_fallback_to_device_intersection(self):
        """Test fallback when no consensus_time_range"""
        metadata = {
            "timeline_metadata": {},
            "device_info": [
                {"name": "device1", "time_range": [0, 400]},
                {"name": "device2", "time_range": [50, 600]},
                {"name": "device3", "time_range": [100, 300]},
            ],
        }

        start, end = calculate_aligned_time_range(metadata)
        # Intersection: max(0, 50, 100) = 100, min(400, 600, 300) = 300
        self.assertEqual(start, 100.0)
        self.assertEqual(end, 300.0)

    def test_no_device_info_raises_error(self):
        """Test error when no device_info"""
        metadata = {"timeline_metadata": {}}

        with self.assertRaises(ValueError):
            calculate_aligned_time_range(metadata)


class TestApplyDriftCorrection(unittest.TestCase):
    """Test apply_drift_correction function"""

    def test_no_drift_returns_same(self):
        """Test when no drift params provided"""
        result = apply_drift_correction(100.0, {})
        self.assertEqual(result, 100.0)

    def test_with_offset_only(self):
        """Test drift with offset only (scale=1)"""
        drift = {"offset": 10.0, "scale": 1.0}
        result = apply_drift_correction(100.0, drift)
        self.assertEqual(result, 110.0)

    def test_with_scale_only(self):
        """Test drift with scale only (offset=0)"""
        drift = {"offset": 0.0, "scale": 2.0}
        result = apply_drift_correction(100.0, drift)
        self.assertEqual(result, 200.0)

    def test_with_full_correction(self):
        """Test full drift correction: device_time = consensus * scale + offset"""
        drift = {"offset": 50.0, "scale": 0.5}
        # 100 * 0.5 + 50 = 100
        result = apply_drift_correction(100.0, drift)
        self.assertEqual(result, 100.0)


class TestExtractTasknameFromFilename(unittest.TestCase):
    """Test extract_taskname_from_filename function"""

    def test_standard_bids_filename(self):
        """Test standard BIDS format filename"""
        filename = "sub-068_ses-01_task-rest_fnirs"
        result = extract_taskname_from_filename(filename)
        self.assertEqual(result, "rest")

    def test_with_different_task(self):
        """Test with picture task"""
        filename = "sub-068_ses-00_task-picture_eeg"
        result = extract_taskname_from_filename(filename)
        self.assertEqual(result, "picture")

    def test_no_task_in_filename(self):
        """Test when no task in filename"""
        filename = "sub-068_ses-01_fnirs"
        result = extract_taskname_from_filename(filename)
        self.assertIsNone(result)


class TestRenameBidsTask(unittest.TestCase):
    """Test rename_bids_task function"""

    def test_rename_ecg_file(self):
        """Test renaming ECG file"""
        filename = "sub-068_ses-01_task-rest_input.csv"
        result = rename_bids_task(filename, "rest", "mytask")
        self.assertEqual(result, "sub-068_ses-01_task-mytask_input.csv")

    def test_rename_fnirs_file(self):
        """Test renaming fNIRS file"""
        filename = "sub-068_ses-01_task-rest_fnirs.snirf"
        result = rename_bids_task(filename, "rest", "mytask")
        self.assertEqual(result, "sub-068_ses-01_task-mytask_fnirs.snirf")

    def test_rename_eeg_file(self):
        """Test renaming EEG file"""
        filename = "sub-068_ses-00_task-picture_eeg.vhdr"
        result = rename_bids_task(filename, "picture", "newtask")
        self.assertEqual(result, "sub-068_ses-00_task-newtask_eeg.vhdr")


if __name__ == "__main__":
    unittest.main()
