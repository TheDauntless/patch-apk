''' ApkTool related functions '''

import subprocess
import os
from progress.bar import Bar
from packaging.version import parse as parse_version

# util imports 

from patch_apk.utils.raw_re_replace import rawREReplace
from patch_apk.utils.disable_apk_split import disableApkSplitting
from patch_apk.utils.remove_duplicate_style import hackRemoveDuplicateStyleEntries
from patch_apk.utils.fix_resource_id import fixPublicResourceIDs
from patch_apk.utils.cli_tools import abort, verbosePrint, warningPrint
from patch_apk.utils.apk_detect_proguard import detectProGuard
from patch_apk.utils.copy_split_apks import copySplitApkFiles


# core imports

# from .apk_builder import APKBuilder # removed due to circular import


class APKTool:

    '''
    ApkTool class for handling APK files.

    This class provides a way to interface with apktool, a powerful tool for
    decompiling and recompiling Android APK files. It also provides helper
    functions for common operations when working with APK files.

    Attributes:
        None

    Methods:
        runApkTool(params): Run apktool with the given parameters.
        getAPktoolVersion(): Get the installed version of apktool.
        combineSplitAPKs(pkgname, localapks, tmppath, disableStylesHack, extract_only):
            Combine multiple split APKs into a single APK.

    Examples:
        >>> APKTool.runApkTool(["d", "org.proxydroid.apk"])
    '''


    @staticmethod
    def runApkTool(params):
        exe = "apktool.bat" if os.name == "nt" else "apktool"
        # Feed "\r\n" so apktool.bat's `pause` won’t block on Windows.
        cp = subprocess.run(
            [exe, *params],
            input="\r\n",        # Should be harmless on linux
            text=True,
            capture_output=True,
            check=False,
        )
        # Return a simple, uniform dict
        return {
            "returncode": cp.returncode,
            "stdout": cp.stdout,
            "stderr": cp.stderr,
            "ok": (cp.returncode == 0),
        }

    @staticmethod
    def getApktoolVersion():
        commands = [["version"], ["v"], ["-version"], ["-v"]]    
        for cmd in commands:
            try:
                result = APKTool.runApkTool(cmd)

                if result["returncode"] != 0:
                    continue
                version_output = result["stdout"].strip().split("\n")[0].strip()
                version_str = version_output.split("-")[0].strip()
                return parse_version(version_str)
            except Exception as e:
                continue
        raise Exception("Error: Failed to get apktool version.")



    @staticmethod
    def combineSplitAPKs(pkgname, localapks, tmppath, disableStylesHack, extract_only):

        from .apk_builder import APKBuilder
        
        warningPrint("[!] App bundle/split APK detected, rebuilding as a single APK.")
        
        # Extract the individual APKs
        baseapkdir = os.path.join(tmppath, pkgname + "-base")
        baseapkfilename = pkgname + "-base.apk"
        splitapkpaths = []

        bar = Bar('[+] Disassembling split APKs', max=len(localapks))
        verboseOutput = ""
        
        for apkpath in localapks:
            verboseOutput += "\nExtracted: " + apkpath
            bar.next()
            apkdir = apkpath[:-4]
            ret = APKTool.runApkTool(["d", apkpath, "-o", apkdir])
            if ret["returncode"] != 0:
                abort("\nError: Failed to run 'apktool d " + apkpath + " -o " + apkdir + "'.\nRun with --debug-output for more information.")
            
            # Record the destination paths of all but the base APK
            if not apkpath.endswith("base.apk"):
                splitapkpaths.append(apkdir)
            
            # Check for ProGuard/AndResGuard - this might b0rk decompile/recompile
            if detectProGuard(apkdir):
                warningPrint("[!] WARNING: Detected ProGuard/AndResGuard, decompile/recompile may not succeed.\n")
        
        bar.finish()

        verbosePrint(verboseOutput)

        # Walk the extracted APK directories and copy files and directories to the base APK
        print("[+] Rebuilding as a single APK")
        copySplitApkFiles(baseapkdir, splitapkpaths)
        
        # Fix public resource identifiers
        fixPublicResourceIDs(baseapkdir, splitapkpaths)
        
        # Hack: Delete duplicate style resource entries.
        if not disableStylesHack:
            hackRemoveDuplicateStyleEntries(baseapkdir)
        
        #Disable APK splitting in the base AndroidManifest.xml file
        disableApkSplitting(baseapkdir)

        # Fix apktool bug where ampersands are improperly escaped: https://github.com/iBotPeaches/Apktool/issues/2703
        verbosePrint("[+] Fixing any improperly escaped ampersands.")
        rawREReplace(os.path.join(baseapkdir, "res", "values", "strings.xml"), r'(&amp)([^;])', r'\1;\2')
        
        # Rebuild the base APK
        APKBuilder.build(baseapkdir)
        
        # Return the new APK path
        return os.path.join(baseapkdir, "dist", baseapkfilename)
    
