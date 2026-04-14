"""
Integration tests for quality assessment batch processing workflows.
"""

import pytest
import pandas as pd
from pathlib import Path

# Import the batch processing function from multichsync.quality
from multichsync.quality import batch_process_snirf_folder


def create_minimal_snirf(
    path: Path,
    n_sources: int = 1,
    n_detectors: int = 1,
    duration_s: float = 30.0,
    sfreq: float = 50.0,
):
    """Create minimal SNIRF file for testing that is MNE-compatible."""
    import h5py
    import numpy as np

    n_timepoints = int(duration_s * sfreq)

    with h5py.File(path, "w") as f:
        nirs = f.create_group("nirs")

        # Add metaDataTags with time unit
        meta = nirs.create_group("metaDataTags")
        meta.create_dataset("TimeUnit", data=np.array("s", dtype=h5py.string_dtype()))
        meta.create_dataset(
            "MeasurementDate", data=np.array("2024-01-01", dtype=h5py.string_dtype())
        )
        meta.create_dataset(
            "MeasurementTime", data=np.array("12:00:00", dtype=h5py.string_dtype())
        )
        meta.create_dataset(
            "SubjectID", data=np.array("test", dtype=h5py.string_dtype())
        )
        meta.create_dataset(
            "LengthUnit", data=np.array("mm", dtype=h5py.string_dtype())
        )

        # Data group - use the standard SNIRF naming
        data = nirs.create_group("data1")

        # Time data
        time_data = np.linspace(0, duration_s, n_timepoints)
        data.create_dataset("time", data=time_data)

        # Create channel list (all HbO-HbR pairs)
        n_channels = n_sources * n_detectors
        if n_channels == 0:
            n_channels = 1

        # Probe - wavelengths and source/detector labels
        probe = nirs.create_group("probe")

        # Create wavelengths array - two wavelengths for HbO and HbR
        wavelengths_list = [760.0, 850.0]

        # Create unique source and detector labels
        source_labels_list = [f"S{s + 1}" for s in range(n_sources)]
        detector_labels_list = [f"D{d + 1}" for d in range(n_detectors)]

        # Handle edge case for single channel (already handled by above logic)
        if n_channels == 1 and n_sources == 1 and n_detectors == 1:
            source_labels_list = ["S1"]
            detector_labels_list = ["D1"]
            wavelengths_list = [760.0, 850.0]

        wavelengths = np.array(wavelengths_list, dtype=np.float64)
        probe.create_dataset("wavelengths", data=wavelengths)
        probe.create_dataset(
            "sourceLabels", data=np.array(source_labels_list, dtype=h5py.string_dtype())
        )
        probe.create_dataset(
            "detectorLabels",
            data=np.array(detector_labels_list, dtype=h5py.string_dtype()),
        )

        # Add 3D positions for sources and detectors (required by MNE)
        source_pos = np.zeros((n_sources, 3), dtype=np.float64)
        for i in range(n_sources):
            source_pos[i] = [i * 20.0, 0.0, 0.0]  # dummy positions

        detector_pos = np.zeros((n_detectors, 3), dtype=np.float64)
        for i in range(n_detectors):
            detector_pos[i] = [i * 20.0 + 10.0, 0.0, 0.0]  # dummy positions

        probe.create_dataset("sourcePos3D", data=source_pos)
        probe.create_dataset("detectorPos3D", data=detector_pos)

        # Create channel labels (HbO and HbR pairs)
        ch_names = []
        for s in range(n_sources):
            for d in range(n_detectors):
                ch_names.append(f"S{s + 1}_D{d + 1} HbO")
                ch_names.append(f"S{s + 1}_D{d + 1} HbR")

        if n_channels == 1 and n_sources == 1 and n_detectors == 1:
            ch_names = ["S1_D1 HbO", "S1_D1 HbR"]

        # Create data matrix - use dataTimeSeries (standard SNIRF name)
        n_ch = len(ch_names)
        # Generate random data with low-frequency oscillation (0.1 Hz) to ensure PSD in band
        t = np.linspace(0, duration_s, n_timepoints)
        nirs_data = np.random.randn(n_ch, n_timepoints).astype(np.float64) * 100 + 1000
        # Add sinusoidal component at 0.1 Hz (within fNIRS typical band)
        for i in range(n_ch):
            nirs_data[i] += 50 * np.sin(2 * np.pi * 0.1 * t)
        data.create_dataset("dataTimeSeries", data=nirs_data)

        # Create measurementList groups to specify data types
        # dataType 99999 = processed hemoglobin (HbO/HbR)
        for i, ch_name in enumerate(ch_names, start=1):
            ml = data.create_group(f"measurementList{i}")
            # 99999 = processed hemoglobin
            ml.create_dataset("dataType", data=np.int32(99999))
            # Add dataTypeLabel to distinguish HbO from HbR
            if "HbO" in ch_name:
                ml.create_dataset(
                    "dataTypeLabel", data=np.array("HbO", dtype=h5py.string_dtype())
                )
            else:
                ml.create_dataset(
                    "dataTypeLabel", data=np.array("HbR", dtype=h5py.string_dtype())
                )
            # Source and detector indices (0-based)
            sd_index = (i - 1) // 2  # Each SD pair has 2 channels (HbO, HbR), 0-based
            source_index = sd_index // n_detectors
            detector_index = sd_index % n_detectors
            ml.create_dataset("sourceIndex", data=np.int32(source_index))
            ml.create_dataset("detectorIndex", data=np.int32(detector_index))
            # Wavelength index (0 or 1 for the two wavelengths)
            wl_index = 0 if "HbO" in ch_name else 1
            ml.create_dataset("wavelengthIndex", data=np.int32(wl_index))

    return path


class TestQualityBatchProcessing:
    """Tests for batch quality assessment of SNIRF files."""

    @pytest.mark.xfail(
        reason="Minimal SNIRF mock lacks realistic spectral content for quality assessment"
    )
    def test_batch_quality_assessment(self, temp_dir):
        """Test batch quality assessment processes SNIRF files and returns summary."""
        # Create input directory with SNIRF file
        input_dir = temp_dir / "input"
        input_dir.mkdir()

        # Create minimal SNIRF file
        snirf_path = input_dir / "test.snirf"
        create_minimal_snirf(
            snirf_path,
            n_sources=1,
            n_detectors=1,
        )

        # Create output directory
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Run batch processing
        summary_df, failed = batch_process_snirf_folder(
            in_dir=input_dir,
            out_dir=output_dir,
            l_freq=0.01,
            h_freq=0.2,
            resample_sfreq=4.0,
            apply_tddr=False,  # Disable for faster tests
            comprehensive=True,
            paradigm="resting",
        )

        # Verify summary DataFrame is returned
        assert isinstance(summary_df, pd.DataFrame)
        assert len(summary_df) > 0

        # Verify failed list is returned
        assert isinstance(failed, list)

        # Verify summary contains expected columns
        expected_columns = ["input_file", "n_hbo_channels", "n_hbr_channels"]
        for col in expected_columns:
            assert col in summary_df.columns, f"Missing column: {col}"

        # Verify output files were created
        assert (output_dir / "snirf_batch_summary.csv").exists()
        assert (output_dir / "snirf_batch_failed.csv").exists()

    def test_empty_directory(self, temp_dir):
        """Test handling of empty input directory raises appropriate error."""
        # Create empty input directory (no SNIRF files)
        input_dir = temp_dir / "empty_input"
        input_dir.mkdir()

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Verify that empty directory raises FileNotFoundError
        with pytest.raises(FileNotFoundError) as exc_info:
            batch_process_snirf_folder(
                in_dir=input_dir,
                out_dir=output_dir,
            )

        # Verify error message indicates no SNIRF files found
        assert "No .snirf files found" in str(exc_info.value)

    @pytest.mark.xfail(
        reason="Minimal SNIRF mock lacks realistic spectral content for quality assessment"
    )
    def test_with_comprehensive_disabled(self, temp_dir):
        """Test batch processing with comprehensive=False skips signal-level metrics."""
        # Create input directory with SNIRF file
        input_dir = temp_dir / "input"
        input_dir.mkdir()

        # Create minimal SNIRF file
        snirf_path = input_dir / "test.snirf"
        create_minimal_snirf(snirf_path, n_sources=1, n_detectors=1)

        # Create output directory
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Run batch processing with comprehensive=False
        summary_df, failed = batch_process_snirf_folder(
            in_dir=input_dir,
            out_dir=output_dir,
            l_freq=0.01,
            h_freq=0.2,
            resample_sfreq=4.0,
            apply_tddr=False,
            comprehensive=False,  # Disable comprehensive assessment
            paradigm="resting",
        )

        # Verify summary DataFrame is returned
        assert isinstance(summary_df, pd.DataFrame)
        assert len(summary_df) > 0

        # Verify failed list is returned
        assert isinstance(failed, list)
        assert len(failed) == 0  # No failures expected

        # Verify comprehensive columns are not present
        # (comprehensive metrics are omitted when comprehensive=False)
        for col in summary_df.columns:
            assert not col.startswith("comprehensive_"), (
                f"Comprehensive columns should not be present when comprehensive=False: {col}"
            )


class TestQualityBatchEdgeCases:
    """Tests for edge cases in batch quality assessment."""

    def test_nonexistent_input_directory(self, temp_dir):
        """Test error handling for non-existent input directory."""
        # Use a non-existent directory path
        nonexistent_dir = temp_dir / "nonexistent"

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Verify that non-existent directory raises FileNotFoundError
        with pytest.raises(FileNotFoundError) as exc_info:
            batch_process_snirf_folder(
                in_dir=nonexistent_dir,
                out_dir=output_dir,
            )

        # Verify error message indicates no SNIRF files found
        assert "No .snirf files found" in str(exc_info.value)
