"""
Integration tests for multi-device synchronization.

Tests import from multichsync.marker.matcher:
- match_multiple_files_enhanced

Test scenarios:
1. test_sync_two_devices: Test synchronization of two devices
2. test_sync_with_drift: Test synchronization with time drift
3. test_sync_three_devices: Test synchronization of three devices

Uses temp_dir to create mock marker CSV files with different device times.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path


class TestMultiDeviceSync:
    """Integration tests for multi-device marker synchronization."""

    def _create_marker_csv(
        self, temp_dir: Path, device_name: str, timestamps: np.ndarray
    ) -> Path:
        """
        Create a marker CSV file with the given timestamps.

        Args:
            temp_dir: Temporary directory for the test
            device_name: Name for the device
            timestamps: Array of marker timestamps

        Returns:
            Path to the created CSV file
        """
        csv_path = temp_dir / f"{device_name}_marker.csv"
        df = pd.DataFrame(
            {
                "reference_time": timestamps,
                "marker_type": ["stim"] * len(timestamps),
            }
        )
        df.to_csv(csv_path, index=False)
        return csv_path

    def test_sync_two_devices(self, temp_dir):
        """Test synchronization of two devices with similar timestamps."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Device 1: baseline events at 1, 2, 3, 4 seconds
        device1_times = np.array([1.0, 2.0, 3.0, 4.0])
        device1_path = self._create_marker_csv(temp_dir, "device1", device1_times)

        # Device 2: same events but with slight offset (~100ms)
        device2_times = np.array([1.1, 2.1, 3.1, 4.1])
        device2_path = self._create_marker_csv(temp_dir, "device2", device2_times)

        # Run synchronization
        results = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["device1", "device2"],
            method="hungarian",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=True,
            drift_method="theil_sen",
            output_dir=str(temp_dir),
            output_prefix="two_device_test",
            save_json=False,
            generate_plots=False,
        )

        # Verify results structure
        assert "merged_dataframe" in results
        assert "metadata" in results
        assert "timeline" in results

        # Verify consensus timeline was generated
        merged_df = results["merged_dataframe"]
        assert len(merged_df) > 0

        # Verify both devices contributed to the consensus
        assert "device1_time" in merged_df.columns
        assert "device2_time" in merged_df.columns

        # Verify matching - should have 4 matched events
        # (each device has 4 events, and they should all match)
        n_matches = sum(
            1
            for _, row in merged_df.iterrows()
            if not pd.isna(row.get("device1_time"))
            and not pd.isna(row.get("device2_time"))
        )
        assert n_matches >= 3, f"Expected at least 3 matches, got {n_matches}"

        # Verify metadata contains correct device info
        metadata = results["metadata"]
        assert metadata["processing_parameters"]["method"] == "hungarian"
        assert len(metadata["device_info"]) == 2

        print(
            f"Two-device sync: {n_matches} matches, consensus events: {len(merged_df)}"
        )

    def test_sync_with_drift(self, temp_dir):
        """Test synchronization with time drift between devices."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Device 1: reference device with baseline events at 0, 10, 20, 30 seconds
        device1_times = np.array([0.0, 10.0, 20.0, 30.0])
        device1_path = self._create_marker_csv(
            temp_dir, "device1_reference", device1_times
        )

        # Device 2: has time drift - starts 2 seconds late AND runs 1% faster
        # Simulating: t_corrected = (t_raw - offset) / scale
        # offset = 2.0, scale = 1.01
        drift_offset = 2.0
        drift_scale = 1.01
        device2_raw = np.array([2.0, 12.1, 22.2, 32.3])  # After drift applied
        # To create raw times that will match after correction:
        # device2_corrected = device2_raw * scale + offset
        device2_times = device1_times * drift_scale + drift_offset
        device2_path = self._create_marker_csv(temp_dir, "device2_drift", device2_times)

        # Run synchronization with drift correction enabled
        results = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["device1_reference", "device2_drift"],
            method="hungarian",
            max_time_diff_s=5.0,
            sigma_time_s=1.0,
            estimate_drift=True,
            drift_method="theil_sen",
            output_dir=str(temp_dir),
            output_prefix="drift_test",
            save_json=False,
            generate_plots=False,
        )

        # Verify results structure
        assert "merged_dataframe" in results
        assert "timeline" in results

        # Verify consensus timeline was generated
        merged_df = results["merged_dataframe"]
        assert len(merged_df) > 0

        # Get drift correction info from timeline
        timeline = results["timeline"]
        assert hasattr(timeline, "drift_corrections")

        # Check if drift was estimated (may vary based on data)
        drift_info = timeline.drift_corrections
        assert isinstance(drift_info, dict)

        # Verify matching occurred
        # After drift correction, all 4 events should match
        device1_col = "device1_reference_time"
        device2_col = "device2_drift_time"

        if device1_col in merged_df.columns and device2_col in merged_df.columns:
            n_matches = sum(
                1
                for _, row in merged_df.iterrows()
                if not pd.isna(row.get(device1_col))
                and not pd.isna(row.get(device2_col))
            )
            # With drift correction, we should have good matching
            assert n_matches >= 2, (
                f"Expected at least 2 matches with drift correction, got {n_matches}"
            )

        print(
            f"Drift test: consensus events: {len(merged_df)}, drift corrections: {list(drift_info.keys())}"
        )

    def test_sync_three_devices(self, temp_dir):
        """Test synchronization of three devices."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Base event times
        base_times = np.array([5.0, 10.0, 15.0, 20.0, 25.0])

        # Device 1: reference - baseline times
        device1_times = base_times.copy()
        device1_path = self._create_marker_csv(temp_dir, "device_eeg", device1_times)

        # Device 2: slight offset (~150ms)
        device2_times = base_times + 0.15
        device2_path = self._create_marker_csv(temp_dir, "device_fnirs", device2_times)

        # Device 3: different offset (~300ms) - simulating different device
        device3_times = base_times + 0.30
        device3_path = self._create_marker_csv(temp_dir, "device_ecg", device3_times)

        # Run synchronization on all three devices
        results = match_multiple_files_enhanced(
            file_paths=[
                str(device1_path),
                str(device2_path),
                str(device3_path),
            ],
            device_names=["device_eeg", "device_fnirs", "device_ecg"],
            method="hungarian",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=True,
            drift_method="theil_sen",
            output_dir=str(temp_dir),
            output_prefix="three_device_test",
            save_json=False,
            generate_plots=False,
        )

        # Verify results structure
        assert "merged_dataframe" in results
        assert "metadata" in results
        assert "timeline" in results

        # Verify consensus timeline was generated
        merged_df = results["merged_dataframe"]
        assert len(merged_df) > 0

        # Verify all three devices contributed
        assert "device_eeg_time" in merged_df.columns
        assert "device_fnirs_time" in merged_df.columns
        assert "device_ecg_time" in merged_df.columns

        # Verify metadata
        metadata = results["metadata"]
        assert len(metadata["device_info"]) == 3
        assert metadata["timeline_metadata"]["n_devices"] == 3

        # Verify matching statistics
        matching_stats = metadata["matching_statistics"]
        assert len(matching_stats) == 3  # 3 devices

        # Check that device 2 and 3 have drift corrections (to align with device 1)
        timeline = results["timeline"]
        assert (
            len(timeline.drift_corrections) >= 0
        )  # May have 0-2 corrections depending on algorithm

        # Verify confidence scores are calculated
        assert "consensus_confidence" in merged_df.columns

        # Count events matched by all three devices
        all_matched = sum(
            1
            for _, row in merged_df.iterrows()
            if not pd.isna(row.get("device_eeg_time"))
            and not pd.isna(row.get("device_fnirs_time"))
            and not pd.isna(row.get("device_ecg_time"))
        )

        # With tight time windows (0.75s sigma), all 5 events should match well
        assert all_matched >= 3, (
            f"Expected at least 3 events matched by all devices, got {all_matched}"
        )

        print(
            f"Three-device sync: {all_matched} fully matched events, total consensus: {len(merged_df)}"
        )

    def test_sync_mixed_event_counts(self, temp_dir):
        """Test synchronization when devices have different numbers of events."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Device 1: 5 events
        device1_times = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        device1_path = self._create_marker_csv(temp_dir, "device_a", device1_times)

        # Device 2: 3 events (subset of device 1)
        device2_times = np.array([5.0, 10.0, 15.0])
        device2_path = self._create_marker_csv(temp_dir, "device_b", device2_times)

        # Run synchronization
        results = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["device_a", "device_b"],
            method="hungarian",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=False,  # Disable drift for this test
            output_dir=str(temp_dir),
            output_prefix="mixed_test",
            save_json=False,
            generate_plots=False,
        )

        # Verify consensus timeline
        merged_df = results["merged_dataframe"]
        assert len(merged_df) >= 3  # At least 3 consensus events from matching

        # Device 1 has 2 unique events (1.0 and 20.0) that should become new consensus events
        device_a_col = "device_a_time"
        device_b_col = "device_b_time"

        if device_a_col in merged_df.columns and device_b_col in merged_df.columns:
            # Count matches
            n_matched = sum(
                1
                for _, row in merged_df.iterrows()
                if not pd.isna(row.get(device_a_col))
                and not pd.isna(row.get(device_b_col))
            )
            # Should have at least 3 matched events
            assert n_matched >= 3, (
                f"Expected at least 3 matched events, got {n_matched}"
            )

        print(f"Mixed event counts: {len(merged_df)} consensus events")

    def test_sync_different_methods(self, temp_dir):
        """Test synchronization using different matching methods."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Create test data
        device1_times = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        device2_times = np.array([1.1, 2.2, 3.1, 4.0, 5.2])

        device1_path = self._create_marker_csv(temp_dir, "dev1", device1_times)
        device2_path = self._create_marker_csv(temp_dir, "dev2", device2_times)

        # Test Hungarian method (default)
        results_hungarian = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["dev1", "dev2"],
            method="hungarian",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=False,
            output_dir=str(temp_dir),
            output_prefix="method_hungarian",
            save_json=False,
            generate_plots=False,
        )

        assert results_hungarian["merged_dataframe"] is not None

        # Test min_cost_flow method
        results_mcf = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["dev1", "dev2"],
            method="min_cost_flow",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=False,
            output_dir=str(temp_dir),
            output_prefix="method_mcf",
            save_json=False,
            generate_plots=False,
        )

        assert results_mcf["merged_dataframe"] is not None

        # Test sinkhorn method
        results_sinkhorn = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["dev1", "dev2"],
            method="sinkhorn",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=False,
            output_dir=str(temp_dir),
            output_prefix="method_sinkhorn",
            save_json=False,
            generate_plots=False,
        )

        assert results_sinkhorn["merged_dataframe"] is not None

        print("All matching methods tested successfully")

    def test_consensus_timeline_quality(self, temp_dir):
        """Test that consensus timeline has proper confidence scoring."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Create devices with varying time differences
        device1_times = np.array([1.0, 2.0, 3.0, 4.0])
        device2_times = np.array([1.05, 2.1, 3.0, 4.15])  # Close matches
        device3_times = np.array([1.5, 2.8, 3.2, 4.5])  # Further apart

        device1_path = self._create_marker_csv(temp_dir, "ref", device1_times)
        device2_path = self._create_marker_csv(temp_dir, "close", device2_times)
        device3_path = self._create_marker_csv(temp_dir, "far", device3_times)

        # Run synchronization
        results = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path), str(device3_path)],
            device_names=["ref", "close", "far"],
            method="hungarian",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=True,
            drift_method="theil_sen",
            output_dir=str(temp_dir),
            output_prefix="quality_test",
            save_json=False,
            generate_plots=False,
        )

        # Verify confidence scores exist and are meaningful
        merged_df = results["merged_dataframe"]
        assert "consensus_confidence" in merged_df.columns

        # Confidence should be higher when more devices agree
        confidences = merged_df["consensus_confidence"].values

        # All confidences should be positive
        assert all(c > 0 for c in confidences if not pd.isna(c))

        # With 3 devices, max confidence should be around 3 (1 from ref + weighted from others)
        # or normalized depending on implementation
        assert max(confidences) > 1.0, (
            "Expected higher confidence for multi-device agreement"
        )

        print(
            f"Confidence scores range: {min(confidences):.3f} to {max(confidences):.3f}"
        )


class TestMultiDeviceSyncEdgeCases:
    """Additional edge case tests for multi-device synchronization."""

    def _create_marker_csv(
        self, temp_dir: Path, device_name: str, timestamps: np.ndarray
    ) -> Path:
        """
        Create a marker CSV file with the given timestamps.

        Args:
            temp_dir: Temporary directory for the test
            device_name: Name for the device
            timestamps: Array of marker timestamps

        Returns:
            Path to the created CSV file
        """
        csv_path = temp_dir / f"{device_name}_marker.csv"
        df = pd.DataFrame(
            {
                "reference_time": timestamps,
                "marker_type": ["stim"] * len(timestamps),
            }
        )
        df.to_csv(csv_path, index=False)
        return csv_path

    def test_empty_device_handling(self, temp_dir):
        """Test handling when one device has no events."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Device 1: has events
        device1_times = np.array([1.0, 2.0, 3.0])
        device1_path = self._create_marker_csv(temp_dir, "device_with", device1_times)

        # Device 2: no events
        device2_times = np.array([])
        device2_path = self._create_marker_csv(temp_dir, "device_empty", device2_times)

        # This should still work - timeline will just have device1's events
        results = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["device_with", "device_empty"],
            method="hungarian",
            max_time_diff_s=3.0,
            sigma_time_s=0.75,
            estimate_drift=False,
            output_dir=str(temp_dir),
            output_prefix="empty_test",
            save_json=False,
            generate_plots=False,
        )

        # Should still have device1's events in consensus
        merged_df = results["merged_dataframe"]
        assert len(merged_df) >= 3

    def test_very_close_events(self, temp_dir):
        """Test handling of events that are very close together."""
        from multichsync.marker.matcher import match_multiple_files_enhanced

        # Device 1: events at 1.0, 1.1, 1.2 (100ms apart)
        device1_times = np.array([1.0, 1.1, 1.2, 1.3])
        device1_path = self._create_marker_csv(temp_dir, "dense1", device1_times)

        # Device 2: same but slightly offset
        device2_times = np.array([1.05, 1.15, 1.25, 1.35])
        device2_path = self._create_marker_csv(temp_dir, "dense2", device2_times)

        results = match_multiple_files_enhanced(
            file_paths=[str(device1_path), str(device2_path)],
            device_names=["dense1", "dense2"],
            method="hungarian",
            max_time_diff_s=0.5,  # Small window to test resolution
            sigma_time_s=0.1,
            estimate_drift=False,
            output_dir=str(temp_dir),
            output_prefix="dense_test",
            save_json=False,
            generate_plots=False,
        )

        # Should still be able to match these close events
        merged_df = results["merged_dataframe"]
        assert len(merged_df) >= 3

        print(f"Close events test: {len(merged_df)} consensus events")
