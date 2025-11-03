from patch_apk.utils.cli_tools import abort, getStdout, verbosePrint
from patch_apk.utils.raw_re_replace import rawREReplace
import os


def hackRemoveDuplicateStyleEntries(baseapkdir):
    # Bail if there is no styles.xml
    if not os.path.exists(os.path.join(baseapkdir, "res", "values", "styles.xml")):
        return