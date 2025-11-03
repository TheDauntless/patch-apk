import subprocess
import os
import re
from patch_apk.utils.cli_tools import abort, verbosePrint, warningPrint

def getAPKPathsForPackage(pkgname, current_user = "0", users_to_try = None):
    print(f"[+] Retrieving APK path(s) for package: {pkgname} for user {current_user}")
    paths = []
    proc = subprocess.run(["adb", "shell", "pm", "path", "--user", current_user, pkgname], stdout=subprocess.PIPE)
    if proc.returncode != 0:
        if not users_to_try:
            proc = subprocess.run(["adb", "shell", "pm", "list", "users"], stdout=subprocess.PIPE)
            out = proc.stdout.decode("utf-8")

            pattern = r'UserInfo{(\d+):'
            users_to_try = re.findall(pattern, out)

        if current_user in users_to_try:
            users_to_try.remove(current_user)

        if len(users_to_try) > 0:
            warningPrint(f"[!] Package not found for user {current_user}, trying next user")
            return getAPKPathsForPackage(pkgname, users_to_try[0], users_to_try)
        else:
            abort("Error: Failed to run 'adb shell pm path " + pkgname + "'.")
    
    out = proc.stdout.decode("utf-8")

    for line in out.split(os.linesep):
        if line.startswith("package:"):
            line = line[8:].strip()
            verbosePrint("[+] APK path: " + line)
            paths.append(line)

    return current_user, paths