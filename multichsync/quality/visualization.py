"""
fNIRS数据质量可视化模块

提供以下可视化功能：
1. 通道质量热图 - 展示所有通道的总体质量评分
2. 信噪比分布直方图 - 显示 tSNR 值的分布
3. HbO-HbR 相关性散点图 - 展示通道对的相关性
"""

from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import pandas as pd

# Try to import visualization dependencies
try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from matplotlib.colors import LinearSegmentedColormap

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    LinearSegmentedColormap = None
    mcolors = None


def _create_quality_colormap():
    """创建质量颜色映射：绿色(好) -> 黄色(一般) -> 红色(差)"""
    if not MATPLOTLIB_AVAILABLE:
        return None

    colors = ["#2ecc71", "#f1c40f", "#e74c3c"]  # green, yellow, red
    return LinearSegmentedColormap.from_list("quality", colors, N=256)


def _load_quality_data(
    quality_detail_path: Path, comprehensive_detail_path: Optional[Path] = None
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """
    加载质量评估数据

    参数:
        quality_detail_path: 质量详细CSV文件路径
        comprehensive_detail_path: 综合质量详细CSV文件路径

    返回:
        (quality_df, comprehensive_df) 元组
    """
    quality_df = pd.read_csv(quality_detail_path)

    comprehensive_df = None
    if comprehensive_detail_path and comprehensive_detail_path.exists():
        comprehensive_df = pd.read_csv(comprehensive_detail_path)

    return quality_df, comprehensive_df


def generate_channel_quality_heatmap(
    quality_detail_path: Path,
    output_path: Path,
    comprehensive_detail_path: Optional[Path] = None,
    title: str = "Channel Quality Heatmap",
    figsize: Tuple[int, int] = (12, 8),
    dpi: int = 150,
) -> Optional[Path]:
    """
    生成通道质量热图

    参数:
        quality_detail_path: 质量详细CSV文件路径 (*_postfilter_detail.csv)
        output_path: 输出图像路径 (*_channel_quality_heatmap.png)
        comprehensive_detail_path: 综合质量详细CSV文件路径 (可选)
        title: 图像标题
        figsize: 图像尺寸 (宽, 高)
        dpi: 图像分辨率

    返回:
        输出文件路径，如果失败返回 None
    """
    if not MATPLOTLIB_AVAILABLE:
        print("警告: matplotlib 不可用，跳过生成通道质量热图")
        return None

    try:
        quality_df, comprehensive_df = _load_quality_data(
            quality_detail_path, comprehensive_detail_path
        )

        # Get channel list
        channels = quality_df["channel"].tolist()
        n_channels = len(channels)

        if n_channels == 0:
            print("警告: 没有通道数据可绘制")
            return None

        # Calculate quality score (0-1)
        # If comprehensive score data exists, use it; otherwise based on bad_final marker
        if comprehensive_df is not None and "bad_final" in comprehensive_df.columns:
            # Use comprehensive data
            scores = []
            for ch in channels:
                row = comprehensive_df[comprehensive_df["channel"] == ch]
                if len(row) > 0:
                    is_bad = row.iloc[0].get("bad_final", False)
                    # Good channel = 1.0, bad channel = 0.0
                    scores.append(0.0 if is_bad else 1.0)
                else:
                    scores.append(0.5)  # Unknown channel
        else:
            # Use basic quality data
            scores = []
            for ch in channels:
                row = quality_df[quality_df["channel"] == ch]
                if len(row) > 0:
                    is_bad = row.iloc[0].get("bad_final", False)
                    scores.append(0.0 if is_bad else 1.0)
                else:
                    scores.append(0.5)

        # Create heatmap data
        score_array = np.array(scores).reshape(-1, 1)

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Use colormap
        cmap = _create_quality_colormap()

        # Draw heatmap
        im = ax.imshow(score_array, cmap=cmap, aspect="auto", vmin=0, vmax=1)

        # Set labels
        ax.set_yticks(range(n_channels))
        ax.set_yticklabels(channels, fontsize=8)
        ax.set_xticks([])
        ax.set_xlabel("")
        ax.set_title(title, fontsize=14, fontweight="bold")

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax, orientation="horizontal", pad=0.15, shrink=0.8)
        cbar.set_label("Quality Score (1=Good, 0=Bad)", fontsize=10)

        # Add channel type annotations (HbO/HbR)
        ch_types = quality_df["type"].tolist() if "type" in quality_df.columns else []
        for i, ctype in enumerate(ch_types):
            color = "white" if i < len(scores) and scores[i] < 0.5 else "black"
            marker = "O" if ctype == "hbo" else "S"

        plt.tight_layout()

        # Save figure
        plt.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close()

        print(f"通道质量热图已保存: {output_path}")
        return output_path

    except Exception as e:
        print(f"生成通道质量热图失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def generate_snr_distribution_histogram(
    quality_detail_path: Path,
    output_path: Path,
    title: str = "SNR Distribution",
    figsize: Tuple[int, int] = (10, 6),
    dpi: int = 150,
    n_bins: int = 30,
    threshold_line: Optional[float] = 1.0,
) -> Optional[Path]:
    """
    生成信噪比分布直方图

    参数:
        quality_detail_path: 质量详细CSV文件路径
        output_path: 输出图像路径 (*_snr_distribution.png)
        title: 图像标题
        figsize: 图像尺寸
        dpi: 图像分辨率
        n_bins: 直方图bins数量
        threshold_line: 阈值线位置 (默认 1.0)

    返回:
        输出文件路径，如果失败返回 None
    """
    if not MATPLOTLIB_AVAILABLE:
        print("警告: matplotlib 不可用，跳过生成信噪比分布图")
        return None

    try:
        quality_df = pd.read_csv(quality_detail_path)

        # Get tSNR data
        if "tsnr" not in quality_df.columns:
            # If no tSNR, use snr_time_db
            snr_col = "snr_time_db"
            if snr_col not in quality_df.columns:
                print("警告: 没有找到 SNR 数据列")
                return None
        else:
            snr_col = "tsnr"

        snr_values = quality_df[snr_col].dropna().values

        if len(snr_values) == 0:
            print("警告: 没有有效的 SNR 数据")
            return None

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Draw histogram
        n, bins, patches = ax.hist(
            snr_values, bins=n_bins, color="steelblue", edgecolor="white", alpha=0.7
        )

        # Set colors based on thresholds
        if threshold_line is not None:
            # Find bin where threshold is located
            ax.axvline(
                x=threshold_line,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"Threshold (tSNR={threshold_line})",
            )

        # Set labels
        ax.set_xlabel("tSNR", fontsize=12)
        ax.set_ylabel("Number of Channels", fontsize=12)
        ax.set_title(title, fontsize=14, fontweight="bold")

        # Add statistics
        mean_snr = np.mean(snr_values)
        median_snr = np.median(snr_values)
        std_snr = np.std(snr_values)

        stats_text = (
            f"Mean: {mean_snr:.2f}\nMedian: {median_snr:.2f}\nStd: {std_snr:.2f}"
        )
        ax.text(
            0.95,
            0.95,
            stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        # Save figure
        plt.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close()

        print(f"信噪比分布图已保存: {output_path}")
        return output_path

    except Exception as e:
        print(f"生成信噪比分布图失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def generate_hbo_hbr_correlation_plot(
    quality_detail_path: Path,
    output_path: Path,
    comprehensive_detail_path: Optional[Path] = None,
    title: str = "HbO vs HbR Correlation",
    figsize: Tuple[int, int] = (10, 8),
    dpi: int = 150,
) -> Optional[Path]:
    """
    生成 HbO-HbR 相关性散点图

    参数:
        quality_detail_path: 质量详细CSV文件路径
        output_path: 输出图像路径 (*_hbr_hbo_correlation.png)
        comprehensive_detail_path: 综合质量详细CSV文件路径 (可选)
        title: 图像标题
        figsize: 图像尺寸
        dpi: 图像分辨率

    返回:
        输出文件路径，如果失败返回 None
    """
    if not MATPLOTLIB_AVAILABLE:
        print("警告: matplotlib 不可用，跳过生成HbO-HbR相关性图")
        return None

    try:
        # Load data
        quality_df, comprehensive_df = _load_quality_data(
            quality_detail_path, comprehensive_detail_path
        )

        # Separate HbO and HbR channels
        hbo_df = (
            quality_df[quality_df["type"] == "hbo"].copy()
            if "type" in quality_df.columns
            else pd.DataFrame()
        )
        hbr_df = (
            quality_df[quality_df["type"] == "hbr"].copy()
            if "type" in quality_df.columns
            else pd.DataFrame()
        )

        if len(hbo_df) == 0 or len(hbr_df) == 0:
            print("警告: 没有足够的 HbO/HbR 通道数据")
            return None

        # Get pair info
        if comprehensive_df is not None and "pair_base" in comprehensive_df.columns:
            pair_column = "pair_base"
        elif "pair_base" in quality_df.columns:
            pair_column = "pair_base"
        else:
            print("警告: 没有找到配对信息")
            return None

        # Get channel data and correlation
        hbo_data = (
            hbo_df.set_index("pair_base")
            if pair_column in hbo_df.columns
            else hbo_df.set_index("channel")
        )
        hbr_data = (
            hbr_df.set_index("pair_base")
            if pair_column in hbr_df.columns
            else hbr_df.set_index("channel")
        )

        # Get all pairs
        if pair_column in hbo_df.columns:
            pairs = hbo_df[pair_column].dropna().unique()
        else:
            pairs = []

        # Create scatter data
        hbo_values = []
        hbr_values = []
        pair_names = []
        correlations = []

        for pair in pairs:
            if pair == "" or pd.isna(pair):
                continue

            # Get data for this pair
            if pair in hbo_data.index and pair in hbr_data.index:
                # Get channel data (if std column exists)
                if "std" in hbo_data.columns:
                    hbo_std = (
                        hbo_data.loc[pair, "std"] if pair in hbo_data.index else np.nan
                    )
                    hbr_std = (
                        hbr_data.loc[pair, "std"] if pair in hbr_data.index else np.nan
                    )
                else:
                    hbo_std = np.nan
                    hbr_std = np.nan

                # Get correlation
                if (
                    comprehensive_df is not None
                    and "hbo_hbr_corr" in comprehensive_df.columns
                ):
                    corr_row = comprehensive_df[comprehensive_df["pair_base"] == pair]
                    if len(corr_row) > 0:
                        corr = corr_row.iloc[0].get("hbo_hbr_corr", np.nan)
                    else:
                        corr = np.nan
                elif "hbo_hbr_corr" in hbo_data.columns:
                    corr = (
                        hbo_data.loc[pair, "hbo_hbr_corr"]
                        if pair in hbo_data.index
                        else np.nan
                    )
                else:
                    corr = np.nan

                if not np.isnan(hbo_std) and not np.isnan(hbr_std):
                    hbo_values.append(hbo_std)
                    hbr_values.append(hbr_std)
                    pair_names.append(pair)
                    correlations.append(corr)

        if len(hbo_values) == 0:
            print("警告: 没有有效的配对数据可绘制")
            return None

        hbo_values = np.array(hbo_values)
        hbr_values = np.array(hbr_values)

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Draw scatter plot
        scatter = ax.scatter(
            hbo_values,
            hbr_values,
            c=correlations,
            cmap="RdBu_r",
            s=100,
            alpha=0.7,
            edgecolors="black",
        )

        # Add regression line
        if len(hbo_values) > 1:
            z = np.polyfit(hbo_values, hbr_values, 1)
            p = np.poly1d(z)
            x_line = np.linspace(min(hbo_values), max(hbo_values), 100)
            ax.plot(x_line, p(x_line), "r--", linewidth=2, label="Regression Line")

        # Add colorbar
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label("HbO-HbR Correlation", fontsize=10)

        # Calculate and display overall correlation coefficient
        overall_corr = np.corrcoef(hbo_values, hbr_values)[0, 1]

        # Set labels
        ax.set_xlabel("HbO Standard Deviation", fontsize=12)
        ax.set_ylabel("HbR Standard Deviation", fontsize=12)
        ax.set_title(
            f"{title}\n(Overall Correlation: r={overall_corr:.3f})",
            fontsize=14,
            fontweight="bold",
        )

        # Add statistics
        stats_text = f"n={len(hbo_values)} pairs\nr = {overall_corr:.3f}"
        ax.text(
            0.05,
            0.95,
            stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            horizontalalignment="left",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        # Add diagonal reference
        min_val = min(min(hbo_values), min(hbr_values))
        max_val = max(max(hbo_values), max(hbr_values))
        ax.plot([min_val, max_val], [min_val, max_val], "k:", alpha=0.3, label="y=x")

        plt.tight_layout()

        # Save figure
        plt.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close()

        print(f"HbO-HbR相关性图已保存: {output_path}")
        return output_path

    except Exception as e:
        print(f"生成HbO-HbR相关性图失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def generate_all_visualizations(
    input_snirf_path: Path,
    output_dir: Path,
    generate_heatmap: bool = True,
    generate_snr: bool = True,
    generate_correlation: bool = True,
    figsize_heatmap: Tuple[int, int] = (12, 8),
    figsize_snr: Tuple[int, int] = (10, 6),
    figsize_corr: Tuple[int, int] = (10, 8),
    dpi: int = 150,
) -> Dict[str, Optional[Path]]:
    """
    为单个 SNIRF 文件生成所有可视化

    参数:
        input_snirf_path: 输入 SNIRF 文件路径
        output_dir: 输出目录
        generate_heatmap: 是否生成热图
        generate_snr: 是否生成 SNR 分布图
        generate_correlation: 是否生成相关性图
        figsize_heatmap: 热图尺寸
        figsize_snr: SNR 图尺寸
        figsize_corr: 相关性图尺寸
        dpi: 图像分辨率

    返回:
        包含所有输出文件路径的字典
    """
    input_snirf_path = Path(input_snirf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = input_snirf_path.stem

    # File paths
    postfilter_detail = output_dir / f"{stem}_postfilter_detail.csv"
    comprehensive_detail = output_dir / f"{stem}_comprehensive_detail.csv"

    results = {}

    if not postfilter_detail.exists():
        print(f"警告: 详细数据文件不存在: {postfilter_detail}")
        return results

    # 1. Channel quality heatmap
    if generate_heatmap:
        heatmap_path = output_dir / f"{stem}_channel_quality_heatmap.png"
        results["heatmap"] = generate_channel_quality_heatmap(
            quality_detail_path=postfilter_detail,
            output_path=heatmap_path,
            comprehensive_detail_path=comprehensive_detail
            if comprehensive_detail.exists()
            else None,
            title=f"Channel Quality Heatmap - {stem}",
            figsize=figsize_heatmap,
            dpi=dpi,
        )

    # 2. SNR distribution histogram
    if generate_snr:
        snr_path = output_dir / f"{stem}_snr_distribution.png"

        # Determine which SNR column to use
        test_df = pd.read_csv(postfilter_detail)
        snr_col = "tsnr" if "tsnr" in test_df.columns else "snr_time_db"

        results["snr_distribution"] = generate_snr_distribution_histogram(
            quality_detail_path=postfilter_detail,
            output_path=snr_path,
            title=f"tSNR Distribution - {stem}",
            figsize=figsize_snr,
            dpi=dpi,
            threshold_line=1.0,
        )

    # 3. HbO-HbR correlation plot
    if generate_correlation:
        corr_path = output_dir / f"{stem}_hbo_hbr_correlation.png"
        results["correlation"] = generate_hbo_hbr_correlation_plot(
            quality_detail_path=postfilter_detail,
            output_path=corr_path,
            comprehensive_detail_path=comprehensive_detail
            if comprehensive_detail.exists()
            else None,
            title=f"HbO vs HbR Correlation - {stem}",
            figsize=figsize_corr,
            dpi=dpi,
        )

    return results
