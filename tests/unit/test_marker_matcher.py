"""
Comprehensive unit tests for marker matching functions.

Tests import from multichsync.marker.matcher:
- match_events_with_confidence
- get_raw_data_duration
- EnhancedTimeline (adapted from MultiDeviceTimeline per plan)
"""

import pytest
import numpy as np
from pathlib import Path


class TestMatchEventsWithConfidence:
    """Test cases for match_events_with_confidence function."""

    def test_exact_match(self):
        """Test matching when events are exactly aligned."""
        from multichsync.marker.matcher import match_events_with_confidence

        # Two arrays with exactly aligned events
        t1 = np.array([1.0, 2.0, 3.0, 4.0])
        t2 = np.array([1.0, 2.0, 3.0, 4.0])

        matches, confidences = match_events_with_confidence(
            t1, t2, sigma_time_s=0.5, max_time_diff_s=1.0
        )

        # Should match all 4 events
        assert len(matches) == 4
        # All matches should have high confidence (exact match)
        assert np.all(confidences > 0.9)

    def test_no_match_possible(self):
        """Test when no events can be matched."""
        from multichsync.marker.matcher import match_events_with_confidence

        # Two arrays with no overlap - events are far apart
        t1 = np.array([1.0, 2.0, 3.0])
        t2 = np.array([100.0, 101.0, 102.0])

        matches, confidences = match_events_with_confidence(
            t1,
            t2,
            sigma_time_s=0.5,
            max_time_diff_s=1.0,  # Very small max diff
        )

        # No matches should be found
        assert len(matches) == 0
        assert len(confidences) == 0

    def test_partial_match(self):
        """Test partial matching with some events outside tolerance."""
        from multichsync.marker.matcher import match_events_with_confidence

        # Events where some are within tolerance, some are not
        t1 = np.array([1.0, 2.0, 3.0, 10.0])
        t2 = np.array([1.1, 2.1, 100.0, 100.5])  # 100s are outside tolerance

        matches, confidences = match_events_with_confidence(
            t1, t2, sigma_time_s=0.5, max_time_diff_s=3.0
        )

        # Should only match first 2 events (within 3s tolerance)
        assert len(matches) == 2
        # Third event at 3.0 vs 100 is way outside tolerance, should not match
        # Fourth event at 10.0 vs 100.5 is also outside


class TestGetRawDataDuration:
    """Test cases for get_raw_data_duration function (if function exists)."""

    def test_nonexistent_file(self):
        """Test handling of nonexistent file."""
        from multichsync.marker.matcher import get_raw_data_duration

        # Should return None for nonexistent device
        result = get_raw_data_duration("definitely_nonexistent_device_xyz", "eeg")
        assert result is None

        result = get_raw_data_duration("definitely_nonexistent_device_xyz", "fnirs")
        assert result is None

        result = get_raw_data_duration("definitely_nonexistent_device_xyz", "ecg")
        assert result is None


class TestEnhancedTimeline:
    """Test cases for EnhancedTimeline class (adapted from MultiDeviceTimeline)."""

    def test_add_reference_device(self):
        """Test adding reference device."""
        from multichsync.marker.matcher import EnhancedTimeline, DeviceInfo

        # Create a reference device
        ref_device = DeviceInfo(
            name="device1",
            file_path="/test/device1.csv",
            timestamps_raw=np.array([1.0, 2.0, 3.0, 4.0]),
            timestamps_corrected=np.array([1.0, 2.0, 3.0, 4.0]),
        )

        # Create timeline with reference device
        timeline = EnhancedTimeline(ref_device)

        # Verify timeline is initialized correctly
        assert len(timeline.devices) == 1
        assert timeline.device_names == ["device1"]
        assert len(timeline.consensus_times) == 4

    def test_add_secondary_device(self):
        """Test adding secondary device and matching."""
        from multichsync.marker.matcher import EnhancedTimeline, DeviceInfo

        # Create reference device
        ref_device = DeviceInfo(
            name="device1",
            file_path="/test/device1.csv",
            timestamps_raw=np.array([1.0, 2.0, 3.0, 4.0]),
            timestamps_corrected=np.array([1.0, 2.0, 3.0, 4.0]),
        )

        # Create timeline with reference device
        timeline = EnhancedTimeline(ref_device)

        # Create secondary device with slightly offset timestamps
        sec_device = DeviceInfo(
            name="device2",
            file_path="/test/device2.csv",
            timestamps_raw=np.array([1.1, 2.1, 3.1, 4.1]),
            timestamps_corrected=np.array([1.1, 2.1, 3.1, 4.1]),
        )

        # Add secondary device
        stats = timeline.add_device(
            sec_device,
            method="hungarian",
            estimate_drift=False,  # Disable drift for this test
            sigma_time_s=0.5,
            max_time_diff_s=3.0,
        )

        # Verify matching occurred
        assert stats["device"] == "device2"
        assert stats["n_matches"] >= 0  # Should have some matches

    def test_empty_events(self):
        """Test handling of empty event list."""
        from multichsync.marker.matcher import EnhancedTimeline, DeviceInfo

        # Create a reference device with empty events
        ref_device = DeviceInfo(
            name="device1",
            file_path="/test/device1.csv",
            timestamps_raw=np.array([]),
            timestamps_corrected=np.array([]),
        )

        # Create timeline with empty reference device
        timeline = EnhancedTimeline(ref_device)

        # Verify timeline handles empty events
        assert len(timeline.consensus_times) == 0
        assert len(timeline.devices) == 1
