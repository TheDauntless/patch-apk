"""
File operation utilities.
"""
from patch_apk.utils.cli_tools import abort, dbgPrint
import os
import re
import xml.etree.ElementTree
from patch_apk.utils.cli_tools import verbosePrint


def rawREReplace(path, pattern, replacement):
    if os.path.exists(path):
        contents = ""
        with open(path, 'r') as file:
            contents = file.read()
        newContents = re.sub(pattern, replacement, contents)
        if (contents != newContents):
            dbgPrint("[~] Patching " + path)
            with open(path, 'w') as file:
                file.write(newContents)
    else:
        abort("\nError: Failed to find file at " + path + " for pattern replacement")