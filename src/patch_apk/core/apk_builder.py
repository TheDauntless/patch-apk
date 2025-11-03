"""
APK building module responsible for rebuilding modified APK files.
"""
import os
import shutil

# core imports
from .apk_tool import APKTool

# utility imports

from patch_apk.utils.cli_tools import verbosePrint, abort, assertSubprocessSuccessfulRun
from patch_apk.utils.fix_private_resources import fixPrivateResources


class APKBuilder:
    """Handles APK building and rebuilding operations."""

    @staticmethod
    def build(baseapkdir):
        # Fix private resources preventing builds (apktool wontfix: https://github.com/iBotPeaches/Apktool/issues/2761)
        fixPrivateResources(baseapkdir)

        verbosePrint("[+] Rebuilding APK with apktool.")
        result = APKTool.runApkTool(["b", baseapkdir])
        if result["returncode"] != 0:
            abort("Error: Failed to run 'apktool b " + baseapkdir + "'.\nRun with --debug-output for more information.")

    
    @staticmethod
    def signAndZipAlign(baseapkdir, baseapkfilename):
        # Zip align the new APK
        verbosePrint("[+] Zip aligning new APK.")
        assertSubprocessSuccessfulRun(["zipalign", "-f", "4", "-p", os.path.join(baseapkdir, "dist", baseapkfilename),
            os.path.join(baseapkdir, "dist", baseapkfilename[:-4] + "-aligned.apk")])
        shutil.move(os.path.join(baseapkdir, "dist", baseapkfilename[:-4] + "-aligned.apk"), os.path.join(baseapkdir, "dist", baseapkfilename))

        # Sign the new APK
        verbosePrint("[+] Signing new APK.")
        apkpath = os.path.join(baseapkdir, "dist", baseapkfilename)
        assertSubprocessSuccessfulRun(["objection", "signapk", apkpath])