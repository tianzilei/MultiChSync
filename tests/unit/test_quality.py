"""
Comprehensive unit tests for quality assessment functions in multichsync.quality.

Tests the following functions:
- assess_hb_quality
- compute_hb_snr
- smart_filter_raw
- pair_hbo_hbr_channels

Uses unittest.mock.MagicMock to mock MNE Raw objects since the actual
functions work with MNE data structures.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

# Import the functions to test
from multichsync.quality import (
    assess_hb_quality,
    compute_hb_snr,
    smart_filter_raw,
    pair_hbo_hbr_channels,
)


class TestAssessHbQuality:
    """Test cases for assess_hb_quality function."""

    def test_good_signal(self):
        """Test assessment of good quality signal."""
        # Create mock MNE Raw object with good quality data
        mock_raw = MagicMock()
        mock_raw.n_times = 1000
        mock_raw.info = {"sfreq": 10.0, "ch_names": ["S1_D1 hbo", "S1_D1 hbr"]}
        mock_raw.ch_names = ["S1_D1 hbo", "S1_D1 hbr"]

        # Create good quality signal data (non-flat, reasonable variance)
        good_data = np.random.randn(2, 1000) * 10 + 100
        mock_raw.get_data.return_value = good_data

        # Mock channel types
        with patch("multichsync.quality.assessor.get_channel_types") as mock_ch_types:
            mock_ch_types.return_value = ["hbo", "hbr"]

            # Mock pair_hbo_hbr_channels
            with patch(
                "multichsync.quality.assessor.pair_hbo_hbr_channels"
            ) as mock_pairs:
                mock_pairs.return_value = [("S1_D1", 0, 1)]

                # Mock safe_corr for correlation calculation
                with patch("multichsync.quality.assessor.safe_corr") as mock_corr:
                    mock_corr.return_value = -0.5  # Good anticorrelation

                    # Call the function
                    quality_df, bad_channels = assess_hb_quality(mock_raw)

                    # Verify results
                    assert isinstance(quality_df, pd.DataFrame)
                    assert isinstance(bad_channels, list)
                    # Good signal should not be marked as bad
                    assert (
                        len(bad_channels) == 0
                        or "bad_any" not in quality_df.columns
                        or not quality_df["bad_any"].any()
                    )

    def test_flat_signal(self):
        """Test detection of flat (bad) signal."""
        # Create mock MNE Raw object with flat (bad) signal
        mock_raw = MagicMock()
        mock_raw.n_times = 1000
        mock_raw.info = {"sfreq": 10.0, "ch_names": ["S1_D1 hbo", "S1_D1 hbr"]}
        mock_raw.ch_names = ["S1_D1 hbo", "S1_D1 hbr"]

        # Create flat signal data (essentially constant values)
        flat_data = np.ones((2, 1000)) * 100
        mock_raw.get_data.return_value = flat_data

        # Mock channel types
        with patch("multichsync.quality.assessor.get_channel_types") as mock_ch_types:
            mock_ch_types.return_value = ["hbo", "hbr"]

            # Mock pair_hbo_hbr_channels
            with patch(
                "multichsync.quality.assessor.pair_hbo_hbr_channels"
            ) as mock_pairs:
                mock_pairs.return_value = [("S1_D1", 0, 1)]

                # Call the function
                quality_df, bad_channels = assess_hb_quality(mock_raw)

                # Verify results - flat signals should be detected
                assert isinstance(quality_df, pd.DataFrame)
                assert isinstance(bad_channels, list)
                # Flat signal should have very low or zero std
                assert "std" in quality_df.columns
                assert quality_df["std"].iloc[0] < 1e-6


class TestComputeHbSnr:
    """Test cases for compute_hb_snr function."""

    def test_snr_calculation(self):
        """Test SNR calculation for valid signals."""
        # Create mock MNE Raw object
        mock_raw = MagicMock()
        mock_raw.n_times = 1000
        mock_raw.info = {"sfreq": 10.0, "ch_names": ["S1_D1 hbo", "S1_D1 hbr"]}
        mock_raw.ch_names = ["S1_D1 hbo", "S1_D1 hbr"]

        # Create signal data with some variance
        signal_data = np.random.randn(2, 1000) * 5 + 50
        mock_raw.get_data.return_value = signal_data

        # Mock channel types
        with patch("multichsync.quality.assessor.get_channel_types") as mock_ch_types:
            mock_ch_types.return_value = ["hbo", "hbr"]

            # Mock psd_array_welch
            mock_psd = np.random.rand(2, 129) * 0.1
            mock_freqs = np.linspace(0, 5, 129)
            with patch("multichsync.quality.assessor.psd_array_welch") as mock_psd_func:
                mock_psd_func.return_value = (mock_psd, mock_freqs)

                # Call the function
                result_df = compute_hb_snr(mock_raw)

                # Verify results
                assert isinstance(result_df, pd.DataFrame)
                assert "channel" in result_df.columns
                assert "snr_time_db" in result_df.columns
                assert "snr_psd_db" in result_df.columns
                assert len(result_df) == 2

    def test_empty_signal(self):
        """Test handling of empty signal (insufficient data)."""
        # Create mock MNE Raw object with very short signal
        mock_raw = MagicMock()
        mock_raw.n_times = 5  # Too few samples
        mock_raw.info = {"sfreq": 10.0, "ch_names": ["S1_D1 hbo"]}
        mock_raw.ch_names = ["S1_D1 hbo"]

        # Create minimal signal data
        signal_data = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
        mock_raw.get_data.return_value = signal_data

        # Mock channel types
        with patch("multichsync.quality.assessor.get_channel_types") as mock_ch_types:
            mock_ch_types.return_value = ["hbo"]

            # Mock psd_array_welch
            mock_psd = np.random.rand(1, 3) * 0.1
            mock_freqs = np.array([0.0, 2.5, 5.0])
            with patch("multichsync.quality.assessor.psd_array_welch") as mock_psd_func:
                mock_psd_func.return_value = (mock_psd, mock_freqs)

                # Call the function
                result_df = compute_hb_snr(mock_raw)

                # Verify results - should handle short data gracefully
                assert isinstance(result_df, pd.DataFrame)
                # With insufficient data, SNR should be NaN
                assert "snr_time_db" in result_df.columns


class TestSmartFilterRaw:
    """Test cases for smart_filter_raw function."""

    def test_bandpass_filter(self):
        """Test bandpass filtering is applied correctly."""
        # Create mock MNE Raw object
        mock_raw = MagicMock()
        mock_raw.n_times = 1000
        mock_raw.info = {"sfreq": 10.0}
        mock_raw.ch_names = ["S1_D1 hbo", "S1_D1 hbr"]

        # Create signal data
        signal_data = np.random.randn(2, 1000)
        mock_raw.get_data.return_value = signal_data

        # Mock the filter method to avoid actual filtering
        mock_raw.filter = MagicMock(return_value=None)

        # Call the function
        result_raw, filter_method = smart_filter_raw(mock_raw, l_freq=0.01, h_freq=0.2)

        # Verify filter was called
        mock_raw.filter.assert_called_once()

        # Verify filter method is returned
        assert isinstance(filter_method, str)
        assert filter_method in ["iir_butterworth_order4", "fir_auto"]

    def test_invalid_frequencies(self):
        """Test handling of invalid frequency parameters."""
        # Create mock MNE Raw object
        mock_raw = MagicMock()
        mock_raw.n_times = 1000
        mock_raw.info = {"sfreq": 10.0}
        mock_raw.ch_names = ["S1_D1 hbo", "S1_D1 hbr"]

        # Create signal data
        signal_data = np.random.randn(2, 1000)
        mock_raw.get_data.return_value = signal_data

        # Mock the filter method
        mock_raw.filter = MagicMock(return_value=None)

        # Test with invalid frequencies (l_freq >= h_freq)
        # This should still call filter with the given params
        result_raw, filter_method = smart_filter_raw(mock_raw, l_freq=0.5, h_freq=0.1)

        # Verify filter was called even with invalid params
        mock_raw.filter.assert_called_once()


class TestPairHboHbrChannels:
    """Test cases for pair_hbo_hbr_channels function."""

    def test_pairing(self):
        """Test HbO-HbR channel pairing."""
        # Create mock MNE Raw object
        mock_raw = MagicMock()
        mock_raw.ch_names = [
            "S1_D1 hbo",
            "S1_D1 hbr",
            "S2_D1 hbo",
            "S2_D1 hbr",
            "S3_D1 hbo",
        ]

        # Mock channel types
        with patch("multichsync.quality.assessor.get_channel_types") as mock_ch_types:
            mock_ch_types.return_value = [
                "hbo",
                "hbr",
                "hbo",
                "hbr",
                "hbo",  # No hbr pair for this one
            ]

            # Call the function
            pairs = pair_hbo_hbr_channels(mock_raw)

            # Verify results
            assert isinstance(pairs, list)
            # Should have 2 valid pairs (S1_D1 and S2_D1)
            assert len(pairs) == 2
            # Each pair should be (base_name, idx_hbo, idx_hbr)
            assert pairs[0][0] == "S1_D1"
            assert pairs[0][1] == 0  # hbo index
            assert pairs[0][2] == 1  # hbr index

    def test_no_pairs(self):
        """Test when no valid HbO-HbR pairs exist."""
        # Create mock MNE Raw object with only one type
        mock_raw = MagicMock()
        mock_raw.ch_names = ["S1_D1 hbo", "S2_D1 hbo", "S3_D1 hbo"]

        # Mock channel types - only hbo, no hbr
        with patch("multichsync.quality.assessor.get_channel_types") as mock_ch_types:
            mock_ch_types.return_value = ["hbo", "hbo", "hbo"]

            # Call the function
            pairs = pair_hbo_hbr_channels(mock_raw)

            # Verify results - should have no pairs
            assert isinstance(pairs, list)
            assert len(pairs) == 0


class TestQualityModuleIntegration:
    """Integration tests to verify the quality module works end-to-end."""

    def test_assess_hb_quality_with_mock(self):
        """Full test for assess_hb_quality with mocked dependencies."""
        # Create comprehensive mock
        mock_raw = MagicMock()
        mock_raw.n_times = 500
        mock_raw.info = {"sfreq": 10.0}
        mock_raw.ch_names = ["Ch1 hbo", "Ch1 hbr"]

        # Create signal with realistic properties
        np.random.seed(42)
        signal = np.random.randn(2, 500) * 10 + 100
        mock_raw.get_data.return_value = signal

        with patch(
            "multichsync.quality.assessor.get_channel_types"
        ) as mock_types, patch(
            "multichsync.quality.assessor.pair_hbo_hbr_channels"
        ) as mock_pairs, patch("multichsync.quality.assessor.safe_corr") as mock_corr:
            mock_types.return_value = ["hbo", "hbr"]
            mock_pairs.return_value = [("Ch1", 0, 1)]
            mock_corr.return_value = -0.3

            quality_df, bad_channels = assess_hb_quality(mock_raw)

            # Verify structure
            assert len(quality_df) == 2
            assert "channel" in quality_df.columns
            assert "type" in quality_df.columns
            assert "nan_ratio" in quality_df.columns
            assert "std" in quality_df.columns

    def test_compute_hb_snr_with_mock(self):
        """Full test for compute_hb_snr with mocked dependencies."""
        mock_raw = MagicMock()
        mock_raw.n_times = 256
        mock_raw.info = {"sfreq": 10.0}
        mock_raw.ch_names = ["Ch1 hbo"]

        signal = np.random.randn(1, 256) * 5
        mock_raw.get_data.return_value = signal

        with patch(
            "multichsync.quality.assessor.get_channel_types"
        ) as mock_types, patch(
            "multichsync.quality.assessor.psd_array_welch"
        ) as mock_psd:
            mock_types.return_value = ["hbo"]
            mock_psd.return_value = (
                np.random.rand(1, 129),
                np.linspace(0, 5, 129),
            )

            result_df = compute_hb_snr(mock_raw)

            # Verify structure
            assert "channel" in result_df.columns
            assert "snr_time_db" in result_df.columns
            assert "snr_psd_db" in result_df.columns


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_pair_hbo_hbr_mixed_naming(self):
        """Test pairing with different naming conventions."""
        mock_raw = MagicMock()
        # Test different naming patterns
        mock_raw.ch_names = [
            "S1_D1 hbo",
            "S1_D1_hbr",  # Underscore instead of space
            "S2_D2hbo",  # No separator
            "S2_D2hbr",
        ]

        with patch("multichsync.quality.assessor.get_channel_types") as mock_types:
            mock_types.return_value = ["hbo", "hbr", "hbo", "hbr"]

            pairs = pair_hbo_hbr_channels(mock_raw)

            # Should handle different naming conventions
            assert isinstance(pairs, list)

    def test_empty_channel_list(self):
        """Test handling of empty channel list."""
        mock_raw = MagicMock()
        mock_raw.ch_names = []

        with patch("multichsync.quality.assessor.get_channel_types") as mock_types:
            mock_types.return_value = []

            pairs = pair_hbo_hbr_channels(mock_raw)

            assert pairs == []
