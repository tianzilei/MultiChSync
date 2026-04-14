"""
Unit tests for marker cleaning functions (clean_marker_csv and clean_marker_folder).
"""

import pandas as pd
import pytest
from pathlib import Path
from multichsync.marker import clean_marker_csv, clean_marker_folder


class TestCleanMarkerCsv:
    """Tests for clean_marker_csv function."""

    def test_remove_duplicates(self, temp_dir):
        """Test removal of duplicate time markers that are too close together."""
        # Create CSV with markers that are too close (interval < min_interval)
        csv_path = temp_dir / "test_duplicates.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [
                    0.0,
                    0.3,
                    0.8,
                    2.0,
                    2.5,
                    4.0,
                ],  # Some markers are too close
                "value": ["A", "B", "C", "D", "E", "F"],
            }
        )
        df.to_csv(csv_path, index=False)

        # Clean with min_interval=1.0
        result = clean_marker_csv(
            csv_path=csv_path, out_path=None, min_rows=2, min_interval=1.0
        )

        assert result == "cleaned"

        # Read cleaned file and verify
        cleaned_df = pd.read_csv(csv_path)
        # The algorithm compares against the LAST KEPT marker:
        # - 0.0: keep (first)
        # - 0.3: diff from 0.0 = 0.3 < 1.0, DROP
        # - 0.8: diff from 0.0 = 0.8 < 1.0, DROP
        # - 2.0: diff from 0.0 = 2.0 >= 1.0, KEEP
        # - 2.5: diff from 2.0 = 0.5 < 1.0, DROP
        # - 4.0: diff from 2.0 = 2.0 >= 1.0, KEEP
        expected_times = [0.0, 2.0, 4.0]
        assert len(cleaned_df) == len(expected_times)
        assert list(cleaned_df["Time(sec)"]) == expected_times

    def test_sort_by_time(self, temp_dir):
        """Test sorting by time column."""
        # Create CSV with unsorted times
        csv_path = temp_dir / "test_sort.csv"
        df = pd.DataFrame(
            {"Time(sec)": [5.0, 1.0, 3.0, 2.0, 4.0], "value": ["a", "b", "c", "d", "e"]}
        )
        df.to_csv(csv_path, index=False)

        result = clean_marker_csv(
            csv_path=csv_path, out_path=None, min_rows=2, min_interval=0.5
        )

        assert result == "cleaned"

        # Verify sorted
        cleaned_df = pd.read_csv(csv_path)
        time_list = list(cleaned_df["Time(sec)"])
        assert time_list == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_min_rows_filter(self, temp_dir):
        """Test filtering by minimum row count."""
        # Create CSV with too few rows
        csv_path = temp_dir / "test_min_rows.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [1.0, 2.0],  # Only 2 rows
                "value": ["a", "b"],
            }
        )
        df.to_csv(csv_path, index=False)

        # Try to clean with min_rows=3
        result = clean_marker_csv(
            csv_path=csv_path, out_path=None, min_rows=3, min_interval=0.5
        )

        assert result == "deleted_too_few_rows"
        assert not csv_path.exists()

    def test_min_rows_filter_exactly_at_minimum(self, temp_dir):
        """Test that files with exactly min_rows are kept."""
        csv_path = temp_dir / "test_exact_min.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [1.0, 2.0, 3.0],  # Exactly 3 rows
                "value": ["a", "b", "c"],
            }
        )
        df.to_csv(csv_path, index=False)

        result = clean_marker_csv(
            csv_path=csv_path, out_path=None, min_rows=3, min_interval=0.5
        )

        assert result == "cleaned"
        cleaned_df = pd.read_csv(csv_path)
        assert len(cleaned_df) == 3

    def test_delete_empty_file(self, temp_dir):
        """Test deletion of empty CSV file."""
        csv_path = temp_dir / "test_empty.csv"
        df = pd.DataFrame({"Time(sec)": [], "value": []})
        df.to_csv(csv_path, index=False)

        result = clean_marker_csv(
            csv_path=csv_path, out_path=None, min_rows=2, min_interval=0.5
        )

        assert result == "deleted_empty"

    def test_missing_time_column(self, temp_dir):
        """Test handling of missing time column."""
        csv_path = temp_dir / "test_no_time.csv"
        df = pd.DataFrame({"value": ["a", "b", "c"]})
        df.to_csv(csv_path, index=False)

        result = clean_marker_csv(
            csv_path=csv_path, time_col="Time(sec)", min_rows=2, min_interval=0.5
        )

        assert result == "missing_time_col"

    def test_auto_detect_time_column(self, temp_dir):
        """Test automatic time column detection."""
        # Test with different time column names
        for time_col_name in ["reference_time", "time", "Time"]:
            csv_path = temp_dir / f"test_{time_col_name}.csv"
            df = pd.DataFrame(
                {time_col_name: [1.0, 2.0, 3.0], "value": ["a", "b", "c"]}
            )
            df.to_csv(csv_path, index=False)

            result = clean_marker_csv(
                csv_path=csv_path, out_path=None, min_rows=2, min_interval=0.5
            )

            assert result == "cleaned"
            cleaned_df = pd.read_csv(csv_path)
            assert len(cleaned_df) == 3

    def test_output_to_different_file(self, temp_dir):
        """Test saving cleaned data to a different file."""
        input_path = temp_dir / "input.csv"
        output_path = temp_dir / "output.csv"

        df = pd.DataFrame({"Time(sec)": [5.0, 1.0, 3.0], "value": ["a", "b", "c"]})
        df.to_csv(input_path, index=False)

        result = clean_marker_csv(
            csv_path=input_path, out_path=output_path, min_rows=2, min_interval=0.5
        )

        assert result == "cleaned"
        assert output_path.exists()
        # Original file should still exist
        assert input_path.exists()

        # Check output is sorted
        cleaned_df = pd.read_csv(output_path)
        assert list(cleaned_df["Time(sec)"]) == [1.0, 3.0, 5.0]


class TestCleanMarkerFolder:
    """Tests for clean_marker_folder function."""

    def test_empty_folder(self, temp_dir):
        """Test handling of empty folder."""
        # Create empty directory
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()

        summary = clean_marker_folder(
            input_dir=empty_dir, output_dir=None, min_rows=2, min_interval=0.5
        )

        assert summary == {}

    def test_multiple_files(self, temp_dir):
        """Test cleaning multiple marker files."""
        # Create multiple CSV files
        file1 = temp_dir / "file1.csv"
        file2 = temp_dir / "file2.csv"
        file3 = temp_dir / "file3.csv"

        # File 1: Valid markers
        df1 = pd.DataFrame(
            {"Time(sec)": [1.0, 2.0, 3.0, 4.0, 5.0], "value": ["a", "b", "c", "d", "e"]}
        )
        df1.to_csv(file1, index=False)

        # File 2: Too few rows
        df2 = pd.DataFrame({"Time(sec)": [1.0], "value": ["a"]})
        df2.to_csv(file2, index=False)

        # File 3: Valid markers (needs cleaning)
        df3 = pd.DataFrame(
            {
                "Time(sec)": [1.0, 1.2, 2.5, 4.0],  # 1.2 is too close to 1.0
                "value": ["a", "b", "c", "d"],
            }
        )
        df3.to_csv(file3, index=False)

        summary = clean_marker_folder(
            input_dir=temp_dir, output_dir=None, min_rows=2, min_interval=1.0
        )

        # file1 should be cleaned
        assert summary["cleaned"] >= 1
        # file2 should be deleted (too few rows)
        assert summary["deleted_too_few_rows"] >= 1
        # file3 should be cleaned
        assert summary["cleaned"] >= 2

    def test_multiple_files_with_output_dir(self, temp_dir):
        """Test cleaning with output to different directory."""
        # Create input files
        input_dir = temp_dir / "input"
        input_dir.mkdir()

        file1 = input_dir / "file1.csv"
        file2 = input_dir / "file2.csv"

        df1 = pd.DataFrame({"Time(sec)": [1.0, 2.0, 3.0], "value": ["a", "b", "c"]})
        df1.to_csv(file1, index=False)

        df2 = pd.DataFrame({"Time(sec)": [5.0, 6.0, 7.0], "value": ["x", "y", "z"]})
        df2.to_csv(file2, index=False)

        output_dir = temp_dir / "output"

        summary = clean_marker_folder(
            input_dir=input_dir, output_dir=output_dir, min_rows=2, min_interval=0.5
        )

        # Check output files exist
        assert (output_dir / "file1.csv").exists()
        assert (output_dir / "file2.csv").exists()
        # Check original files still exist
        assert file1.exists()
        assert file2.exists()

    def test_nested_directory_structure(self, temp_dir):
        """Test cleaning with nested subdirectory structure."""
        # Create nested structure: input/subdir1/file1.csv, input/subdir2/file2.csv
        subdir1 = temp_dir / "subdir1"
        subdir2 = temp_dir / "subdir2"
        subdir1.mkdir()
        subdir2.mkdir()

        file1 = subdir1 / "file1.csv"
        file2 = subdir2 / "file2.csv"

        df1 = pd.DataFrame({"Time(sec)": [1.0, 2.0, 3.0], "value": ["a", "b", "c"]})
        df1.to_csv(file1, index=False)

        df2 = pd.DataFrame({"Time(sec)": [1.0, 2.0, 3.0], "value": ["x", "y", "z"]})
        df2.to_csv(file2, index=False)

        output_dir = temp_dir / "output"

        summary = clean_marker_folder(
            input_dir=temp_dir, output_dir=output_dir, min_rows=2, min_interval=0.5
        )

        # Check nested structure preserved
        assert (output_dir / "subdir1" / "file1.csv").exists()
        assert (output_dir / "subdir2" / "file2.csv").exists()

    def test_filter_hidden_files(self, temp_dir):
        """Test that hidden files (starting with .) are ignored."""
        # Create normal file
        normal_file = temp_dir / "normal.csv"
        df = pd.DataFrame({"Time(sec)": [1.0, 2.0, 3.0], "value": ["a", "b", "c"]})
        df.to_csv(normal_file, index=False)

        # Create hidden file (should be ignored)
        hidden_file = temp_dir / ".hidden.csv"
        df_hidden = pd.DataFrame({"Time(sec)": [1.0, 2.0], "value": ["x", "y"]})
        df_hidden.to_csv(hidden_file, index=False)

        summary = clean_marker_folder(
            input_dir=temp_dir, output_dir=None, min_rows=2, min_interval=0.5
        )

        # Only normal file should be processed
        assert summary["cleaned"] == 1
        # Hidden file should be ignored (not deleted)
        assert hidden_file.exists()

    def test_reference_time_column(self, temp_dir):
        """Test cleaning with reference_time column (fNIRS format)."""
        csv_path = temp_dir / "fnirs_marker.csv"
        df = pd.DataFrame(
            {
                "reference_time": [10.0, 20.0, 30.0, 40.0],
                "value": ["stim1", "stim2", "stim3", "stim4"],
            }
        )
        df.to_csv(csv_path, index=False)

        result = clean_marker_csv(
            csv_path=csv_path,
            time_col=None,  # Should auto-detect
            min_rows=2,
            min_interval=5.0,
        )

        assert result == "cleaned"
        cleaned_df = pd.read_csv(csv_path)
        # With min_interval=5.0, all markers should be kept (differences >= 10)
        assert len(cleaned_df) == 4

    def test_invalid_time_values(self, temp_dir):
        """Test handling of invalid time values."""
        csv_path = temp_dir / "test_invalid_times.csv"
        df = pd.DataFrame(
            {
                "Time(sec)": [1.0, "invalid", 3.0, None, 5.0],
                "value": ["a", "b", "c", "d", "e"],
            }
        )
        df.to_csv(csv_path, index=False)

        result = clean_marker_csv(csv_path=csv_path, min_rows=2, min_interval=0.5)

        # Should clean and keep only valid times
        assert result == "cleaned"
        cleaned_df = pd.read_csv(csv_path)
        # Should have valid times only
        assert len(cleaned_df) == 3
