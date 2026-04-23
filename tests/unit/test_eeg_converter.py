"""
Unit tests for EEG converter functions
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

from multichsync.eeg.converter import convert_eeg_format
from multichsync.eeg.batch import batch_convert_eeg_format


class TestConvertEegFormat:
    """Test suite for convert_eeg_format function"""

    @patch("multichsync.eeg.converter.read_eeg_file")
    @patch("multichsync.eeg.converter.write_eeg_file")
    def test_eeglab_to_brainvision(self, mock_write, mock_read, tmp_path):
        """Test EEGLAB to BrainVision conversion"""
        # Setup mock raw object
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1", "Ch2"]
        mock_raw.info = {"sfreq": 500}
        mock_raw.n_times = 1000
        mock_raw.times = [i / 500 for i in range(1000)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)

        # Setup mock parsed result
        mock_read.return_value = {
            "raw": mock_raw,
            "format": "eeglab",
            "file_path": str(tmp_path / "test.set"),
            "metadata": {"n_channels": 2, "sfreq": 500},
            "channels": [],
        }

        # Setup mock write
        mock_write.return_value = str(tmp_path / "convert" / "test.vhdr")

        # Create test input file
        input_file = tmp_path / "test.set"
        input_file.touch()

        # Call the function
        output_path = tmp_path / "output.vhdr"
        result_raw, result_path = convert_eeg_format(
            file_path=str(input_file),
            export_format="BrainVision",
            output_path=str(output_path),
            overwrite=True,
        )

        # Verify read was called
        mock_read.assert_called_once()

        # Verify write was called with correct format
        mock_write.assert_called_once()
        call_args = mock_write.call_args
        assert call_args.kwargs["export_format"] == "BrainVision"

        # Verify result
        assert result_raw is mock_raw
        assert "test.vhdr" in result_path

    @patch("multichsync.eeg.converter.read_eeg_file")
    @patch("multichsync.eeg.converter.write_eeg_file")
    def test_unsupported_format(self, mock_write, mock_read):
        """Test error handling for unsupported format"""
        # This should raise an error for unsupported format
        # The convert_eeg_to_format function validates the format
        from multichsync.eeg.converter import convert_eeg_to_format

        with pytest.raises(ValueError, match="不支持的输出格式"):
            convert_eeg_to_format(
                file_path="/fake/path.set", output_format="UnsupportedFormat"
            )

    @patch("multichsync.eeg.converter.read_eeg_file")
    @patch("multichsync.eeg.converter.write_eeg_file")
    def test_eeg_to_edf_format(self, mock_write, mock_read, tmp_path):
        """Test EEG to EDF conversion"""
        # Setup mock raw object
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1", "Ch2", "Ch3"]
        mock_raw.info = {"sfreq": 256}
        mock_raw.n_times = 512
        mock_raw.times = [i / 256 for i in range(512)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)

        # Setup mock parsed result
        mock_read.return_value = {
            "raw": mock_raw,
            "format": "curry",
            "file_path": str(tmp_path / "test.cdt"),
            "metadata": {"n_channels": 3, "sfreq": 256},
            "channels": [],
        }

        # Setup mock write
        mock_write.return_value = str(tmp_path / "convert" / "test.edf")

        # Create test input file
        input_file = tmp_path / "test.cdt"
        input_file.touch()

        # Call the function
        result_raw, result_path = convert_eeg_format(
            file_path=str(input_file), export_format="EDF", overwrite=True
        )

        # Verify write was called with EDF format
        call_args = mock_write.call_args
        assert call_args.kwargs["export_format"] == "EDF"

        # Verify result contains edf extension
        assert result_path.endswith(".edf")

    @patch("multichsync.eeg.converter.read_eeg_file")
    @patch("multichsync.eeg.converter.write_eeg_file")
    def test_custom_output_path(self, mock_write, mock_read, tmp_path):
        """Test conversion with custom output path"""
        # Setup mock
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1"]
        mock_raw.info = {"sfreq": 500}
        mock_raw.n_times = 100
        mock_raw.times = [i / 500 for i in range(100)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)

        mock_read.return_value = {"raw": mock_raw, "format": "eeglab"}
        mock_write.return_value = str(tmp_path / "custom" / "output.vhdr")

        # Create test input file
        input_file = tmp_path / "input.set"
        input_file.touch()

        # Call with custom output path
        custom_output = tmp_path / "custom_output.vhdr"
        result_raw, result_path = convert_eeg_format(
            file_path=str(input_file),
            export_format="BrainVision",
            output_path=str(custom_output),
        )

        # Verify output path was passed correctly
        call_args = mock_write.call_args
        assert "output_path" in call_args.kwargs

    @patch("multichsync.eeg.converter.read_eeg_file")
    @patch("multichsync.eeg.converter.write_eeg_file")
    def test_resampling_500hz_to_250hz(self, mock_write, mock_read, tmp_path):
        """Test resampling from 500Hz to 250Hz"""
        # Setup mock raw object with 500Hz sampling rate
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1", "Ch2"]
        mock_raw.info = {"sfreq": 500.0}
        mock_raw.n_times = 1000
        mock_raw.times = [i / 500 for i in range(1000)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)
        
        # Create a mock resampled raw object
        mock_resampled = MagicMock()
        mock_resampled.ch_names = ["Ch1", "Ch2"]
        mock_resampled.info = {"sfreq": 250.0}
        mock_resampled.n_times = 500
        mock_resampled.times = [i / 250 for i in range(500)]
        mock_resampled.annotations = MagicMock()
        mock_resampled.annotations.__len__ = MagicMock(return_value=0)
        
        # Mock the resample method
        mock_raw.resample = MagicMock(return_value=mock_resampled)
        
        # Setup mock parsed result
        mock_read.return_value = {
            "raw": mock_raw,
            "format": "eeglab",
            "file_path": str(tmp_path / "test.set"),
            "metadata": {"n_channels": 2, "sfreq": 500.0},
            "channels": [],
        }
        
        # Setup mock write
        mock_write.return_value = str(tmp_path / "convert" / "test.vhdr")
        
        # Create test input file
        input_file = tmp_path / "test.set"
        input_file.touch()
        
        # Call the function with sampling_rate=250
        result_raw, result_path = convert_eeg_format(
            file_path=str(input_file),
            export_format="BrainVision",
            output_path=str(tmp_path / "output.vhdr"),
            sampling_rate=250.0,
        )
        
        # Verify resample was called with 250Hz
        mock_raw.resample.assert_called_once_with(250.0, npad='auto')
        
        # Verify write was called with resampled raw
        call_args = mock_write.call_args
        assert call_args.kwargs["raw"] is mock_resampled
        assert call_args.kwargs["sampling_rate"] == 250.0

    @patch("multichsync.eeg.converter.read_eeg_file")
    @patch("multichsync.eeg.converter.write_eeg_file")
    def test_no_resampling_when_none(self, mock_write, mock_read, tmp_path):
        """Test no resampling when sampling_rate is None"""
        # Setup mock raw object
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1", "Ch2"]
        mock_raw.info = {"sfreq": 500.0}
        mock_raw.n_times = 1000
        mock_raw.times = [i / 500 for i in range(1000)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)
        
        # Mock the resample method (should not be called)
        mock_raw.resample = MagicMock()
        
        # Setup mock parsed result
        mock_read.return_value = {
            "raw": mock_raw,
            "format": "eeglab",
            "file_path": str(tmp_path / "test.set"),
            "metadata": {"n_channels": 2, "sfreq": 500.0},
            "channels": [],
        }
        
        # Setup mock write
        mock_write.return_value = str(tmp_path / "convert" / "test.vhdr")
        
        # Create test input file
        input_file = tmp_path / "test.set"
        input_file.touch()
        
        # Call the function without sampling_rate (default None)
        result_raw, result_path = convert_eeg_format(
            file_path=str(input_file),
            export_format="BrainVision",
            output_path=str(tmp_path / "output.vhdr"),
        )
        
        # Verify resample was NOT called
        mock_raw.resample.assert_not_called()
        
        # Verify write was called with original raw
        call_args = mock_write.call_args
        assert call_args.kwargs["raw"] is mock_raw
        assert call_args.kwargs.get("sampling_rate") is None

    @patch("multichsync.eeg.converter.read_eeg_file")
    @patch("multichsync.eeg.converter.write_eeg_file")
    def test_no_resampling_within_tolerance(self, mock_write, mock_read, tmp_path):
        """Test no resampling when rates are equal within 0.1 Hz tolerance"""
        # Setup mock raw object with 250.05 Hz sampling rate
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1", "Ch2"]
        mock_raw.info = {"sfreq": 250.05}
        mock_raw.n_times = 1000
        mock_raw.times = [i / 250.05 for i in range(1000)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)
        
        # Mock the resample method (should not be called)
        mock_raw.resample = MagicMock()
        
        # Setup mock parsed result
        mock_read.return_value = {
            "raw": mock_raw,
            "format": "eeglab",
            "file_path": str(tmp_path / "test.set"),
            "metadata": {"n_channels": 2, "sfreq": 250.05},
            "channels": [],
        }
        
        # Setup mock write
        mock_write.return_value = str(tmp_path / "convert" / "test.vhdr")
        
        # Create test input file
        input_file = tmp_path / "test.set"
        input_file.touch()
        
        # Call the function with sampling_rate=250.0 (difference 0.05 < 0.1)
        result_raw, result_path = convert_eeg_format(
            file_path=str(input_file),
            export_format="BrainVision",
            output_path=str(tmp_path / "output.vhdr"),
            sampling_rate=250.0,
        )
        
        # Verify resample was NOT called (difference within tolerance)
        mock_raw.resample.assert_not_called()
        
        # Verify write was called with original raw
        call_args = mock_write.call_args
        assert call_args.kwargs["raw"] is mock_raw
        assert call_args.kwargs["sampling_rate"] == 250.0


class TestBatchConvertEegFormat:
    """Test suite for batch_convert_eeg_format function"""

    @patch("multichsync.eeg.batch.convert_eeg_format")
    def test_empty_directory(self, mock_convert, tmp_path):
        """Test handling of empty input directory"""
        # Create an empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Call the function
        result = batch_convert_eeg_format(
            input_dir=str(empty_dir), export_format="BrainVision"
        )

        # Verify empty list is returned
        assert result == []
        # Verify convert was not called
        mock_convert.assert_not_called()

    @patch("multichsync.eeg.batch.convert_eeg_format")
    def test_recursive_option(self, mock_convert, tmp_path):
        """Test recursive directory search"""
        # Create directory structure with EEG files
        # /input/
        #   /subdir1/
        #     file1.set
        #   /subdir2/
        #     file2.set
        #   root.set

        input_dir = tmp_path / "input"
        input_dir.mkdir()

        subdir1 = input_dir / "subdir1"
        subdir1.mkdir()

        subdir2 = input_dir / "subdir2"
        subdir2.mkdir()

        # Create test files
        (input_dir / "root.set").touch()
        (subdir1 / "file1.set").touch()
        (subdir2 / "file2.set").touch()

        # Setup mock to return valid results
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1"]
        mock_raw.info = {"sfreq": 500}
        mock_raw.n_times = 100
        mock_raw.times = [i / 500 for i in range(100)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)

        def mock_convert_side_effect(
            file_path, export_format, output_path=None, **kwargs
        ):
            return mock_raw, str(output_path) if output_path else "/fake/output.vhdr"

        mock_convert.side_effect = mock_convert_side_effect

        # Test non-recursive (should only find root.set)
        result_non_recursive = batch_convert_eeg_format(
            input_dir=str(input_dir), export_format="BrainVision", recursive=False
        )

        # Reset mock
        mock_convert.reset_mock()

        # Test recursive (should find all .set files)
        result_recursive = batch_convert_eeg_format(
            input_dir=str(input_dir), export_format="BrainVision", recursive=True
        )

        # Verify recursive finds more files
        assert len(result_recursive) >= len(result_non_recursive)

    @patch("multichsync.eeg.batch.convert_eeg_format")
    def test_batch_with_unsupported_files(self, mock_convert, tmp_path):
        """Test batch conversion with unsupported file types"""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Create only unsupported files
        (input_dir / "readme.txt").write_text("This is a text file")
        (input_dir / "data.csv").write_text("col1,col2\n1,2\n3,4")

        # Call the function
        result = batch_convert_eeg_format(
            input_dir=str(input_dir), export_format="BrainVision"
        )

        # Verify empty list is returned
        assert result == []
        mock_convert.assert_not_called()

    @patch("multichsync.eeg.batch.convert_eeg_format")
    def test_batch_convert_to_eeglab_format(self, mock_convert, tmp_path):
        """Test batch conversion to EEGLAB format"""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Create test file
        test_file = input_dir / "test.set"
        test_file.touch()

        # Setup mock
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1"]
        mock_raw.info = {"sfreq": 500}
        mock_raw.n_times = 100
        mock_raw.times = [i / 500 for i in range(100)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)

        def mock_convert_side_effect(
            file_path, export_format, output_path=None, **kwargs
        ):
            return mock_raw, str(output_path) if output_path else "/fake/output.set"

        mock_convert.side_effect = mock_convert_side_effect

        # Call batch conversion
        result = batch_convert_eeg_format(
            input_dir=str(input_dir), export_format="EEGLAB"
        )

        # Verify conversion was called with correct format
        assert mock_convert.called
        call_args = mock_convert.call_args
        assert call_args.kwargs["export_format"] == "EEGLAB"

    @patch("multichsync.eeg.batch.convert_eeg_format")
    def test_batch_with_sampling_rate(self, mock_convert, tmp_path):
        """Test batch conversion with sampling_rate parameter"""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Create test file
        test_file = input_dir / "test.set"
        test_file.touch()

        # Setup mock
        mock_raw = MagicMock()
        mock_raw.ch_names = ["Ch1"]
        mock_raw.info = {"sfreq": 500}
        mock_raw.n_times = 100
        mock_raw.times = [i / 500 for i in range(100)]
        mock_raw.annotations = MagicMock()
        mock_raw.annotations.__len__ = MagicMock(return_value=0)

        def mock_convert_side_effect(
            file_path, export_format, output_path=None, **kwargs
        ):
            # Verify sampling_rate is passed in kwargs
            assert "sampling_rate" in kwargs
            assert kwargs["sampling_rate"] == 250.0
            return mock_raw, str(output_path) if output_path else "/fake/output.vhdr"

        mock_convert.side_effect = mock_convert_side_effect

        # Call batch conversion with sampling_rate
        result = batch_convert_eeg_format(
            input_dir=str(input_dir),
            export_format="BrainVision",
            sampling_rate=250.0,
        )

        # Verify conversion was called
        assert mock_convert.called
        call_args = mock_convert.call_args
        assert call_args.kwargs["sampling_rate"] == 250.0

    @patch("multichsync.eeg.batch.convert_eeg_format")
    def test_batch_nonexistent_directory(self, mock_convert, tmp_path):
        """Test batch conversion with non-existent directory"""
        nonexistent_dir = tmp_path / "nonexistent"

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            batch_convert_eeg_format(
                input_dir=str(nonexistent_dir), export_format="BrainVision"
            )
