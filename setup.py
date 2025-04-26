from setuptools import setup, find_packages

setup(
    name="doccli",              # the package name on PyPI (if you ever publish)
    version="0.1.0",
    packages=find_packages(),    # finds the `doccli/` folder
    install_requires=[
        "click>=8.0",
        "openai",
        "pdfminer.six",
    ],
	extras_require={
		"dev": [
			"pytest",
        ]
    }
    entry_points={
        "console_scripts": [
            # format: "<command-name>=<module.path>:<callable>"
            "doccli=doccli.main:cli",
        ],
    },
    author="Ethan Liang",
    description="Document Analyzer CLI",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
)
