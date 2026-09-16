from setuptools import setup, find_packages

setup(
    name="gaming-center",
    version="1.0.0",
    description="Linux Game Service Center mit PCGamingWiki Integration",
    author="Julian",
    packages=find_packages(),
    install_requires=[
        "PyQt6>=6.4.0",
    ],
    entry_points={
        "console_scripts": [
            "gaming-center=gaming_center.app:main",
        ],
    },
    python_requires=">=3.8",
)
