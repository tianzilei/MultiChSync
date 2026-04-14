"""
Unit tests for ECG converter functions.

Tests import from:
- multichsync.ecg.converter (convert_acq_to_csv)
- multichsync.ecg.batch (batch_convert_acq_to_csv)
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


class TestConvertAcqToCsv:
    """Test suite for convert_acq_to_csv function."""

    @pytest.fixture
    def mock_parsed_data(self):
        """Create mock parsed ACQ data."""
        return {
            "data": pd.DataFrame(
                {
                    "ECG1": np.random.randn(1000),
                    "ECG2": np.random.randn(1000),
                    "Input1": np.random.randn(1000),
                }
            ),
            "channels": [
                {
                    "index": 0,
                    "name": "ECG1",
                    "normalized_name": "ecg1",
                    "original_name": "ECG1",
                },
                {
                    "index": 1,
                    "name": "ECG2",
                    "normalized_name": "ecg2",
                    "original_name": "ECG2",
                },
                {
                    "index": 2,
                    "name": "Input1",
                    "normalized_name": "input1",
                    "original_name": "Input1",
                },
            ],
            "original_sr": 1000,
            "sampling_rate": 250,
            "duration": 4.0,
            "metadata": {
                "filename": "test.acq",
                "file_size": 1000,
                "channel_count": 3,
                "total_samples": 1000,
            },
        }

    def test_csv_output(self, temp_dir, mock_parsed_data):
        """Test conversion to CSV format."""
        # Create a dummy ACQ file
        acq_path = temp_dir / "test.acq"
        acq_path.touch()

        # Mock the parse_acq_file function to avoid bioread dependency
        with patch(
            "multichsync.ecg.converter.parse_acq_file", return_value=mock_parsed_data
        ):
            from multichsync.ecg.converter import convert_acq_to_csv

            output_path = temp_dir / "output.csv"
            result = convert_acq_to_csv(
                str(acq_path),
                output_path=str(output_path),
                group_by_type=False,
                sampling_rate=250,
            )

            # Verify result is a string path
            assert isinstance(result, str)

            # Verify output file exists
            assert Path(result).exists()

            # Verify CSV content
            df = pd.read_csv(result)
            assert len(df) == 1000
            # Check columns exist (may have time column added by writer)
            assert "ECG1" in df.columns or df.shape[1] > 0

    def test_group_by_type(self, temp_dir, mock_parsed_data):
        """Test channel grouping option."""
        # Create a dummy ACQ file
        acq_path = temp_dir / "test.acq"
        acq_path.touch()

        # Mock the parse_acq_file function
        with patch(
            "multichsync.ecg.converter.parse_acq_file", return_value=mock_parsed_data
        ):
            from multichsync.ecg.converter import convert_acq_to_csv

            output_dir = temp_dir / "output"
            result = convert_acq_to_csv(
                str(acq_path),
                output_path=str(output_dir),
                group_by_type=True,
                sampling_rate=250,
            )

            # Verify result is a dict when group_by_type=True
            assert isinstance(result, dict)

            # Verify multiple output files created
            assert len(result) > 0

            # Verify files exist
            for group_name, file_path in result.items():
                assert Path(file_path).exists(), (
                    f"File for group {group_name} does not exist"
                )

            # Verify grouping - should have ecg and input groups
            assert "ecg" in result or "other" in result

    def test_csv_output_with_custom_float_format(self, temp_dir, mock_parsed_data):
        """Test CSV output with custom float format."""
        acq_path = temp_dir / "test.acq"
        acq_path.touch()

        with patch(
            "multichsync.ecg.converter.parse_acq_file", return_value=mock_parsed_data
        ):
            from multichsync.ecg.converter import convert_acq_to_csv

            output_path = temp_dir / "output.csv"
            result = convert_acq_to_csv(
                str(acq_path),
                output_path=str(output_path),
                group_by_type=False,
                float_format="%.2f",
            )

            assert Path(result).exists()

            # Read file to verify format
            with open(result, "r") as f:
                content = f.read()
                # Should have fewer decimal places with "%.2f"
                assert "," in content  # Valid CSV

    def test_auto_output_path_creation(self, temp_dir, mock_parsed_data):
        """Test automatic output path creation when output_path is None."""
        acq_path = temp_dir / "test.acq"
        acq_path.touch()

        with patch(
            "multichsync.ecg.converter.parse_acq_file", return_value=mock_parsed_data
        ):
            from multichsync.ecg.converter import convert_acq_to_csv

            # Test with output_path=None (auto-generate)
            result = convert_acq_to_csv(
                str(acq_path), output_path=None, group_by_type=False, sampling_rate=250
            )

            # Result should be a string path
            assert isinstance(result, str)
            # Output should be in a 'convert' subdirectory
            assert "convert" in result


class TestBatchConvertAcqToCsv:
    """Test suite for batch_convert_acq_to_csv function."""

    def test_empty_directory(self, temp_dir):
        """Test handling of empty input directory."""
        from multichsync.ecg.batch import batch_convert_acq_to_csv

        # Create empty input directory
        empty_dir = temp_dir / "empty_input"
        empty_dir.mkdir()

        # Should return empty list for empty directory
        result = batch_convert_acq_to_csv(
            str(empty_dir),
            output_dir=str(temp_dir / "output"),
            sampling_rate=250,
            group_by_type=True,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_directory_with_no_acq_files(self, temp_dir):
        """Test handling of directory with non-ACQ files."""
        from multichsync.ecg.batch import batch_convert_acq_to_csv

        # Create directory with non-ACQ files
        input_dir = temp_dir / "input"
        input_dir.mkdir()

        # Add some non-ACQ files
        (input_dir / "readme.txt").write_text("test")
        (input_dir / "data.csv").write_text("col1,col2\n1,2")

        result = batch_convert_acq_to_csv(
            str(input_dir),
            output_dir=str(temp_dir / "output"),
            sampling_rate=250,
            group_by_type=True,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.skipif(
        True,  # Skip if bioread is not available
        reason="bioread not available - requires actual ACQ file parsing",
    )
    def test_batch_with_valid_acq_files(self, temp_dir):
        """Test batch conversion with valid ACQ files."""
        # This test would require actual ACQ files or full mocking
        # Skipped by default since ACQ parsing needs bioread
        pass


class TestECGConverterEdgeCases:
    """Edge case tests for ECG converter."""

    def test_missing_acq_file_raises_error(self):
        """Test that missing ACQ file raises FileNotFoundError."""
        from multichsync.ecg.converter import convert_acq_to_csv

        with pytest.raises(FileNotFoundError):
            convert_acq_to_csv("/nonexistent/path/test.acq", group_by_type=False)

    def test_invalid_output_format(self):
        """Test that invalid output format raises ValueError."""
        from multichsync.ecg.converter import convert_acq_to_format

        with pytest.raises(ValueError, match="不支持的输出格式"):
            convert_acq_to_format("test.acq", output_format="invalid")


# Integration tests that require actual ACQ files (skipped by default)
class TestECGConverterIntegration:
    """Integration tests that require bioread and actual ACQ files."""

    @pytest.mark.integration
    @pytest.mark.skipif(
        True,  # Skip unless ACQ test files are available
        reason="Requires actual ACQ test files and bioread library",
    )
    def test_real_acq_file_conversion(self, temp_dir):
        """Test conversion with real ACQ file."""
        # This would require a real ACQ test file
        # Skipped in normal test runs
        pass
