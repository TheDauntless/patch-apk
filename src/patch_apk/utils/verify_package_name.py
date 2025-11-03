import subprocess
from patch_apk.utils.cli_tools import abort, warningPrint
import os

def verifyPackageName(pkgname):
    # Get a list of installed packages matching the given name
    packages = []
    proc = subprocess.run(["adb", "shell", "pm", "list", "packages"], stdout=subprocess.PIPE)
    if proc.returncode != 0:
        abort("Error: Failed to run 'adb shell pm list packages'.")
    out = proc.stdout.decode("utf-8")
    for line in out.split(os.linesep):
        if line.startswith("package:"):
            line = line[8:].strip()
            if pkgname.lower() in line.lower():
                packages.append(line)
    
    # Bail out if no matching packages were found
    if len(packages) == 0:
        abort("Error, no packages found on the device matching the search term '" + pkgname + "'.\nRun 'adb shell pm list packages' to verify installed package names.")
    
    # Return the target package name, offering a choice to the user if necessary
    if len(packages) == 1:
        return packages[0]
    else:
        warningPrint("[!] Multiple matching packages installed, select the package to patch.")
        choice = -1
        while choice == -1:
            for i in range(len(packages)):
                print("[" + str(i + 1) + "] " + packages[i])
            choice = input("\nChoice: ")
            if not choice.isnumeric() or int(choice) < 1 or int(choice) > len(packages):
                print("\nInvalid choice.\n")
                choice = -1
        print("")
        return packages[int(choice) - 1]