from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="multichsync",
    version="0.1.0",
    author="Neuroimaging Team",
    author_email="example@example.com",
    description="多模态神经影像数据转换工具",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/username/multichsync",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "multichsync=multichsync.cli:main",
        ],
    },
    include_package_data=True,
    keywords="neuroimaging, fnirs, eeg, ecg, converter, snirf",
)