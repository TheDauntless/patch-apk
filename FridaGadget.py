#!/usr/bin/env python3
from __future__ import annotations
import re
import gzip
import lzma
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import time
from Log import Log
import requests.exceptions


import requests
class FridaGadget:

    LATEST_URL = "https://api.github.com/repos/frida/frida/releases/latest"
    TAG_URL_TPL = "https://api.github.com/repos/frida/frida/releases/tags/{tag}"

    # Examples:
    #   frida-gadget-16.4.1-android-arm64.so.xz
    #   frida-gadget-16.4.1-android-arm.so.xz
    #   frida-gadget-16.4.1-android-x86_64.so.xz
    #   frida-gadget-16.4.1-android-x86.so.gz
    ANDROID_GADGET_RE = re.compile(
        r"^frida-gadget-[0-9.]+-android-(arm64|arm|x86_64|x86)\.so(\.(xz|gz))?$"
    )

    ARCH_TO_ABI = {
        "arm": "armeabi-v7a",
        "arm64": "arm64-v8a",
        "x86": "x86",
        "x86_64": "x86_64",
    }

    def __init__(self, user_agent: str = "patch-apk", verbose : bool = False):
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": user_agent,
        })
        # Cache root under the script directory
        self.cache_root = Path(__file__).resolve().parent / ".gadgetCache"

    # ---------- Public API ----------
    

    def obtain_gadgets(self, version: Optional[str] = None) -> tuple[str, List[str]]:
        """
        Ensure Android Frida Gadget .so files are cached at:
        <cache_root>/<tag>/<abi>/libfrida-gadget.so

        Returns:
        (tag, abis_ready)
        """
        release = self.fetch_release(version=version)
        tag = release.get("tag_name") or "unknown"

        if self.verbose:
            Log.info(f"Downloading gadget version {tag}")

        cache_dir = self.cache_root / tag
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Which ABIs are already cached?
        cached_abis = self._cached_abis(cache_dir)

        # Assets for Android only
        wanted_assets = [
            a for a in release.get("assets", [])
            if self._is_android_gadget(a.get("name", ""))
        ]
        if not wanted_assets:
            Log.abort(f"No Android frida-gadget assets found in release {tag}.")

        # Download any missing ABIs into cache
        for asset in wanted_assets:
            name = asset["name"]
            url = asset["browser_download_url"]
            arch = self._extract_arch(name)          # arm / arm64 / x86 / x86_64
            abi = self.ARCH_TO_ABI[arch]             # armeabi-v7a / arm64-v8a / x86 / x86_64

            cache_so = cache_dir / abi / "libfrida-gadget.so"
            if abi not in cached_abis or not cache_so.exists():
                if self.verbose:
                    Log.info(f"Downloading gadget {url}")
                cache_so.parent.mkdir(parents=True, exist_ok=True)

                tmp_download = cache_so.parent / name     # store the archive in same abi dir
                self._download_stream(url, tmp_download)

                # Decompress/move into the canonical libfrida-gadget.so in cache
                self._to_final_so(tmp_download, cache_so, True)

        # Refresh list of ABIs now present
        abis_ready = self._cached_abis(cache_dir)
        if self.verbose:
            for abi in sorted(abis_ready):
                Log.info(f"Cached: {cache_dir / abi / 'libfrida-gadget.so'}")

        return tag


    def copy_android_gadgets(
        self,
        dest_root: Path | str,
        version: Optional[str] = None,
        gadget_config: Optional[Path | str] = None,
        script_source: Optional[Path | str] = None,
    ) -> List[Path]:
        """
        Copy cached gadgets into an APK-like layout under dest_root:

        dest_root/
            lib/<abi>/libfrida-gadget.so
            lib/<abi>/libfrida-gadget.config.so (optional)
            lib/<abi>/libfrida-gadget.script.so (optional)

        """
        dest_root = Path(dest_root).expanduser().resolve()
        cache_root: Path = Path(self.cache_root).expanduser().resolve()

        if not cache_root.exists():
            Log.abort(f"Gadget cache root not found: {cache_root}")

        # --- resolve tag directory ---
        tag_dir: Optional[Path] = None
        if version:
            # try exact match
            cand = cache_root / version
            if cand.is_dir():
                tag_dir = cand
            else:
                # be forgiving with 'v' prefix
                no_v = version[1:] if version.startswith("v") else version
                with_v = f"v{version}" if not version.startswith("v") else version
                for name in (no_v, with_v):
                    cand = cache_root / name
                    if cand.is_dir():
                        tag_dir = cand
                        break
            if not tag_dir:
                raise RuntimeError(f"No cached gadgets for version/tag '{version}' under {cache_root}")
        else:
            # pick the most recently modified tag dir
            tag_dirs = [p for p in cache_root.iterdir() if p.is_dir()]
            if not tag_dirs:
                Log.abort(f"No cached gadget versions found under {cache_root}")
            tag_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            tag_dir = tag_dirs[0]

        if self.verbose:
            Log.info(f"Using cached gadget tag: {tag_dir.name}")

        # --- iterate ABIs under tag dir and copy ---
        copied: List[Path] = []
        any_found = False
        for abi_dir in sorted([d for d in tag_dir.iterdir() if d.is_dir()]):
            src_so = abi_dir / "libfrida-gadget.so"
            if not src_so.exists():
                continue
            any_found = True

            dest_so_dir = dest_root / "lib" / abi_dir.name
            dest_so_dir.mkdir(parents=True, exist_ok=True)
            dest_so = dest_so_dir / "libfrida-gadget.so"

            shutil.copyfile(src_so, dest_so)
            copied.append(dest_so)
            if self.verbose:
                Log.info(f"Copied: {src_so} -> {dest_so}")

            if gadget_config:
                dest_config = dest_so_dir / "libfrida-gadget.config.so"
                shutil.copyfile(gadget_config, dest_config)
                copied.append(dest_config)
                if self.verbose:
                    Log.info(f"Copied config: {gadget_config} -> {dest_config}")

            if script_source:
                dest_script = dest_so_dir / "libfrida-gadget.script.so"
                shutil.copyfile(script_source, dest_script)
                copied.append(dest_script)
                if self.verbose:
                    Log.info(f"Copied script: {script_source} -> {dest_script}")

        if not any_found:
            Log.abort(f"No cached libfrida-gadget.so found under {tag_dir}")

        return copied


    def fetch_release_latest(self) -> Dict:
        r = self.session.get(self.LATEST_URL, timeout=30)
        r.raise_for_status()
        return r.json()

    def fetch_release_tag(self, tag: str) -> Dict:

        try:
            url = self.TAG_URL_TPL.format(tag=tag)
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            else:
                Log.abort(f"HTTP error fetching release tag '{tag}': {e.response.status_code} {e.response.reason}")

        except Exception as e:
            Log.abort(f"Error connecting to GitHub API: {e}")

    def fetch_release(self, version: Optional[str] = None) -> Dict:

        if version:
            if tag := self.fetch_release_tag(version):
                return tag
        
        return self.fetch_release_latest()

    # ---------- Internals ----------

    def _is_android_gadget(self, name: str) -> bool:
        return bool(self.ANDROID_GADGET_RE.match(name))

    def _extract_arch(self, filename: str) -> str:
        m = self.ANDROID_GADGET_RE.match(filename)
        if not m:
            raise ValueError(f"Unsupported gadget filename: {filename}")
        return m.group(1)

    def _download_stream(self, url: str, dest: Path) -> None:
        with self.session.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)

    def _to_final_so(self, src: Path, final_so: Path, do_decompress: bool) -> Path:
        name = src.name
        if do_decompress and name.endswith(".xz"):
            with lzma.open(src, "rb") as f_in, open(final_so, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            src.unlink(missing_ok=True)
            return final_so
        if do_decompress and name.endswith(".gz"):
            with gzip.open(src, "rb") as f_in, open(final_so, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            src.unlink(missing_ok=True)
            return final_so

        # Already a .so (or decompression disabled): move/copy to final name
        if name.endswith(".so"):
            if src != final_so:
                if final_so.exists():
                    final_so.unlink()
                src.replace(final_so)
            return final_so

        shutil.copyfile(src, final_so)
        return final_so

    def _cached_abis(self, cache_dir: Path) -> List[str]:
        """Return ABIs present in the cache for this tag."""
        found = []
        for abi in self.ARCH_TO_ABI.values():
            if (cache_dir / abi / "libfrida-gadget.so").exists():
                found.append(abi)
        return found

