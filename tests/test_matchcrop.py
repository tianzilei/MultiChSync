"""Tests for crop_ecg_data function in matchcrop module"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from multichsync.marker.matchcrop import crop_ecg_data


class TestCropECGData:
    """Test suite for crop_ecg_data function"""

    def test_crop_with_header(self, tmp_path):
        """Test cropping ECG data with proper header"""
        # Create test CSV with header
        input_file = tmp_path / "test_with_header.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                "CH1": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6],
                "CH2": [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6],
            }
        )
        df.to_csv(input_file, index=False)

        output_file = tmp_path / "output.csv"

        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=0.5,
            end_time=2.5,
            device_offset=0.0,
        )

        assert result["original_rows"] == 7
        assert result["cropped_rows"] == 5  # 0.5, 1.0, 1.5, 2.0, 2.5

        # Check output file
        output_df = pd.read_csv(output_file)
        assert "Time(sec)" in output_df.columns
        assert len(output_df) == 5
        # Time should start from 0
        assert output_df["Time(sec)"].iloc[0] == 0.0

    def test_crop_headerless_csv(self, tmp_path):
        """Test cropping headerless ECG CSV (common issue)"""
        # Create headerless CSV - first row is data, not header
        input_file = tmp_path / "test_headerless.csv"

        # Write CSV without header
        data = """0.0,1.0,2.0
0.5,1.1,2.1
1.0,1.2,2.2
1.5,1.3,2.3
2.0,1.4,2.4
2.5,1.5,2.5
3.0,1.6,2.6"""

        with open(input_file, "w") as f:
            f.write(data)

        output_file = tmp_path / "output.csv"

        # This should work after the fix - auto-detect headerless and assign column names
        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=0.5,
            end_time=2.5,
            device_offset=0.0,
        )

        assert result["original_rows"] == 7
        assert result["cropped_rows"] == 5

        # Check output file has proper columns
        output_df = pd.read_csv(output_file)
        assert "Time(sec)" in output_df.columns
        assert len(output_df) == 5

    def test_crop_with_time_column_names(self, tmp_path):
        """Test cropping with various time column names"""
        test_cases = [
            {"time_col": "time"},
            {"time_col": "Time"},
            {"time_col": "reference_time"},
        ]

        for tc in test_cases:
            input_file = tmp_path / f"test_{tc['time_col']}.csv"
            df = pd.DataFrame(
                {
                    tc["time_col"]: [0.0, 0.5, 1.0, 1.5, 2.0],
                    "CH1": [1.0, 1.1, 1.2, 1.3, 1.4],
                }
            )
            df.to_csv(input_file, index=False)

            output_file = tmp_path / "output.csv"

            result = crop_ecg_data(
                input_file=input_file,
                output_file=output_file,
                start_time=0.5,
                end_time=1.5,
                device_offset=0.0,
            )

            assert result["cropped_rows"] == 3
            output_df = pd.read_csv(output_file)
            assert tc["time_col"] in output_df.columns

    def test_crop_with_device_offset(self, tmp_path):
        """Test cropping with device offset"""
        input_file = tmp_path / "test_offset.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
                "CH1": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
            }
        )
        df.to_csv(input_file, index=False)

        output_file = tmp_path / "output.csv"

        # With device_offset=0.5, actual crop range becomes [0.0, 1.5]
        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=0.5,
            end_time=2.0,
            device_offset=0.5,
        )

        # Should crop time in [0.0, 1.5] range
        assert result["cropped_rows"] == 4

    def test_crop_empty_result(self, tmp_path):
        """Test cropping when no data in range"""
        input_file = tmp_path / "test_empty.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [0.0, 0.5, 1.0],
                "CH1": [1.0, 1.1, 1.2],
            }
        )
        df.to_csv(input_file, index=False)

        output_file = tmp_path / "output.csv"

        # Request range outside data range
        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=10.0,
            end_time=20.0,
            device_offset=0.0,
        )

        assert result["cropped_rows"] == 0
        assert len(pd.read_csv(output_file)) == 0

    def test_crop_creates_output_dir(self, tmp_path):
        """Test that output directory is created if not exists"""
        input_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [0.0, 1.0, 2.0],
                "CH1": [1.0, 1.1, 1.2],
            }
        )
        df.to_csv(input_file, index=False)

        # Output to non-existent subdirectory
        output_file = tmp_path / "subdir" / "output.csv"

        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=0.0,
            end_time=2.0,
            device_offset=0.0,
        )

        assert output_file.exists()
        assert result["cropped_rows"] == 3

    def test_crop_returns_dict(self, tmp_path):
        """Test that function returns expected dict structure"""
        input_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [0.0, 1.0, 2.0],
                "CH1": [1.0, 1.1, 1.2],
            }
        )
        df.to_csv(input_file, index=False)

        output_file = tmp_path / "output.csv"

        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=0.0,
            end_time=2.0,
            device_offset=0.0,
        )

        assert isinstance(result, dict)
        assert "original_rows" in result
        assert "cropped_rows" in result
        assert "time_range" in result
        assert "output_file" in result

    def test_crop_numeric_time_column(self, tmp_path):
        """Test that time column is converted to numeric if read as string"""
        input_file = tmp_path / "test_numeric.csv"

        # Create CSV with numeric time values that might be read as strings
        df = pd.DataFrame(
            {
                "Time(sec)": ["0.0", "0.5", "1.0", "1.5", "2.0"],
                "CH1": [1.0, 1.1, 1.2, 1.3, 1.4],
            }
        )
        df.to_csv(input_file, index=False)

        output_file = tmp_path / "output.csv"

        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=0.5,
            end_time=1.5,
            device_offset=0.0,
        )

        assert result["cropped_rows"] == 3

        output_df = pd.read_csv(output_file)
        assert pd.api.types.is_numeric_dtype(output_df["Time(sec)"])
