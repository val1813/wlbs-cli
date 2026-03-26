from setuptools import setup

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="wlbs-scan",
    version="0.6.9",
    description="WLBS Behavior Graph Scanner — static + dynamic curvature analysis for Python/JS codebases",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Zhongchang Huang (黄中常)",
    author_email="valhuang@kaiwucl.com",
    url="https://github.com/val1813/wlbs-cli",
    python_requires=">=3.8",
    packages=["wlbs_scan"],
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "wlbs=wlbs_scan:main",
            "wlbs-scan=wlbs_scan:main",
        ],
    },
    keywords=[
        "static analysis", "behavior graph", "curvature", "world-line",
        "code quality", "CI", "fault localization", "MoE",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: Other/Proprietary License",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "Operating System :: OS Independent",
    ],
)
