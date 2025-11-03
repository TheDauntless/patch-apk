import os

####################
# Attempt to detect ProGuard/AndResGuard.
####################
def detectProGuard(extractedPath):
    if os.path.exists(os.path.join(extractedPath, "original", "META-INF", "proguard")):
        return True
    if os.path.exists(os.path.join(extractedPath, "original", "META-INF", "MANIFEST.MF")):
        fh = open(os.path.join(extractedPath, "original", "META-INF", "MANIFEST.MF"))
        d = fh.read()
        fh.close()
        if "proguard" in d.lower():
            return True
    return False