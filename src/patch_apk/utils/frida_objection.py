import os
import tempfile
import shutil
import xml.etree.ElementTree
import subprocess

# core imports

from patch_apk.core.apk_tool import APKTool

# utility imports

from patch_apk.utils.cli_tools import abort, assertSubprocessSuccessfulRun, warningPrint
from patch_apk.utils.remove_duplicate_class import remove_duplicate_classes

def fixAPKBeforeObjection(apkfile, fix_network_security_config):
    print("[+] Prepping AndroidManifest.xml")
    with tempfile.TemporaryDirectory() as tmppath:
        apkdir = os.path.join(tmppath, "apk")
        ret = APKTool.runApkTool(["d", "--only-main-classes", apkfile, "-o", apkdir,])
        if ret["returncode"] != 0:
            abort("Error: Failed to run 'apktool d " + apkfile + " -o " + apkdir + "'.\nRun with --debug-output for more information.")
        
        # Load AndroidManifest.xml
        manifestPath = os.path.join(apkdir, "AndroidManifest.xml")
        tree = xml.etree.ElementTree.parse(manifestPath)
        
        # Register the namespaces and get the prefix for the "android" namespace
        namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(manifestPath, events=["start-ns"])])
        for ns in namespaces:
            xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
        ns = "{" + namespaces["android"] + "}"
        
        # Ensure INTERNET permission is present
        hasInternetPermission = False
        for el in tree.getroot():
            if el.tag == "uses-permission" and ns + "name" in el.attrib:
                if el.attrib[ns + "name"] == "android.permission.INTERNET":
                    hasInternetPermission = True
                    break
        if not hasInternetPermission:
            print("[+] Adding android.permission.INTERNET to AndroidManifest.xml")
            usesPermissionEl = xml.etree.ElementTree.Element("uses-permission")
            usesPermissionEl.attrib[ns + "name"] = "android.permission.INTERNET"
            tree.getroot().insert(0, usesPermissionEl)
        
        # Set extractNativeLibs to true
        appEl = tree.find(".//application")
        if appEl is not None:
            print("[+] \tSetting extractNativeLibs to true")
            appEl.attrib[ns + "extractNativeLibs"] = "true"


        if fix_network_security_config:
            print("[+] \tEnabling support for user-installed CA certificates.")

            # Add networkSecurityConfig
            for el in tree.findall("application"):
                el.attrib[ns + "networkSecurityConfig"] = "@xml/network_security_config"

            # Create a network security config file
            fh = open(os.path.join(apkdir, "res", "xml", "network_security_config.xml"), "wb")
            fh.write("<?xml version=\"1.0\" encoding=\"utf-8\" ?><network-security-config><base-config><trust-anchors><certificates src=\"system\" /><certificates src=\"user\" /></trust-anchors></base-config></network-security-config>".encode("utf-8"))
            fh.close()
        
        # Save the updated AndroidManifest.xml
        tree.write(manifestPath, encoding="utf-8", xml_declaration=True)
        # Remove problematic duplicate classes
        try:
            remove_duplicate_classes(apkdir)
        except Exception as e:
            print(f"[!] Warning: Failed to remove duplicate classes: {e}")
            pass
        # Rebuild apk file
        result = APKTool.runApkTool(["b", apkdir])
        if result["returncode"] != 0:
            abort("Error: Failed to run 'apktool b " + apkdir + "'.\nRun with --debug-output for more information.")


        # Move rebuilt APK back to original location
        rebuilt_apk = os.path.join(apkdir, "dist", os.path.basename(apkfile))
        if os.path.exists(rebuilt_apk):
            shutil.move(rebuilt_apk, apkfile)
        else:
            abort("Error: Rebuilt APK not found.")
            
            
def patchingWithObjection(apkfile):
        # Patch the target APK with objection
    print("[+] Patching " + apkfile.split(os.sep)[-1] + " with objection.")
    warningPrint("[!] The application will be patched with Frida 16.7.19. See https://github.com/sensepost/objection/issues/737 for more information.")
    if subprocess.run(["objection", "patchapk", "-V", "16.7.19", "--skip-resources", "--ignore-nativelibs", "-s", apkfile], capture_output=True).returncode != 0:
        print("[+] Objection patching failed, trying alternative approach")
        warningPrint("[!] If you get an error, the application might not have a launchable activity")
        
        # Try without --skip-resources, since objection potentially wasn't able to identify the starting activity
        # There could have been another reason for the failure, but it's a sensible fallback
        # Another reason could be a missing INTERNET permission
        assertSubprocessSuccessfulRun(["objection", "patchapk","-V", "16.7.19",  "--ignore-nativelibs", "-s", apkfile])