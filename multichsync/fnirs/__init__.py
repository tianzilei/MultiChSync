from .parser import parse_fnirs_header, load_coordinates
from .writer import write_snirf
from .converter import convert_fnirs_to_snirf
from .batch import batch_convert_fnirs_to_snirf
try:
    from .mne_patch import patch_snirf_for_mne, patch_snirf_inplace
except ImportError:
    # If h5py not available, provide stub function
    patch_snirf_for_mne = None
    patch_snirf_inplace = None

__all__ = [
    'parse_fnirs_header',
    'load_coordinates',
    'write_snirf',
    'convert_fnirs_to_snirf',
    'batch_convert_fnirs_to_snirf',
    'patch_snirf_for_mne',
    'patch_snirf_inplace',
]