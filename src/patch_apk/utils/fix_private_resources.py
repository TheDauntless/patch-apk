import os
from patch_apk.utils.cli_tools import verbosePrint
from patch_apk.utils.raw_re_replace import rawREReplace


####################
# Fix private resources preventing builds (apktool wontfix: https://github.com/iBotPeaches/Apktool/issues/2761)
####################
def fixPrivateResources(baseapkdir):
    
    verbosePrint("[+] Forcing all private resources to be public")
    updated = 0
    for (root, dirs, files) in os.walk(os.path.join(baseapkdir, "res")):
        for f in files:
            if f.lower().endswith(".xml"):
                rawREReplace(os.path.join(root, f), '@android', '@*android')
                updated += 1
    if updated > 0:
        verbosePrint("[+] Updated " + str(updated) + " private resources before building APK.")