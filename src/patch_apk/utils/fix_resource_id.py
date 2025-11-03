import os
import xml.etree.ElementTree
from patch_apk.utils.cli_tools import verbosePrint, dbgPrint
from patch_apk.config.constants import NULL_DECODED_DRAWABLE_COLOR


def fixPublicResourceIDs(baseapkdir, splitapkpaths):
    # Bail if the base APK does not have a public.xml
    if not os.path.exists(os.path.join(baseapkdir, "res", "values", "public.xml")):
        return
    verbosePrint("[+] Found public.xml in the base APK, fixing resource identifiers across split APKs.")
    
    # Mappings of resource IDs and names
    idToDummyName = {}
    dummyNameToRealName = {}
    
    # Step 1) Find all resource IDs that apktool has assigned a name of APKTOOL_DUMMY_XXX to.
    #         Load these into the lookup tables ready to resolve the real resource names from
    #         the split APKs in step 2 below.
    baseXmlTree = xml.etree.ElementTree.parse(os.path.join(baseapkdir, "res", "values", "public.xml"))
    for el in baseXmlTree.getroot():
        if "name" in el.attrib and "id" in el.attrib:
            if el.attrib["name"].startswith("APKTOOL_DUMMY_") and el.attrib["name"] not in idToDummyName:
                idToDummyName[el.attrib["id"]] = el.attrib["name"]
                dummyNameToRealName[el.attrib["name"]] = None
    verbosePrint("[+] Resolving " + str(len(idToDummyName)) + " resource identifiers.")
    
    # Step 2) Parse the public.xml file from each split APK in search of resource IDs matching
    #         those loaded during step 1. Each match gives the true resource name allowing us to
    #         replace all APKTOOL_DUMMY_XXX resource names with the true resource names back in
    #         the base APK.
    found = 0
    for splitdir in splitapkpaths:
        if os.path.exists(os.path.join(splitdir, "res", "values", "public.xml")):
            tree = xml.etree.ElementTree.parse(os.path.join(splitdir, "res", "values", "public.xml"))
            for el in tree.getroot():
                if "name" in el.attrib and "id" in el.attrib:
                    if el.attrib["id"] in idToDummyName:
                        dummyNameToRealName[idToDummyName[el.attrib["id"]]] = el.attrib["name"]
                        found += 1
    verbosePrint("[+] Located " + str(found) + " true resource names.")
    
    # Step 3) Update the base APK to replace all APKTOOL_DUMMY_XXX resource names with the true
    #         resource name.
    updated = 0
    for el in baseXmlTree.getroot():
        if "name" in el.attrib and "id" in el.attrib:
            if el.attrib["name"] in dummyNameToRealName and dummyNameToRealName[el.attrib["name"]] is not None:
                el.attrib["name"] = dummyNameToRealName[el.attrib["name"]]
                updated += 1
    baseXmlTree.write(os.path.join(baseapkdir, "res", "values", "public.xml"), encoding="utf-8", xml_declaration=True)
    verbosePrint("[+] Updated " + str(updated) + " dummy resource names with true names in the base APK.")
    
    # Step 4) Find all references to APKTOOL_DUMMY_XXX resources within other XML resource files
    #         in the base APK and update them to refer to the true resource name.
    updated = 0
    for (root, dirs, files) in os.walk(os.path.join(baseapkdir, "res")):
        for f in files:
            if f.lower().endswith(".xml"):
                try:
                    # Load the XML
                    xmlPath = os.path.join(root, f)
                    dbgPrint("[~] Parsing " + xmlPath)
                    tree = xml.etree.ElementTree.parse(xmlPath)
                    
                    # Register the namespaces and get the prefix for the "android" namespace
                    namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(baseapkdir, "AndroidManifest.xml"), events=["start-ns"])])
                    for ns in namespaces:
                        xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
                    ns = "{" + namespaces["android"] + "}" # type: ignore
                    
                    # Update references to APKTOOL_DUMMY_XXX resources
                    changed = False
                    for el in tree.iter():
                        # Check for references to APKTOOL_DUMMY_XXX resources in attributes of this element
                        for attr in el.attrib:
                            val = el.attrib[attr]
                            if val.startswith("@") and "/" in val and val.split("/")[1].startswith("APKTOOL_DUMMY_") and dummyNameToRealName[val.split("/")[1]] is not None:
                                el.attrib[attr] = val.split("/")[0] + "/" + dummyNameToRealName[val.split("/")[1]]
                                updated += 1
                                changed = True
                            elif val.startswith("APKTOOL_DUMMY_") and dummyNameToRealName[val] is not None:
                                el.attrib[attr] = dummyNameToRealName[val]
                                updated += 1
                                changed = True
                            
                            if changed:
                                dbgPrint("[~] Patching dummy apktool attribute \"" + attr + "\" value \"" + val + "\"" + (" -> \"" + el.attrib[attr] + "\"" if val != el.attrib[attr] else "") + " (" + str(updated) + ")")
                            
                            # Fix for untracked bug where drawables are decoded without drawable values (@null)
                            if f == "drawables.xml" and attr == "name" and el.text is None:
                                dbgPrint("[~] Patching null decoded drawable \"" + el.attrib[attr] + "\" (" + str(updated) + ")")
                                el.text = NULL_DECODED_DRAWABLE_COLOR
                        
                        # Check for references to APKTOOL_DUMMY_XXX resources in the element text
                        val = el.text
                        if val is not None and val.startswith("@") and "/" in val and val.split("/")[1].startswith("APKTOOL_DUMMY_") and dummyNameToRealName[val.split("/")[1]] is not None:
                            el.text = val.split("/")[0] + "/" + dummyNameToRealName[val.split("/")[1]]
                            updated += 1
                            changed = True
                            dbgPrint("[~] Patching dummy apktool element \"" + el.get('name', el.tag) + "\" value \"" + val + (" -> \"" + el.text + "\"" if val != el.text else "") + str(updated) + ")")
                    
                    # Save the file if it was updated
                    if changed:
                        dbgPrint("[+] Writing patched " + f)
                        tree.write(os.path.join(root, f), encoding="utf-8", xml_declaration=True)
                except xml.etree.ElementTree.ParseError:
                    print("[-] XML parse error in " + os.path.join(root, f) + ", skipping.")
    verbosePrint("[+] Updated " + str(updated) + " references to dummy resource names in the base APK.")