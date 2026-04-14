import os
from pathlib import Path
from .converter import convert_fnirs_to_snirf


def batch_convert_fnirs_to_snirf(input_dir, src_coords_csv, det_coords_csv, output_dir=None, **kwargs):
    """
    批量转换fNIRS TXT文件为SNIRF格式
    
    参数:
        input_dir: 输入目录路径
        src_coords_csv: source坐标CSV文件路径
        det_coords_csv: detector坐标CSV文件路径
        output_dir: 输出目录路径，默认为输入目录
        **kwargs: 传递给convert_fnirs_to_snirf的额外参数
        
    返回:
        converted_files: 转换成功的文件列表
    """
    if output_dir is None:
        output_dir = input_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    converted_files = []
    for file in os.listdir(input_dir):
        # Skip hidden files (macOS ._ files) and system files
        if file.startswith('.') or file == '__MACOSX':
            continue
        if file.upper().endswith('.TXT'):
            txt_path = os.path.join(input_dir, file)
            output_path = os.path.join(output_dir, Path(file).stem + '.snirf')
            try:
                convert_fnirs_to_snirf(
                    txt_path=txt_path,
                    src_coords_csv=src_coords_csv,
                    det_coords_csv=det_coords_csv,
                    output_path=output_path,
                    **kwargs
                )
                converted_files.append(output_path)
            except Exception as e:
                print(f"转换失败 {file}: {e}")
    
    print(f"\n共转换 {len(converted_files)} 个文件")
    return converted_files