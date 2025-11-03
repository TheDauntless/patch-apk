"""
Main entry point for the patch-apk tool.
"""
import os
import shutil
import subprocess
import tempfile

#   core imports

from patch_apk.core.apk_tool import APKTool

#   utility imports

from patch_apk.utils.cli_tools import getArgs, warningPrint, assertSubprocessSuccessfulRun
from patch_apk.utils.dependencies import checkDependencies 
from patch_apk.utils.frida_objection import fixAPKBeforeObjection, patchingWithObjection
from patch_apk.utils.get_target_apk import getTargetAPK
from patch_apk.utils.get_apk_paths import getAPKPathsForPackage
from patch_apk.utils.verify_package_name import verifyPackageName

def main():
    # Grab argz
    args = getArgs()

    # Check that dependencies are available
    checkDependencies(args.extract_only)

    # Warn for unexpected version
    apktoolVersion = APKTool.getApktoolVersion()
    print(f"Using apktool v{apktoolVersion}")
    
    # Verify the package name and ensure it's installed (also supports partial package names)
    pkgname = verifyPackageName(args.pkgname)
    
    # Get the APK path(s) from the device
    current_user, apkpaths = getAPKPathsForPackage(pkgname)
    
    # Create a temp directory to work from
    with tempfile.TemporaryDirectory() as tmppath:
        # Get the APK to patch. Combine app bundles/split APKs into a single APK.
        apkfile = getTargetAPK(pkgname, apkpaths, tmppath, args.disable_styles_hack, args.extract_only)
        
        # Save the APK if requested
        if args.save_apk is not None or args.extract_only:
            targetName = args.save_apk if args.save_apk is not None else pkgname + ".apk" # type: ignore
            print("[+] Saving a copy of the APK to " + targetName)
            shutil.copy(apkfile, targetName)

            if args.extract_only:
                os.remove(apkfile)
                return

        # Before patching with objection, add INTERNET permission if not already present, and set extractNativeLibs to true
        fixAPKBeforeObjection(apkfile, not args.no_enable_user_certs)
        
        # Patch the APK with objection
        patchingWithObjection(apkfile)
    
        os.remove(apkfile)
        shutil.move(apkfile[:-4] + ".objection.apk", apkfile)
        
        # Uninstall the original package from the device
        print(f"[+] Uninstalling the original package from the device. (user: {current_user})")
        assertSubprocessSuccessfulRun(["adb", "uninstall", "--user", current_user, pkgname])
        
        # Install the patched APK
        print(f"[+] Installing the patched APK to the device. (user: {current_user})")
        assertSubprocessSuccessfulRun(["adb", "install", "--user", current_user, apkfile])

        
        # Done
        print("[+] Done")


if __name__ == '__main__':
    main()