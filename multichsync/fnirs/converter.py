from pathlib import Path
from .parser import parse_shimadzu_txt, parse_fnirs_header, _load_coordinates_with_map
from .writer import write_snirf, _write_snirf_core
try:
    from .mne_patch import patch_snirf_for_mne, patch_snirf_inplace
except ImportError:
    # 如果h5py不可用，提供存根函数
    patch_snirf_for_mne = None
    patch_snirf_inplace = None


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
    # 解析TXT文件（使用新的解析器）
    parsed = parse_shimadzu_txt(txt_path)
    
    # 加载坐标和映射
    source_pos_3d, source_labels, source_map = _load_coordinates_with_map(src_coords_csv, expected_prefix="T")
    detector_pos_3d, detector_labels, detector_map = _load_coordinates_with_map(det_coords_csv, expected_prefix="R")
    
    # 输出路径
    if output_path is None:
        output_path = Path(txt_path).with_suffix('.snirf')
    else:
        output_path = Path(output_path)
    
    # 写入SNIRF（使用核心写入函数）
    _write_snirf_core(
        output_path=output_path,
        parsed=parsed,
        source_pos_3d=source_pos_3d,
        detector_pos_3d=detector_pos_3d,
        source_labels=source_labels,
        detector_labels=detector_labels,
        source_map=source_map,
        detector_map=detector_map,
        **kwargs
    )
    
    print(f"SNIRF文件已保存: {output_path}")
    
    # 如果需要，应用MNE兼容性修复
    if patch_for_mne:
        if patch_snirf_inplace is None:
            print("警告: 无法导入MNE修复模块，跳过修复步骤")
        else:
            try:
                # 原地修复文件
                patched_path = patch_snirf_inplace(
                    snirf_path=output_path,
                    dummy_wavelengths=(760.0, 850.0),
                    move_hbt_to_aux=True,
                    aux_name="HbT"
                )
                print(f"已应用MNE兼容性修复: {patched_path}")
            except Exception as e:
                print(f"警告: MNE修复失败: {e}")
                print("SNIRF文件已创建但未应用MNE修复")
    
    return str(output_path)


def convert_fnirs_to_snirf_legacy(txt_path, src_coords_csv, det_coords_csv, output_path=None):
    """
    向后兼容的转换函数（保持旧接口）
    
    参数:
        txt_path: fNIRS TXT文件路径
        src_coords_csv: source坐标CSV文件路径
        det_coords_csv: detector坐标CSV文件路径  
        output_path: 输出SNIRF文件路径，默认为同名.snirf
        
    返回:
        output_path: 输出文件路径
    """
    # 解析TXT文件（使用旧接口）
    meta, channel_pairs, times, data_matrix = parse_fnirs_header(txt_path)
    
    # 加载坐标（使用旧接口）
    from .parser import load_coordinates
    sourcePos3D, detectorPos3D, src_labels, det_labels = load_coordinates(src_coords_csv, det_coords_csv)
    
    # 创建映射（假设标签格式为T1,T2,...和R1,R2,...）
    src_map = {}
    for i, label in enumerate(src_labels, start=1):
        # 提取数字部分
        if label.startswith('T'):
            num = int(label[1:])
        else:
            # 尝试提取数字
            import re
            match = re.search(r'\d+', label)
            num = int(match.group()) if match else i
        src_map[num] = i
    
    det_map = {}
    for i, label in enumerate(det_labels, start=1):
        if label.startswith('R'):
            num = int(label[1:])
        else:
            import re
            match = re.search(r'\d+', label)
            num = int(match.group()) if match else i
        det_map[num] = i
    
    # 输出路径
    if output_path is None:
        output_path = Path(txt_path).stem + '.snirf'
    
    # 写入SNIRF（使用旧接口的write_snirf）
    from .writer import write_snirf as write_snirf_legacy
    write_snirf_legacy(
        output_path=output_path,
        meta=meta,
        channel_pairs=channel_pairs,
        times=times,
        data_matrix=data_matrix,
        sourcePos3D=sourcePos3D,
        detectorPos3D=detectorPos3D,
        src_map=src_map,
        det_map=det_map
    )
    
    return output_path