# Event Matching Module Analysis

## Overview

**Purpose**: Multi-device event matching with three algorithms: Hungarian (linear assignment), Min-Cost Flow, and Sinkhorn (optimal transport soft matching).

**Entry point**: `event_matching.py:124` - `match_events()` function

**Current implementation**: Simplified version with basic matching algorithms, missing higher‑level utilities referenced in tests and examples.

## Missing Functions (Referenced but Not Defined)

The following functions are imported in `test_event_matching.py` and `run_example.py` but are **not defined** anywhere in the codebase:

| Function | Referenced in | Expected signature (from usage) |
|----------|---------------|---------------------------------|
| `parse_timestamps_to_seconds` | `test_event_matching.py:6` | `(s: pd.Series, assume_epoch="auto") → (t: np.ndarray, is_epoch: bool, meta: dict)` |
| `preprocess_series` | `run_example.py:4` | `(series, dedup_window_s: float) → processed_series` |
| `align_and_merge_three` | `test_event_matching.py:11`, `run_example.py:5` | `(series_list, method="min_cost_flow", max_time_diff_s, sigma_time_s, unmatch_cost_a, unmatch_cost_b, drift_init, drift_fit, drift_iters, integrate_order) → (merged_df, mappings, matches)` |
| `estimate_affine_time_mapping` | `test_event_matching.py:10` | `(t_ref, t_dev, init="dtw", fit="theil_sen", min_pairs=10) → object with offset, scale` |
| `plot_time_diff_hist` | `run_example.py:6` | `(matches, out_path)` |
| `plot_timeline_scatter` | `run_example.py:6` | `(merged_df, device_names, out_path)` |
| `MarkerSeries` class | `test_event_matching.py:12` | `__init__(self, name, times)` |

**Note**: The existing `load_marker_csv` (line 156) has a different signature (`path: str`) than the one expected by `run_example.py` (`path, name, assume_epoch`). Similarly, the matching functions (`match_hungarian`, `match_min_cost_flow`, `match_sinkhorn`) in the current file accept only `(t1, t2, cost_power)` while the tests expect additional parameters (`max_time_diff_s`, `sigma_time_s`, `unmatch_cost_a`, `unmatch_cost_b`, etc.).

## Current Implementation (What IS Defined)

### Utility Function

**`compute_cost_matrix`** (`event_matching.py:21`)
- **Purpose**: Compute pairwise cost matrix based on absolute time difference raised to a power.
- **Data flow**: `t1[:, None] - t2[None, :]` → absolute difference → `diff ** power`.
- **Side effects**: None.
- **External calls**: None (pure NumPy).

### Hungarian Algorithm

**`match_hungarian`** (`event_matching.py:33`)
- **Purpose**: Solve linear assignment problem using SciPy's `linear_sum_assignment`.
- **Data flow**:
  1. `compute_cost_matrix(t1, t2, cost_power)` → `C`
  2. `linear_sum_assignment(C)` → `row_ind, col_ind`
  3. Zip indices into `matches` list, sum selected costs.
- **State mutations**: None.
- **Error paths**: None explicit; SciPy may raise `ValueError` on invalid inputs.
- **External calls**: `scipy.optimize.linear_sum_assignment`.

### Min‑Cost Flow Algorithm

**`match_min_cost_flow`** (`event_matching.py:49`)
- **Purpose**: Solve assignment as a min‑cost flow problem using NetworkX.
- **Data flow**:
  1. Build directed graph with source `"s"`, sink `"t"`, nodes `"a{i}"` for `t1`, `"b{j}"` for `t2`.
  2. Add edges with capacity 1 and weight `int(C[i,j]*1000)`.
  3. Call `nx.max_flow_min_cost`.
  4. Extract edges with positive flow as matches.
- **State mutations**: None.
- **Error paths**: None explicit; NetworkX may raise exceptions.
- **External calls**: `networkx.DiGraph`, `nx.max_flow_min_cost`.

### Sinkhorn / Optimal Transport Algorithm

**`sinkhorn`** (`event_matching.py:87`)
- **Purpose**: Compute Sinkhorn scaling (soft assignment) matrix.
- **Data flow**: `K = exp(-C / reg)` → iterate `u = 1/(K @ v)`, `v = 1/(K.T @ u)` → `P = diag(u) @ K @ diag(v)`.
- **Side effects**: None.
- **External calls**: None (pure NumPy).

**`match_sinkhorn`** (`event_matching.py:102`)
- **Purpose**: Soft matching via Sinkhorn, thresholding on probability matrix.
- **Data flow**:
  1. `compute_cost_matrix` → `C`
  2. `sinkhorn(C, reg)` → `P`
  3. For `P[i,j] > threshold`, add `(i,j)` to matches; total cost weighted by `P`.
- **State mutations**: None.
- **Error paths**: None explicit.

### Unified Interface

**`match_events`** (`event_matching.py:124`)
- **Purpose**: Dispatch to one of the three matching methods.
- **Control flow**:
  - `method == "hungarian"` → `match_hungarian`
  - `method == "min_cost_flow"` → `match_min_cost_flow`
  - `method == "sinkhorn"` → `match_sinkhorn`
  - else raise `ValueError`.
- **Data flow**: Pass `t1, t2` and `**kwargs` to selected method.
- **Error paths**: `ValueError` for unknown method.

### CSV Interface

**`load_marker_csv`** (`event_matching.py:156`)
- **Purpose**: Load marker CSV file and extract `reference_time` column.
- **Data flow**:
  1. `pd.read_csv(path)`
  2. Validate `"reference_time"` column exists.
  3. Return `(df["reference_time"].values, df)`.
- **Error paths**: `ValueError` if column missing.
- **External calls**: `pandas.read_csv`.

**`match_csv_files`** (`event_matching.py:163`)
- **Purpose**: Load two CSV files and run `match_events`.
- **Data flow**:
  1. `load_marker_csv(file1)` → `t1, df1`
  2. `load_marker_csv(file2)` → `t2, df2`
  3. `match_events(t1, t2, method, **kwargs)`.
- **Side effects**: Reads files from disk.
- **Error paths**: Propagates errors from `load_marker_csv` and `match_events`.

### Example Block

**`if __name__ == "__main__":`** (`event_matching.py:181`)
- **Purpose**: Demonstrate the three algorithms on synthetic data.
- **Data flow**: Create `t1 = [0.5, 2.0, 3.5, 5.0]`, `t2 = [0.6, 2.1, 3.7, 4.9]` and call `match_events` with each method.
- **Side effects**: Prints results to stdout.

## Data Flow Summary

1. **Input**: Two arrays of timestamps (`t1`, `t2`) or two CSV files.
2. **Cost matrix**: Computed via `compute_cost_matrix` (absolute time difference).
3. **Matching**: One of three algorithms produces a list of `(i, j)` pairs and total cost.
4. **Output**: Tuple `(matches, total_cost)` (for Hungarian and Min‑Cost Flow) or `(matches, total_cost, P)` (for Sinkhorn).

## External Dependencies

- `numpy` – array operations
- `pandas` – CSV reading (only in `load_marker_csv`)
- `scipy.optimize.linear_sum_assignment` – Hungarian algorithm
- `networkx` – min‑cost flow algorithm (optional, only used if `match_min_cost_flow` called)

## Discrepancies with Tests and Examples

| Aspect | Current Implementation | Expected (from tests/examples) |
|--------|------------------------|--------------------------------|
| `load_marker_csv` signature | `(path: str)` | `(path, name, assume_epoch="auto")` |
| `match_hungarian` signature | `(t1, t2, cost_power=1)` | `(t1, t2, max_time_diff_s, sigma_time_s, unmatch_cost_a, unmatch_cost_b, ...)` |
| `match_min_cost_flow` signature | `(t1, t2, cost_power=1)` | `(t1, t2, max_time_diff_s, sigma_time_s, unmatch_cost_a, unmatch_cost_b, backend="networkx")` |
| `match_sinkhorn` signature | `(t1, t2, cost_power=1, reg=0.1, threshold=0.01)` | `(t1, t2, max_time_diff_s, sigma_time_s, unmatch_cost_a, unmatch_cost_b, sinkhorn_reg, slack_mass, harden, harden_p_min)` |
| Missing utilities | None | `parse_timestamps_to_seconds`, `preprocess_series`, `align_and_merge_three`, `estimate_affine_time_mapping`, `plot_time_diff_hist`, `plot_timeline_scatter`, `MarkerSeries` class |

## Conclusion

The `event_matching.py` file present in the root directory is a **simplified, standalone implementation** of three matching algorithms. It does **not** provide the higher‑level functions (`parse_timestamps_to_seconds`, `preprocess_series`, `align_and_merge_three`, etc.) that are imported by `test_event_matching.py` and `run_example.py`. Those functions are **not defined elsewhere** in the codebase.

The tests and examples appear to be written against a **different, more comprehensive version** of the event‑matching module that either never existed or was replaced by the current simplified version. The mismatch suggests that the test suite and example script are currently **non‑functional** with the existing `event_matching.py`.