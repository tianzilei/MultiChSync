# MultiChSync Code Style Guide

## Overview

This document describes the coding conventions and patterns used in the MultiChSync project. Following these patterns ensures consistency across the codebase and makes it easier for AI agents and developers to understand and extend the code.

## Language & Documentation

### Primary Language
- **Code**: Python 3.8+ with type hints
- **Comments**: Mixed English and Chinese (中文注释常见)
- **Docstrings**: English with Chinese translations for parameter descriptions

### Documentation Style
```python
def convert_fnirs_to_snirf(txt_path, src_coords_csv, det_coords_csv, output_path=None, 
                          patch_for_mne: bool = True, **kwargs):
    """
    将fNIRS TXT文件转换为SNIRF格式
    
    参数:
        txt_path: fNIRS TXT文件路径
        src_coords_csv: source坐标CSV文件路径
        det_coords_csv: detector坐标CSV文件路径  
        output_path: 输出SNIRF文件路径，默认为同名.snirf
        patch_for_mne: 是否应用MNE兼容性修复（默认: True）
        **kwargs: 传递给write_snirf的额外参数
        
    返回:
        output_path: 输出文件路径
    """
```

**Key Points**:
- Function docstrings use Chinese for parameter descriptions
- English used for technical terms and code
- Triple-quoted docstrings with clear sections
- Parameter and return types described in Chinese

## Naming Conventions

### Files and Directories
- **Directories**: `snake_case` (e.g., `multichsync/`, `fnirs/`, `quality/`)
- **Python files**: `snake_case.py` (e.g., `converter.py`, `info_extractor.py`)
- **Test files**: `test_*.py` (e.g., `test_event_matching.py`)
- **Example files**: `*_example.py` (e.g., `fnirs_example.py`)

### Functions and Methods
```python
# Conversion functions: verb_noun or verb_source_to_target
def convert_fnirs_to_snirf(...): ...
def parse_shimadzu_txt(...): ...
def write_snirf(...): ...

# Batch functions: batch_ prefix
def batch_convert_fnirs_to_snirf(...): ...

# Private/internal functions: leading underscore
def _overwrite_if_exists(...): ...
def _write_scalar_str(...): ...
```

**Patterns**:
- Public functions: `snake_case`, descriptive names
- Private functions: `_snake_case` with leading underscore
- Batch operations: `batch_` prefix
- Conversion functions: `convert_*_to_*` or `parse_*`/`write_*`

### Classes
```python
@dataclass
class ParsedTxt:
    meta: dict[str, Any]
    channel_pairs: list[tuple[int, int]]
    times: np.ndarray

class MarkerSeries:
    def __init__(self, name, times):
        self.name = name
        self.times = times
```

**Patterns**:
- Class names: `CamelCase`
- Dataclasses common for data containers
- Minimal class usage - mostly functional programming

### Variables and Parameters
```python
# Local variables: snake_case
output_path = Path(txt_path).with_suffix('.snirf')
data_matrix = np.zeros((n_channels, n_samples))

# Parameters: snake_case with type hints (newer code)
def process_one_snirf(snirf_path: str, out_dir: Path, l_freq: float = 0.01) -> dict:

# Legacy code may use camelCase for position data
sourcePos3D = np.array([...])  # Older code
```

**Patterns**:
- Variables: `snake_case`
- Type hints used in newer code (Python 3.8+)
- Some legacy variables use `camelCase` (particularly position data)

### Constants
```python
# Module-level constants: UPPER_SNAKE_CASE
_VLEN_STR = h5py.string_dtype(encoding="utf-8")
POSSIBLE_TIME_COLS = ["reference_time", "Time(sec)", "time", "Time", "referencetime"]

# Private constants: _UPPER_SNAKE_CASE or _snake_case
_MNE_AVAILABLE = True
```

**Patterns**:
- Public constants: `UPPER_SNAKE_CASE`
- Private constants: `_UPPER_SNAKE_CASE` or `_snake_case`
- Defined at module level near imports

## File Organization

### Module Structure
Each module follows this pattern:
```
module_name/
├── __init__.py     # Public API exports
├── parser.py       # Input parsing
├── writer.py       # Output writing  
├── converter.py    # Main conversion logic
└── batch.py        # Batch processing
```

### Import Style
```python
# Standard library imports first
import os
from pathlib import Path
from typing import Dict, List, Optional

# Third-party imports
import numpy as np
import pandas as pd
import h5py

# Local imports (relative)
from .parser import parse_shimadzu_txt, parse_fnirs_header
from .writer import write_snirf, _write_snirf_core

# Conditional imports with fallbacks
try:
    from .mne_patch import patch_snirf_for_mne, patch_snirf_inplace
except ImportError:
    # Provide stub functions if dependency missing
    patch_snirf_for_mne = None
    patch_snirf_inplace = None
```

**Rules**:
1. Standard library imports first
2. Third-party imports second (alphabetical within group)
3. Local imports last (relative imports within package)
4. Conditional imports with graceful fallbacks
5. Explicit `__all__` lists in `__init__.py` files

### __init__.py Pattern
```python
# multichsync/fnirs/__init__.py
from .parser import parse_fnirs_header, load_coordinates
from .writer import write_snirf
from .converter import convert_fnirs_to_snirf
from .batch import batch_convert_fnirs_to_snirf

try:
    from .mne_patch import patch_snirf_for_mne, patch_snirf_inplace
except ImportError:
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
```

## Code Patterns

### Error Handling
```python
# CLI functions: try-except with sys.exit(1)
def fnirs_convert(args):
    try:
        output_path = convert_fnirs_to_snirf(...)
        print(f"转换成功: {output_path}")
    except Exception as e:
        print(f"转换失败: {e}")
        sys.exit(1)

# Library functions: raise exceptions with descriptive messages
def parse_shimadzu_txt(txt_path):
    if not Path(txt_path).exists():
        raise FileNotFoundError(f"TXT文件不存在: {txt_path}")
    # ... parsing logic
    
# Batch processing: per-file error isolation
def batch_process_snirf_folder(in_dir, out_dir, ...):
    results = []
    failed = []
    for snirf_file in snirf_files:
        try:
            result = process_one_snirf(snirf_file, ...)
            results.append(result)
        except Exception as e:
            failed.append((snirf_file, str(e)))
    return results, failed
```

**Patterns**:
- CLI: `try-except` with `sys.exit(1)` on failure
- Library: Raise specific exceptions with helpful messages
- Batch: Isolate errors per file, continue processing others

### Data Validation
```python
# Type and value checking
def _load_coordinates_with_map(csv_path, expected_prefix):
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"坐标文件不存在: {csv_path}")
    
    df = pd.read_csv(csv_path)
    if df.shape[1] < 3:
        raise ValueError(f"坐标文件需要至少3列: {csv_path}")
    
    # Validate label prefixes
    for label in df.iloc[:, 0]:
        if not label.startswith(expected_prefix):
            raise ValueError(f"坐标标签'{label}'不以'{expected_prefix}'开头")
```

### Configuration and Defaults
```python
# Sensible defaults with override parameters
def process_one_snirf(snirf_path, out_dir, 
                     l_freq=0.01,           # Low-pass frequency
                     h_freq=0.2,            # High-pass frequency  
                     resample_sfreq=None,   # Resampling (None = no resample)
                     apply_tddr=True,       # Apply TDDR by default
                     comprehensive=True,    # Comprehensive assessment by default
                     paradigm="resting",    # Default paradigm
                     events=None):
    # ... implementation
```

**Patterns**:
- Sensible defaults for common use cases
- Boolean flags for optional features (default to True for safety)
- `None` as sentinel for "no action" defaults

### Data Processing Pipeline
```python
# Clear pipeline stages
def convert_fnirs_to_snirf(txt_path, src_coords_csv, det_coords_csv, ...):
    # 1. Parse input
    parsed = parse_shimadzu_txt(txt_path)
    
    # 2. Load coordinates  
    source_pos_3d, source_labels, source_map = _load_coordinates_with_map(...)
    detector_pos_3d, detector_labels, detector_map = _load_coordinates_with_map(...)
    
    # 3. Write output
    _write_snirf_core(
        output_path=output_path,
        parsed=parsed,
        source_pos_3d=source_pos_3d,
        detector_pos_3d=detector_pos_3d,
        # ... other parameters
    )
    
    # 4. Apply patches if requested
    if patch_for_mne and patch_snirf_for_mne:
        output_path = patch_snirf_for_mne(...)
    
    return output_path
```

## Testing Patterns

### Test File Structure
```python
# test_event_matching.py
import numpy as np
import pandas as pd
import pytest

from event_matching import (
    parse_timestamps_to_seconds,
    match_hungarian,
    match_min_cost_flow,
    # ... other imports
)

def test_parse_numeric_relative_seconds():
    s = pd.Series([0.0, 1.5, 2.0])
    t, is_epoch, meta = parse_timestamps_to_seconds(s, assume_epoch="auto")
    assert is_epoch is False
    assert np.allclose(t, [0.0, 1.5, 2.0])

def test_hungarian_unmatched():
    t_a, t_b = _simple_case()
    mr = match_hungarian(t_a, t_b, max_time_diff_s=0.5, ...)
    assert mr.pairs.shape[0] == 2
    assert set(mr.unmatched_a.tolist()) == {2}
```

**Patterns**:
- Test files in root directory (not `tests/` folder)
- Functions start with `test_`
- Use `pytest` and standard `assert` statements
- Helper functions with `_` prefix
- Import from module being tested

### Integration Tests
```python
# test_metadata_functionality.py
def test_metadata_writing():
    """Test process_one_snirf_with_metadata function."""
    print("\n2. Testing metadata writing functionality...")
    
    from multichsync.fnirs import patch_snirf_for_mne
    from multichsync.quality import process_one_snirf_with_metadata
    
    # Create temporary directories
    temp_dir = tempfile.mkdtemp(prefix="multichsync_test_")
    # ... test logic with cleanup
```

**Patterns**:
- Use temporary directories for file I/O tests
- Print progress messages
- Clean up resources in `finally` block
- Test both success and error paths

## CLI Patterns

### Command Structure
```python
# multichsync/cli.py
def fnirs_convert(args):
    """处理fNIRS转换命令"""
    try:
        output_path = convert_fnirs_to_snirf(...)
        print(f"转换成功: {output_path}")
    except Exception as e:
        print(f"转换失败: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="多模态神经影像数据转换工具")
    subparsers = parser.add_subparsers(dest="module", help="模块选择")
    
    # fNIRS module
    fnirs_parser = subparsers.add_parser("fnirs", help="fNIRS转换")
    fnirs_subparsers = fnirs_parser.add_subparsers(dest="command", help="命令选择")
    
    # fnirs convert subcommand
    convert_parser = fnirs_subparsers.add_parser("convert", help="转换单个文件")
    convert_parser.add_argument("--txt-path", required=True, help="TXT文件路径")
    convert_parser.add_argument("--src-coords", required=True, help="source坐标文件")
    convert_parser.add_argument("--det-coords", required=True, help="detector坐标文件")
    convert_parser.set_defaults(func=fnirs_convert)
    
    # ... other subcommands
```

**Patterns**:
- Hierarchical command structure: `module` → `command` → `options`
- Each command maps to a handler function
- Handler functions follow `module_command` naming
- Consistent error handling with `sys.exit(1)` on failure

## Type Hints

### Usage Guidelines
```python
# Newer code uses type hints extensively
def convert_acq_to_csv(acq_path: str, 
                       output_path: Optional[str] = None,
                       sampling_rate: Optional[int] = 250,
                       group_by_type: bool = True,
                       float_format: str = "%.6f") -> Union[str, Dict[str, str]]:
    """
    将ACQ文件转换为CSV格式
    
    Parameters
    ----------
    acq_path : str
        输入ACQ文件路径
    # ... other params
        
    Returns
    -------
    str or dict
        如果group_by_type为False，返回单个文件路径
        如果group_by_type为True，返回文件路径字典
    """
```

**Patterns**:
- Type hints for parameters and return values
- Use `Optional` for parameters that can be `None`
- Use `Union` for multiple return types
- Legacy code may not have type hints

## Logging and Output

### Progress Reporting
```python
# Print progress messages for CLI
print(f"批量转换完成，共 {len(converted_files)} 个文件")

# Verbose output control
def convert_eeg_format(file_path, export_format="BrainVision", verbose=None):
    if verbose:
        print(f"正在读取文件: {file_path}")
    # ... processing
    if verbose:
        print(f"转换完成: {output_path}")
```

**Patterns**:
- Use `print()` for CLI progress messages
- `verbose` parameter controls detailed output
- No formal logging framework (`logging` module)

## Do's and Don'ts

### ✅ DO
- Use descriptive `snake_case` names for functions and variables
- Add type hints to new functions
- Write docstrings in Chinese for parameter descriptions
- Use relative imports within the package
- Handle missing dependencies gracefully with fallbacks
- Validate inputs early and raise descriptive exceptions
- Use `try-except` in CLI handlers with `sys.exit(1)` on error
- Isolate errors in batch processing to continue with other files
- Use `@dataclass` for data containers
- Follow the established module structure for new modules

### ❌ DON'T
- Don't use `camelCase` for new variables (legacy exception for position data)
- Don't add new dependencies without updating `requirements.txt`
- Don't modify SNIRF files in-place without `--inplace` flag
- Don't use global variables for configuration
- Don't write tests that depend on specific external data paths
- Don't commit large data files to the repository
- Don't use `print()` for library functions (only CLI)

### 🔧 Legacy Code Notes
- Some older code uses `camelCase` variable names (e.g., `sourcePos3D`)
- Not all functions have type hints
- Test files are in root directory instead of `tests/` folder
- No formal logging framework (`logging` module not used)

## Adding New Code

### New Module Template
```python
"""
{Module name}模块
{Brief description}
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Union

# Local imports
from .parser import parse_{format}_file
from .writer import write_{format}_output

def convert_{format}_to_{target}(input_path: str, 
                                output_path: Optional[str] = None,
                                **kwargs) -> str:
    """
    {Brief description in Chinese}
    
    参数:
        input_path: 输入文件路径
        output_path: 输出文件路径，默认为自动生成
        **kwargs: 其他参数
        
    返回:
        output_path: 输出文件路径
    """
    # 1. Parse input
    parsed = parse_{format}_file(input_path)
    
    # 2. Process data
    # ... processing logic
    
    # 3. Write output
    if output_path is None:
        output_path = Path(input_path).with_suffix('.{ext}')
    
    write_{format}_output(output_path, processed_data, **kwargs)
    
    return output_path


def batch_convert_{format}_to_{target}(input_dir: str,
                                      output_dir: str,
                                      **kwargs) -> List[str]:
    """
    批量转换{format}文件
    
    参数:
        input_dir: 输入目录
        output_dir: 输出目录
        **kwargs: 其他参数
        
    返回:
        converted_files: 转换后的文件列表
    """
    converted_files = []
    for input_file in Path(input_dir).glob("*.{ext}"):
        try:
            output_file = convert_{format}_to_{target}(input_file, ...)
            converted_files.append(output_file)
        except Exception as e:
            print(f"转换失败 {input_file}: {e}")
    
    return converted_files
```

### Adding to CLI
1. Add import in `cli.py`
2. Create handler function following `{module}_{command}` pattern
3. Add command to appropriate subparser in `main()`
4. Add to module's `__init__.py` exports