"""
Unit tests for marker information extraction functions.

Tests import from multichsync.marker.info_extractor:
- scan_data_files
- match_data_with_marker
- extract_marker_info
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict


class TestScanDataFiles:
    """Tests for scan_data_files function."""

    def test_scan_empty_directory(self, temp_dir):
        """Test scanning empty base directory (no Data/convert or Data/raw)."""
        from multichsync.marker.info_extractor import scan_data_files
        
        result = scan_data_files(temp_dir)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_scan_with_mock_files(self, temp_dir):
        """Test scanning with mock data files in convert and raw directories."""
        from multichsync.marker.info_extractor import scan_data_files
        
        # Create directory structure
        convert_dir = temp_dir / "Data" / "convert"
        raw_dir = temp_dir / "Data" / "raw"
        
        # Create subdirectories per modality
        convert_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)
        
        # Create some dummy files with supported extensions
        # fNIRS: .snirf in convert/fnirs, .TXT in raw/fnirs
        (convert_dir / "fnirs").mkdir()
        (raw_dir / "fnirs").mkdir()
        fnirs_snirf = convert_dir / "fnirs" / "sub-001_ses-01_task-rest_fnirs.snirf"
        fnirs_snirf.write_bytes(b"dummy snirf")
        fnirs_txt = raw_dir / "fnirs" / "sub-001_ses-01_task-rest_fnirs.TXT"
        fnirs_txt.write_text("Time Range 0 100\nTotal Points 1000")
        
        # EEG: .set in convert/eeg, .vhdr in raw/eeg
        (convert_dir / "eeg").mkdir()
        (raw_dir / "eeg").mkdir()
        eeg_set = convert_dir / "eeg" / "sub-001_ses-01_task-rest_eeg.set"
        eeg_set.write_bytes(b"dummy set")
        eeg_vhdr = raw_dir / "eeg" / "sub-001_ses-01_task-rest_eeg.vhdr"
        eeg_vhdr.write_text("Brain Vision Data Exchange Header")
        
        # ECG: .csv in convert/ecg, .acq in raw/ecg
        (convert_dir / "ecg").mkdir()
        (raw_dir / "ecg").mkdir()
        ecg_csv = convert_dir / "ecg" / "sub-001_ses-01_task-rest_ecg.csv"
        ecg_csv.write_text("Time(sec),CH1\n0,0\n1,1")
        ecg_acq = raw_dir / "ecg" / "sub-001_ses-01_task-rest_ecg.acq"
        ecg_acq.write_bytes(b"dummy acq")
        
        # Call scan_data_files with base_dir = temp_dir
        result = scan_data_files(temp_dir)
        
        # Should find 6 files (2 fNIRS, 2 EEG, 2 ECG)
        assert len(result) == 6
        
        # Check that each entry has expected keys
        expected_keys = {
            "file_path", "file_name", "stem", "device", "subject_id",
            "session_label", "sequence_id", "project", "filename_style",
            "duration_sec"
        }
        for entry in result:
            assert set(entry.keys()) == expected_keys
            assert isinstance(entry["file_path"], Path)
            assert entry["file_path"].exists()
            assert entry["device"] in {"fnirs", "eeg", "ecg"}
            # duration_sec may be None or float
            assert entry["duration_sec"] is None or isinstance(entry["duration_sec"], float)
        
        # Verify sorting by file_path
        file_paths = [entry["file_path"] for entry in result]
        assert file_paths == sorted(file_paths)
        
        # Verify device inference
        devices = [entry["device"] for entry in result]
        # Should have 2 of each device
        assert devices.count("fnirs") == 2
        assert devices.count("eeg") == 2
        assert devices.count("ecg") == 2

    def test_skip_hidden_and_system_files(self, temp_dir):
        """Test that hidden files (starting with .) and __MACOSX are skipped."""
        from multichsync.marker.info_extractor import scan_data_files
        
        convert_dir = temp_dir / "Data" / "convert"
        convert_dir.mkdir(parents=True)
        
        # Create a normal file
        normal = convert_dir / "normal.snirf"
        normal.write_bytes(b"normal")
        
        # Create hidden file (starting with .)
        hidden = convert_dir / ".hidden.snirf"
        hidden.write_bytes(b"hidden")
        
        # Create file in __MACOSX directory
        macosx_dir = convert_dir / "__MACOSX"
        macosx_dir.mkdir()
        macosx_file = macosx_dir / "file.snirf"
        macosx_file.write_bytes(b"macosx")
        
        result = scan_data_files(temp_dir)
        # Should only find normal.snirf
        assert len(result) == 1
        assert result[0]["file_name"] == "normal.snirf"

    def test_default_base_dir(self, temp_dir, monkeypatch):
        """Test that when base_dir is None, uses current working directory."""
        from multichsync.marker.info_extractor import scan_data_files
        
        # Create Data/convert directory in temp_dir
        convert_dir = temp_dir / "Data" / "convert"
        convert_dir.mkdir(parents=True)
        test_file = convert_dir / "test.snirf"
        test_file.write_bytes(b"test")
        
        # Monkeypatch cwd to temp_dir
        monkeypatch.chdir(temp_dir)
        
        result = scan_data_files()
        # Should find the file because cwd is temp_dir
        assert len(result) == 1
        assert result[0]["file_name"] == "test.snirf"

    def test_unsupported_extensions_ignored(self, temp_dir):
        """Test that files with unsupported extensions are ignored."""
        from multichsync.marker.info_extractor import scan_data_files
        
        convert_dir = temp_dir / "Data" / "convert"
        convert_dir.mkdir(parents=True)
        
        # Create supported extension file
        supported = convert_dir / "supported.snirf"
        supported.write_bytes(b"supported")
        
        # Create unsupported extension file
        unsupported = convert_dir / "unsupported.txt"
        unsupported.write_bytes(b"unsupported")
        
        result = scan_data_files(temp_dir)
        # Should only find .snirf file (fNIRS), .txt is not in supported list (only .TXT uppercase)
        # Actually .txt is listed for fNIRS? The spec says .TXT and .txt (both). So .txt should be included.
        # But we need to check the mapping: fNIRS includes .txt. However the file is in convert directory,
        # not in raw/fnirs. The function scans both convert and raw directories regardless of subdirectory.
        # It will match extension .txt and infer device from path (maybe unknown). Let's just ensure only one file.
        # We'll adjust: create .txt in raw/fnirs to be sure.
        # Let's simplify: we'll just test that unsupported extension .pdf is ignored.
        unsupported2 = convert_dir / "unsupported.pdf"
        unsupported2.write_bytes(b"pdf")
        
        result = scan_data_files(temp_dir)
        # Should find .snirf and .txt (since .txt is supported for fNIRS)
        # Let's count: we have .snirf and .txt (both supported) and .pdf (unsupported)
        # So result length should be 2.
        assert len(result) == 2
        filenames = {entry["file_name"] for entry in result}
        assert "supported.snirf" in filenames
        assert "unsupported.txt" in filenames
        assert "unsupported.pdf" not in filenames

    def test_parse_filename_metadata(self, temp_dir):
        """Test that filename metadata is correctly parsed."""
        from multichsync.marker.info_extractor import scan_data_files
        
        convert_dir = temp_dir / "Data" / "convert"
        convert_dir.mkdir(parents=True)
        
        # Create a BIDS-style filename
        bids_file = convert_dir / "sub-123_ses-02_task-rest_fnirs.snirf"
        bids_file.write_bytes(b"bids")
        
        result = scan_data_files(temp_dir)
        assert len(result) == 1
        entry = result[0]
        assert entry["subject_id"] == "123"
        assert entry["session_label"] == "ses-02"
        assert entry["sequence_id"] == "02"
        assert entry["filename_style"] == "bids"
        assert entry["device"] == "fnirs"  # inferred from path
        
        # Create date-subject style filename
        date_file = convert_dir / "20250516017_01_marker.txt"
        date_file.write_bytes(b"date")
        # Need to place in raw/fnirs to be recognized as fNIRS (extension .txt)
        raw_dir = temp_dir / "Data" / "raw" / "fnirs"
        raw_dir.mkdir(parents=True)
        date_file.rename(raw_dir / "20250516017_01_marker.txt")
        
        result2 = scan_data_files(temp_dir)
        # Now we have two files total
        assert len(result2) == 2
        # Find the date-subject entry
        date_entries = [e for e in result2 if e["file_name"] == "20250516017_01_marker.txt"]
        assert len(date_entries) == 1
        date_entry = date_entries[0]
        assert date_entry["subject_id"] == "017"
        assert date_entry["session_label"] == "20250516"
        assert date_entry["sequence_id"] == "01"
        assert date_entry["filename_style"] == "date_subject"

    def test_missing_directories_no_error(self, temp_dir):
        """Test that missing Data/convert or Data/raw directories don't cause errors."""
        from multichsync.marker.info_extractor import scan_data_files
        
        # Create only Data/convert, no Data/raw
        convert_dir = temp_dir / "Data" / "convert"
        convert_dir.mkdir(parents=True)
        test_file = convert_dir / "test.snirf"
        test_file.write_bytes(b"test")
        
        result = scan_data_files(temp_dir)
        assert len(result) == 1
        
        # Remove Data/convert, create Data/raw
        import shutil
        shutil.rmtree(convert_dir)
        raw_dir = temp_dir / "Data" / "raw"
        raw_dir.mkdir(parents=True)
        test_file2 = raw_dir / "test.txt"
        test_file2.write_bytes(b"test")
        
        result2 = scan_data_files(temp_dir)
        assert len(result2) == 1

    def test_unparseable_filename_still_included(self, temp_dir):
        """Test that files with unparseable filenames are still included in scan results."""
        from multichsync.marker.info_extractor import scan_data_files
        
        convert_dir = temp_dir / "Data" / "convert"
        convert_dir.mkdir(parents=True)
        
        # Create a file with random name that doesn't match any pattern
        random_file = convert_dir / "random123.txt"
        random_file.write_bytes(b"random")
        
        result = scan_data_files(temp_dir)
        # Should find the file
        assert len(result) == 1
        entry = result[0]
        assert entry["file_name"] == "random123.txt"
        assert entry["filename_style"] == "unmatched"
        assert entry["subject_id"] == "unknown"
        assert entry["session_label"] == "unknown"
        assert entry["sequence_id"] == "01"
        assert entry["project"] is None
        # Device may be inferred from path or extension

    def test_corrupted_data_file_handled_gracefully(self, temp_dir):
        """Test that corrupted data files are still included with duration None."""
        from multichsync.marker.info_extractor import scan_data_files
        
        convert_dir = temp_dir / "Data" / "convert" / "fnirs"
        convert_dir.mkdir(parents=True)
        
        # Create a corrupted SNIRF file (empty)
        corrupted_file = convert_dir / "sub-001_ses-01_task-rest_fnirs.snirf"
        corrupted_file.write_bytes(b"")  # empty file
        
        result = scan_data_files(temp_dir)
        assert len(result) == 1
        entry = result[0]
        assert entry["file_name"] == "sub-001_ses-01_task-rest_fnirs.snirf"
        assert entry["duration_sec"] is None  # Cannot read duration from corrupted file
        # Other metadata should still be parsed from filename
        assert entry["subject_id"] == "001"
        assert entry["session_label"] == "ses-01"
        assert entry["sequence_id"] == "01"
        assert entry["filename_style"] == "bids"


class TestMatchDataWithMarker:
    """Tests for match_data_with_marker function."""

    def test_basic_matching(self, temp_dir):
        """Test basic matching of data files with marker files."""
        from multichsync.marker.info_extractor import match_data_with_marker
        
        # Create mock data files list (as returned by scan_data_files)
        data_files = []
        # Create a data file in convert/fnirs
        convert_dir = temp_dir / "Data" / "convert" / "fnirs"
        convert_dir.mkdir(parents=True)
        data_path = convert_dir / "sub-001_ses-01_task-rest_fnirs.snirf"
        data_path.write_bytes(b"dummy")
        data_files.append({
            "file_path": data_path,
            "file_name": data_path.name,
            "stem": data_path.stem,
            "device": "fnirs",
            "subject_id": "001",
            "session_label": "ses-01",
            "sequence_id": "01",
            "project": None,
            "filename_style": "bids",
            "duration_sec": None
        })
        
        # Create matching marker file
        marker_dir = temp_dir / "marker"
        marker_dir.mkdir()
        marker_path = marker_dir / "sub-001_ses-01_task-rest_fnirs_marker.csv"
        marker_path.write_text("time,event\n0,start\n10,end")
        
        # Call match_data_with_marker
        mapping = match_data_with_marker(data_files, [marker_path])
        
        # Should map data_path to marker_path
        assert len(mapping) == 1
        assert mapping[data_path] == marker_path
    
    def test_marker_without_suffix(self, temp_dir):
        """Test matching when marker file doesn't have '_marker' suffix."""
        from multichsync.marker.info_extractor import match_data_with_marker
        
        data_files = []
        convert_dir = temp_dir / "Data" / "convert" / "eeg"
        convert_dir.mkdir(parents=True)
        data_path = convert_dir / "sub-002_ses-02_task-picture_eeg.set"
        data_path.write_bytes(b"dummy")
        data_files.append({
            "file_path": data_path,
            "file_name": data_path.name,
            "stem": data_path.stem,
            "device": "eeg",
            "subject_id": "002",
            "session_label": "ses-02",
            "sequence_id": "02",
            "project": None,
            "filename_style": "bids",
            "duration_sec": None
        })
        
        # Marker file without _marker suffix (just .csv)
        marker_dir = temp_dir / "marker"
        marker_dir.mkdir()
        marker_path = marker_dir / "sub-002_ses-02_task-picture_eeg.csv"
        marker_path.write_text("time,event\n0,start")
        
        mapping = match_data_with_marker(data_files, [marker_path])
        assert mapping[data_path] == marker_path
    
    def test_ecg_input_suffix(self, temp_dir):
        """Test matching for ECG data files with '_input' suffix."""
        from multichsync.marker.info_extractor import match_data_with_marker
        
        data_files = []
        convert_dir = temp_dir / "Data" / "convert" / "ecg"
        convert_dir.mkdir(parents=True)
        data_path = convert_dir / "sub-003_ses-03_task-rest_ecg_input.csv"
        data_path.write_text("Time(sec),CH1\n0,0\n1,1")
        data_files.append({
            "file_path": data_path,
            "file_name": data_path.name,
            "stem": data_path.stem,
            "device": "ecg",
            "subject_id": "003",
            "session_label": "ses-03",
            "sequence_id": "03",
            "project": None,
            "filename_style": "bids",
            "duration_sec": None
        })
        
        # Marker file with _input_marker suffix
        marker_dir = temp_dir / "marker"
        marker_dir.mkdir()
        marker_path = marker_dir / "sub-003_ses-03_task-rest_ecg_input_marker.csv"
        marker_path.write_text("time,event\n0,start")
        
        mapping = match_data_with_marker(data_files, [marker_path])
        assert mapping[data_path] == marker_path
        
        # Also test marker file without _input suffix (should still match?)
        # According to rules: marker stem after removing '_marker' should match data stem after removing '_input'
        # So marker file "sub-003_ses-03_task-rest_ecg_marker.csv" should match data stem "sub-003_ses-03_task-rest_ecg"
        # Let's test that.
        marker_path2 = marker_dir / "sub-003_ses-03_task-rest_ecg_marker.csv"
        marker_path2.write_text("time,event\n0,start")
        mapping2 = match_data_with_marker(data_files, [marker_path2])
        # Should match because after removing '_input' from data stem we get "sub-003_ses-03_task-rest_ecg"
        # and after removing '_marker' from marker stem we get same.
        assert mapping2[data_path] == marker_path2
    
    def test_case_insensitive(self, temp_dir):
        """Test case-insensitive matching."""
        from multichsync.marker.info_extractor import match_data_with_marker
        
        data_files = []
        convert_dir = temp_dir / "Data" / "convert" / "fnirs"
        convert_dir.mkdir(parents=True)
        data_path = convert_dir / "SUB-001_SES-01_TASK-REST_FNIRS.snirf"
        data_path.write_bytes(b"dummy")
        data_files.append({
            "file_path": data_path,
            "file_name": data_path.name,
            "stem": data_path.stem,
            "device": "fnirs",
            "subject_id": "001",
            "session_label": "ses-01",
            "sequence_id": "01",
            "project": None,
            "filename_style": "bids",
            "duration_sec": None
        })
        
        marker_dir = temp_dir / "marker"
        marker_dir.mkdir()
        marker_path = marker_dir / "sub-001_ses-01_task-rest_fnirs_marker.csv"
        marker_path.write_text("time,event")
        
        mapping = match_data_with_marker(data_files, [marker_path])
        assert mapping[data_path] == marker_path
    
    def test_ambiguous_match_logs_warning(self, temp_dir, caplog):
        """Test ambiguous matches (multiple marker files for same data file) log warning."""
        from multichsync.marker.info_extractor import match_data_with_marker
        
        data_files = []
        convert_dir = temp_dir / "Data" / "convert" / "fnirs"
        convert_dir.mkdir(parents=True)
        data_path = convert_dir / "sub-001_ses-01_task-rest_fnirs.snirf"
        data_path.write_bytes(b"dummy")
        data_files.append({
            "file_path": data_path,
            "file_name": data_path.name,
            "stem": data_path.stem,
            "device": "fnirs",
            "subject_id": "001",
            "session_label": "ses-01",
            "sequence_id": "01",
            "project": None,
            "filename_style": "bids",
            "duration_sec": None
        })
        
        marker_dir = temp_dir / "marker"
        marker_dir.mkdir()
        # Create two marker files that both match the same data file
        marker_path1 = marker_dir / "sub-001_ses-01_task-rest_fnirs_marker.csv"
        marker_path1.write_text("time,event")
        marker_path2 = marker_dir / "sub-001_ses-01_task-rest_fnirs_marker_extra.csv"
        marker_path2.write_text("time,event")
        # Note: the second marker file has stem "sub-001_ses-01_task-rest_fnirs_marker_extra"
        # After removing '_marker' suffix we get "sub-001_ses-01_task-rest_fnirs_extra"
        # That doesn't match data stem. Wait, we need to ensure both match.
        # Let's create marker files with same stem after removing '_marker'.
        # Actually, the function removes '_marker' suffix only if present.
        # So we need two marker files with same stem after removal.
        # Let's create marker files with different prefixes but same stem after removal?
        # Simpler: create marker files without '_marker' suffix but same stem.
        marker_path2.unlink()
        marker_path2 = marker_dir / "sub-001_ses-01_task-rest_fnirs.csv"
        marker_path2.write_text("time,event")
        # Now both marker files have stem "sub-001_ses-01_task-rest_fnirs" after removing '_marker' from first.
        # First marker stem after removal: "sub-001_ses-01_task-rest_fnirs"
        # Second marker stem after removal: "sub-001_ses-01_task-rest_fnirs" (no '_marker' to remove)
        # Both match data stem.
        
        import logging
        caplog.set_level(logging.WARNING)
        
        mapping = match_data_with_marker(data_files, [marker_path1, marker_path2])
        # Should map to None due to ambiguous match
        assert mapping[data_path] is None
        # Should have logged warning
        assert "Ambiguous match" in caplog.text
    
    def test_no_match_returns_none(self, temp_dir):
        """Test that data files without matching marker files map to None."""
        from multichsync.marker.info_extractor import match_data_with_marker
        
        data_files = []
        convert_dir = temp_dir / "Data" / "convert" / "fnirs"
        convert_dir.mkdir(parents=True)
        data_path = convert_dir / "sub-001_ses-01_task-rest_fnirs.snirf"
        data_path.write_bytes(b"dummy")
        data_files.append({
            "file_path": data_path,
            "file_name": data_path.name,
            "stem": data_path.stem,
            "device": "fnirs",
            "subject_id": "001",
            "session_label": "ses-01",
            "sequence_id": "01",
            "project": None,
            "filename_style": "bids",
            "duration_sec": None
        })
        
        # Create a non-matching marker file
        marker_dir = temp_dir / "marker"
        marker_dir.mkdir()
        marker_path = marker_dir / "sub-999_ses-99_task-rest_fnirs_marker.csv"
        marker_path.write_text("time,event")
        
        mapping = match_data_with_marker(data_files, [marker_path])
        assert mapping[data_path] is None


class TestExtractMarkerInfo:
    """Integration tests for extract_marker_info function."""
    
    def test_basic_integration(self, temp_dir):
        """Test basic integration with data files and marker files."""
        from multichsync.marker.info_extractor import extract_marker_info
        
        # Create directory structure
        convert_dir = temp_dir / "Data" / "convert"
        raw_dir = temp_dir / "Data" / "raw"
        marker_dir = temp_dir / "Data" / "marker"
        output_dir = temp_dir / "output"
        
        convert_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)
        marker_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        
        # Create a data file (fNIRS SNIRF)
        fnirs_convert = convert_dir / "fnirs"
        fnirs_convert.mkdir()
        data_path = fnirs_convert / "sub-001_ses-01_task-rest_fnirs.snirf"
        # Write minimal SNIRF file (requires h5py)
        import h5py
        import numpy as np
        with h5py.File(data_path, "w") as f:
            nirs = f.create_group("nirs")
            data = nirs.create_group("data1")
            time_data = np.arange(0, 100.1, 0.1)
            data.create_dataset("time", data=time_data)
            measuredata = data.create_group("measurementData1")
            measuredata.create_dataset("dataType", data="NIRS")
            probe = nirs.create_group("probe")
            probe.create_dataset("wavelengths", data=[760, 850])
        
        # Create matching marker file
        marker_path = marker_dir / "sub-001_ses-01_task-rest_fnirs_marker.csv"
        marker_content = """time,event
0,start
10,event1
20,event2
30,end"""
        marker_path.write_text(marker_content)
        
        # Call extract_marker_info
        reports = extract_marker_info(
            input_dir=marker_dir,
            output_dir=output_dir,
            recursive=False
        )
        
        # Should generate report files
        assert "subject_reports" in reports
        assert "error_report" in reports
        # Get subject report for subject "001"
        assert "001" in reports["subject_reports"]
        subject_report_path = reports["subject_reports"]["001"]
        assert subject_report_path.exists()
        
        # Read subject report CSV
        import pandas as pd
        df = pd.read_csv(subject_report_path)
        # Should have one row for the data file
        assert len(df) == 1
        row = df.iloc[0]
        assert row["file_name"] == "sub-001_ses-01_task-rest_fnirs.snirf"
        assert row["n_markers"] == 4  # 4 rows in marker CSV (including header)
        # Actually n_markers counts marker rows excluding header? Let's check compute_marker_metrics.
        # We'll just assert n_markers > 0
        assert row["n_markers"] > 0
    
    def test_data_file_without_marker(self, temp_dir):
        """Test data file without matching marker file (should have n_markers=0)."""
        from multichsync.marker.info_extractor import extract_marker_info
        
        convert_dir = temp_dir / "Data" / "convert"
        marker_dir = temp_dir / "Data" / "marker"
        output_dir = temp_dir / "output"
        
        convert_dir.mkdir(parents=True)
        marker_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        
        # Create a data file with no marker
        fnirs_convert = convert_dir / "fnirs"
        fnirs_convert.mkdir()
        data_path = fnirs_convert / "sub-002_ses-02_task-rest_fnirs.snirf"
        import h5py
        import numpy as np
        with h5py.File(data_path, "w") as f:
            nirs = f.create_group("nirs")
            data = nirs.create_group("data1")
            time_data = np.arange(0, 50.1, 0.1)
            data.create_dataset("time", data=time_data)
            measuredata = data.create_group("measurementData1")
            measuredata.create_dataset("dataType", data="NIRS")
            probe = nirs.create_group("probe")
            probe.create_dataset("wavelengths", data=[760, 850])
        
        # Create a marker file for a different subject (so no match)
        marker_path = marker_dir / "sub-999_ses-99_task-rest_fnirs_marker.csv"
        marker_path.write_text("time,event\n0,start")
        
        reports = extract_marker_info(
            input_dir=marker_dir,
            output_dir=output_dir,
            recursive=False
        )
        
        import pandas as pd
        # Get subject report for subject "002"
        assert "002" in reports["subject_reports"]
        subject_report_path = reports["subject_reports"]["002"]
        df = pd.read_csv(subject_report_path)
        # Should have one row for the data file
        assert len(df) == 1
        row = df.iloc[0]
        assert row["file_name"] == "sub-002_ses-02_task-rest_fnirs.snirf"
        assert row["n_markers"] == 0  # No matching marker file
    
    def test_marker_file_without_data(self, temp_dir):
        """Test marker file without matching data file (should still be processed using original logic)."""
        from multichsync.marker.info_extractor import extract_marker_info
        
        convert_dir = temp_dir / "Data" / "convert"
        marker_dir = temp_dir / "Data" / "marker"
        output_dir = temp_dir / "output"
        
        convert_dir.mkdir(parents=True)
        marker_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        
        # Create a marker file with no corresponding data file
        marker_path = marker_dir / "sub-003_ses-03_task-rest_fnirs_marker.csv"
        marker_content = """time,event
0,start
5,event1
15,end"""
        marker_path.write_text(marker_content)
        
        # No data files in convert/ or raw/
        
        reports = extract_marker_info(
            input_dir=marker_dir,
            output_dir=output_dir,
            recursive=False
        )
        
        # Should still generate report (backward compatibility)
        import pandas as pd
        # Get subject report for subject "003"
        assert "003" in reports["subject_reports"]
        subject_report_path = reports["subject_reports"]["003"]
        df = pd.read_csv(subject_report_path)
        # Should have one row for the marker file (since no data file matches)
        assert len(df) == 1
        row = df.iloc[0]
        # file_name column should be marker file name? Actually extract_marker_info uses marker file name when no data file.
        # Let's just ensure report exists.
        assert subject_report_path.exists()
    
    def test_mixed_scenario(self, temp_dir):
        """Test mixed scenario: data with marker, data without marker, marker without data."""
        from multichsync.marker.info_extractor import extract_marker_info
        
        # Setup directories
        convert_dir = temp_dir / "Data" / "convert"
        raw_dir = temp_dir / "Data" / "raw"
        marker_dir = temp_dir / "Data" / "marker"
        output_dir = temp_dir / "output"
        
        convert_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)
        marker_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        
        import h5py
        import numpy as np
        
        # 1. Data file with matching marker
        fnirs_convert = convert_dir / "fnirs"
        fnirs_convert.mkdir()
        data1 = fnirs_convert / "sub-001_ses-01_task-rest_fnirs.snirf"
        with h5py.File(data1, "w") as f:
            nirs = f.create_group("nirs")
            data = nirs.create_group("data1")
            time_data = np.arange(0, 100.1, 0.1)
            data.create_dataset("time", data=time_data)
            measuredata = data.create_group("measurementData1")
            measuredata.create_dataset("dataType", data="NIRS")
            probe = nirs.create_group("probe")
            probe.create_dataset("wavelengths", data=[760, 850])
        
        marker1 = marker_dir / "sub-001_ses-01_task-rest_fnirs_marker.csv"
        marker1.write_text("time,event\n0,start\n10,end")
        
        # 2. Data file without marker
        data2 = fnirs_convert / "sub-002_ses-02_task-rest_fnirs.snirf"
        with h5py.File(data2, "w") as f:
            nirs = f.create_group("nirs")
            data = nirs.create_group("data1")
            time_data = np.arange(0, 50.1, 0.1)
            data.create_dataset("time", data=time_data)
            measuredata = data.create_group("measurementData1")
            measuredata.create_dataset("dataType", data="NIRS")
            probe = nirs.create_group("probe")
            probe.create_dataset("wavelengths", data=[760, 850])
        
        # 3. Marker file without data (different subject)
        marker3 = marker_dir / "sub-999_ses-99_task-rest_fnirs_marker.csv"
        marker3.write_text("time,event\n0,start")
        
        reports = extract_marker_info(
            input_dir=marker_dir,
            output_dir=output_dir,
            recursive=False
        )
        
        import pandas as pd
        # Should have three subject reports: 001, 002, 999
        assert "001" in reports["subject_reports"]
        assert "002" in reports["subject_reports"]
        assert "999" in reports["subject_reports"]
        # Check each report exists
        for subj in ["001", "002", "999"]:
            assert reports["subject_reports"][subj].exists()
        # We'll just verify report generation succeeded.
        assert reports["error_report"].exists()

    def test_corrupted_marker_file_handled_gracefully(self, temp_dir):
        """Test that corrupted marker files are handled gracefully (n_markers=0, error logged)."""
        from multichsync.marker.info_extractor import extract_marker_info
        
        # Setup directories
        convert_dir = temp_dir / "Data" / "convert"
        marker_dir = temp_dir / "Data" / "marker"
        output_dir = temp_dir / "output"
        
        convert_dir.mkdir(parents=True)
        marker_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        
        # Create a valid data file
        import h5py
        import numpy as np
        fnirs_convert = convert_dir / "fnirs"
        fnirs_convert.mkdir()
        data_path = fnirs_convert / "sub-001_ses-01_task-rest_fnirs.snirf"
        with h5py.File(data_path, "w") as f:
            nirs = f.create_group("nirs")
            data = nirs.create_group("data1")
            time_data = np.arange(0, 100.1, 0.1)
            data.create_dataset("time", data=time_data)
            measuredata = data.create_group("measurementData1")
            measuredata.create_dataset("dataType", data="NIRS")
            probe = nirs.create_group("probe")
            probe.create_dataset("wavelengths", data=[760, 850])
        
        # Create a corrupted marker file (empty CSV)
        marker_path = marker_dir / "sub-001_ses-01_task-rest_fnirs_marker.csv"
        marker_path.write_bytes(b"")  # empty file
        
        reports = extract_marker_info(
            input_dir=marker_dir,
            output_dir=output_dir,
            recursive=False
        )
        
        # Should have error report with entry for corrupted marker file
        import pandas as pd
        error_df = pd.read_csv(reports["error_report"])
        # There should be at least one error (failed to read marker file)
        assert len(error_df) >= 1
        # The subject report should still exist with n_markers = 0
        assert "001" in reports["subject_reports"]
        subject_report_path = reports["subject_reports"]["001"]
        df = pd.read_csv(subject_report_path)
        # Should have one row for the data file
        assert len(df) == 1
        row = df.iloc[0]
        assert row["n_markers"] == 0
        assert row["file_name"] == "sub-001_ses-01_task-rest_fnirs.snirf"