"""
Patch SNIRF files for MNE compatibility.

This module provides functions to fix SNIRF files that cannot be read by MNE-Python
due to issues with processed HbT channels or missing wavelength information.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
import re

import h5py
import numpy as np

_VLEN_STR = h5py.string_dtype(encoding="utf-8")


def _write_scalar_str(group: h5py.Group | h5py.File, name: str, value: str) -> None:
    """Write a string scalar to an HDF5 group."""
    if name in group:
        del group[name]
    group.create_dataset(name, data=str(value), dtype=_VLEN_STR)


def _write_scalar_int(group: h5py.Group | h5py.File, name: str, value: int) -> None:
    """Write an integer scalar to an HDF5 group."""
    if name in group:
        del group[name]
    group.create_dataset(name, data=np.int32(value), dtype="i4")


def _list_indexed_names(group: h5py.Group, prefix: str) -> list[str]:
    """List names in a group that match a prefix followed by numbers."""
    pairs = []
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for k in group.keys():
        m = pat.match(k)
        if m:
            pairs.append((int(m.group(1)), k))
    pairs.sort()
    return [k for _, k in pairs]


def _next_indexed_name(group: h5py.Group, prefix: str) -> str:
    """Get the next available name for an indexed group."""
    names = _list_indexed_names(group, prefix)
    if not names:
        return f"{prefix}1"
    last = int(re.search(r"(\d+)$", names[-1]).group(1))
    return f"{prefix}{last + 1}"


def _ensure_wavelengths(probe: h5py.Group, dummy_wavelengths: Sequence[float]) -> None:
    """Ensure /nirs/probe/wavelengths contains at least two wavelengths."""
    arr = np.asarray(dummy_wavelengths, dtype=np.float64)
    if arr.ndim != 1 or arr.size < 2:
        raise ValueError("dummy_wavelengths must be a 1-D sequence with at least two values")

    if "wavelengths" not in probe:
        probe.create_dataset("wavelengths", data=arr, dtype="f8")
        return

    current = np.asarray(probe["wavelengths"][()])
    if current.size < 2:
        del probe["wavelengths"]
        probe.create_dataset("wavelengths", data=arr, dtype="f8")


def _measurement_lists_sorted(data_grp: h5py.Group) -> list[h5py.Group]:
    """Get measurementList groups in order."""
    out = []
    for name in _list_indexed_names(data_grp, "measurementList"):
        out.append(data_grp[name])
    return out


def _read_processed_label(ml: h5py.Group) -> str:
    """Read dataTypeLabel from a measurementList group."""
    if "dataTypeLabel" not in ml:
        return ""
    value = ml["dataTypeLabel"][()]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _read_data_type(ml: h5py.Group) -> int | None:
    """Read dataType from a measurementList group."""
    if "dataType" not in ml:
        return None
    return int(np.asarray(ml["dataType"][()]).item())


def _rewrite_measurement_lists(data_grp: h5py.Group, keep_indices: list[int]) -> None:
    """Rewrite measurementList groups keeping only specified indices."""
    old_names = _list_indexed_names(data_grp, "measurementList")
    old_cache = []
    for name in old_names:
        tmp = {}
        grp = data_grp[name]
        for key, item in grp.items():
            tmp[key] = (item[()], item.dtype)
        old_cache.append(tmp)

    for name in old_names:
        del data_grp[name]

    for new_i, old_i in enumerate(keep_indices, start=1):
        new_grp = data_grp.create_group(f"measurementList{new_i}")
        cache = old_cache[old_i]
        for key, (val, dtype) in cache.items():
            new_grp.create_dataset(key, data=val, dtype=dtype)


def patch_snirf_for_mne(
    input_snirf: str | Path,
    output_snirf: str | Path | None = None,
    *,
    dummy_wavelengths: Sequence[float] = (760.0, 850.0),
    move_hbt_to_aux: bool = True,
    aux_name: str = "HbT",
) -> Path:
    """
    Patch SNIRF for MNE compatibility.

    Parameters
    ----------
    input_snirf
        Path to source .snirf file.
    output_snirf
        Path to patched .snirf file. If None, save next to input with
        suffix '_mne_fixed.snirf'.
    dummy_wavelengths
        Fallback wavelengths written to /nirs/probe/wavelengths if missing/empty.
    move_hbt_to_aux
        If True, removed HbT columns are saved as an aux block.
    aux_name
        Name written to the aux channel containing removed HbT data.

    Returns
    -------
    Path
        Path to patched file.
    """
    input_snirf = Path(input_snirf)
    if output_snirf is None:
        output_snirf = input_snirf.with_name(input_snirf.stem + "_mne_fixed.snirf")
    output_snirf = Path(output_snirf)

    # Copy first, patch second.
    output_snirf.write_bytes(input_snirf.read_bytes())

    with h5py.File(output_snirf, "r+") as f:
        if "nirs" not in f:
            raise ValueError("Missing /nirs group")
        nirs = f["nirs"]

        if "probe" not in nirs:
            raise ValueError("Missing /nirs/probe group")
        probe = nirs["probe"]
        _ensure_wavelengths(probe, dummy_wavelengths)

        if "metaDataTags" not in nirs:
            meta = nirs.create_group("metaDataTags")
        else:
            meta = nirs["metaDataTags"]

        data_names = _list_indexed_names(nirs, "data")
        if not data_names:
            raise ValueError("No /nirs/data# groups found")

        patched_any = False

        for data_name in data_names:
            data_grp = nirs[data_name]
            if "dataTimeSeries" not in data_grp:
                continue

            mts = np.asarray(data_grp["dataTimeSeries"][()])
            if mts.ndim != 2:
                raise ValueError(f"{data_name}/dataTimeSeries must be 2-D")

            ml_groups = _measurement_lists_sorted(data_grp)
            if len(ml_groups) != mts.shape[1]:
                raise ValueError(
                    f"{data_name}: measurementList count ({len(ml_groups)}) "
                    f"does not match dataTimeSeries columns ({mts.shape[1]})"
                )

            keep_indices = []
            drop_indices = []

            for idx, ml in enumerate(ml_groups):
                dtype_val = _read_data_type(ml)
                label = _read_processed_label(ml).strip().lower()
                is_hbt = (dtype_val == 99999) and (label == "hbt")
                if is_hbt:
                    drop_indices.append(idx)
                else:
                    keep_indices.append(idx)

            if not drop_indices:
                continue

            patched_any = True
            kept = mts[:, keep_indices]
            dropped = mts[:, drop_indices]

            del data_grp["dataTimeSeries"]
            data_grp.create_dataset("dataTimeSeries", data=np.asarray(kept, dtype=np.float64), dtype="f8")
            _rewrite_measurement_lists(data_grp, keep_indices)

            if move_hbt_to_aux:
                aux_key = _next_indexed_name(nirs, "aux")
                aux_grp = nirs.create_group(aux_key)
                _write_scalar_str(aux_grp, "name", aux_name)
                aux_grp.create_dataset("dataTimeSeries", data=np.asarray(dropped, dtype=np.float64), dtype="f8")

                if "time" in data_grp:
                    aux_grp.create_dataset("time", data=np.asarray(data_grp["time"][()]), dtype="f8")

        _write_scalar_str(meta, "MNECompatibilityMode", "true")
        _write_scalar_str(
            meta,
            "MNECompatibilityNotes",
            "Patched for MNE: ensured probe/wavelengths and removed processed HbT channels from main data blocks."
        )
        _write_scalar_str(meta, "MNECompatibilityDummyWavelengths", ",".join(map(str, dummy_wavelengths)))
        _write_scalar_int(meta, "MNECompatibilityHbTMovedToAux", 1 if move_hbt_to_aux else 0)

    return output_snirf


def patch_snirf_inplace(
    snirf_path: str | Path,
    *,
    dummy_wavelengths: Sequence[float] = (760.0, 850.0),
    move_hbt_to_aux: bool = True,
    aux_name: str = "HbT",
) -> Path:
    """
    Patch SNIRF file in-place for MNE compatibility.

    Parameters
    ----------
    snirf_path
        Path to .snirf file to patch in-place.
    dummy_wavelengths
        Fallback wavelengths written to /nirs/probe/wavelengths if missing/empty.
    move_hbt_to_aux
        If True, removed HbT columns are saved as an aux block.
    aux_name
        Name written to the aux channel containing removed HbT data.

    Returns
    -------
    Path
        Path to patched file (same as input).
    """
    snirf_path = Path(snirf_path)
    
    with h5py.File(snirf_path, "r+") as f:
        if "nirs" not in f:
            raise ValueError("Missing /nirs group")
        nirs = f["nirs"]

        if "probe" not in nirs:
            raise ValueError("Missing /nirs/probe group")
        probe = nirs["probe"]
        _ensure_wavelengths(probe, dummy_wavelengths)

        if "metaDataTags" not in nirs:
            meta = nirs.create_group("metaDataTags")
        else:
            meta = nirs["metaDataTags"]

        data_names = _list_indexed_names(nirs, "data")
        if not data_names:
            raise ValueError("No /nirs/data# groups found")

        patched_any = False

        for data_name in data_names:
            data_grp = nirs[data_name]
            if "dataTimeSeries" not in data_grp:
                continue

            mts = np.asarray(data_grp["dataTimeSeries"][()])
            if mts.ndim != 2:
                raise ValueError(f"{data_name}/dataTimeSeries must be 2-D")

            ml_groups = _measurement_lists_sorted(data_grp)
            if len(ml_groups) != mts.shape[1]:
                raise ValueError(
                    f"{data_name}: measurementList count ({len(ml_groups)}) "
                    f"does not match dataTimeSeries columns ({mts.shape[1]})"
                )

            keep_indices = []
            drop_indices = []

            for idx, ml in enumerate(ml_groups):
                dtype_val = _read_data_type(ml)
                label = _read_processed_label(ml).strip().lower()
                is_hbt = (dtype_val == 99999) and (label == "hbt")
                if is_hbt:
                    drop_indices.append(idx)
                else:
                    keep_indices.append(idx)

            if not drop_indices:
                continue

            patched_any = True
            kept = mts[:, keep_indices]
            dropped = mts[:, drop_indices]

            del data_grp["dataTimeSeries"]
            data_grp.create_dataset("dataTimeSeries", data=np.asarray(kept, dtype=np.float64), dtype="f8")
            _rewrite_measurement_lists(data_grp, keep_indices)

            if move_hbt_to_aux:
                aux_key = _next_indexed_name(nirs, "aux")
                aux_grp = nirs.create_group(aux_key)
                _write_scalar_str(aux_grp, "name", aux_name)
                aux_grp.create_dataset("dataTimeSeries", data=np.asarray(dropped, dtype=np.float64), dtype="f8")

                if "time" in data_grp:
                    aux_grp.create_dataset("time", data=np.asarray(data_grp["time"][()]), dtype="f8")

        _write_scalar_str(meta, "MNECompatibilityMode", "true")
        _write_scalar_str(
            meta,
            "MNECompatibilityNotes",
            "Patched for MNE: ensured probe/wavelengths and removed processed HbT channels from main data blocks."
        )
        _write_scalar_str(meta, "MNECompatibilityDummyWavelengths", ",".join(map(str, dummy_wavelengths)))
        _write_scalar_int(meta, "MNECompatibilityHbTMovedToAux", 1 if move_hbt_to_aux else 0)

    return snirf_path