"""
EEG转换模块
支持Curry、EEGLAB格式转换为BrainVision、EEGLAB、EDF格式
"""

from .parser import read_eeg_file, guess_input_format
from .writer import write_eeg_file
from .converter import convert_eeg_format, convert_eeg_to_brainvision, convert_eeg_to_eeglab, convert_eeg_to_edf
from .batch import batch_convert_eeg_format, batch_convert_eeg_to_brainvision, batch_convert_eeg_to_eeglab, batch_convert_eeg_to_edf

__all__ = [
    'read_eeg_file',
    'guess_input_format',
    'write_eeg_file',
    'convert_eeg_format',
    'convert_eeg_to_brainvision',
    'convert_eeg_to_eeglab',
    'convert_eeg_to_edf',
    'batch_convert_eeg_format',
    'batch_convert_eeg_to_brainvision',
    'batch_convert_eeg_to_eeglab',
    'batch_convert_eeg_to_edf',
]