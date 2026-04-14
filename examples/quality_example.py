#!/usr/bin/env python3
"""
fNIRS质量评估示例

展示 MultiChSync 的质量评估功能，包括：
1. 基本质量评估
2. 综合信号水平评估
3. 元数据写入
4. 静息态指标批量计算
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 70)
    print("MultiChSync 质量评估示例")
    print("=" * 70)
    
    # 创建临时目录用于演示
    temp_dir = tempfile.mkdtemp(prefix="multichsync_quality_demo_")
    print(f"临时演示目录: {temp_dir}")
    
    try:
        # 检查是否有可用的SNIRF文件
        snirf_files = list(Path("Data/convert/fnirs").glob("*.snirf"))
        if not snirf_files:
            print("未找到SNIRF文件。请先运行数据转换或指定文件路径。")
            print("使用示例文件：Data/convert/fnirs/20251101060_1.snirf")
            return
        
        # 使用第一个SNIRF文件作为示例
        input_snirf = snirf_files[0]
        print(f"\n1. 使用示例文件: {input_snirf.name}")
        
        # 导入质量评估模块
        from multichsync.quality import (
            process_one_snirf,
            process_one_snirf_with_metadata,
            assess_hb_quality_comprehensive,
            compute_task_metrics,
            compute_resting_metrics,
            batch_compute_resting_metrics
        )
        from multichsync.fnirs import patch_snirf_for_mne
        
        # 首先修复SNIRF文件以便MNE读取
        patched_snirf = Path(temp_dir) / "patched.snirf"
        patch_snirf_for_mne(
            input_snirf=str(input_snirf),
            output_snirf=str(patched_snirf),
            dummy_wavelengths=(760.0, 850.0),
            move_hbt_to_aux=True
        )
        print(f"   ✓ 已修复SNIRF文件以兼容MNE: {patched_snirf.name}")
        
        # 1. 基本质量评估
        print("\n2. 基本质量评估")
        basic_output = Path(temp_dir) / "basic_quality"
        basic_output.mkdir(exist_ok=True)
        
        summary = process_one_snirf(
            snirf_path=str(patched_snirf),
            out_dir=str(basic_output),
            l_freq=0.01,
            h_freq=0.2,
            resample_sfreq=4.0,
            apply_tddr=True
        )
        
        print(f"   ✓ 基本质量评估完成")
        print(f"     坏通道数（滤波前）: {summary.get('n_bad_prefilter', 'N/A')}")
        print(f"     坏通道数（滤波后）: {summary.get('n_bad_postfilter', 'N/A')}")
        print(f"     输出文件: {basic_output}")
        
        # 2. 综合信号水平评估
        print("\n3. 综合信号水平评估")
        comprehensive_output = Path(temp_dir) / "comprehensive_quality"
        comprehensive_output.mkdir(exist_ok=True)
        
        summary_comprehensive = process_one_snirf(
            snirf_path=str(patched_snirf),
            out_dir=str(comprehensive_output),
            comprehensive=True,
            paradigm="resting",
            l_freq=0.01,
            h_freq=0.2,
            resample_sfreq=4.0,
            apply_tddr=True
        )
        
        print(f"   ✓ 综合信号水平评估完成")
        print(f"     硬门控坏通道数: {summary_comprehensive.get('comprehensive_bad_channels_count', 'N/A')}")
        print(f"     平均变异系数: {summary_comprehensive.get('comprehensive_mean_cv', 'N/A'):.3f}")
        print(f"     平均时域SNR: {summary_comprehensive.get('comprehensive_mean_tsnr', 'N/A'):.2f} dB")
        print(f"     输出文件: {comprehensive_output}")
        
        # 3. 元数据写入
        print("\n4. 元数据写入功能")
        metadata_output = Path(temp_dir) / "metadata_quality"
        metadata_output.mkdir(exist_ok=True)
        
        output_snirf = metadata_output / f"{patched_snirf.stem}_processed.snirf"
        
        summary_metadata = process_one_snirf_with_metadata(
            snirf_path=str(patched_snirf),
            out_dir=str(metadata_output),
            l_freq=0.01,
            h_freq=0.2,
            resample_sfreq=4.0,
            apply_tddr=True,
            comprehensive=True,
            paradigm="resting",
            write_metadata=True,
            output_snirf_path=str(output_snirf),
            write_report_csv=True,
            overwrite=True
        )
        
        print(f"   ✓ 元数据写入完成")
        print(f"     输出SNIRF文件: {output_snirf.name}")
        print(f"     整体质量分数: {summary_metadata.get('overall_score', 'N/A')}")
        
        # 验证元数据已写入
        try:
            import h5py
            with h5py.File(output_snirf, 'r') as f:
                if 'nirs' in f and 'metaDataTags' in f['nirs']:
                    meta = f['nirs/metaDataTags']
                    if 'bad_chs' in meta:
                        bad_chs = meta['bad_chs'][()].decode('utf-8') if hasattr(meta['bad_chs'][()], 'decode') else str(meta['bad_chs'][()])
                        print(f"     坏通道列表: {bad_chs[:50]}...")
        except Exception as e:
            print(f"     元数据验证失败: {e}")
        
        # 4. 静息态指标批量计算（模拟）
        print("\n5. 静息态指标批量计算（模拟）")
        
        # 创建模拟输入目录
        sim_input_dir = Path(temp_dir) / "sim_snirf"
        sim_input_dir.mkdir(exist_ok=True)
        
        # 复制几个文件用于演示
        for i, snirf_file in enumerate(snirf_files[:2]):
            sim_file = sim_input_dir / f"sim_{i}.snirf"
            shutil.copy(snirf_file, sim_file)
        
        metrics_output = Path(temp_dir) / "resting_metrics"
        metrics_output.mkdir(exist_ok=True)
        
        print(f"   模拟批量处理 {len(list(sim_input_dir.glob('*.snirf')))} 个文件")
        
        # 实际项目中可以使用 batch_compute_resting_metrics
        # 这里仅演示API调用
        print("   batch_compute_resting_metrics() 函数用法：")
        print("   from multichsync.quality import batch_compute_resting_metrics")
        print(f"   summary_df = batch_compute_resting_metrics(")
        print(f"       input_dir='{sim_input_dir}',")
        print(f"       output_dir='{metrics_output}',")
        print(f"       overwrite=True")
        print("   )")
        
        # 5. 直接使用高级API函数
        print("\n6. 高级API函数示例")
        
        # 加载数据
        import mne
        raw = mne.io.read_raw_snirf(str(patched_snirf), preload=True)
        
        # 计算静息态指标（单通道示例）
        print("   计算单通道静息态指标...")
        from multichsync.quality import compute_resting_metrics
        
        # 模拟多通道数据
        n_channels = min(8, raw.get_data().shape[0] // 2)
        if n_channels >= 2:
            hbo_data = raw.get_data(picks='hbo')[:n_channels]
            hbr_data = raw.get_data(picks='hbr')[:n_channels]
            
            resting_results = compute_resting_metrics(
                hbo_matrix=hbo_data,
                hbr_matrix=hbr_data,
                fs=raw.info['sfreq']
            )
            
            print(f"     平均可靠性: {resting_results.get('mean_reliability', 'N/A'):.3f}")
            print(f"     保留时长比例: {resting_results.get('retained_duration_fraction', 'N/A'):.3f}")
        
        # 计算任务指标（模拟事件）
        print("   计算任务指标（模拟事件）...")
        from multichsync.quality import compute_task_metrics
        
        # 模拟事件
        events = {
            'onsets': [10.0, 30.0, 50.0, 70.0, 90.0],
            'durations': [5.0, 5.0, 5.0, 5.0, 5.0],
            'artifacts': [(15.0, 20.0)]
        }
        
        if 'hbo' in raw:
            hbo_channel = raw.get_data(picks='hbo')[0]
            hbr_channel = raw.get_data(picks='hbr')[0]
            
            task_results = compute_task_metrics(
                hbo=hbo_channel,
                hbr=hbr_channel,
                fs=raw.info['sfreq'],
                events=events
            )
            
            print(f"     中位数CNR (HbO): {task_results.get('median_cnr_hbo', 'N/A'):.3f}")
            print(f"     中位数CNR (HbR): {task_results.get('median_cnr_hbr', 'N/A'):.3f}")
            print(f"     良好事件比例: {task_results.get('good_event_fraction', 'N/A'):.3f}")
        
        print("\n" + "=" * 70)
        print("示例完成！")
        print(f"所有输出文件保存在临时目录: {temp_dir}")
        print("您可以查看以下目录：")
        print(f"  - 基本质量评估: {basic_output}")
        print(f"  - 综合信号水平评估: {comprehensive_output}")
        print(f"  - 元数据写入: {metadata_output}")
        print(f"  - 静息态指标: {metrics_output}")
        print("\n实际使用时，请将临时目录替换为您的项目路径。")
        
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保已安装所有依赖项：pip install -r requirements.txt")
    except Exception as e:
        print(f"示例执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 询问是否保留临时目录
        keep = input(f"\n是否保留临时目录 {temp_dir}？(y/N): ").strip().lower()
        if keep != 'y':
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("临时目录已删除。")
        else:
            print(f"临时目录保留在: {temp_dir}")

if __name__ == "__main__":
    main()