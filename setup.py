from setuptools import setup, find_packages

setup(
    name="falyx",
    version="0.0.1",
    description="Reserved package name for future CLI framework.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Roland Thomas Jr",
    author_email="roland@rtj.dev",
    packages=find_packages(),
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 1 - Planning",
    ],
)
