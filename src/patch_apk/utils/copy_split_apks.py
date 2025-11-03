import os
from patch_apk.utils.cli_tools import dbgPrint
import shutil

def copySplitApkFiles(baseapkdir, splitapkpaths):
    for apkdir in splitapkpaths:
        for (root, dirs, files) in os.walk(apkdir):
            # Skip the original files directory
            if not root.startswith(os.path.join(apkdir, "original")):
                # Create any missing directories
                for d in dirs:
                    # Translate directory path to base APK path and create the directory if it doesn't exist
                    p = baseapkdir + os.path.join(root, d)[len(apkdir):]
                    if not os.path.exists(p):
                        dbgPrint("[+] Creating directory in base APK: " + p[len(baseapkdir):])
                        os.mkdir(p)
                
                # Copy files into the base APK
                for f in files:
                    # Skip the AndroidManifest.xml and apktool.yml in the APK root directory
                    if apkdir == root and (f == "AndroidManifest.xml" or f == "apktool.yml"):
                        continue
                    
                    # Translate path to base APK
                    p = baseapkdir + os.path.join(root, f)[len(apkdir):]
                    
                    # Copy files into the base APK, except for XML files in the res directory
                    if f.lower().endswith(".xml") and p.startswith(os.path.join(baseapkdir, "res")):
                        continue
                    dbgPrint("[+] Moving file to base APK: " + p[len(baseapkdir):])
                    shutil.move(os.path.join(root, f), p)


