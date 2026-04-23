"""
Unit tests for adjust_offsets module
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from multichsync.marker.adjust_offsets import (
    adjust_offsets,
    generate_diff_report,
    load_and_adjust_metadata,
    parse_offset_spec,
    rebuild_timeline,
)


class TestParseOffsetSpec(unittest.TestCase):
    """Test parse_offset_spec function"""

    def test_parse_string_single_device(self):
        """Test parsing single device offset string"""
        spec = "device1:1.5"
        result = parse_offset_spec(spec)
        self.assertEqual(result, {"device1": 1.5})

    def test_parse_string_multiple_devices(self):
        """Test parsing multiple device offsets string"""
        spec = "device1:1.5,device2:-0.3,device3:0.0"
        result = parse_offset_spec(spec)
        self.assertEqual(result, {"device1": 1.5, "device2": -0.3, "device3": 0.0})

    def test_parse_string_with_spaces(self):
        """Test parsing with spaces around commas and colons"""
        spec = "device1 : 1.5 , device2 : -0.3"
        result = parse_offset_spec(spec)
        self.assertEqual(result, {"device1": 1.5, "device2": -0.3})

    def test_parse_string_invalid_format(self):
        """Test parsing invalid format raises ValueError"""
        spec = "device1=1.5"
        with self.assertRaises(ValueError):
            parse_offset_spec(spec)

    def test_parse_string_invalid_offset_value(self):
        """Test parsing invalid offset value raises ValueError"""
        spec = "device1:abc"
        with self.assertRaises(ValueError):
            parse_offset_spec(spec)

    def test_parse_json_file_dict(self):
        """Test parsing JSON file with dict format"""
        json_content = {"device1": 1.5, "device2": -0.3}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_content, f)
            json_path = f.name

        try:
            result = parse_offset_spec(json_path)
            self.assertEqual(result, {"device1": 1.5, "device2": -0.3})
        finally:
            Path(json_path).unlink()

    def test_parse_json_file_list_of_dicts(self):
        """Test parsing JSON file with list of dicts format"""
        json_content = [
            {"device": "device1", "offset": 1.5},
            {"device": "device2", "offset": -0.3},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_content, f)
            json_path = f.name

        try:
            result = parse_offset_spec(json_path)
            self.assertEqual(result, {"device1": 1.5, "device2": -0.3})
        finally:
            Path(json_path).unlink()

    def test_parse_json_file_invalid(self):
        """Test parsing invalid JSON file raises ValueError"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            json_path = f.name

        try:
            with self.assertRaises(ValueError):
                parse_offset_spec(json_path)
        finally:
            Path(json_path).unlink()


class TestLoadAndAdjustMetadata(unittest.TestCase):
    """Test load_and_adjust_metadata function"""

    def setUp(self):
        """Set up mock data for testing"""
        # Create mock metadata JSON structure
        self.mock_metadata = {
            "device_info": [
                {
                    "name": "device1",
                    "file_path": "/path/to/device1_marker.csv",
                    "drift_correction": {
                        "offset": 0.5,
                        "scale": 1.0,
                        "r_squared": 0.9,
                        "n_matches": 10,
                        "method": "theil_sen",
                    },
                },
                {
                    "name": "device2",
                    "file_path": "/path/to/device2_marker.csv",
                    "drift_correction": {
                        "offset": -0.2,
                        "scale": 1.0,
                        "r_squared": 0.8,
                        "n_matches": 8,
                        "method": "theil_sen",
                    },
                },
            ],
            "timeline_metadata": {"consensus_time_range": [0.0, 100.0]},
        }

        # Create mock DeviceInfo objects
        self.mock_device1 = MagicMock()
        self.mock_device1.name = "device1"
        self.mock_device1.timestamps_raw = np.array([1.0, 2.0, 3.0])
        self.mock_device1.drift_result = MagicMock()
        self.mock_device1.drift_result.offset = 0.5
        self.mock_device1.drift_result.scale = 1.0
        self.mock_device1.drift_result.r_squared = 0.9
        self.mock_device1.drift_result.n_matches = 10
        self.mock_device1.drift_result.method = "theil_sen"
        self.mock_device1.drift_result.to_dict.return_value = {
            "offset": 0.5,
            "scale": 1.0,
            "r_squared": 0.9,
            "n_matches": 10,
            "method": "theil_sen",
        }

        self.mock_device2 = MagicMock()
        self.mock_device2.name = "device2"
        self.mock_device2.timestamps_raw = np.array([1.5, 2.5, 3.5])
        self.mock_device2.drift_result = MagicMock()
        self.mock_device2.drift_result.offset = -0.2
        self.mock_device2.drift_result.scale = 1.0
        self.mock_device2.drift_result.r_squared = 0.8
        self.mock_device2.drift_result.n_matches = 8
        self.mock_device2.drift_result.method = "theil_sen"
        self.mock_device2.drift_result.to_dict.return_value = {
            "offset": -0.2,
            "scale": 1.0,
            "r_squared": 0.8,
            "n_matches": 8,
            "method": "theil_sen",
        }

    @patch("multichsync.marker.adjust_offsets.load_marker_csv_enhanced")
    @patch("multichsync.marker.adjust_offsets.apply_drift_correction")
    def test_load_and_adjust_replace_offsets(self, mock_apply_drift, mock_load_marker):
        """Test loading and adjusting metadata with replace offsets"""
        # Mock load_marker_csv_enhanced to return our mock devices
        mock_load_marker.side_effect = [self.mock_device1, self.mock_device2]

        # Mock apply_drift_correction to return adjusted timestamps
        mock_apply_drift.side_effect = lambda ts, drift: ts + drift.offset

        # Create temporary JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.mock_metadata, f)
            json_path = Path(f.name)

        try:
            offsets = {"device1": 1.0, "device2": 0.0}  # Replace offsets
            metadata, adjusted_devices = load_and_adjust_metadata(
                json_path, offsets, add_to_existing=False
            )

            # Check metadata is returned unchanged (except device_info updates later)
            self.assertEqual(metadata, self.mock_metadata)

            # Check adjusted devices list
            self.assertEqual(len(adjusted_devices), 2)
            self.assertEqual(adjusted_devices[0].name, "device1")
            self.assertEqual(adjusted_devices[1].name, "device2")

            # Check drift results were updated
            self.assertIsNotNone(adjusted_devices[0].drift_result)
            self.assertIsNotNone(adjusted_devices[1].drift_result)
            assert adjusted_devices[0].drift_result is not None
            assert adjusted_devices[1].drift_result is not None
            self.assertEqual(adjusted_devices[0].drift_result.offset, 1.0)  # Replaced
            self.assertEqual(adjusted_devices[1].drift_result.offset, 0.0)  # Replaced

            # Check timestamps were corrected
            self.assertTrue(hasattr(adjusted_devices[0], "timestamps_corrected"))

        finally:
            json_path.unlink()

    @patch("multichsync.marker.adjust_offsets.load_marker_csv_enhanced")
    @patch("multichsync.marker.adjust_offsets.apply_drift_correction")
    def test_load_and_adjust_add_to_existing(self, mock_apply_drift, mock_load_marker):
        """Test loading and adjusting metadata with add_to_existing=True"""
        mock_load_marker.side_effect = [self.mock_device1, self.mock_device2]
        mock_apply_drift.side_effect = lambda ts, drift: ts + drift.offset

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.mock_metadata, f)
            json_path = Path(f.name)

        try:
            offsets = {"device1": 0.5}  # Add 0.5 to existing offset
            metadata, adjusted_devices = load_and_adjust_metadata(
                json_path, offsets, add_to_existing=True
            )

            # device1 offset should be 0.5 + 0.5 = 1.0
            self.assertIsNotNone(adjusted_devices[0].drift_result)
            self.assertIsNotNone(adjusted_devices[1].drift_result)
            assert adjusted_devices[0].drift_result is not None
            assert adjusted_devices[1].drift_result is not None
            self.assertEqual(adjusted_devices[0].drift_result.offset, 1.0)
            # device2 offset unchanged (not in offsets)
            self.assertEqual(adjusted_devices[1].drift_result.offset, -0.2)

        finally:
            json_path.unlink()

    @patch("multichsync.marker.adjust_offsets.load_marker_csv_enhanced")
    def test_load_and_adjust_no_device_info(self, mock_load_marker):
        """Test loading metadata with no device_info raises ValueError"""
        metadata_no_devices: dict = {"timeline_metadata": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(metadata_no_devices, f)
            json_path = Path(f.name)

        try:
            with self.assertRaises(ValueError):
                load_and_adjust_metadata(json_path, {}, add_to_existing=False)
        finally:
            json_path.unlink()


class TestRebuildTimeline(unittest.TestCase):
    """Test rebuild_timeline function"""

    def setUp(self):
        """Set up mock devices for testing"""
        # Create mock DeviceInfo objects
        self.device1 = MagicMock()
        self.device1.name = "device1"
        self.device1.timestamps_corrected = np.array([1.0, 2.0, 3.0])
        self.device1.drift_result = MagicMock()

        self.device2 = MagicMock()
        self.device2.name = "device2"
        self.device2.timestamps_corrected = np.array([1.5, 2.5, 3.5])
        self.device2.drift_result = MagicMock()

    @patch("multichsync.marker.adjust_offsets.EnhancedTimeline")
    def test_rebuild_timeline_single_device(self, mock_timeline_class):
        """Test rebuilding timeline with single device"""
        mock_timeline = MagicMock()
        mock_timeline_class.return_value = mock_timeline

        timeline = rebuild_timeline([self.device1])

        # EnhancedTimeline should be created with first device
        mock_timeline_class.assert_called_once_with(self.device1)
        # No add_device calls for single device
        self.assertEqual(mock_timeline.add_device.call_count, 0)
        self.assertEqual(timeline, mock_timeline)

    @patch("multichsync.marker.adjust_offsets.EnhancedTimeline")
    def test_rebuild_timeline_multiple_devices(self, mock_timeline_class):
        """Test rebuilding timeline with multiple devices"""
        mock_timeline = MagicMock()
        mock_timeline_class.return_value = mock_timeline

        timeline = rebuild_timeline([self.device1, self.device2])

        # EnhancedTimeline created with first device
        mock_timeline_class.assert_called_once_with(self.device1)
        # add_device called for second device with estimate_drift=False
        mock_timeline.add_device.assert_called_once_with(
            self.device2,
            method="hungarian",
            estimate_drift=False,
            drift_method="theil_sen",
            sigma_time_s=0.75,
            max_time_diff_s=3.0,
        )
        self.assertEqual(timeline, mock_timeline)

    def test_rebuild_timeline_no_devices(self):
        """Test rebuilding timeline with no devices raises ValueError"""
        with self.assertRaises(ValueError):
            rebuild_timeline([])


class TestAdjustOffsets(unittest.TestCase):
    """Test adjust_offsets function"""

    def setUp(self):
        """Set up mock data for testing"""
        self.mock_metadata = {
            "device_info": [
                {
                    "name": "device1",
                    "file_path": "/path/to/device1_marker.csv",
                    "drift_correction": {"offset": 0.5, "scale": 1.0},
                },
                {
                    "name": "device2",
                    "file_path": "/path/to/device2_marker.csv",
                    "drift_correction": {"offset": -0.2, "scale": 1.0},
                },
            ],
            "timeline_metadata": {"consensus_time_range": [0.0, 100.0]},
        }

        # Mock DeviceInfo objects
        self.mock_device1 = MagicMock()
        self.mock_device1.name = "device1"
        self.mock_device1.timestamps_raw = np.array([1.0, 2.0, 3.0])
        self.mock_device1.drift_result = MagicMock()
        self.mock_device1.drift_result.offset = 0.5
        self.mock_device1.drift_result.scale = 1.0
        self.mock_device1.drift_result.to_dict.return_value = {
            "offset": 0.5,
            "scale": 1.0,
        }

        self.mock_device2 = MagicMock()
        self.mock_device2.name = "device2"
        self.mock_device2.timestamps_raw = np.array([1.5, 2.5, 3.5])
        self.mock_device2.drift_result = MagicMock()
        self.mock_device2.drift_result.offset = -0.2
        self.mock_device2.drift_result.scale = 1.0
        self.mock_device2.drift_result.to_dict.return_value = {
            "offset": -0.2,
            "scale": 1.0,
        }

        # Mock timeline
        self.mock_timeline = MagicMock()
        self.mock_timeline.get_merged_dataframe.return_value = pd.DataFrame(
            {"consensus_time": [1.0, 2.0, 3.0], "consensus_confidence": [1.0, 1.0, 1.0]}
        )
        self.mock_timeline.get_metadata.return_value = {
            "n_devices": 2,
            "device_names": ["device1", "device2"],
            "n_consensus_events": 3,
            "consensus_time_range": [1.0, 3.0],
        }

    @patch("multichsync.marker.adjust_offsets.load_and_adjust_metadata")
    @patch("multichsync.marker.adjust_offsets.rebuild_timeline")
    @patch("multichsync.marker.adjust_offsets.generate_diff_report")
    def test_adjust_offsets_basic(
        self, mock_diff_report, mock_rebuild_timeline, mock_load_adjust
    ):
        """Test basic adjust_offsets functionality"""
        # Mock dependencies
        mock_load_adjust.return_value = (
            self.mock_metadata,
            [self.mock_device1, self.mock_device2],
        )
        mock_rebuild_timeline.return_value = self.mock_timeline
        mock_diff_report.return_value = "Diff report content"

        # Create temporary input JSON
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.mock_metadata, f)
            json_path = Path(f.name)

        # Create temporary output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            try:
                offsets = {"device1": 1.0, "device2": 0.0}
                result = adjust_offsets(
                    json_path=json_path,
                    offsets=offsets,
                    output_dir=output_dir,
                    output_prefix="test",
                    add_to_existing=False,
                    method="hungarian",
                    sigma_time_s=0.75,
                    max_time_diff_s=3.0,
                )

                # Check load_and_adjust_metadata was called correctly
                mock_load_adjust.assert_called_once_with(json_path, offsets, False)

                # Check rebuild_timeline was called correctly
                mock_rebuild_timeline.assert_called_once_with(
                    [self.mock_device1, self.mock_device2],
                    method="hungarian",
                    sigma_time_s=0.75,
                    max_time_diff_s=3.0,
                )

                # Check output files were created
                csv_path = output_dir / "test_timeline.csv"
                json_output_path = output_dir / "test_metadata.json"
                diff_path = output_dir / "test_diff_report.txt"

                self.assertTrue(csv_path.exists())
                self.assertTrue(json_output_path.exists())
                self.assertTrue(diff_path.exists())

                # Check result dictionary
                self.assertIn("output_files", result)
                self.assertIn("adjusted_devices", result)
                self.assertIn("offsets_applied", result)
                self.assertIn("timeline_statistics", result)

                # Check diff report was generated
                mock_diff_report.assert_called_once_with(json_path, json_output_path)

            finally:
                json_path.unlink()

    @patch("multichsync.marker.adjust_offsets.load_and_adjust_metadata")
    @patch("multichsync.marker.adjust_offsets.rebuild_timeline")
    @patch("multichsync.marker.adjust_offsets.generate_diff_report")
    def test_adjust_offsets_no_diff_report(
        self, mock_diff_report, mock_rebuild_timeline, mock_load_adjust
    ):
        """Test adjust_offsets when diff report generation fails"""
        mock_load_adjust.return_value = (
            self.mock_metadata,
            [self.mock_device1, self.mock_device2],
        )
        mock_rebuild_timeline.return_value = self.mock_timeline
        mock_diff_report.return_value = None  # Simulate diff report failure

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.mock_metadata, f)
            json_path = Path(f.name)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            try:
                offsets = {"device1": 1.0}
                result = adjust_offsets(
                    json_path=json_path,
                    offsets=offsets,
                    output_dir=output_dir,
                    output_prefix="test",
                )

                # Check diff report file was not created
                diff_path = output_dir / "test_diff_report.txt"
                self.assertFalse(diff_path.exists())

                # Check result indicates no diff report
                self.assertIsNone(result["output_files"]["diff_report"])

            finally:
                json_path.unlink()


class TestGenerateDiffReport(unittest.TestCase):
    """Test generate_diff_report function"""

    def test_generate_diff_report_basic(self):
        """Test generating diff report with basic metadata"""
        original_metadata = {
            "device_info": [
                {"name": "device1", "drift_correction": {"offset": 0.5, "scale": 1.0}},
                {"name": "device2", "drift_correction": {"offset": -0.2, "scale": 1.0}},
            ],
            "timeline_metadata": {"consensus_time_range": [0.0, 100.0]},
        }

        adjusted_metadata = {
            "device_info": [
                {"name": "device1", "drift_correction": {"offset": 1.5, "scale": 1.0}},
                {"name": "device2", "drift_correction": {"offset": -0.2, "scale": 1.0}},
            ],
            "timeline_metadata": {"consensus_time_range": [0.0, 100.0]},
        }

        # Create temporary JSON files
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f1:
            json.dump(original_metadata, f1)
            original_path = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f2:
            json.dump(adjusted_metadata, f2)
            adjusted_path = Path(f2.name)

        try:
            report = generate_diff_report(original_path, adjusted_path)

            # Check report contains expected content
            self.assertIsNotNone(report)
            assert report is not None  # for mypy
            self.assertIn("Offset Adjustment Diff Report", report)
            self.assertIn("Device: device1", report)
            self.assertIn("0.500s -> 1.500s", report)
            self.assertIn("Device: device2", report)
            self.assertIn("-0.200s -> -0.200s", report)

        finally:
            original_path.unlink()
            adjusted_path.unlink()

    def test_generate_diff_report_missing_drift(self):
        """Test generating diff report with missing drift correction"""
        original_metadata = {
            "device_info": [{"name": "device1"}]  # No drift_correction
        }

        adjusted_metadata = {
            "device_info": [
                {"name": "device1", "drift_correction": {"offset": 1.0, "scale": 1.0}}
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f1:
            json.dump(original_metadata, f1)
            original_path = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f2:
            json.dump(adjusted_metadata, f2)
            adjusted_path = Path(f2.name)

        try:
            report = generate_diff_report(original_path, adjusted_path)

            self.assertIsNotNone(report)
            assert report is not None  # for mypy
            self.assertIn("Device: device1", report)
            self.assertIn("(no original) -> 1.000s", report)

        finally:
            original_path.unlink()
            adjusted_path.unlink()

    def test_generate_diff_report_json_error(self):
        """Test diff report generation when JSON parsing fails"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f1:
            f1.write("invalid json")
            original_path = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f2:
            f2.write("{}")
            adjusted_path = Path(f2.name)

        try:
            report = generate_diff_report(original_path, adjusted_path)
            # Should return None when exception occurs
            self.assertIsNone(report)
        finally:
            original_path.unlink()
            adjusted_path.unlink()


if __name__ == "__main__":
    unittest.main()
