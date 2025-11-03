"""
Command-line interface argument handling.
"""

import argparse
import sys
from termcolor import colored
import subprocess

def getArgs():
    # Only parse args once
    if not hasattr(getArgs, "parsed_args"):
        # Parse the command line
        parser = argparse.ArgumentParser(
            description="patch-apk - Pull and patch Android apps for use with objection/frida. Supports split APKs."
        )
        parser.add_argument("--no-enable-user-certs", help="Prevent patch-apk from enabling user-installed certificate support via network security config in the patched APK.", action="store_true")
        parser.add_argument("--save-apk", help="Save a copy of the APK (or single APK) prior to patching for use with other tools. APK will be saved under the given name.")
        parser.add_argument("--extract-only", help="Disable including objection and pushing modified APK to device.", action="store_true")
        parser.add_argument("--disable-styles-hack", help="Disable the styles hack that removes duplicate entries from res/values/styles.xml.", action="store_true")
        parser.add_argument("--debug-output", help="Enable debug output.", action="store_true")
        parser.add_argument("-v", "--verbose", help="Enable verbose output.", action="store_true")
        parser.add_argument("pkgname", help="The name, or partial name, of the package to patch (e.g. com.foo.bar).")
        
        # Store the parsed args
        getArgs.parsed_args = parser.parse_args()
    
    # Return the parsed command line args
    return getArgs.parsed_args

def abort(msg):
    print(colored(msg, "red"))
    sys.exit(1)


def verbosePrint(msg):
    if getArgs().verbose:
        for line in msg.split("\n"):
            print(colored("    " + line, "light_grey"))


def dbgPrint(msg):
    if getArgs().debug_output:
        print(msg)

####################
# Warning print
####################
def warningPrint(msg):
    print(colored(msg, "yellow"))



def getStdout():
    if getArgs().debug_output:
        return None
    else:
        return subprocess.DEVNULL



def assertSubprocessSuccessfulRun(args):
    if subprocess.run(args, stdout=getStdout(), stderr=getStdout()).returncode != 0:
        abort(f"Error: Failed to run {' '.join(args)}.\nRun with --debug-output for more information.")