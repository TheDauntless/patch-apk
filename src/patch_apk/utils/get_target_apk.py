import os
from patch_apk.utils.cli_tools import verbosePrint, assertSubprocessSuccessfulRun
from progress.bar import Bar
from patch_apk.core.apk_tool import APKTool

def getTargetAPK(pkgname, apkpaths, tmppath, disableStylesHack, extract_only):
    # Pull the APKs from the device

    bar = Bar('[+] Pulling APK file(s) from device', max=len(apkpaths))
    verboseOutput = ""

    localapks = []
    for remotepath in apkpaths:
        baseapkname = remotepath.split('/')[-1]
        localapks.append(os.path.join(tmppath, pkgname + "-" + baseapkname))
        verboseOutput += f"[+] Pulled: {pkgname}-{baseapkname}"
        bar.next()
        # assertSubprocessSuccessfulRun(["adb", "pull", remotepath, localapks[-1]])
        assertSubprocessSuccessfulRun(["adb", "pull", remotepath, localapks[-1]] )
    
    bar.finish()
    verbosePrint(verboseOutput.rstrip())

    # Return the target APK path
    if len(localapks) == 1:
        return localapks[0]
    else:
        # Combine split APKs
        return APKTool.combineSplitAPKs(pkgname, localapks, tmppath, disableStylesHack, extract_only)