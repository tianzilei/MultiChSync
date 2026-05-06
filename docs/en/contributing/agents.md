# AGENTS.md

MultiChSync — multimodal neuroimaging data conversion (fNIRS, EEG, ECG).

Python 3.8+ · MIT · Entry point: `multichsync=multichsync.cli:main`

## Toolchain

| Tool | Command | Config |
|------|---------|--------|
| Install (dev) | `pip install -e ".[dev]"` | `pyproject.toml` |
| Test | `pytest --cov=multichsync --cov-report=term-missing -n auto` | `pyproject.toml` [tool.pytest.ini_options] |
| Format | `black multichsync tests` | `line-length=88`, `target-version=py38` |
| Lint | `ruff check multichsync tests` | selects E,W,F,I,B,C4,UP ignores E501,B008 |
| Typecheck | `mypy multichsync` | strict-equality, disallow-incomplete-defs, warn-unreachable |

CI runs on GH Actions: 3 OS × Python 3.8-3.12 (excludes macos-3.12, windows-3.12).  
Coverage threshold: **35%** (low, intentional — coverage-check job only on PRs).

## Module Architecture

Each modality follows the same internal layout:

```
multichsync/{modality}/
├── __init__.py     # re-exports, may wrap imports in try/except
├── parser.py       # input format parsing
├── writer.py       # output format writing
├── converter.py    # orchestration logic
└── batch.py        # batch processing
```

### Modules

| Module | Key File | Lines | Notes |
|--------|----------|-------|-------|
| `fnirs/` | `parser.py` | ~347 | Shimadzu TXT → SNIRF v1.1 |
| `ecg/` | `parser.py` | ~269 | Biopac ACQ → CSV (via bioread) |
| `eeg/` | `parser.py` | ~161 | Curry/EEGLAB → BrainVision/EEGLAB/EDF (via MNE) |
| `marker/` | `matcher.py` | ~1495 | Event matching (hungarian/mincostflow/sinkhorn) |
| `quality/` | `assessor.py` | ~2311 | Comprehensive fNIRS QC (signal metrics, filtering) |
| `cli.py` | — | ~1924 | All argparse definitions + handler functions |

**Critical**: `quality/__init__.py` wraps all imports in `try/except ImportError` — if deps are missing, functions become `None`. Always check availability before calling.

### CLI Structure

```
multichsync <module> <subcommand> [options]
```

Modules: `fnirs` `ecg` `eeg` `marker` `quality`

`multichsync marker match --method` maps CLI names to internal names via `METHOD_NAME_MAPPING`:
- CLI `mincostflow` → internal `min_cost_flow`
- CLI `hungarian` → internal `hungarian`
- CLI `sinkhorn` → internal `sinkhorn`

**CLI error messages are in Chinese**. Don't change this; it's the project convention.

## Data Layout

All in `Data/` (gitignored — only `.gitignore` is tracked):

```
Data/
├── raw/{fnirs,EEG,ECG}/        # input: .txt, .csv, .set/.fdt, .acq
├── convert/{fnirs,EEG,ECG}/    # output: .snirf, .vhdr/.vmrk/.eeg, .csv
├── marker/{fnirs,ecg,eeg}/     # extracted markers
└── quality/                    # QC reports + visualizations
```

## Testing

- **Unit tests**: `tests/unit/test_*.py`
- **Integration tests**: `tests/integration/test_*.py`
- **Pytest markers**: `unit`, `integration`, `slow`
- **Fixtures**: `temp_dir`, `mock_eeg_files`, `mock_snirf_file`, `mock_ecg_csv` in `tests/conftest.py`
- Run single test: `pytest tests/unit/test_fnirs_converter.py -v`

**Heads-up**: ECG batch marker extraction (`marker batch --types ecg`) **deletes** source `_input.csv` on success. Don't run on data you want to keep without backups.

## Gotchas

1. **CLI uses Chinese** error/output strings throughout. Keep them when modifying CLI handlers.
2. **EEG resampling**: 0.1Hz tolerance — if original rate is already close to target, resampling is skipped.
3. **ECG marker batch deletes input files** (line `csv_file.unlink(missing_ok=True)`). This is intentional.
4. **quality module stub pattern**: All functions become `None` on import failure. Guard calls with `if process_one_snirf is not None:`.
5. **fnirs mne_patch** also uses try/except import — `patch_snirf_for_mne` may be `None`.
6. **utils/__init__.py is empty** — no shared utilities currently exist. Add new shared code here.
7. **logging**: YAML-based config in `config/logging.yaml`. Quality module logs at DEBUG; others at INFO.
8. **macOS hidden file filtering**: Batch operations filter `._*` and `__MACOSX` artifacts.
9. **coverage minimum is 35%** — don't be alarmed by low coverage requirements.
