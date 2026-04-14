#!/usr/bin/env python3
"""
移动测试文件到 tests/unit/ 目录并更新导入路径。

用法:
    python move_tests.py [--dry-run] [--verbose]
"""

import argparse
import re
import shutil
from pathlib import Path

TEST_FILES = [
    "test_event_matching.py",
    "test_enhanced_matching_real.py",
    "test_metadata_functionality.py",
]


def update_imports(content: str) -> str:
    """更新测试文件中的导入路径。"""
    # 替换从根目录导入 multichsync 的语句
    # 从: from multichsync... 或 import multichsync
    # 到: from ..multichsync...

    # 处理 import multichsync
    content = re.sub(
        r"^import multichsync(\s|$)",
        "import sys\nsys.path.insert(0, str(Path(__file__).parent.parent))\nimport multichsync",
        content,
        flags=re.MULTILINE,
    )

    # 处理 from multichsync import ...
    content = re.sub(
        r"^from multichsync import",
        "from ..multichsync import",
        content,
        flags=re.MULTILINE,
    )

    # 处理 from multichsync.module import ...
    content = re.sub(
        r"^from multichsync\\.(.*?) import",
        r"from ..multichsync.\1 import",
        content,
        flags=re.MULTILINE,
    )

    return content


def main():
    parser = argparse.ArgumentParser(description="移动测试文件并更新导入")
    parser.add_argument("--dry-run", action="store_true", help="只显示计划的操作")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    source_dir = Path.cwd()
    target_dir = source_dir / "tests" / "unit"

    if not target_dir.exists():
        target_dir.mkdir(parents=True)

    for test_file in TEST_FILES:
        source_path = source_dir / test_file
        if not source_path.exists():
            print(f"警告: {test_file} 不存在，跳过")
            continue

        target_path = target_dir / test_file

        if args.dry_run:
            print(f"[干运行] 将移动 {source_path} -> {target_path}")
            continue

        if args.verbose:
            print(f"移动 {source_path} -> {target_path}")

        # 读取并更新导入
        content = source_path.read_text(encoding="utf-8")
        updated_content = update_imports(content)

        # 写入目标文件
        target_path.write_text(updated_content, encoding="utf-8")

        # 删除源文件
        source_path.unlink()

        print(f"已移动并更新 {test_file}")


if __name__ == "__main__":
    main()
