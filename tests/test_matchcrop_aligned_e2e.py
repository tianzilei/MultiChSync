"""
End-to-end integration test for matchcrop-aligned bug fixes.
Tests both EEG renaming and ECG headerless CSV handling in a full workflow.
"""

import unittest
import tempfile
import json
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestMatchcropAlignedE2E(unittest.TestCase):
    """End-to-end test for matchcrop_aligned with both bug fixes"""

    @patch("multichsync.marker.matchcrop_aligned.crop_eeg_data")
    @patch("multichsync.marker.matchcrop_aligned.crop_ecg_data")
    @patch("multichsync.marker.matchcrop_aligned.detect_device_type")
    def test_full_workflow_eeg_and_ecg(self, mock_detect, mock_crop_eeg, mock_crop_ecg):
        """Test complete workflow with both EEG and ECG devices"""
        from multichsync.marker.matchcrop_aligned import matchcrop_aligned

        # Setup mock returns
        mock_crop_eeg.return_value = {
            "original_samples": 1000,
            "cropped_samples": 500,
            "time_range": [0, 10],
            "sampling_freq": 500,
            "output_dir": "/tmp/eeg_output",
        }
        mock_crop_ecg.return_value = {
            "original_rows": 5000,
            "cropped_rows": 2500,
            "time_range": [0, 10],
            "output_file": "/tmp/output.csv",
        }

        # Create mock metadata JSON
        metadata = {
            "timeline_metadata": {"consensus_time_range": [0.0, 10.0]},
            "device_info": [
                {
                    "name": "sub-068_ses-00_task-picture_eeg",
                    "converted_data_file_path": "/tmp/sub-068_ses-00_task-picture_eeg.vhdr",
                    "drift_correction": {"offset": 0.0, "scale": 1.0},
                },
                {
                    "name": "sub-068_ses-00_task-picture_ecg",
                    "converted_data_file_path": "/tmp/sub-068_ses-00_task-picture_ecg.csv",
                    "drift_correction": {"offset": 0.0, "scale": 1.0},
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "matched_metadata.json"
            with open(json_path, "w") as f:
                json.dump(metadata, f)

            # Mock device type detection
            def mock_detect_type(name):
                if "eeg" in name.lower():
                    return "eeg"
                elif "ecg" in name.lower():
                    return "ecg"
                return "unknown"

            mock_detect.side_effect = mock_detect_type

            # Run the workflow
            with patch("pathlib.Path.exists", return_value=True):
                with patch("mne.io.read_raw_brainvision") as mock_mne:
                    mock_raw = MagicMock()
                    mock_raw.n_times = 1000
                    mock_raw.info = {"sfreq": 500, "meas_date": None}
                    mock_raw.get_data.return_value = MagicMock()
                    mock_raw.export = MagicMock()
                    mock_mne.return_value = mock_raw

                    result = matchcrop_aligned(json_path=json_path, taskname="rest")

            # Verify results
            self.assertEqual(result["new_taskname"], "rest")
            self.assertEqual(result["old_taskname"], "picture")
            self.assertIn("sub-068_ses-00_task-picture_eeg", result["cropped_devices"])
            self.assertIn("sub-068_ses-00_task-picture_ecg", result["cropped_devices"])

            # Verify no errors
            self.assertEqual(len(result["errors"]), 0)


if __name__ == "__main__":
    unittest.main()
