#!/usr/bin/env python3
"""
移动文档文件到 docs/ 目录。

用法:
    python move_docs.py [--dry-run] [--verbose]
"""
import argparse
import shutil
from pathlib import Path

DOC_FILES = [
    "fnirs_signal_level_qc_metrics.md",
    "event_matching_analysis.md",
    "custom-instructions.md.md",
]

def main():
    parser = argparse.ArgumentParser(description="移动文档文件")
    parser.add_argument("--dry-run", action="store_true", help="只显示计划的操作")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()
    
    source_dir = Path.cwd()
    target_dir = source_dir / "docs"
    
    if not target_dir.exists():
        target_dir.mkdir(parents=True)
    
    for doc_file in DOC_FILES:
        source_path = source_dir / doc_file
        if not source_path.exists():
            print(f"警告: {doc_file} 不存在，跳过")
            continue
        
        target_path = target_dir / doc_file
        
        if args.dry_run:
            print(f"[干运行] 将移动 {source_path} -> {target_path}")
            continue
        
        if args.verbose:
            print(f"移动 {source_path} -> {target_path}")
        
        shutil.move(str(source_path), str(target_path))
        print(f"已移动 {doc_file}")

if __name__ == "__main__":
    main()