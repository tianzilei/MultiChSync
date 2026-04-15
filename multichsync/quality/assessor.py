"""
fNIRS数据质量评估模块

功能：
1. 读取 HbO/HbR SNIRF 文件
2. 计算 Pre-filter 坏通道
3. 计算 Pre-filter 时域/频域 SNR
4. 滤波（短记录自动 IIR，长记录 FIR）+ 可选 TDDR
5. 计算 Post-filter 坏通道
6. 计算 Post-filter 时域/频域 SNR
7. 输出每个文件 detail CSV 和 summary JSON
8. 输出批量汇总 CSV

依赖：mne, pandas, numpy
"""

from pathlib import Path
import json
from typing import Tuple, Optional, List, Dict, Any
import numpy as np
import pandas as pd
import h5py

# Try to import mne, provide stub if not available
try:
    import mne
    from mne.time_frequency import psd_array_welch

    MNE_AVAILABLE = True
except ImportError:
    MNE_AVAILABLE = False
    # Provide stub so module can import, but function will raise ImportError
    mne = None
    psd_array_welch = None

# Try to import mne_nirs, for writing SNIRF file (optional)
try:
    from mne_nirs.io import write_raw_snirf

    MNE_NIRS_AVAILABLE = True
except ImportError:
    MNE_NIRS_AVAILABLE = False
    write_raw_snirf = None


# =========================
# Basic utility functions
# =========================
def safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    """安全计算相关性，处理缺失值和零方差"""
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 3:
        return np.nan
    x2 = x[mask]
    y2 = y[mask]
    if np.std(x2) == 0 or np.std(y2) == 0:
        return np.nan
    return np.corrcoef(x2, y2)[0, 1]


def mad(x: np.ndarray) -> float:
    """计算中位数绝对偏差"""
    x = np.asarray(x, dtype=float)
    med = np.nanmedian(x)
    return np.nanmedian(np.abs(x - med))


def round_dataframe(df: pd.DataFrame, decimals: int = 2) -> pd.DataFrame:
    """递归舍入DataFrame中的所有数值列（包括嵌套结构）"""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype in [np.float64, np.float32, float]:
            df[col] = df[col].round(decimals)
        elif isinstance(df[col].iloc[0] if len(df) > 0 else None, dict):
            # Nested dict column
            df[col] = df[col].apply(
                lambda x: (
                    {
                        k: round(v, decimals)
                        if isinstance(v, (int, float)) and not isinstance(v, bool)
                        else v
                        for k, v in x.items()
                    }
                    if isinstance(x, dict)
                    else x
                )
            )
    return df


def round_dict_values(d: dict, decimals: int = 2) -> dict:
    """递归舍入字典中的所有数值（保留非数值类型）"""
    result = {}
    for k, v in d.items():
        if isinstance(v, bool):
            result[k] = v
        elif isinstance(v, (int, np.integer)) and not isinstance(v, bool):
            result[k] = int(v)
        elif isinstance(v, (float, np.floating)):
            result[k] = round(float(v), decimals)
        elif isinstance(v, dict):
            result[k] = round_dict_values(v, decimals)
        elif isinstance(v, list):
            result[k] = [
                round(x, decimals)
                if isinstance(x, (int, float)) and not isinstance(x, bool)
                else x
                for x in v
            ]
        else:
            result[k] = v
    return result


def get_channel_types(raw) -> List[str]:
    """获取所有通道类型"""
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")
    return [mne.channel_type(raw.info, i) for i in range(len(raw.ch_names))]


def pick_hbo_hbr(raw) -> Tuple[np.ndarray, np.ndarray]:
    """选择 HbO 和 HbR 通道"""
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")
    hbo = mne.pick_types(raw.info, fnirs="hbo")
    hbr = mne.pick_types(raw.info, fnirs="hbr")
    return hbo, hbr


def normalize_base_name(ch_name: str) -> str:
    """规范化通道名，移除 hbo/hbr 后缀"""
    return (
        ch_name.replace(" hbo", "")
        .replace(" hbr", "")
        .replace("_hbo", "")
        .replace("_hbr", "")
    )


def pair_hbo_hbr_channels(raw) -> List[Tuple[str, int, int]]:
    """
    配对 HbO/HbR 通道

    返回：
        [(base_name, idx_hbo, idx_hbr), ...]
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    pairs = []
    ch_names = raw.ch_names
    ch_types = get_channel_types(raw)

    base_map = {}
    for idx, (name, ctype) in enumerate(zip(ch_names, ch_types)):
        if ctype not in ("hbo", "hbr"):
            continue
        base = normalize_base_name(name)
        base_map.setdefault(base, {})
        base_map[base][ctype] = idx

    for base, d in base_map.items():
        if "hbo" in d and "hbr" in d:
            pairs.append((base, d["hbo"], d["hbr"]))

    return pairs


def expand_fnirs_bads_to_pairs(raw, bads: List[str]) -> List[str]:
    """
    fNIRS 坏通道必须按 hbo/hbr 成对补全

    参数：
        raw: MNE raw 对象
        bads: 原始坏通道列表

    返回：
        扩展后的坏通道列表（包含配对通道）
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    ch_names = raw.ch_names
    ch_types = get_channel_types(raw)

    pair_map = {}
    for name, ctype in zip(ch_names, ch_types):
        if ctype not in ("hbo", "hbr"):
            continue
        base = normalize_base_name(name)
        pair_map.setdefault(base, {})
        pair_map[base][ctype] = name

    bads_set = set(bads)
    expanded = set(bads)

    for _, pair in pair_map.items():
        pair_names = set(pair.values())
        if bads_set & pair_names:
            expanded |= pair_names

    return [ch for ch in ch_names if ch in expanded]


def bandpower_from_psd(
    psd: np.ndarray, freqs: np.ndarray, fmin: float, fmax: float
) -> float:
    """从PSD计算指定频带的功率"""
    mask = (freqs >= fmin) & (freqs < fmax)
    if not np.any(mask):
        return np.nan
    return np.trapezoid(psd[mask], freqs[mask])


# =========================
# Filter function
# =========================
def smart_filter_raw(
    raw, l_freq: float = 0.01, h_freq: float = 0.2, verbose: bool = False
) -> Tuple[Any, str]:
    """
    智能滤波：对短记录自动使用 IIR，避免 FIR filter_length > signal length

    参数：
        raw: MNE raw 对象
        l_freq: 低通频率
        h_freq: 高通频率
        verbose: 是否显示详细信息

    返回：
        raw: 过滤后的 raw 对象
        filter_method_used: 使用的滤波方法描述
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    n_times = raw.n_times
    sfreq = float(raw.info["sfreq"])
    duration_sec = n_times / sfreq if sfreq > 0 else np.nan

    use_iir = False

    # Prefer IIR for low/high pass + short recordings
    if l_freq is not None and l_freq <= 0.02 and duration_sec < 300:
        use_iir = True

    if use_iir:
        raw.filter(
            l_freq=l_freq,
            h_freq=h_freq,
            method="iir",
            iir_params=dict(order=4, ftype="butter"),
            verbose=verbose,
        )
        filter_method_used = "iir_butterworth_order4"
    else:
        raw.filter(
            l_freq=l_freq,
            h_freq=h_freq,
            method="fir",
            verbose=verbose,
        )
        filter_method_used = "fir_auto"

    return raw, filter_method_used


# =========================
# Signal-level quality metrics (based on fnirs_signal_level_qc_metrics.md)
# =========================
def compute_signal_metrics(
    x: np.ndarray,
    fs: float,
    epsilon_mu: float = 1e-8,
    epsilon_sigma: float = 1e-8,
    epsilon_MAD: float = 1e-8,
) -> Dict[str, float]:
    """
    Compute comprehensive signal-level quality metrics for a single time series.

    Based on: fnirs_signal_level_qc_metrics.md
    All metrics are computed at the full-signal level.

    Parameters:
    -----------
    x : np.ndarray
        Signal time series
    fs : float
        Sampling frequency (Hz)
    epsilon_mu, epsilon_sigma, epsilon_MAD : float
        Small positive constants for numerical stability

    Returns:
    --------
    Dict with metrics:
    - near_flatline : 1 if signal is near-flatline, 0 otherwise
    - range : max(x) - min(x)
    - cv : coefficient of variation (sigma / |mu|)
    - tsnr : temporal signal-to-noise ratio (|mu| / sigma)
    - rdi : robust derivative index (median|dx| / MAD(x))
    - drift : baseline drift index (|slope| / sigma)
    - spectral_entropy : spectral entropy over analysis band
    - power_low : power in low frequency band [0.01, 0.08] Hz
    - power_mayer : power in Mayer band [0.08, 0.15] Hz
    - power_resp : power in respiration band [0.15, 0.40] Hz
    - mayer_ratio : Mayer band power ratio
    - resp_ratio : Respiration band power ratio
    """
    x = np.asarray(x, dtype=float)
    x_finite = x[np.isfinite(x)]
    n_finite = len(x_finite)

    if n_finite < 10:
        # Return NaN for all metrics if insufficient data
        return {
            "near_flatline": np.nan,
            "range": np.nan,
            "cv": np.nan,
            "tsnr": np.nan,
            "rdi": np.nan,
            "drift": np.nan,
            "spectral_entropy": np.nan,
            "power_low": np.nan,
            "power_mayer": np.nan,
            "power_resp": np.nan,
            "mayer_ratio": np.nan,
            "resp_ratio": np.nan,
        }

    # 1. Basic statistics
    mu = np.mean(x_finite)
    sigma = np.std(x_finite)
    med = np.median(x_finite)
    mad_val = np.median(np.abs(x_finite - med))
    x_range = np.max(x_finite) - np.min(x_finite)

    # 2. Near-flatline indicator (tau_flat = 1e-6 default)
    tau_flat = 1e-6
    near_flatline = 1 if x_range < tau_flat else 0

    # 3. Coefficient of variation
    cv = sigma / (abs(mu) + epsilon_mu)

    # 4. Temporal SNR
    tsnr = abs(mu) / (sigma + epsilon_sigma)

    # 5. Robust derivative index
    dx = np.diff(x_finite)
    if len(dx) > 0:
        rdi = np.median(np.abs(dx)) / (mad_val + epsilon_MAD)
    else:
        rdi = np.nan

    # 6. Baseline drift index (linear trend)
    n = len(x_finite)
    if n >= 2:
        t = np.arange(n) / fs
        # Simple linear regression for slope
        beta1 = np.cov(t, x_finite)[0, 1] / np.var(t) if np.var(t) > 0 else 0
        drift = abs(beta1) / (sigma + epsilon_sigma)
    else:
        drift = np.nan

    # 7. Spectral metrics
    try:
        # Try to import scipy.signal.welch, fallback to simpler method if not available
        try:
            from scipy.signal import welch

            freqs, psd = welch(x_finite, fs=fs, nperseg=min(256, n_finite))
        except ImportError:
            # Fallback: use simple FFT-based PSD estimation
            n_fft = min(256, n_finite)
            fft_result = np.fft.rfft(x_finite - np.mean(x_finite), n=n_fft)
            psd = np.abs(fft_result) ** 2
            freqs = np.fft.rfftfreq(n_fft, d=1.0 / fs)

        # Spectral entropy
        # Normalize PSD to create probability distribution
        psd_pos = psd[psd > 0]
        if len(psd_pos) > 0:
            q = psd_pos / np.sum(psd_pos)
            spectral_entropy = -np.sum(q * np.log(q + epsilon_mu))
        else:
            spectral_entropy = np.nan

        # Band power ratios
        # Low frequency: [0.01, 0.08] Hz
        mask_low = (freqs >= 0.01) & (freqs < 0.08)
        # Mayer band: [0.08, 0.15] Hz
        mask_mayer = (freqs >= 0.08) & (freqs < 0.15)
        # Respiration band: [0.15, 0.40] Hz
        mask_resp = (freqs >= 0.15) & (freqs < 0.40)

        def band_power(mask):
            if np.any(mask):
                return np.trapezoid(psd[mask], freqs[mask])
            return 0.0

        power_low = band_power(mask_low)
        power_mayer = band_power(mask_mayer)
        power_resp = band_power(mask_resp)

        # Band power ratios
        total_power_low_resp = power_low + power_resp + epsilon_mu
        total_power_low_mayer = power_low + power_mayer + epsilon_mu

        mayer_ratio = power_mayer / total_power_low_resp
        resp_ratio = power_resp / total_power_low_mayer

    except Exception:
        spectral_entropy = np.nan
        power_low = np.nan
        power_mayer = np.nan
        power_resp = np.nan
        mayer_ratio = np.nan
        resp_ratio = np.nan

    return {
        "near_flatline": near_flatline,
        "range": x_range,
        "cv": cv,
        "tsnr": tsnr,
        "rdi": rdi,
        "drift": drift,
        "spectral_entropy": spectral_entropy,
        "power_low": power_low,
        "power_mayer": power_mayer,
        "power_resp": power_resp,
        "mayer_ratio": mayer_ratio,
        "resp_ratio": resp_ratio,
    }


def compute_hbo_hbr_pair_metrics(
    hbo: np.ndarray, hbr: np.ndarray, epsilon_sigma: float = 1e-8
) -> Dict[str, float]:
    """
    Compute HbO-HbR pair metrics for paired channels.

    Based on: fnirs_signal_level_qc_metrics.md

    Parameters:
    -----------
    hbo, hbr : np.ndarray
        Paired HbO and HbR time series
    epsilon_sigma : float
        Small positive constant for numerical stability

    Returns:
    --------
    Dict with pair metrics:
    - hbo_hbr_corr : Pearson correlation
    - hbo_hbr_var_ratio : variance ratio (sigma_hbo / sigma_hbr)
    - hbo_hbr_deriv_corr : derivative correlation
    """
    mask = np.isfinite(hbo) & np.isfinite(hbr)
    hbo_finite = hbo[mask]
    hbr_finite = hbr[mask]

    if len(hbo_finite) < 10:
        return {
            "hbo_hbr_corr": np.nan,
            "hbo_hbr_var_ratio": np.nan,
            "hbo_hbr_deriv_corr": np.nan,
        }

    # 1. Full-signal correlation
    if np.std(hbo_finite) > 0 and np.std(hbr_finite) > 0:
        hbo_hbr_corr = np.corrcoef(hbo_finite, hbr_finite)[0, 1]
    else:
        hbo_hbr_corr = np.nan

    # 2. Variance ratio
    sigma_hbo = np.std(hbo_finite)
    sigma_hbr = np.std(hbr_finite)
    hbo_hbr_var_ratio = sigma_hbo / (sigma_hbr + epsilon_sigma)

    # 3. Derivative correlation
    d_hbo = np.diff(hbo_finite)
    d_hbr = np.diff(hbr_finite)
    if len(d_hbo) >= 10 and len(d_hbr) >= 10:
        if np.std(d_hbo) > 0 and np.std(d_hbr) > 0:
            hbo_hbr_deriv_corr = np.corrcoef(d_hbo, d_hbr)[0, 1]
        else:
            hbo_hbr_deriv_corr = np.nan
    else:
        hbo_hbr_deriv_corr = np.nan

    return {
        "hbo_hbr_corr": hbo_hbr_corr,
        "hbo_hbr_var_ratio": hbo_hbr_var_ratio,
        "hbo_hbr_deriv_corr": hbo_hbr_deriv_corr,
    }


def map_metric_to_score(value: float, metric_type: str, a: float, b: float) -> float:
    """
    Map a raw metric value to a 0-1 score using anchor points.

    Based on: fnirs_signal_level_qc_metrics.md

    Parameters:
    -----------
    value : float
        Raw metric value
    metric_type : str
        Type of metric: 'lower_better', 'higher_better', 'pair_corr',
                       'var_ratio', 'band_metric'
    a, b : float
        Anchor points defining the mapping

    Returns:
    --------
    Score between 0 and 1
    """
    if np.isnan(value):
        return 0.0

    if metric_type == "lower_better":
        # Lower values are better
        if value <= a:
            return 1.0
        elif value >= b:
            return 0.0
        else:
            return 1.0 - (value - a) / (b - a)

    elif metric_type == "higher_better":
        # Higher values are better
        if value >= b:
            return 1.0
        elif value <= a:
            return 0.0
        else:
            return (value - a) / (b - a)

    elif metric_type == "pair_corr":
        # For correlations, optimal is negative (HbO-HbR anticorrelation)
        # Map -1 → 1, 0 → 0.5, 1 → 0
        if value <= -0.8:
            return 1.0
        elif value >= 0.8:
            return 0.0
        else:
            return 0.5 - 0.5 * value / 0.8

    elif metric_type == "var_ratio":
        # Variance ratio should be close to 1 (balanced HbO/HbR variance)
        # Map 0.5 → 1, 1 → 1, 2 → 0 (asymmetric examples)
        ratio = abs(np.log2(value + 1e-8))
        if ratio <= 0.5:  # Within factor of sqrt(2)
            return 1.0
        elif ratio >= 2.0:  # Beyond factor of 4
            return 0.0
        else:
            return 1.0 - (ratio - 0.5) / 1.5

    elif metric_type == "band_metric":
        # For band ratios, moderate values are best
        # Avoid extreme dominance of one band
        if 0.1 <= value <= 10.0:
            return 1.0 - 0.9 * abs(np.log10(value + 1e-8)) / 2.0
        else:
            return 0.1

    return 0.5  # Default


# =========================
# SNR calculation function
# =========================
def compute_hb_snr(
    raw,
    signal_band: Tuple[float, float] = (0.01, 0.2),
    noise_band: Tuple[float, float] = (0.2, 0.5),
) -> pd.DataFrame:
    """
    对 HbO/HbR 通道计算时域和频域 SNR

    参数：
        raw: MNE raw 对象
        signal_band: 信号频带 (Hz)
        noise_band: 噪声频带 (Hz)

    返回：
        DataFrame 包含每通道的 SNR 信息
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    data = raw.get_data()
    ch_names = raw.ch_names
    ch_types = get_channel_types(raw)
    sfreq = float(raw.info["sfreq"])

    n_ch = len(ch_names)
    if data.shape[0] != n_ch:
        raise RuntimeError(
            f"Data channel count mismatch: len(ch_names)={n_ch}, data.shape[0]={data.shape[0]}"
        )

    psds, freqs = psd_array_welch(
        data,
        sfreq=sfreq,
        fmin=min(signal_band[0], noise_band[0]),
        fmax=max(signal_band[1], noise_band[1]),
        n_fft=min(256, data.shape[1]),
        n_per_seg=min(256, data.shape[1]),
        n_overlap=0,
        average="mean",
        remove_dc=True,
        verbose=False,
    )

    if psds.shape[0] != n_ch:
        raise RuntimeError(
            f"PSD channel count mismatch after psd_array_welch: "
            f"len(ch_names)={n_ch}, psds.shape[0]={psds.shape[0]}"
        )

    rows = []
    for i, (name, ctype) in enumerate(zip(ch_names, ch_types)):
        x = data[i].astype(float)
        x = x[np.isfinite(x)]

        if len(x) < 10:
            rows.append(
                {
                    "channel": name,
                    "type": ctype,
                    "snr_time_db": np.nan,
                    "snr_psd_db": np.nan,
                }
            )
            continue

        sig_std = np.std(x)
        noise_std = np.std(np.diff(x)) if len(x) > 1 else np.nan
        if np.isfinite(sig_std) and np.isfinite(noise_std) and noise_std > 0:
            snr_time_db = 20 * np.log10(sig_std / noise_std)
        else:
            snr_time_db = np.nan

        psd = psds[i]
        signal_power = bandpower_from_psd(psd, freqs, signal_band[0], signal_band[1])
        noise_power = bandpower_from_psd(psd, freqs, noise_band[0], noise_band[1])

        if np.isfinite(signal_power) and np.isfinite(noise_power) and noise_power > 0:
            snr_psd_db = 10 * np.log10(signal_power / noise_power)
        else:
            snr_psd_db = np.nan

        rows.append(
            {
                "channel": name,
                "type": ctype,
                "snr_time_db": snr_time_db,
                "snr_psd_db": snr_psd_db,
            }
        )

    return pd.DataFrame(rows)


# =========================
# Quality assessment function
# =========================


def assess_hb_quality_comprehensive(
    raw,
    fs: float,
    paradigm: str = "resting",
    events: Optional[Dict[str, Any]] = None,
    epsilon_mu: float = 1e-8,
    epsilon_sigma: float = 1e-8,
    epsilon_MAD: float = 1e-8,
    apply_hard_gating: bool = True,
) -> Tuple[pd.DataFrame, List[str], Dict[str, Any]]:
    """
    Comprehensive HbO/HbR quality assessment with signal-level metrics.

    Based on: fnirs_signal_level_qc_metrics.md

    Parameters:
    -----------
    raw : MNE raw object
        Raw data with HbO/HbR channels
    fs : float
        Sampling frequency (Hz)
    paradigm : str
        Paradigm type: "task" or "resting"
    events : dict, optional
        Event information for task-based metrics
    epsilon_* : float
        Numerical stability constants
    apply_hard_gating : bool
        Whether to apply hard gating rules

    Returns:
    --------
    quality_df : DataFrame
        Comprehensive quality metrics for each channel
    bad_channels : list
        List of bad channel names (if apply_hard_gating=True)
    summary : dict
        Run-level summary metrics
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    data = raw.get_data()
    ch_names = raw.ch_names
    ch_types = get_channel_types(raw)

    # Get HbO/HbR pairs
    pairs = pair_hbo_hbr_channels(raw)

    # Initialize results
    rows = []
    pair_metrics_list = []

    # Process each channel
    for i, (name, ctype) in enumerate(zip(ch_names, ch_types)):
        if ctype not in ("hbo", "hbr"):
            continue

        x = data[i].astype(float)

        # Compute signal-level metrics
        signal_metrics = compute_signal_metrics(
            x, fs, epsilon_mu, epsilon_sigma, epsilon_MAD
        )

        row = {
            "channel": name,
            "type": ctype,
            "nan_ratio": 1.0 - np.mean(np.isfinite(x)),
            "std": np.nanstd(x) if np.any(np.isfinite(x)) else np.nan,
            "mad": mad(x),
            "ptp": np.nanmax(x) - np.nanmin(x) if np.any(np.isfinite(x)) else np.nan,
        }
        row.update(signal_metrics)
        rows.append(row)

    quality_df = pd.DataFrame(rows)

    # Add pair information and compute pair metrics
    quality_df["pair_base"] = ""
    quality_df["hbo_hbr_corr"] = np.nan
    quality_df["hbo_hbr_var_ratio"] = np.nan
    quality_df["hbo_hbr_deriv_corr"] = np.nan

    for base, idx_hbo, idx_hbr in pairs:
        if idx_hbo < len(quality_df) and idx_hbr < len(quality_df):
            hbo_data = data[idx_hbo]
            hbr_data = data[idx_hbr]

            pair_metrics = compute_hbo_hbr_pair_metrics(
                hbo_data, hbr_data, epsilon_sigma
            )

            quality_df.loc[idx_hbo, "pair_base"] = base
            quality_df.loc[idx_hbr, "pair_base"] = base
            quality_df.loc[idx_hbo, "hbo_hbr_corr"] = pair_metrics["hbo_hbr_corr"]
            quality_df.loc[idx_hbr, "hbo_hbr_corr"] = pair_metrics["hbo_hbr_corr"]
            quality_df.loc[idx_hbo, "hbo_hbr_var_ratio"] = pair_metrics[
                "hbo_hbr_var_ratio"
            ]
            quality_df.loc[idx_hbr, "hbo_hbr_var_ratio"] = pair_metrics[
                "hbo_hbr_var_ratio"
            ]
            quality_df.loc[idx_hbo, "hbo_hbr_deriv_corr"] = pair_metrics[
                "hbo_hbr_deriv_corr"
            ]
            quality_df.loc[idx_hbr, "hbo_hbr_deriv_corr"] = pair_metrics[
                "hbo_hbr_deriv_corr"
            ]

            pair_metrics_list.append({"pair_base": base, **pair_metrics})

    # Apply hard gating if requested
    bad_channels = []
    if apply_hard_gating:
        # Hard gating rules from markdown
        # 1. Near-flatline
        quality_df["bad_flat"] = quality_df["near_flatline"] == 1

        # 2. High coefficient of variation (threshold: 5.0)
        quality_df["bad_cv"] = quality_df["cv"] > 5.0

        # 3. High robust derivative index (threshold: 10.0)
        quality_df["bad_rdi"] = quality_df["rdi"] > 10.0

        # 4. High NaN ratio
        quality_df["bad_nan"] = quality_df["nan_ratio"] > 0.05

        # Combine hard gates
        quality_df["bad_hard"] = (
            quality_df["bad_flat"]
            | quality_df["bad_cv"]
            | quality_df["bad_rdi"]
            | quality_df["bad_nan"]
        )

        # Apply pair rule: if one channel in pair fails, both fail
        quality_df["bad_pair"] = False
        for base in quality_df["pair_base"].dropna().unique():
            if base == "":
                continue
            mask = quality_df["pair_base"] == base
            if quality_df.loc[mask, "bad_hard"].any():
                quality_df.loc[mask, "bad_pair"] = True

        quality_df["bad_final"] = quality_df["bad_pair"] | (
            (quality_df["pair_base"] == "") & quality_df["bad_hard"]
        )

        bad_channels = quality_df.loc[quality_df["bad_final"], "channel"].tolist()
        bad_channels = expand_fnirs_bads_to_pairs(raw, bad_channels)
        quality_df["bad_final"] = quality_df["channel"].isin(bad_channels)

    # Compute run-level summary
    summary = {
        "n_channels": len(quality_df),
        "n_hbo": len(quality_df[quality_df["type"] == "hbo"]),
        "n_hbr": len(quality_df[quality_df["type"] == "hbr"]),
        "n_pairs": len(pairs),
        "fs": fs,
    }

    if apply_hard_gating:
        summary.update(
            {
                "n_bad_channels": len(bad_channels),
                "bad_channel_fraction": len(bad_channels) / len(quality_df)
                if len(quality_df) > 0
                else 0.0,
                "bad_channels": "; ".join(bad_channels),
            }
        )

    # Add average metrics
    for metric in [
        "cv",
        "tsnr",
        "rdi",
        "drift",
        "spectral_entropy",
        "mayer_ratio",
        "resp_ratio",
        "hbo_hbr_corr",
        "hbo_hbr_var_ratio",
        "hbo_hbr_deriv_corr",
    ]:
        if metric in quality_df.columns:
            vals = quality_df[metric].dropna()
            if len(vals) > 0:
                summary[f"mean_{metric}"] = float(np.mean(vals))
                summary[f"median_{metric}"] = float(np.median(vals))

    # Paradigm-specific metrics
    if paradigm == "task" and events is not None:
        # Compute task metrics for each channel pair (or average across channels)
        # For simplicity, compute across all HbO and HbR channels
        hbo_indices = [i for i, ctype in enumerate(ch_types) if ctype == "hbo"]
        hbr_indices = [i for i, ctype in enumerate(ch_types) if ctype == "hbr"]
        if hbo_indices and hbr_indices:
            # Take first channel pair as representative, or average across pairs
            # For now, compute for first pair only
            if pairs:
                base, idx_hbo, idx_hbr = pairs[0]
                hbo_data = data[idx_hbo]
                hbr_data = data[idx_hbr]
                task_metrics = compute_task_metrics(
                    hbo_data,
                    hbr_data,
                    fs,
                    events,
                    baseline_duration=5.0,
                    response_duration=10.0,
                )
                summary.update(
                    {
                        "task_median_cnr_hbo": task_metrics["median_cnr_hbo"],
                        "task_median_cnr_hbr": task_metrics["median_cnr_hbr"],
                        "task_good_event_fraction": task_metrics["good_event_fraction"],
                        "task_n_events": task_metrics["n_events"],
                    }
                )
    elif paradigm == "resting":
        # Compute resting-state metrics across all channels
        hbo_indices = [i for i, ctype in enumerate(ch_types) if ctype == "hbo"]
        hbr_indices = [i for i, ctype in enumerate(ch_types) if ctype == "hbr"]
        if hbo_indices and hbr_indices:
            # Prepare data matrices (n_channels, n_times)
            hbo_matrix = data[hbo_indices, :]
            hbr_matrix = data[hbr_indices, :]
            # Convert bad channel names to indices
            bad_ch_idx = []
            for i, name in enumerate(ch_names):
                if name in bad_channels:
                    bad_ch_idx.append(i)
            resting_metrics = compute_resting_metrics(
                hbo_matrix, hbr_matrix, fs, bad_channels=bad_ch_idx
            )
            summary.update(
                {
                    "resting_split_half_reliability_hbo": resting_metrics[
                        "split_half_reliability_hbo"
                    ],
                    "resting_split_half_reliability_hbr": resting_metrics[
                        "split_half_reliability_hbr"
                    ],
                    "resting_mean_reliability": resting_metrics["mean_reliability"],
                    "resting_retained_duration_fraction": resting_metrics[
                        "retained_duration_fraction"
                    ],
                }
            )

    return quality_df, bad_channels, summary


# =========================
# Comprehensive scoring function
# =========================


def compute_comprehensive_score(
    quality_df: pd.DataFrame,
    paradigm: str = "resting",
    weights: Optional[Dict[str, float]] = None,
    anchor_points: Optional[Dict[str, Tuple[float, float]]] = None,
) -> Dict[str, Any]:
    """
    Compute comprehensive quality score based on signal-level metrics.

    Based on: fnirs_signal_level_qc_metrics.md pseudocode.

    Parameters:
    -----------
    quality_df : DataFrame
        Quality metrics from assess_hb_quality_comprehensive
    paradigm : str
        Paradigm type: "task" or "resting"
    weights : dict, optional
        Weights for different metric groups
    anchor_points : dict, optional
        Anchor points (a, b) for metric mapping

    Returns:
    --------
    Dict with per-channel scores and run-level score
    """
    if weights is None:
        # Default weights from markdown (simplified)
        weights = {
            "cv": 0.1,
            "tsnr": 0.15,
            "rdi": 0.15,
            "drift": 0.1,
            "spectral_entropy": 0.1,
            "mayer_ratio": 0.05,
            "resp_ratio": 0.05,
            "pair_corr": 0.1,
            "var_ratio": 0.1,
            "deriv_pair": 0.1,
        }

    if anchor_points is None:
        # Default anchor points (a, b) for metric mapping
        # These are example values and should be tuned
        anchor_points = {
            "cv": (0.1, 3.0),  # lower_better
            "tsnr": (1.0, 10.0),  # higher_better
            "rdi": (0.1, 5.0),  # lower_better
            "drift": (0.01, 0.5),  # lower_better
            "spectral_entropy": (0.5, 3.0),  # lower_better
            "mayer_ratio": (0.01, 10.0),  # band_metric
            "resp_ratio": (0.01, 10.0),  # band_metric
            "pair_corr": (-0.8, 0.8),  # pair_corr
            "var_ratio": (0.5, 2.0),  # var_ratio
            "deriv_pair": (-0.8, 0.8),  # pair_corr
        }

    # Initialize scores
    channel_scores = []

    # Process each channel or pair
    unique_bases = quality_df["pair_base"].dropna().unique()

    for base in unique_bases:
        if base == "":
            continue

        pair_df = quality_df[quality_df["pair_base"] == base]
        if len(pair_df) != 2:  # Should have HbO and HbR
            continue

        # Get metrics for both channels
        hbo_row = pair_df[pair_df["type"] == "hbo"].iloc[0]
        hbr_row = pair_df[pair_df["type"] == "hbr"].iloc[0]

        # Map metrics to scores
        scores = {}

        # Signal-level metrics (average of HbO and HbR)
        for metric in [
            "cv",
            "tsnr",
            "rdi",
            "drift",
            "spectral_entropy",
            "mayer_ratio",
            "resp_ratio",
        ]:
            if metric in anchor_points:
                a, b = anchor_points[metric]

                if metric in ["mayer_ratio", "resp_ratio"]:
                    metric_type = "band_metric"
                elif metric in ["tsnr"]:
                    metric_type = "higher_better"
                else:
                    metric_type = "lower_better"

                # Average score for HbO and HbR
                val_hbo = hbo_row.get(metric, np.nan)
                val_hbr = hbr_row.get(metric, np.nan)

                score_hbo = map_metric_to_score(val_hbo, metric_type, a, b)
                score_hbr = map_metric_to_score(val_hbr, metric_type, a, b)

                if not np.isnan(score_hbo) and not np.isnan(score_hbr):
                    scores[metric] = (score_hbo + score_hbr) / 2.0
                elif not np.isnan(score_hbo):
                    scores[metric] = score_hbo
                elif not np.isnan(score_hbr):
                    scores[metric] = score_hbr
                else:
                    scores[metric] = 0.0

        # Pair metrics
        if "pair_corr" in anchor_points:
            a, b = anchor_points["pair_corr"]
            corr_val = hbo_row.get("hbo_hbr_corr", np.nan)
            scores["pair_corr"] = map_metric_to_score(corr_val, "pair_corr", a, b)

        if "var_ratio" in anchor_points:
            a, b = anchor_points["var_ratio"]
            var_ratio_val = hbo_row.get("hbo_hbr_var_ratio", np.nan)
            scores["var_ratio"] = map_metric_to_score(var_ratio_val, "var_ratio", a, b)

        if "deriv_pair" in anchor_points:
            a, b = anchor_points["deriv_pair"]
            deriv_corr_val = hbo_row.get("hbo_hbr_deriv_corr", np.nan)
            scores["deriv_pair"] = map_metric_to_score(
                deriv_corr_val, "pair_corr", a, b
            )

        # Compute weighted composite score
        composite_score = 0.0
        total_weight = 0.0

        for metric, score in scores.items():
            if metric in weights:
                composite_score += weights[metric] * score
                total_weight += weights[metric]

        if total_weight > 0:
            composite_score /= total_weight
        else:
            composite_score = 0.0

        # Classify quality tier
        if composite_score < 0.50:
            quality_tier = "poor"
        elif composite_score < 0.70:
            quality_tier = "fair"
        elif composite_score < 0.85:
            quality_tier = "good"
        else:
            quality_tier = "excellent"

        channel_scores.append(
            {
                "pair_base": base,
                "composite_score": composite_score,
                "quality_tier": quality_tier,
                **scores,
            }
        )

    # Compute run-level score (trimmed mean of channel scores)
    if channel_scores:
        scores = [s["composite_score"] for s in channel_scores]
        # Trimmed mean (remove 10% extremes)
        n = len(scores)
        trim_n = int(0.1 * n)
        if trim_n > 0:
            sorted_scores = sorted(scores)
            trimmed_scores = sorted_scores[trim_n:-trim_n] if trim_n * 2 < n else scores
        else:
            trimmed_scores = scores

        run_score = np.mean(trimmed_scores) if trimmed_scores else 0.0

        # Classify run quality
        if run_score < 0.50:
            run_tier = "poor"
        elif run_score < 0.70:
            run_tier = "fair"
        elif run_score < 0.85:
            run_tier = "good"
        else:
            run_tier = "excellent"
    else:
        run_score = 0.0
        run_tier = "poor"

    return {
        "run_score": run_score,
        "run_tier": run_tier,
        "channel_scores": channel_scores,
        "n_channels_scored": len(channel_scores),
    }


# =========================
# Task-based metrics (stub - requires event information)
# =========================


def compute_task_metrics(
    hbo_data: np.ndarray,
    hbr_data: np.ndarray,
    fs: float,
    events: Dict[str, Any],
    baseline_duration: float = 5.0,
    response_duration: float = 10.0,
    tau_cnr_hbo: float = 0.5,
    tau_cnr_hbr: float = 0.5,
    tau_event_drift: float = 0.1,
    epsilon_sigma: float = 1e-8,
) -> Dict[str, Any]:
    """
    Compute task-based metrics (CNR, GoodEventFraction).

    Based on: fnirs_signal_level_qc_metrics.md pseudocode for task-based design.

    Parameters:
    -----------
    hbo_data, hbr_data : np.ndarray
        Paired HbO and HbR time series for a single channel
    fs : float
        Sampling frequency (Hz)
    events : dict
        Event information with keys:
        - 'onsets': list of event onset times in seconds
        - 'durations': list of event durations in seconds (same length as onsets)
        Optional keys:
        - 'conditions': list of condition labels
        - 'artifacts': list of artifact intervals (start, end) in seconds
    baseline_duration : float
        Duration of baseline window before each event (seconds)
    response_duration : float
        Duration of response window after event onset (seconds)
    tau_cnr_hbo, tau_cnr_hbr : float
        CNR thresholds for HbO and HbR below which an event is marked bad
    tau_event_drift : float
        Baseline drift threshold (slope magnitude) above which event is marked bad
    epsilon_sigma : float
        Small positive constant for numerical stability

    Returns:
    --------
    Dict with task metrics:
    - median_cnr_hbo : median CNR across events for HbO
    - median_cnr_hbr : median CNR across events for HbR
    - good_event_fraction : fraction of events passing quality checks
    - n_events : total number of events processed
    """
    # Extract event information
    onsets = events.get("onsets", [])
    durations = events.get("durations", [])
    if len(onsets) != len(durations):
        raise ValueError("Length of onsets and durations must match")

    n_events = len(onsets)
    if n_events == 0:
        return {
            "median_cnr_hbo": np.nan,
            "median_cnr_hbr": np.nan,
            "good_event_fraction": np.nan,
            "n_events": 0,
        }

    # Convert times to sample indices
    onsets_samples = [int(round(onset * fs)) for onset in onsets]
    durations_samples = [int(round(duration * fs)) for duration in durations]
    baseline_samples = int(round(baseline_duration * fs))
    response_samples = int(round(response_duration * fs))

    # Get artifact intervals if provided
    artifact_intervals = events.get("artifacts", [])
    artifact_masks = []
    for start, end in artifact_intervals:
        start_samp = int(round(start * fs))
        end_samp = int(round(end * fs))
        artifact_masks.append((start_samp, end_samp))

    cnr_list_hbo = []
    cnr_list_hbr = []
    event_good_flags = []

    n_samples = len(hbo_data)
    if len(hbr_data) != n_samples:
        raise ValueError("HbO and HbR data must have same length")

    for i, (onset, duration) in enumerate(zip(onsets_samples, durations_samples)):
        # Define baseline window: before event onset
        baseline_start = onset - baseline_samples
        baseline_end = onset
        # Ensure baseline window is within data bounds
        if baseline_start < 0:
            baseline_start = 0
        if baseline_end > n_samples:
            baseline_end = n_samples

        # Define response window: after event onset, for response_duration
        response_start = onset
        response_end = onset + response_samples
        if response_end > n_samples:
            response_end = n_samples

        # Skip if windows are too small
        if (baseline_end - baseline_start < 3) or (response_end - response_start < 3):
            cnr_list_hbo.append(np.nan)
            cnr_list_hbr.append(np.nan)
            event_good_flags.append(False)
            continue

        # Extract data segments
        baseline_hbo = hbo_data[baseline_start:baseline_end]
        baseline_hbr = hbr_data[baseline_start:baseline_end]
        response_hbo = hbo_data[response_start:response_end]
        response_hbr = hbr_data[response_start:response_end]

        # Compute CNR for HbO and HbR
        # CNR = |mean(baseline) - mean(response)| / sqrt(var(baseline) + var(response))
        mean_b_hbo = np.nanmean(baseline_hbo)
        mean_r_hbo = np.nanmean(response_hbo)
        var_b_hbo = np.nanvar(baseline_hbo)
        var_r_hbo = np.nanvar(response_hbo)

        mean_b_hbr = np.nanmean(baseline_hbr)
        mean_r_hbr = np.nanmean(response_hbr)
        var_b_hbr = np.nanvar(baseline_hbr)
        var_r_hbr = np.nanvar(response_hbr)

        cnr_hbo = np.abs(mean_b_hbo - mean_r_hbo) / np.sqrt(
            var_b_hbo + var_r_hbo + epsilon_sigma
        )
        cnr_hbr = np.abs(mean_b_hbr - mean_r_hbr) / np.sqrt(
            var_b_hbr + var_r_hbr + epsilon_sigma
        )

        cnr_list_hbo.append(cnr_hbo)
        cnr_list_hbr.append(cnr_hbr)

        # Compute baseline drift (linear slope magnitude)
        # Simple linear regression slope = cov(t, x) / var(t)
        n_b = len(baseline_hbo)
        if n_b >= 2:
            t_b = np.arange(n_b) / fs
            slope_hbo = (
                np.cov(t_b, baseline_hbo)[0, 1] / np.var(t_b) if np.var(t_b) > 0 else 0
            )
            slope_hbr = (
                np.cov(t_b, baseline_hbr)[0, 1] / np.var(t_b) if np.var(t_b) > 0 else 0
            )
            baseline_drift_hbo = np.abs(slope_hbo)
            baseline_drift_hbr = np.abs(slope_hbr)
        else:
            baseline_drift_hbo = 0.0
            baseline_drift_hbr = 0.0

        # Check for severe artifact overlap
        severe_artifact_overlap = False
        for art_start, art_end in artifact_masks:
            if not (art_end < baseline_start or art_start > response_end):
                severe_artifact_overlap = True
                break

        # Determine if event is good
        event_is_good = True
        if cnr_hbo < tau_cnr_hbo and cnr_hbr < tau_cnr_hbr:
            event_is_good = False
        if baseline_drift_hbo > tau_event_drift or baseline_drift_hbr > tau_event_drift:
            event_is_good = False
        if severe_artifact_overlap:
            event_is_good = False

        event_good_flags.append(event_is_good)

    # Compute median CNR (ignore NaN)
    valid_cnr_hbo = [c for c in cnr_list_hbo if not np.isnan(c)]
    valid_cnr_hbr = [c for c in cnr_list_hbr if not np.isnan(c)]

    median_cnr_hbo = np.nanmedian(valid_cnr_hbo) if valid_cnr_hbo else np.nan
    median_cnr_hbr = np.nanmedian(valid_cnr_hbr) if valid_cnr_hbr else np.nan

    # Good event fraction
    good_event_fraction = np.mean(event_good_flags) if event_good_flags else 0.0

    return {
        "median_cnr_hbo": float(median_cnr_hbo),
        "median_cnr_hbr": float(median_cnr_hbr),
        "good_event_fraction": float(good_event_fraction),
        "n_events": n_events,
    }


# =========================
# Resting-state metrics (stub - requires split-half analysis)
# =========================


def compute_resting_metrics(
    hbo_data: np.ndarray,
    hbr_data: np.ndarray,
    fs: float,
    bad_channels: Optional[List[int]] = None,
    bad_segments: Optional[List[Tuple[int, int]]] = None,
    epsilon_corr: float = 1e-8,
) -> Dict[str, Any]:
    """
    Compute resting-state metrics (split-half reliability, retained duration fraction).

    Based on: fnirs_signal_level_qc_metrics.md pseudocode for resting-state design.

    Parameters:
    -----------
    hbo_data, hbr_data : np.ndarray
        HbO and HbR time series data.
        If 1D arrays (single channel), shape = (n_times,)
        If 2D arrays (multiple channels), shape = (n_channels, n_times)
    fs : float
        Sampling frequency (Hz)
    bad_channels : list of int, optional
        Indices of bad channels to exclude from analysis
    bad_segments : list of tuples, optional
        List of (start_sample, end_sample) intervals to mask out as bad segments
    epsilon_corr : float
        Small positive constant for numerical stability in correlation

    Returns:
    --------
    Dict with resting-state metrics:
    - split_half_reliability_hbo : split-half reliability for HbO channels
    - split_half_reliability_hbr : split-half reliability for HbR channels
    - mean_reliability : average of HbO and HbR reliabilities
    - retained_duration_fraction : fraction of data retained after removing bad segments
    """
    # Ensure data is 2D: (n_channels, n_times)
    if hbo_data.ndim == 1:
        hbo_data = hbo_data[np.newaxis, :]
    if hbr_data.ndim == 1:
        hbr_data = hbr_data[np.newaxis, :]

    n_ch_hbo, n_times = hbo_data.shape
    n_ch_hbr, n_times_hbr = hbr_data.shape
    if n_times != n_times_hbr:
        raise ValueError("HbO and HbR data must have same number of time points")
    if n_ch_hbo != n_ch_hbr:
        raise ValueError("HbO and HbR data must have same number of channels")

    n_channels = n_ch_hbo

    # 1. Remove bad channels
    if bad_channels is None:
        bad_channels = []
    good_channels = [i for i in range(n_channels) if i not in bad_channels]

    if len(good_channels) < 2:
        # Insufficient channels for connectivity analysis
        return {
            "split_half_reliability_hbo": np.nan,
            "split_half_reliability_hbr": np.nan,
            "mean_reliability": np.nan,
            "retained_duration_fraction": 1.0,
        }

    hbo_good = hbo_data[good_channels, :]
    hbr_good = hbr_data[good_channels, :]

    # 2. Mask bad segments
    retained_mask = np.ones(n_times, dtype=bool)
    if bad_segments is not None:
        for start, end in bad_segments:
            if start < 0:
                start = 0
            if end > n_times:
                end = n_times
            retained_mask[start:end] = False

    retained_indices = np.where(retained_mask)[0]
    retained_fraction = len(retained_indices) / n_times if n_times > 0 else 0.0

    if len(retained_indices) < 10:
        # Insufficient data for split-half analysis
        return {
            "split_half_reliability_hbo": np.nan,
            "split_half_reliability_hbr": np.nan,
            "mean_reliability": np.nan,
            "retained_duration_fraction": retained_fraction,
        }

    # 3. Split retained data into temporal halves
    n_retained = len(retained_indices)
    half_point = n_retained // 2

    # First half indices
    half1_idx = retained_indices[:half_point]
    half2_idx = retained_indices[half_point:]

    # Extract halves
    hbo_half1 = hbo_good[:, half1_idx]
    hbo_half2 = hbo_good[:, half2_idx]
    hbr_half1 = hbr_good[:, half1_idx]
    hbr_half2 = hbr_good[:, half2_idx]

    # 4. Compute functional connectivity matrices (Pearson correlation)
    def compute_fc_matrix(data):
        """Compute correlation matrix for data (n_channels, n_times)"""
        n_ch, n_t = data.shape
        if n_t < 2:
            return np.full((n_ch, n_ch), np.nan)
        # Center data
        data_centered = data - np.mean(data, axis=1, keepdims=True)
        # Compute covariance
        cov = np.dot(data_centered, data_centered.T) / (n_t - 1)
        # Compute standard deviations
        std = np.sqrt(np.diag(cov))
        # Avoid division by zero
        std[std == 0] = epsilon_corr
        # Compute correlation matrix
        corr = cov / np.outer(std, std)
        # Ensure values are within [-1, 1] (numerical errors)
        np.clip(corr, -1, 1, out=corr)
        return corr

    fc_hbo_half1 = compute_fc_matrix(hbo_half1)
    fc_hbo_half2 = compute_fc_matrix(hbo_half2)
    fc_hbr_half1 = compute_fc_matrix(hbr_half1)
    fc_hbr_half2 = compute_fc_matrix(hbr_half2)

    # 5. Vectorize upper triangles (excluding diagonal)
    def vec_upper_triangle(mat):
        n = mat.shape[0]
        if n < 2:
            return np.array([])
        # Get upper triangle indices (i < j)
        rows, cols = np.triu_indices(n, k=1)
        return mat[rows, cols]

    vec_hbo1 = vec_upper_triangle(fc_hbo_half1)
    vec_hbo2 = vec_upper_triangle(fc_hbo_half2)
    vec_hbr1 = vec_upper_triangle(fc_hbr_half1)
    vec_hbr2 = vec_upper_triangle(fc_hbr_half2)

    # 6. Compute split-half reliability (correlation between vectors)
    def safe_corr_vec(x, y):
        if len(x) < 3 or len(y) < 3:
            return np.nan
        if np.std(x) == 0 or np.std(y) == 0:
            return np.nan
        return np.corrcoef(x, y)[0, 1]

    rel_hbo = safe_corr_vec(vec_hbo1, vec_hbo2)
    rel_hbr = safe_corr_vec(vec_hbr1, vec_hbr2)

    # Mean reliability
    mean_rel = (
        np.nanmean([rel_hbo, rel_hbr])
        if not (np.isnan(rel_hbo) and np.isnan(rel_hbr))
        else np.nan
    )

    return {
        "split_half_reliability_hbo": float(rel_hbo),
        "split_half_reliability_hbr": float(rel_hbr),
        "mean_reliability": float(mean_rel),
        "retained_duration_fraction": float(retained_fraction),
    }


# =========================
# Quality assessment function (original)
# =========================
def assess_hb_quality(raw) -> Tuple[pd.DataFrame, List[str]]:
    """
    针对 HbO/HbR 数据做通道级质量评估

    参数：
        raw: MNE raw 对象

    返回：
        quality_df: 质量评估 DataFrame
        bad_channels: 坏通道列表
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    data = raw.get_data()
    ch_names = raw.ch_names
    ch_types = get_channel_types(raw)

    rows = []
    for i, (name, ctype) in enumerate(zip(ch_names, ch_types)):
        x = data[i].astype(float)

        finite_ratio = np.mean(np.isfinite(x))
        nan_ratio = 1.0 - finite_ratio
        std_val = np.nanstd(x)
        mad_val = mad(x)
        ptp_val = np.nanmax(x) - np.nanmin(x) if np.any(np.isfinite(x)) else np.nan

        dx = np.diff(x)
        deriv_mad = mad(dx) if len(dx) > 0 else np.nan
        deriv_std = np.nanstd(dx) if len(dx) > 0 else np.nan

        rows.append(
            {
                "channel": name,
                "type": ctype,
                "nan_ratio": nan_ratio,
                "std": std_val,
                "mad": mad_val,
                "ptp": ptp_val,
                "deriv_mad": deriv_mad,
                "deriv_std": deriv_std,
            }
        )

    quality_df = pd.DataFrame(rows)
    quality_df["pair_base"] = ""
    quality_df["hbo_hbr_corr"] = np.nan

    pairs = pair_hbo_hbr_channels(raw)
    for base, idx_hbo, idx_hbr in pairs:
        corr = safe_corr(data[idx_hbo], data[idx_hbr])
        quality_df.loc[idx_hbo, "pair_base"] = base
        quality_df.loc[idx_hbr, "pair_base"] = base
        quality_df.loc[idx_hbo, "hbo_hbr_corr"] = corr
        quality_df.loc[idx_hbr, "hbo_hbr_corr"] = corr

    quality_df["bad_nan"] = quality_df["nan_ratio"] > 0.05
    quality_df["bad_flat"] = quality_df["std"] < 1e-8
    quality_df["bad_jump"] = False
    quality_df["bad_corr"] = False

    med_deriv = np.nanmedian(quality_df["deriv_mad"])
    mad_deriv = mad(quality_df["deriv_mad"])
    if np.isfinite(mad_deriv) and mad_deriv > 0:
        robust_z = 0.6745 * (quality_df["deriv_mad"] - med_deriv) / mad_deriv
        quality_df["deriv_mad_robust_z"] = robust_z
        quality_df["bad_jump"] = robust_z > 5
    else:
        quality_df["deriv_mad_robust_z"] = np.nan

    quality_df.loc[quality_df["type"].isin(["hbo", "hbr"]), "bad_corr"] = (
        quality_df["hbo_hbr_corr"] > 0.3
    )

    quality_df["bad_any"] = (
        quality_df["bad_nan"]
        | quality_df["bad_flat"]
        | quality_df["bad_jump"]
        | quality_df["bad_corr"]
    )

    quality_df["bad_pair"] = False
    for base in quality_df["pair_base"].dropna().unique():
        if base == "":
            continue
        mask = quality_df["pair_base"] == base
        if quality_df.loc[mask, "bad_any"].any():
            quality_df.loc[mask, "bad_pair"] = True

    quality_df["bad_final"] = quality_df["bad_pair"] | (
        (quality_df["pair_base"] == "") & quality_df["bad_any"]
    )

    bad_channels = quality_df.loc[quality_df["bad_final"], "channel"].tolist()
    bad_channels = expand_fnirs_bads_to_pairs(raw, bad_channels)
    quality_df["bad_final"] = quality_df["channel"].isin(bad_channels)

    return quality_df, bad_channels


# =========================
# Single file processing function
# =========================
def process_one_snirf(
    snirf_path: str | Path,
    out_dir: str | Path,
    l_freq: float = 0.01,
    h_freq: float = 0.2,
    resample_sfreq: Optional[float] = 4.0,
    apply_tddr: bool = True,
    signal_band: Tuple[float, float] = (0.01, 0.2),
    noise_band: Tuple[float, float] = (0.2, 0.5),
    comprehensive: bool = True,  # Enable comprehensive signal level assessment by default
    paradigm: str = "resting",
    events: Optional[Dict[str, Any]] = None,
    write_metadata: bool = True,  # Enable metadata writing by default
    output_snirf_path: Optional[str | Path] = None,
    write_report_csv: bool = True,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    处理单个 SNIRF 文件的质量评估

    参数：
        snirf_path: SNIRF 文件路径
        out_dir: 输出目录
        l_freq: 低通滤波频率
        h_freq: 高通滤波频率
        resample_sfreq: 重采样频率（None 表示不重采样）
        apply_tddr: 是否应用 TDDR
        signal_band: 信号频带
        noise_band: 噪声频带
        comprehensive: 是否执行基于信号水平的综合质量评估（根据 fnirs_signal_level_qc_metrics.md），默认启用
        paradigm: 实验范式，"task" 或 "resting"
        events: 事件信息字典，用于任务范式的指标计算
        write_metadata: 是否将质量评估结果写入 SNIRF 文件元数据，默认启用
        output_snirf_path: 输出 SNIRF 文件路径（None 则自动生成 {stem}_processed.snirf）
        write_report_csv: 是否生成单行 CSV 报告，默认启用
        overwrite: 是否覆盖已存在的输出文件，默认不覆盖

    返回：
        summary: 汇总信息字典，包含元数据写入相关信息（如 metadata_written, output_snirf_file 等）
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    snirf_path = Path(snirf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = snirf_path.stem

    raw = mne.io.read_raw_snirf(str(snirf_path), preload=True, verbose=False)

    hbo_picks, hbr_picks = pick_hbo_hbr(raw)
    if len(hbo_picks) == 0 and len(hbr_picks) == 0:
        raise RuntimeError(f"No hbo/hbr channels detected in {snirf_path.name}")

    raw_hb = raw.copy().pick(hbo_picks.tolist() + hbr_picks.tolist())

    if resample_sfreq is not None and raw_hb.info["sfreq"] > resample_sfreq:
        raw_hb.resample(resample_sfreq, npad="auto")

    # Pre-filter quality assessment
    quality_pre, bad_pre = assess_hb_quality(raw_hb)
    bad_pre = expand_fnirs_bads_to_pairs(raw_hb, bad_pre)
    snr_pre = compute_hb_snr(raw_hb, signal_band=signal_band, noise_band=noise_band)

    # Comprehensive quality assessment (based on signal level)
    comprehensive_quality_df = None
    comprehensive_bad_channels = []
    comprehensive_summary = {}
    if comprehensive:
        fs = raw_hb.info["sfreq"]
        comprehensive_quality_df, comprehensive_bad_channels, comprehensive_summary = (
            assess_hb_quality_comprehensive(
                raw=raw_hb,
                fs=fs,
                paradigm=paradigm,
                events=events,
                apply_hard_gating=True,
            )
        )
        # Save comprehensive detailed results (rounded to 2 decimal places)
        round_dataframe(comprehensive_quality_df).to_csv(
            out_dir / f"{stem}_comprehensive_detail.csv",
            index=False,
            encoding="utf-8-sig",
        )
        # Save comprehensive summary results (rounded values)
        rounded_summary = round_dict_values(comprehensive_summary, decimals=2)
        with open(
            out_dir / f"{stem}_comprehensive_summary.json", "w", encoding="utf-8"
        ) as f:
            json.dump(rounded_summary, f, ensure_ascii=False, indent=2)

    detail_pre = quality_pre.merge(
        snr_pre[["channel", "snr_time_db", "snr_psd_db"]], on="channel", how="left"
    )
    round_dataframe(detail_pre).to_csv(
        out_dir / f"{stem}_prefilter_detail.csv", index=False, encoding="utf-8-sig"
    )

    # Filter + TDDR
    raw_proc = raw_hb.copy()
    raw_proc.info["bads"] = bad_pre.copy()

    raw_proc, filter_method_used = smart_filter_raw(
        raw_proc, l_freq=l_freq, h_freq=h_freq, verbose=False
    )

    if apply_tddr:
        raw_proc = mne.preprocessing.nirs.temporal_derivative_distribution_repair(
            raw_proc
        )

    # Post-filter quality assessment
    quality_post, bad_post = assess_hb_quality(raw_proc)
    bad_post = expand_fnirs_bads_to_pairs(raw_proc, bad_post)
    snr_post = compute_hb_snr(raw_proc, signal_band=signal_band, noise_band=noise_band)

    detail_post = quality_post.merge(
        snr_post[["channel", "snr_time_db", "snr_psd_db"]], on="channel", how="left"
    )
    round_dataframe(detail_post).to_csv(
        out_dir / f"{stem}_postfilter_detail.csv", index=False, encoding="utf-8-sig"
    )

    summary = {
        "input_file": snirf_path.name,
        "n_hbo_channels": int(len(hbo_picks)),
        "n_hbr_channels": int(len(hbr_picks)),
        "sampling_rate_hz": float(raw_hb.info["sfreq"]),
        "duration_sec": float(raw_hb.times[-1]) if len(raw_hb.times) else 0.0,
        "Pre-filter bad channels": "; ".join(bad_pre),
        "n_bad_prefilter": int(len(bad_pre)),
        "Post-filter bad channels": "; ".join(bad_post),
        "n_bad_postfilter": int(len(bad_post)),
        "Pre-filter mean time SNR (dB)": round(
            float(np.nanmean(snr_pre["snr_time_db"])), 2
        ),
        "Pre-filter mean freq SNR (dB)": round(
            float(np.nanmean(snr_pre["snr_psd_db"])), 2
        ),
        "Post-filter mean time SNR (dB)": round(
            float(np.nanmean(snr_post["snr_time_db"])), 2
        ),
        "Post-filter mean freq SNR (dB)": round(
            float(np.nanmean(snr_post["snr_psd_db"])), 2
        ),
        "Pre-filter median time SNR (dB)": round(
            float(np.nanmedian(snr_pre["snr_time_db"])), 2
        ),
        "Pre-filter median freq SNR (dB)": round(
            float(np.nanmedian(snr_pre["snr_psd_db"])), 2
        ),
        "Post-filter median time SNR (dB)": round(
            float(np.nanmedian(snr_post["snr_time_db"])), 2
        ),
        "Post-filter median freq SNR (dB)": round(
            float(np.nanmedian(snr_post["snr_psd_db"])), 2
        ),
        "filter_l_freq": l_freq,
        "filter_h_freq": h_freq,
        "resample_sfreq": resample_sfreq,
        "apply_tddr": apply_tddr,
        "filter_method_used": filter_method_used,
    }

    # Add Comprehensive assessment results (if enabled)
    if comprehensive and comprehensive_summary:
        # Round values in comprehensive_summary
        rounded_comprehensive = round_dict_values(comprehensive_summary, decimals=2)
        summary.update(
            {
                "comprehensive_bad_channels": "; ".join(comprehensive_bad_channels),
                "n_comprehensive_bad_channels": int(len(comprehensive_bad_channels)),
                "comprehensive_bad_channel_fraction": rounded_comprehensive.get(
                    "bad_channel_fraction", 0.0
                ),
                "comprehensive_mean_cv": rounded_comprehensive.get("mean_cv", None),
                "comprehensive_mean_tsnr": rounded_comprehensive.get("mean_tsnr", None),
                "comprehensive_mean_rdi": rounded_comprehensive.get("mean_rdi", None),
                "comprehensive_mean_drift": rounded_comprehensive.get(
                    "mean_drift", None
                ),
                "comprehensive_mean_spectral_entropy": rounded_comprehensive.get(
                    "mean_spectral_entropy", None
                ),
                "comprehensive_mean_mayer_ratio": rounded_comprehensive.get(
                    "mean_mayer_ratio", None
                ),
                "comprehensive_mean_resp_ratio": rounded_comprehensive.get(
                    "mean_resp_ratio", None
                ),
                "comprehensive_mean_hbo_hbr_corr": rounded_comprehensive.get(
                    "mean_hbo_hbr_corr", None
                ),
                "comprehensive_mean_hbo_hbr_var_ratio": rounded_comprehensive.get(
                    "mean_hbo_hbr_var_ratio", None
                ),
                "comprehensive_mean_hbo_hbr_deriv_corr": rounded_comprehensive.get(
                    "mean_hbo_hbr_deriv_corr", None
                ),
            }
        )

    # Metadata writing (if enabled)
    metadata_written = False
    output_snirf_file = None
    report_csv_file = None

    if write_metadata:
        # Determine bad channels (using post-filter bad channel list)
        bad_pre = summary.get("Pre-filter bad channels", "").split("; ")
        bad_post = summary.get("Post-filter bad channels", "").split("; ")
        # Filter empty strings
        bad_pre = [ch for ch in bad_pre if ch]
        bad_post = [ch for ch in bad_post if ch]

        # Use post-filter bad channels as final bad channels
        bad_channels = bad_post if len(bad_post) > 0 else bad_pre

        # Calculate channel scores (simplified: good=1, bad=0)
        channel_scores = {}
        for ch in raw.ch_names:
            channel_scores[ch] = 0.0 if ch in bad_channels else 1.0

        # Calculate overall score (good channel ratio)
        overall_score = (
            1.0 - (len(bad_channels) / len(raw.ch_names))
            if len(raw.ch_names) > 0
            else 0.0
        )

        # Determine output SNIRF file path
        if output_snirf_path is None:
            output_snirf_file = out_dir / f"{stem}_processed.snirf"
        else:
            output_snirf_file = Path(output_snirf_path)

        # Check if file already exists
        if output_snirf_file.exists() and not overwrite:
            raise FileExistsError(
                f"输出文件已存在: {output_snirf_file}。使用 --overwrite 覆盖。"
            )

        # Copy original file to output path (as base)
        import shutil

        shutil.copy(snirf_path, output_snirf_file)

        # Try to use mne_nirs to write metadata, fall back to h5py if not available
        try:
            import mne_nirs
            from mne_nirs.io import write_raw_snirf

            # Create a copy of Raw object with bad channel markers
            raw_with_bads = raw.copy()
            raw_with_bads.info["bads"] = bad_channels.copy()

            # Write SNIRF file, mne_nirs will automatically write bad channel info to metaDataTags
            write_raw_snirf(raw_with_bads, output_snirf_file, overwrite=True)

            # Use h5py to add additional metadata tags
            import h5py

            with h5py.File(output_snirf_file, "r+") as f:
                if "nirs" in f and "metaDataTags" in f["nirs"]:
                    meta = f["nirs/metaDataTags"]

                    # Write bad channel list (semicolon separated)
                    bad_chs_str = "; ".join(bad_channels)
                    if "bad_chs" in meta:
                        del meta["bad_chs"]
                    meta.create_dataset("bad_chs", data=bad_chs_str)

                    # Write overall score
                    if "overall_score" in meta:
                        del meta["overall_score"]
                    meta.create_dataset("overall_score", data=overall_score)

                    # Write channel scores JSON
                    import json as json_module

                    channel_scores_json = json_module.dumps(channel_scores)
                    if "channel_scores_json" in meta:
                        del meta["channel_scores_json"]
                    meta.create_dataset("channel_scores_json", data=channel_scores_json)

                    # Add processing parameters and timestamp
                    import datetime

                    now = datetime.datetime.now().isoformat()
                    if "processing_date" in meta:
                        del meta["processing_date"]
                    meta.create_dataset("processing_date", data=now)

                    if "processing_tool" in meta:
                        del meta["processing_tool"]
                    meta.create_dataset("processing_tool", data="MultiChSync")

            metadata_written = True

        except ImportError:
            # mne_nirs not available, use h5py to write directly
            import h5py
            import json as json_module
            import datetime

            with h5py.File(output_snirf_file, "r+") as f:
                if "nirs" not in f:
                    raise RuntimeError("SNIRF 文件缺少 /nirs 组")

                if "metaDataTags" not in f["nirs"]:
                    # Create metaDataTags group
                    meta = f["nirs"].create_group("metaDataTags")
                else:
                    meta = f["nirs/metaDataTags"]

                # Write bad channel list (semicolon separated)
                bad_chs_str = "; ".join(bad_channels)
                if "bad_chs" in meta:
                    del meta["bad_chs"]
                meta.create_dataset("bad_chs", data=bad_chs_str)

                # Write overall score
                if "overall_score" in meta:
                    del meta["overall_score"]
                meta.create_dataset("overall_score", data=overall_score)

                # Write channel scores JSON
                channel_scores_json = json_module.dumps(channel_scores)
                if "channel_scores_json" in meta:
                    del meta["channel_scores_json"]
                meta.create_dataset("channel_scores_json", data=channel_scores_json)

                # Add processing parameters and timestamp
                now = datetime.datetime.now().isoformat()
                if "processing_date" in meta:
                    del meta["processing_date"]
                meta.create_dataset("processing_date", data=now)

                if "processing_tool" in meta:
                    del meta["processing_tool"]
                meta.create_dataset("processing_tool", data="MultiChSync")

            metadata_written = True

        # Generate single-line CSV report (if enabled)
        if write_report_csv:
            report_csv_file = out_dir / f"{stem}_metadata_report.csv"
            report_data = {
                "input_file": snirf_path.name,
                "n_channels": len(raw.ch_names),
                "n_bad_channels": len(bad_channels),
                "bad_channels": "; ".join(bad_channels),
                "overall_score": round(overall_score, 2),
                "output_snirf_file": str(output_snirf_file.name),
                "metadata_written": metadata_written,
                "processing_date": datetime.datetime.now().isoformat(),
            }
            report_df = pd.DataFrame([report_data])
            report_df.to_csv(report_csv_file, index=False, encoding="utf-8-sig")

        # Update summary dictionary
        summary.update(
            {
                "metadata_written": metadata_written,
                "output_snirf_file": str(output_snirf_file)
                if output_snirf_file
                else None,
                "report_csv_file": str(report_csv_file) if report_csv_file else None,
                "bad_channels": "; ".join(bad_channels),
                "n_bad_channels": len(bad_channels),
                "overall_score": overall_score,
            }
        )

    with open(out_dir / f"{stem}_summary.json", "w", encoding="utf-8") as f:
        json.dump(
            round_dict_values(summary, decimals=2), f, ensure_ascii=False, indent=2
        )

    return summary


# =========================
# Batch processing function
# =========================
def batch_process_snirf_folder(
    in_dir: str | Path,
    out_dir: str | Path,
    l_freq: float = 0.01,
    h_freq: float = 0.2,
    resample_sfreq: Optional[float] = 4.0,
    apply_tddr: bool = True,
    signal_band: Tuple[float, float] = (0.01, 0.2),
    noise_band: Tuple[float, float] = (0.2, 0.5),
    comprehensive: bool = True,
    paradigm: str = "resting",
    events: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    """
    批量处理 SNIRF 文件夹

    参数：
        in_dir: 输入目录
        out_dir: 输出目录
        l_freq: 低通滤波频率
        h_freq: 高通滤波频率
        resample_sfreq: 重采样频率
        apply_tddr: 是否应用 TDDR
        signal_band: 信号频带
        noise_band: 噪声频带
        comprehensive: 是否执行基于信号水平的综合质量评估（根据 fnirs_signal_level_qc_metrics.md）
        paradigm: 实验范式，"task" 或 "resting"
        events: 事件信息字典，用于任务范式的指标计算

    返回：
        summary_df: 汇总 DataFrame
        failed: 失败文件列表
    """
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob("*.snirf"))
    # Filter out hidden files (macOS ._ files) and system files
    files = [
        f
        for f in files
        if not any(part.startswith(".") or part == "__MACOSX" for part in f.parts)
    ]
    if not files:
        raise FileNotFoundError(f"No .snirf files found in: {in_dir}")

    results = []
    failed = []

    for f in files:
        print(f"Processing: {f.name}")
        try:
            res = process_one_snirf(
                snirf_path=f,
                out_dir=out_dir,
                l_freq=l_freq,
                h_freq=h_freq,
                resample_sfreq=resample_sfreq,
                apply_tddr=apply_tddr,
                signal_band=signal_band,
                noise_band=noise_band,
                comprehensive=comprehensive,
                paradigm=paradigm,
                events=events,
            )
            results.append(res)
            print(f"Done: {f.name}")
        except Exception as e:
            failed.append({"input_file": f.name, "error": str(e)})
            print(f"Failed: {f.name} | {e}")

    summary_df = pd.DataFrame(results)
    summary_csv = out_dir / "snirf_batch_summary.csv"
    round_dataframe(summary_df).to_csv(summary_csv, index=False, encoding="utf-8-sig")

    if failed:
        failed_df = pd.DataFrame(failed)
        failed_df.to_csv(
            out_dir / "snirf_batch_failed.csv", index=False, encoding="utf-8-sig"
        )

    print("\nBatch finished.")
    print(f"Summary saved to: {summary_csv}")
    if failed:
        print(f"Failed files: {len(failed)}")

    return summary_df, failed


# =========================
# Metadata writing function (based on snirf_quality_pipeline.py)
# =========================


def process_one_snirf_with_metadata(
    snirf_path: str | Path,
    out_dir: str | Path,
    l_freq: float = 0.01,
    h_freq: float = 0.2,
    resample_sfreq: Optional[float] = 4.0,
    apply_tddr: bool = True,
    signal_band: Tuple[float, float] = (0.01, 0.2),
    noise_band: Tuple[float, float] = (0.2, 0.5),
    comprehensive: bool = True,  # Enable comprehensive signal level assessment by default
    paradigm: str = "resting",
    events: Optional[Dict[str, Any]] = None,
    write_metadata: bool = True,
    output_snirf_path: Optional[str | Path] = None,
    write_report_csv: bool = True,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    处理单个 SNIRF 文件的质量评估，并将结果写入 SNIRF 文件的元数据中

    参数：
        snirf_path: SNIRF 文件路径
        out_dir: 输出目录（用于保存报告文件）
        l_freq: 低通滤波频率
        h_freq: 高通滤波频率
        resample_sfreq: 重采样频率（None 表示不重采样）
        apply_tddr: 是否应用 TDDR
        signal_band: 信号频带
        noise_band: 噪声频带
        comprehensive: 是否执行基于信号水平的综合质量评估
        paradigm: 实验范式，"task" 或 "resting"
        events: 事件信息字典
        write_metadata: 是否将坏通道信息和质量分数写入 SNIRF 文件
        output_snirf_path: 输出 SNIRF 文件路径（None 则自动生成）
        write_report_csv: 是否生成单行 CSV 报告
        overwrite: 是否覆盖已存在的输出文件

    返回：
        summary: 汇总信息字典，包含额外的元数据写入信息
    """
    if not MNE_AVAILABLE:
        raise ImportError("MNE is required for this function")

    snirf_path = Path(snirf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = snirf_path.stem

    # 1. Run standard quality assessment
    summary = process_one_snirf(
        snirf_path=snirf_path,
        out_dir=out_dir,
        l_freq=l_freq,
        h_freq=h_freq,
        resample_sfreq=resample_sfreq,
        apply_tddr=apply_tddr,
        signal_band=signal_band,
        noise_band=noise_band,
        comprehensive=comprehensive,
        paradigm=paradigm,
        events=events,
    )

    # 2. Read raw data to get bad channel info
    raw = mne.io.read_raw_snirf(str(snirf_path), preload=True, verbose=False)

    # Determine bad channels (using post-filter bad channel list)
    bad_pre = summary.get("Pre-filter bad channels", "").split("; ")
    bad_post = summary.get("Post-filter bad channels", "").split("; ")
    # Filter empty strings
    bad_pre = [ch for ch in bad_pre if ch]
    bad_post = [ch for ch in bad_post if ch]

    # Use post-filter bad channels as final bad channels
    bad_channels = bad_post if len(bad_post) > 0 else bad_pre

    # 3. Calculate channel scores (simplified: good=1, bad=0)
    channel_scores = {}
    for ch in raw.ch_names:
        channel_scores[ch] = 0.0 if ch in bad_channels else 1.0

    # Calculate overall score (good channel ratio)
    overall_score = (
        1.0 - (len(bad_channels) / len(raw.ch_names)) if len(raw.ch_names) > 0 else 0.0
    )

    # 4. If needed, write metadata to SNIRF file
    metadata_written = False
    output_snirf_file = None

    if write_metadata:
        # Determine output SNIRF file path
        if output_snirf_path is None:
            output_snirf_file = out_dir / f"{stem}_processed.snirf"
        else:
            output_snirf_file = Path(output_snirf_path)

        # Check if file already exists
        if output_snirf_file.exists() and not overwrite:
            raise FileExistsError(
                f"Output SNIRF file already exists: {output_snirf_file}. "
                "Use overwrite=True to overwrite."
            )

        # Write bad channel info to MNE raw object
        raw.info["bads"] = bad_channels.copy()

        # Try to use mne_nirs to write SNIRF (if available)
        if MNE_NIRS_AVAILABLE and write_raw_snirf is not None:
            write_raw_snirf(raw, str(output_snirf_file))
            metadata_written = True
        else:
            # If mne_nirs not available, use h5py to directly modify original file or create copy
            # Ensure output file exists and contains correct SNIRF structure
            import shutil

            if not output_snirf_file.exists():
                # File does not exist, copy from original
                shutil.copy2(snirf_path, output_snirf_file)
                print(f"复制原始文件到: {output_snirf_file}")
            elif overwrite and output_snirf_file != snirf_path:
                # File exists and overwrite allowed, recopy to ensure correct structure
                shutil.copy2(snirf_path, output_snirf_file)
                print(f"覆盖文件并复制原始结构: {output_snirf_file}")
            elif not overwrite and output_snirf_file != snirf_path:
                # File exists but overwrite not allowed (this case should have been caught by previous checks)
                # For safety, still copy here (actually won't execute)
                shutil.copy2(snirf_path, output_snirf_file)
                print(f"复制原始文件到现有位置: {output_snirf_file}")

            # Use h5py to add metadata tags
            try:
                with h5py.File(output_snirf_file, "a") as f:
                    # Ensure nirs/metaDataTags group exists
                    if "nirs" not in f:
                        raise KeyError("SNIRF file missing 'nirs' group")

                    nirs_group = f["nirs"]
                    if "metaDataTags" not in nirs_group:
                        meta_group = nirs_group.create_group("metaDataTags")
                    else:
                        meta_group = nirs_group["metaDataTags"]

                    # Write bad channel list
                    if bad_channels:
                        meta_group["bad_chs"] = ";".join(bad_channels)
                    else:
                        meta_group["bad_chs"] = ""

                    # Write overall score
                    meta_group["overall_score"] = str(overall_score)

                    # Write channel scores (JSON format)
                    meta_group["channel_scores_json"] = json.dumps(channel_scores)

                    # Write processing timestamp
                    from datetime import datetime

                    meta_group["processing_timestamp"] = datetime.now().isoformat()

                    # Write processing parameters summary
                    meta_group["processing_params"] = json.dumps(
                        {
                            "l_freq": l_freq,
                            "h_freq": h_freq,
                            "resample_sfreq": resample_sfreq,
                            "apply_tddr": apply_tddr,
                            "comprehensive": comprehensive,
                            "paradigm": paradigm,
                        }
                    )

                metadata_written = True
            except Exception as e:
                print(f"警告: 无法将元数据写入 SNIRF 文件: {e}")
                metadata_written = False

    # 5. If needed, generate single-line CSV report
    report_csv_path = None
    if write_report_csv:
        report_csv_path = out_dir / f"{stem}_report.csv"

        # Prepare report data
        report_data = {
            "file": snirf_path.name,
            "overall_score": overall_score,
            "n_bad_channels": len(bad_channels),
            "bad_channels": ";".join(bad_channels) if bad_channels else "",
            "prefilter_bad_channels": ";".join(bad_pre) if bad_pre else "",
            "postfilter_bad_channels": ";".join(bad_post) if bad_post else "",
            "channel_scores_json": json.dumps(channel_scores),
            "metadata_written": metadata_written,
            "output_snirf_file": str(output_snirf_file) if output_snirf_file else "",
        }

        # Add other useful fields from summary
        for key in [
            "n_hbo_channels",
            "n_hbr_channels",
            "sampling_rate_hz",
            "duration_sec",
            "Pre-filter mean time SNR (dB)",
            "Post-filter mean time SNR (dB)",
        ]:
            if key in summary:
                report_data[key] = summary[key]

        report_df = pd.DataFrame([report_data])
        report_df.to_csv(report_csv_path, index=False, encoding="utf-8-sig")

    # 6. Update summary dictionary
    summary.update(
        {
            "metadata_written": metadata_written,
            "output_snirf_file": str(output_snirf_file) if output_snirf_file else "",
            "overall_score": overall_score,
            "n_bad_channels": len(bad_channels),
            "bad_channels": ";".join(bad_channels) if bad_channels else "",
            "report_csv_file": str(report_csv_path) if report_csv_path else "",
        }
    )

    return summary


# =========================
# Batch processing function (with metadata writing)
# =========================


def batch_process_snirf_folder_with_metadata(
    in_dir: str | Path,
    out_dir: str | Path,
    l_freq: float = 0.01,
    h_freq: float = 0.2,
    resample_sfreq: Optional[float] = 4.0,
    apply_tddr: bool = True,
    signal_band: Tuple[float, float] = (0.01, 0.2),
    noise_band: Tuple[float, float] = (0.2, 0.5),
    comprehensive: bool = True,
    paradigm: str = "resting",
    events: Optional[Dict[str, Any]] = None,
    write_metadata: bool = True,
    write_report_csv: bool = True,
    overwrite: bool = False,
) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    """
    批量处理 SNIRF 文件夹，并将结果写入 SNIRF 文件的元数据中

    参数：
        in_dir: 输入目录
        out_dir: 输出目录
        l_freq: 低通滤波频率
        h_freq: 高通滤波频率
        resample_sfreq: 重采样频率
        apply_tddr: 是否应用 TDDR
        signal_band: 信号频带
        noise_band: 噪声频带
        comprehensive: 是否执行基于信号水平的综合质量评估
        paradigm: 实验范式，"task" 或 "resting"
        events: 事件信息字典
        write_metadata: 是否将坏通道信息和质量分数写入 SNIRF 文件
        write_report_csv: 是否生成单行 CSV 报告
        overwrite: 是否覆盖已存在的输出文件

    返回：
        summary_df: 汇总 DataFrame
        failed: 失败文件列表
    """
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob("*.snirf"))
    # Filter hidden files (macOS ._ files) and system files
    files = [
        f
        for f in files
        if not any(part.startswith(".") or part == "__MACOSX" for part in f.parts)
    ]
    if not files:
        raise FileNotFoundError(f"No .snirf files found in: {in_dir}")

    results = []
    failed = []

    for f in files:
        print(f"Processing with metadata: {f.name}")
        try:
            res = process_one_snirf_with_metadata(
                snirf_path=f,
                out_dir=out_dir,
                l_freq=l_freq,
                h_freq=h_freq,
                resample_sfreq=resample_sfreq,
                apply_tddr=apply_tddr,
                signal_band=signal_band,
                noise_band=noise_band,
                comprehensive=comprehensive,
                paradigm=paradigm,
                events=events,
                write_metadata=write_metadata,
                output_snirf_path=None,  # auto-generate
                write_report_csv=write_report_csv,
                overwrite=overwrite,
            )
            results.append(res)
            print(f"Done: {f.name}")
        except Exception as e:
            failed.append({"input_file": f.name, "error": str(e)})
            print(f"Failed: {f.name} | {e}")

    summary_df = pd.DataFrame(results)
    summary_csv = out_dir / "snirf_batch_summary_with_metadata.csv"
    round_dataframe(summary_df).to_csv(summary_csv, index=False, encoding="utf-8-sig")

    if failed:
        failed_df = pd.DataFrame(failed)
        failed_df.to_csv(
            out_dir / "snirf_batch_failed.csv", index=False, encoding="utf-8-sig"
        )

    print("\nBatch with metadata finished.")
    print(f"Summary saved to: {summary_csv}")
    if failed:
        print(f"Failed files: {len(failed)}")

    return summary_df, failed


def batch_compute_resting_metrics(
    input_dir: str | Path,
    output_dir: str | Path,
    temp_dir: Optional[str | Path] = None,
) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    """
    批量计算所有fNIRS文件的静息态指标

    参数:
        input_dir: 包含.snirf文件的输入目录
        output_dir: 输出目录
        temp_dir: 临时目录路径（用于存储补丁后的文件）

    返回:
        summary_df: 汇总DataFrame
        failed: 失败文件列表
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if temp_dir is None:
        temp_dir = output_dir / "temp_patched"
    temp_dir = Path(temp_dir)

    # Find all .snirf files
    snirf_files = sorted(input_dir.glob("*.snirf"))

    # Filter hidden files (macOS ._ files) and system files
    snirf_files = [
        f
        for f in snirf_files
        if not any(part.startswith(".") or part == "__MACOSX" for part in f.parts)
    ]

    if not snirf_files:
        raise FileNotFoundError(f"No .snirf files found in: {input_dir}")

    print(f"Found {len(snirf_files)} SNIRF files")

    # Create temp directory for patch files
    temp_dir.mkdir(exist_ok=True)

    # Helper function: clean data for JSON serialization
    def _clean_for_json(obj):
        """递归清理对象，将NumPy类型转换为Python原生类型，NaN转换为None"""
        import numpy as np

        if isinstance(obj, (np.floating, float)):
            # Check if NaN or Inf
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, (np.integer, int)):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            # Recursively process array elements
            return [_clean_for_json(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: _clean_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [_clean_for_json(item) for item in obj]
        else:
            return obj

    # Process each file
    results = []
    failed = []

    for i, snirf_path in enumerate(snirf_files, 1):
        print(f"[{i}/{len(snirf_files)}] Processing: {snirf_path.name}")

        # Use functions from previous script (need to import them)
        # Simplified here: directly call compute_resting_metrics_for_file
        # But for module completeness, we reimplement the logic

        try:
            # Load SNIRF file
            raw = mne.io.read_raw_snirf(str(snirf_path), preload=True, verbose=False)
        except Exception as e:
            # If direct load fails, try patching
            print(f"  Failed to load directly: {e}")
            try:
                from ..fnirs.mne_patch import patch_snirf_for_mne

                patched_path = temp_dir / f"patched_{snirf_path.name}"
                patch_snirf_for_mne(
                    input_snirf=snirf_path,
                    output_snirf=patched_path,
                    dummy_wavelengths=(760.0, 850.0),
                    move_hbt_to_aux=True,
                )
                raw = mne.io.read_raw_snirf(
                    str(patched_path), preload=True, verbose=False
                )
            except Exception as e2:
                print(f"  Failed to patch and load: {e2}")
                failed.append(
                    {
                        "file_name": snirf_path.name,
                        "file_path": str(snirf_path),
                        "error": str(e2),
                    }
                )
                continue

        try:
            # Extract HbO/HbR data
            hbo_picks = mne.pick_types(raw.info, fnirs="hbo")
            hbr_picks = mne.pick_types(raw.info, fnirs="hbr")

            if len(hbo_picks) == 0 or len(hbr_picks) == 0:
                raise ValueError(
                    f"No HbO/HbR channels detected: HbO={len(hbo_picks)}, HbR={len(hbr_picks)}"
                )

            data = raw.get_data()
            fs = raw.info["sfreq"]

            # Ensure channel count matches
            min_channels = min(len(hbo_picks), len(hbr_picks))
            hbo_data = data[hbo_picks[:min_channels], :]
            hbr_data = data[hbr_picks[:min_channels], :]

            # Calculate resting-state metrics
            resting_metrics = compute_resting_metrics(
                hbo_data, hbr_data, fs, bad_channels=None, bad_segments=None
            )

            # Execute comprehensive quality assessment to get channel-level info
            quality_df, bad_channels, quality_summary = assess_hb_quality_comprehensive(
                raw=raw, fs=fs, paradigm="resting", apply_hard_gating=True
            )

            # Get channel pair info
            pairs = pair_hbo_hbr_channels(raw)

            # Analyze pair channel quality
            # First, create channel name to quality status mapping
            channel_bad_status = {}
            for _, row in quality_df.iterrows():
                channel_bad_status[row["channel"]] = row.get("bad_final", False)

            # Analyze pair channels
            possible_bad_pairs = []  # pairs where both hbo and hbr are bad
            all_good_pairs = []  # pairs where both hbo and hbr are good
            pair_scores = {}  # pair scores (for selecting best)

            for base_name, idx_hbo, idx_hbr in pairs:
                if idx_hbo < len(quality_df) and idx_hbr < len(quality_df):
                    hbo_ch_name = quality_df.iloc[idx_hbo]["channel"]
                    hbr_ch_name = quality_df.iloc[idx_hbr]["channel"]

                    hbo_bad = channel_bad_status.get(hbo_ch_name, True)
                    hbr_bad = channel_bad_status.get(hbr_ch_name, True)

                    # If both channels are bad
                    if hbo_bad and hbr_bad:
                        possible_bad_pairs.append(base_name)

                    # If both channels are good
                    if not hbo_bad and not hbr_bad:
                        all_good_pairs.append(base_name)

                        # Calculate pair score (use comprehensive score, or reliability if not available)
                        # Simplified here: use average TSNR of both channels as score
                        hbo_tsnr = quality_df.iloc[idx_hbo].get("tsnr", 0)
                        hbr_tsnr = quality_df.iloc[idx_hbr].get("tsnr", 0)
                        pair_score = (
                            (hbo_tsnr + hbr_tsnr) / 2
                            if not (np.isnan(hbo_tsnr) or np.isnan(hbr_tsnr))
                            else 0
                        )
                        pair_scores[base_name] = pair_score

            # Select best 5% channel pairs
            best_channels = []
            if all_good_pairs and pair_scores:
                # Sort by score
                sorted_pairs = sorted(
                    pair_scores.items(), key=lambda x: x[1], reverse=True
                )
                # Take top 5%
                n_best = max(1, int(len(sorted_pairs) * 0.05))
                best_channels = [pair[0] for pair in sorted_pairs[:n_best]]

            # Calculate n_possible_bad_sequence (simplified here to bad pair count)
            n_possible_bad_sequence = len(possible_bad_pairs)

            # Prepare results - adjust columns as per user request
            result = {
                "file_name": snirf_path.name,
                "file_path": str(snirf_path),  # will be deleted
                "n_channels_hbo": hbo_data.shape[0],
                "n_channels_hbr": hbr_data.shape[0],
                "n_timepoints": hbo_data.shape[1],  # will be deleted
                "sampling_freq": fs,  # will be deleted
                "duration_seconds": hbo_data.shape[1] / fs if fs > 0 else 0,
                # Resting-state metrics
                **resting_metrics,
                # New columns
                "n_possible_bad_sequence": n_possible_bad_sequence,
                "possible_bad_sequence": "; ".join(possible_bad_pairs)
                if possible_bad_pairs
                else "",
                "possible_bad_channels": (
                    "; ".join(possible_bad_pairs) if possible_bad_pairs else ""
                ),  # same as possible_bad_sequence
                "best_channels": "; ".join(best_channels) if best_channels else "",
                # Keep duration_seconds, but user did not say to delete it
                # New: detailed channel-level metrics
                "channel_metrics": quality_df.replace({np.nan: None}).to_dict(
                    "records"
                ),
                "quality_summary": quality_summary,
                "bad_channels": bad_channels,
            }

            # Note: before final output, we will delete unneeded columns
            # Here we first collect all data, filter when saving CSV

            results.append(result)
            print(
                f"  Success: mean_reliability={resting_metrics['mean_reliability']:.3f}, "
                f"bad_pairs={n_possible_bad_sequence}, best_pairs={len(best_channels)}"
            )

        except Exception as e:
            print(f"  Error processing file: {e}")
            failed.append(
                {
                    "file_name": snirf_path.name,
                    "file_path": str(snirf_path),
                    "error": str(e),
                }
            )

    # Clean up temp directory
    if temp_dir.exists():
        try:
            for f in temp_dir.glob("*"):
                f.unlink()
            temp_dir.rmdir()
        except Exception as e:
            print(f"Warning: Failed to clean temp directory {temp_dir}: {e}")

    # Save results
    if results:
        # Save as JSON file (one per file)
        for result in results:
            file_name = result["file_name"]
            json_path = output_dir / f"{Path(file_name).stem}_resting_metrics.json"
            # Clean data for JSON serialization
            cleaned_result = _clean_for_json(result)
            rounded_result = round_dict_values(cleaned_result, decimals=2)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(rounded_result, f, ensure_ascii=False, indent=2)

        # Save as summary CSV file
        df = pd.DataFrame(results)

        # Delete unneeded columns as per user request
        columns_to_drop = [
            "file_path",
            "n_timepoints",
            "sampling_freq",
            "retained_duration_fraction",
        ]
        # Also delete nested data structure columns (these should only be in JSON)
        nested_columns_to_drop = ["channel_metrics", "quality_summary", "bad_channels"]
        columns_to_drop.extend(nested_columns_to_drop)
        columns_to_keep = [col for col in df.columns if col not in columns_to_drop]
        df_filtered = df[columns_to_keep]

        csv_path = output_dir / "resting_metrics_summary.csv"
        round_dataframe(df_filtered).to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\nSaved summary CSV: {csv_path}")
        print(f"Successfully processed {len(results)} files")
        print(f"Columns in CSV: {', '.join(df_filtered.columns)}")

    if failed:
        print(f"\nFailed to process {len(failed)} files:")
        for f in failed:
            print(f"  {f['file_name']}: {f['error']}")

        # Save failed files list
        failed_df = pd.DataFrame(failed)
        failed_csv_path = output_dir / "failed_files.csv"
        failed_df.to_csv(failed_csv_path, index=False, encoding="utf-8-sig")
        print(f"Failed files list saved to: {failed_csv_path}")

    summary_df = pd.DataFrame(results) if results else pd.DataFrame()
    return summary_df, failed
