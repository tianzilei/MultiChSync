#!/usr/bin/env python3
"""
fNIRS转换示例
"""

import sys
import os

# 添加父目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multichsync.fnirs import convert_fnirs_to_snirf

def main():
    """
    示例：转换单个fNIRS文件
    
    需要准备以下文件：
    1. data.TXT - fNIRS数据文件（NIRS-SPM格式）
    2. source_coordinates.csv - source坐标文件
    3. detector_coordinates.csv - detector坐标文件
    """
    
    # 示例文件路径（请根据实际情况修改）
    txt_path = "data.TXT"
    src_coords_csv = "source_coordinates.csv"
    det_coords_csv = "detector_coordinates.csv"
    output_path = "output.snirf"
    
    # 检查文件是否存在
    for file_path in [txt_path, src_coords_csv, det_coords_csv]:
        if not os.path.exists(file_path):
            print(f"警告：文件不存在 - {file_path}")
            print("请准备相应的数据文件后再运行此示例")
            return
    
    try:
        # 执行转换
        result_path = convert_fnirs_to_snirf(
            txt_path=txt_path,
            src_coords_csv=src_coords_csv,
            det_coords_csv=det_coords_csv,
            output_path=output_path
        )
        
        print(f"转换成功！")
        print(f"输入文件: {txt_path}")
        print(f"输出文件: {result_path}")
        
    except Exception as e:
        print(f"转换失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()