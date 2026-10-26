#!/usr/bin/env python3
import argparse, os, re, sys, tempfile, shutil, subprocess
from pathlib import Path

from APK import APK
from ADBHelper import ADBHelper, ADBError
from Log import Log
from FridaGadget import FridaGadget
from termcolor import colored # pip3 install termcolor
from packaging.version import parse as parse_version

def sign_with_apksigner(apk_path: str):

    DEBUG_KS_NAME  = "patchapk.jks"
    DEBUG_KS_ALIAS = "patchapk"
    DEBUG_KS_PASS  = "patchapk" 
  
    script_dir = os.path.dirname(os.path.realpath(__file__))
    ks_path = os.path.join(script_dir, DEBUG_KS_NAME)

    command_name = "apksigner.bat" if os.name == "nt" else "apksigner"
    apksigner_path = shutil.which(command_name)

    if apksigner_path is None:
        raise RuntimeError(
            f"{command_name} was not found. Add the Android SDK "
            "build-tools directory to PATH."
        )

    cmd = [
        apksigner_path,
        "sign",
        "--ks", ks_path,
        "--ks-key-alias", DEBUG_KS_ALIAS,
        "--ks-pass", f"pass:{DEBUG_KS_PASS}",
        "--key-pass", f"pass:{DEBUG_KS_PASS}",
        "--ks-type", "JKS",
        "--v1-signing-enabled=false",
        "--v2-signing-enabled=true",
        "--v3-signing-enabled=true",
        "--v4-signing-enabled=false",
        apk_path,
    ]

    Log.verbose("[apksigner] " + subprocess.list2cmdline(cmd))
    subprocess.run(cmd, check=True)

_BRIDGE_INFO = {
    "java":  ("Java",  "frida-java-bridge"),
    "objc":  ("ObjC",  "frida-objc-bridge"),
    "swift": ("Swift", "frida-swift-bridge"),
}


def detect_script_bridges(script_path: str):
    """Return (needed_bridges, has_bundle_marker) for a user-supplied Frida script.

    needed_bridges is a list of "java" / "objc" / "swift" for the bridges the
    script uses as bare globals. has_bundle_marker is True if the file appears
    to already be a frida-compile output that includes the bridge modules.
    """
    with open(script_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    has_marker = any(pkg in content for _, pkg in _BRIDGE_INFO.values())

    needed = []
    for key, (globl, _) in _BRIDGE_INFO.items():
        # Bare use like `Java.perform(` — exclude `foo.Java.` and identifier prefixes
        if re.search(r"(?<![A-Za-z0-9_$.])" + re.escape(globl) + r"\.", content):
            needed.append(key)

    return needed, has_marker


def _bridge_workspace_root() -> str:
    return os.path.join(os.path.expanduser("~"), ".cache", "patch-apk", "bridge-workspace")


def _ensure_bridge_workspace(bridges) -> str:
    """Ensure ~/.cache/patch-apk/bridge-workspace has node_modules for the requested bridges.

    npm install runs only for bridges that aren't already installed.
    """
    root = _bridge_workspace_root()
    os.makedirs(root, exist_ok=True)

    pkg_json = os.path.join(root, "package.json")
    if not os.path.isfile(pkg_json):
        with open(pkg_json, "w") as f:
            f.write('{"name":"patch-apk-bridges","version":"0.0.1","private":true}\n')

    missing = [_BRIDGE_INFO[k][1] for k in bridges
               if not os.path.isdir(os.path.join(root, "node_modules", _BRIDGE_INFO[k][1]))]
    if missing:
        npm = shutil.which("npm")
        if npm is None:
            Log.abort(
                f"npm is required to install the bridge modules ({', '.join(missing)}).\n"
                "Install Node.js/npm, then re-run — or pass --no-bridge-autocompile if the script "
                "is already bundled."
            )
        Log.info(f"Installing frida bridge modules: {', '.join(missing)}")
        r = subprocess.run(
            [npm, "install", "--silent", "--no-audit", "--no-fund", *missing],
            cwd=root, capture_output=True, text=True,
        )
        if r.returncode != 0:
            Log.abort("npm install failed:\n" + (r.stderr or r.stdout or "").rstrip())
    return root


def bundle_script_with_bridges(script_path: str, bridges) -> str:
    """Run frida-compile to bundle the user's script with the required bridges.

    Returns the absolute path of the produced agent .js file.
    """
    fc = shutil.which("frida-compile")
    bridge_names = ", ".join(_BRIDGE_INFO[k][0] for k in bridges)

    if fc is None:
        Log.abort(
            f"Script uses {bridge_names} but is not bundled with the corresponding "
            f"frida-*-bridge module. Since Frida 17.0, the language bridges are "
            f"no longer part of the runtime and must be bundled into the script.\n\n"
            f"frida-compile was not found on PATH. Install it with:\n"
            f"    pip install frida-tools     (recommended)\n"
            f"    # or\n"
            f"    npm i -g frida-compile\n\n"
            f"Then re-run patch-apk. To skip this check, pass --no-bridge-autocompile."
        )

    root = _ensure_bridge_workspace(bridges)
    run_dir = tempfile.mkdtemp(prefix="run_", dir=root)
    entry_path = os.path.join(run_dir, "entry.js")
    out_path   = os.path.join(run_dir, "agent.js")

    with open(script_path, "r", encoding="utf-8", errors="replace") as f:
        user_content = f.read()

    preamble = []
    for key in bridges:
        globl, pkg = _BRIDGE_INFO[key]
        preamble.append(f"import {globl} from '{pkg}';")
        preamble.append(f"globalThis.{globl} = {globl};")

    with open(entry_path, "w", encoding="utf-8") as f:
        f.write("\n".join(preamble) + "\n\n" + user_content)

    Log.info(f"Bundling script with {bridge_names} bridge via frida-compile")
    result = subprocess.run(
        [fc, "entry.js", "-o", "agent.js"],
        cwd=run_dir, capture_output=True, text=True,
    )
    if result.returncode != 0 or not os.path.isfile(out_path):
        err = (result.stderr or result.stdout or "").rstrip()
        Log.abort(
            "frida-compile failed:\n" + err + "\n\n"
            f"If the error mentions a missing module, ensure npm is available and re-run — "
            f"the cache at {root} will be recreated as needed."
        )

    return out_path


def choose_package(adb: ADBHelper, pattern: str) -> str:
    matches = adb.get_packages(pattern)
    if not matches:
        Log.abort(f"No packages found matching '{pattern}'")

    if len(matches) == 1:
        return matches[0]

    # Multiple matches: show menu, ask user to choose by number
    Log.info("Multiple matching packages found. Select the package to patch:")
    for i, name in enumerate(matches, start=1):
        Log.info(f"[{i}] {name}", "")

    while True:
        try:
            choice = input("\nChoice (number, or 'q' to cancel): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            Log.abort("Selection cancelled.")

        if choice in ("q", "quit", "exit"):
            Log.abort("Selection cancelled by user.")

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(matches):
                selected = matches[idx - 1]
                return selected

        Log.warn("Invalid choice. Please enter a number from the list, or 'q' to cancel.")


def main():
    ap = argparse.ArgumentParser(description="Pull, merge/patch, add gadget, build, align, sign, install.")
    ap.add_argument("pkg_pattern", nargs="?", help="Package name or substring (omit when using --apk)")
    ap.add_argument("--apk", help="Path to a local APK to patch (skips ADB pull/install, no device required)")
    ap.add_argument("--serial", help="adb -s <serial>")
    ap.add_argument("--user", default="0", help="Preferred user id (fallback to others if not found)")
    ap.add_argument("--gadget-version", default=None, help="Frida Gadget version (None = latest)")
    ap.add_argument("--no-user-certs", action="store_true", default=False,
                    help="Do not enable user-installed CA certs via networkSecurityConfig")
    ap.add_argument("--no-gadget", action="store_true", default=False,
                    help="Do not add Frida Gadget")
    ap.add_argument("--extract-only", action="store_true", default=False,
                    help="Only extract, merge and rebuild. Alias for --no-gadget --no-user-certs --no-install")
    ap.add_argument("--disable-styles-hack", action="store_true", default=False,
                    help="Skip duplicate <style><item> removal (merge step)")
    ap.add_argument("--no-install", action="store_true", help="Do not install to device at the end")
    ap.add_argument("--keep-splits", action="store_true", help="Keep split APKs when extracting")
    ap.add_argument("-c", "--gadget-config", help="Path to Frida Gadget configuration JSON file")
    ap.add_argument("-l", "--script-source", help="Path to a custom script to bundle with the gadget")
    ap.add_argument("--no-bridge-autocompile", action="store_true", default=False,
                    help="Do not auto-bundle the script with frida-*-bridge modules via frida-compile")
    ap.add_argument("--save-apk", help="Copy final APK to this path")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    Log.verbose_enabled = args.verbose

    if bool(args.pkg_pattern) == bool(args.apk):
        ap.error("Specify either pkg_pattern or --apk (but not both).")

    if args.gadget_version and args.no_gadget:
        Log.abort("Cannot specify --gadget-version when --no-gadget is set.")

    if args.gadget_config and args.no_gadget:
        Log.abort("Cannot specify --gadget-config when --no-gadget is set.")

    if args.gadget_config:
        args.gadget_config = os.path.abspath(args.gadget_config)
        if not os.path.isfile(args.gadget_config):
            Log.abort(f"Gadget configuration file not found: {args.gadget_config}")

    if args.script_source:
        args.script_source = os.path.abspath(args.script_source)

    if args.script_source and not args.gadget_config:
        Log.warn("A script source was specified (--script-source) but no gadget configuration was set (--gadget-config). A default config will be used which launches the given script.")
        script_dir = os.path.dirname(os.path.realpath(__file__))
        args.gadget_config = os.path.join(script_dir, "gadget_script.json")
        if not os.path.isfile(args.gadget_config):
            Log.abort(f"Default gadget configuration file not found: {args.gadget_config}")

    if args.script_source and not os.path.isfile(args.script_source):
        Log.abort(f"Script source file not found: {args.script_source}")

    if args.script_source and not args.no_bridge_autocompile:
        needed, has_marker = detect_script_bridges(args.script_source)
        if needed and not has_marker:
            bridge_names = ", ".join(_BRIDGE_INFO[k][0] for k in needed)
            Log.warn(
                f"Script references {bridge_names} but does not appear to bundle the "
                f"corresponding frida-*-bridge module. Since Frida gadget 17.0 these "
                f"bridges must be included in the script itself."
            )
            args.script_source = bundle_script_with_bridges(args.script_source, needed)
            Log.info(f"Bundled script: {colored(args.script_source, 'green')}")

    if args.apk:
        if not os.path.isfile(args.apk):
            Log.abort(f"APK file not found: {args.apk}")
        adb = None
        resolved_user = None
        apk_paths = None
        pkg = Path(args.apk).stem + "-patched"
        args.no_install = True
        Log.info(f"Using APK: {colored(args.apk, 'green')}")
    else:
        adb = ADBHelper(serial=args.serial)
        pkg = choose_package(adb, args.pkg_pattern)

        Log.info(f"Using package: {colored(pkg, 'green')}")

        resolved_user, apk_paths = adb.get_apk_paths(pkg, user=args.user)

        if not apk_paths:
            Log.abort(f"No APK paths found for {pkg}")

        if resolved_user != args.user:
            Log.warn(f"Requested user '{args.user}' not found for package; using user '{resolved_user}' instead.")
    
    if not args.extract_only:
        Log.info("Fetching Frida gadgets")
        gadget_version = FridaGadget().obtain_gadgets(args.gadget_version)
        if not args.gadget_version:
            Log.warn(f"No Frida Gadget version specified; using latest available ({gadget_version}).")

        if args.gadget_version and gadget_version != args.gadget_version:
            Log.warn(f"Requested Frida Gadget version '{args.gadget_version}' not found; using '{gadget_version}' instead.")

    Log.verbose(f"Resolved user: {resolved_user}")
    Log.verbose(f"APK paths: {apk_paths}")

    with tempfile.TemporaryDirectory(prefix="patchapk_") as tmp:
        if args.apk:
            dst = os.path.join(tmp, os.path.basename(args.apk))
            shutil.copyfile(args.apk, dst)
            local_apks = [dst]
            Log.info(f"Loaded {len(local_apks)} APK(s)")
        else:
            # Pull split(s) via ADBHelper
            local_apks = adb.pull_files(apk_paths, tmp, pkg)
            Log.info(f"Pulled {len(local_apks)} APK(s)")

        # Keep splits if requested
        if args.keep_splits:
            target = f"{pkg}_splits"
            Path(target).mkdir(parents=True, exist_ok=True)
        
            for p in local_apks:
                shutil.copyfile(p, Path(target) / (os.path.basename(p).replace(pkg + "-", "")))
            Log.info(f"Saved split APKs to: {colored(target, 'green')}")

        for p in local_apks:
            Log.info(f" - {os.path.basename(p)}")

        # Test if apktool is version 3.0.2 or newer
        command_name = "apktool.bat" if os.name == "nt" else "apktool"
        apktool_path = shutil.which(command_name)


        apktool_version = subprocess.run([apktool_path, "-version"], capture_output=True, text=True, input="\n").stdout.strip().split("\n")[0]

        if parse_version(apktool_version) < parse_version("3.0.2"):
            Log.abort(f"apktool version 3.0.2 or newer is required, found {apktool_version}")
            return

        if len(local_apks) == 1:
            Log.info("Single APK detected")
            base = APK(local_apks[0])
        else:
            Log.info(f"Split APK set detected ({len(local_apks)})")
            apks = [APK(p) for p in local_apks]

            # Find base APK (heuristic: filename containing "base", else first)
            base = next((p for p in apks if "base.apk" in p.apk_path), apks[0])
            others = [p for p in apks if p != base]
            base.merge_with(others, disable_styles_hack=args.disable_styles_hack)


        if len(local_apks) == 1:
            # If there's only one APK, and extract-only is requested, just copy it and exit
            if args.extract_only:
                target = args.save_apk if args.save_apk else f"{pkg}.apk"
                Path(os.path.dirname(target) or ".").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(local_apks[0], target)
                Log.info(f"Saved APK: {colored(target, 'green')}")
                return
        
            # Otherwise, disassemble it for patching
            base.disassemble()

        # Apply patches
        if not args.extract_only:
            base.apply_patches(version=gadget_version,
                               enable_user_certs=not args.no_user_certs,
                               frida_gadget=not args.no_gadget,
                               gadget_config=args.gadget_config,
                               script_source=args.script_source)
        # Build final APK
        base.assemble()

        # If extract-only, save and exit
        if args.extract_only:
            target = args.save_apk if args.save_apk else f"{pkg}.apk"
            Path(os.path.dirname(target) or ".").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base.apk_path, target)
            Log.info(f"Saved APK: {colored(target, 'green')}")
            return

        # Prep apk for installation
        base.zipalign(in_place=True)
        final_apk = base.apk_path

        # Sign
        Log.info("Signing with apksigner")
        sign_with_apksigner(final_apk)

        # Save copy if requested
        if args.save_apk or args.no_install:
            target = args.save_apk if args.save_apk else f"{pkg}.apk"
            Path(os.path.dirname(target) or ".").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(final_apk, target)
            Log.info(f"Saved APK: {colored(target, 'green')}")


        # Install via ADBHelper
        if not args.no_install:

            Log.info(f"Uninstalling original (user {resolved_user})")
            adb.uninstall_pkg(pkg, user=resolved_user)
            
            Log.info(f"Installing patched version (user {resolved_user})")
            adb.install_apk(final_apk, user=resolved_user, replace=True)


if __name__ == "__main__":
    try:
        main()
    except ADBError as e:
        Log.abort(f"[ADB ERROR] {e}", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        Log.abort(f"[PROC ERROR] {e}", file=sys.stderr)
    except KeyboardInterrupt:
        sys.exit(130)
