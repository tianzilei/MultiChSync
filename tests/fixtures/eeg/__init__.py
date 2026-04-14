"""
EEG test fixtures - minimal mock files for testing.
"""

import pytest
import tempfile
from pathlib import Path


def create_minimal_vhdr(
    base_name: str, n_channels: int = 1, sfreq: float = 500
) -> dict:
    """Create minimal BrainVision header file content."""
    channels = "\n".join([f"Ch{i + 1}=Fp{i + 1},,0.1" for i in range(n_channels)])
    sampling_interval = int(1e6 / sfreq)  # in microseconds

    vhdr = f"""Brain Vision Data Exchange Header File Version 1.0

[Common Infos]
Codepage=UTF-8
DataFile={base_name}.eeg
MarkerFile={base_name}.vmrk

[Binary Infos]
BinaryFormat=INT_16

[Channel Infos]
{channels}

[Coordinates]

[Sampling Interval]
{sampling_interval}
"""
    return {"vhdr": vhdr, "base": base_name}


def create_minimal_vmrk(base_name: str, n_markers: int = 2) -> str:
    """Create minimal BrainVision marker file content."""
    markers = ["Mk1=New Segment,,0,1,0,0"]
    for i in range(n_markers):
        markers.append(f"Mk{i + 2}=Stimulus,S  {i + 1},{1000 * (i + 1)},1,0")

    return f"""Brain Vision Data Exchange Marker File Version 1.0

[Common Infos]
DataFile={base_name}.eeg

[Marker Infos]
{chr(10).join(markers)}
"""


@pytest.fixture
def eeg_1ch_500hz(temp_dir):
    """Create 1 channel EEG at 500Hz."""
    base = "test_1ch_500hz"
    vhdr = create_minimal_vhdr(base, n_channels=1, sfreq=500)

    vhdr_path = temp_dir / f"{base}.vhdr"
    vmrk_path = temp_dir / f"{base}.vmrk"
    eeg_path = temp_dir / f"{base}.eeg"

    vhdr_path.write_text(vhdr["vhdr"])
    vmrk_path.write_text(create_minimal_vmrk(base))
    eeg_path.write_bytes(b"\x00" * 100)  # Minimal EEG data

    return {"base": base, "vhdr": vhdr_path, "vmrk": vmrk_path, "eeg": eeg_path}
