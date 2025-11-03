from pathlib import Path
from setuptools import setup, find_packages
import re


HERE = Path(__file__).parent


def _safe_read_text(p: Path) -> str:
    """Read a text file trying several encodings to avoid UnicodeDecodeError.

    Tries utf-8, utf-8-sig, utf-16, and latin-1 in that order. If the file
    doesn't exist returns an empty string.
    """
    if not p.exists():
        return ""
    encodings = ("utf-8", "utf-8-sig", "utf-16", "latin-1")
    data = p.read_bytes()
    for enc in encodings:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # as a last resort, decode with latin-1 replacing errors to avoid failing the build
    return data.decode("latin-1", errors="replace")


def read_requirements(req_file: Path):
    text = _safe_read_text(req_file)
    if not text:
        return []
    lines = text.splitlines()
    reqs = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    return reqs


def get_version(pkg_init: Path):
    if not pkg_init.exists():
        return "0.0.0"
    text = _safe_read_text(pkg_init)
    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text)
    return m.group(1) if m else "0.0.0"


long_description = ""
readme_file = HERE / "README.md"
if readme_file.exists():
    long_description = _safe_read_text(readme_file)

install_requires = read_requirements(HERE / "requirements.txt")

setup(
    name="patch-apk",
    version=get_version(HERE / "src" / "patch_apk" / "__init__.py"),
    description="App Bundle / Split APK aware patcher for objection",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            "patch-apk=patch_apk.main:main",
        ]
    },
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
