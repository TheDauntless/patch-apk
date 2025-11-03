import subprocess
import os
import shutil
from patch_apk.utils.cli_tools import abort

def checkDependencies(extract_only):
    deps = ["adb", "apktool", "aapt"]

    if not extract_only:
        deps += ["objection", "zipalign", "apksigner"]

    missing = []
    for dep in deps:
        if shutil.which(dep) is None:
            missing.append(dep)
    if len(missing) > 0:
        abort("Error, missing dependencies, ensure the following commands are available on the PATH: " + (", ".join(missing)))
    
    # Verify that an Android device is connected
    proc = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE)
    if proc.returncode != 0:
        abort("Error: Failed to run 'adb devices'.")
    deviceOut = proc.stdout.decode("utf-8")
    if len(deviceOut.strip().split(os.linesep)) == 1:
        abort("Error, no Android device connected (\"adb devices\"), connect a device first.")
    
    # Check that the included keystore exists
    if not os.path.exists(os.path.realpath(os.path.join(os.path.realpath(__file__), "..", "data", "patch-apk.keystore"))):
        abort("Error, the keystore was not found at " + os.path.realpath(os.path.join(os.path.realpath(__file__), "..", "data", "patch-apk.keystore")) + ", please clone the repository or get the keystore file and place it at this location.")