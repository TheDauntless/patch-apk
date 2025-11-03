from patch_apk.utils.cli_tools import verbosePrint
import os
import xml.etree.ElementTree

def disableApkSplitting(baseapkdir):
    verbosePrint("[+] Disabling APK splitting in AndroidManifest.xml of base APK.")
    
    # Load AndroidManifest.xml
    tree = xml.etree.ElementTree.parse(os.path.join(baseapkdir, "AndroidManifest.xml"))
    
    # Register the namespaces and get the prefix for the "android" namespace
    namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(baseapkdir, "AndroidManifest.xml"), events=["start-ns"])]) # pyright: ignore[reportArgumentType]
    for ns in namespaces:
        xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
    ns = "{" + namespaces["android"] + "}"
    
    # Disable APK splitting
    appEl = None
    elsToRemove = []
    for el in tree.iter():
        if el.tag == "application":
            appEl = el
            if ns + "isSplitRequired" in el.attrib:
                del el.attrib[ns + "isSplitRequired"]
            if ns + "extractNativeLibs" in el.attrib:
                el.attrib[ns + "extractNativeLibs"] = "true"
        elif appEl is not None and el.tag == "meta-data":
            if ns + "name" in el.attrib:
                if el.attrib[ns + "name"] == "com.android.vending.splits.required":
                    elsToRemove.append(el)
                elif el.attrib[ns + "name"] == "com.android.vending.splits":
                    elsToRemove.append(el)
    for el in elsToRemove:
        appEl.remove(el)
    
    # Clean up <manifest> tag
    root = tree.getroot()
    if ns + "isSplitRequired" in root.attrib:
        del root.attrib[ns + "isSplitRequired"]
    if ns + "requiredSplitTypes" in root.attrib:
        del root.attrib[ns + "requiredSplitTypes"]
    if ns + "splitTypes" in root.attrib:
        del root.attrib[ns + "splitTypes"]

    # Save the updated AndroidManifest.xml
    tree.write(os.path.join(baseapkdir, "AndroidManifest.xml"), encoding="utf-8", xml_declaration=True)