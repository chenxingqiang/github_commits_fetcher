from setuptools import setup, find_packages

setup(
    name="github_commits_fetcher",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "requests",
        "pandas",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "github-commits-fetcher=github_commits_fetcher.fetcher:main",
        ],
    },
    author="xingqiang chen",
    author_email="joy6677@qq.com",
    description="A tool to fetch and process GitHub commits",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/chenxingqiang/github_commits_fetcher",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
