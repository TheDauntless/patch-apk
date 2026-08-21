#!/usr/bin/env python3
import os, re, sys, shutil, tempfile, subprocess, xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.parse import urlsplit
from pathlib import Path
from typing import List, Optional
from Log import Log
from ErrorHandler import ErrorHandler
from packaging.version import parse as parse_version

# If you put FridaGadget.py next to this file, this import will work.
from FridaGadget import FridaGadget


class APK:

    GADGET_LOADER_CLASS = "patchapk.FridaGadgetLoader"
    GADGET_LOADER_SOURCE = "FridaGadgetLoader.smali"
    GADGET_LOADER_TARGET = "smali/patchapk/FridaGadgetLoader.smali"
   
    NULL_DECODED_DRAWABLE_COLOR = "#000000ff"

    def __init__(self, apk_path: str, workdir: Optional[str] = None, verbose: bool = False, fix_aggressive: bool = False):
        self.apk_path = os.path.abspath(apk_path)
        self.verbose = verbose
        self._check_exists(self.apk_path)
        self._tmpbase = tempfile.TemporaryDirectory() if workdir is None else None
        self.workdir = workdir or self._tmpbase.name
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        self.has_been_merged = False
        self.error_handler = ErrorHandler(fix_aggressive)

    # ---------- Creation ----------
    @classmethod
    def from_url(cls, url: str, dest: Optional[str] = None) -> "APK":
        """
        Download an .apk from a URL to dest (or temp), then return an APK instance.
        """
        req = Request(url, headers={"User-Agent": "curl/7.79"})
        with urlopen(req) as r:
            data = r.read()

        filename = dest
        if not filename:
            name = os.path.basename(urlsplit(url).path) or "download.apk"
            filename = os.path.join(tempfile.mkdtemp(prefix="apkdl_"), name)

        with open(filename, "wb") as f:
            f.write(data)

        Log.verbose(f" Downloaded APK: {filename} ({len(data)} bytes)")
        return cls(filename)

    # ---------- Public APIs ----------
    def disassemble(self) -> str:
        
        Log.info(f"Disassembling {os.path.basename(self.apk_path)} with apktool")

        """
        apktool d -> returns path to decoded dir.
        """
        self.decoded = os.path.join(self.workdir, "apk_decoded")
        args = ["d", self.apk_path, "-o", self.decoded, "-f"]

        self._apktool(args, ok_required=True)

        Log.verbose(f" Disassembled to: {self.decoded}")
        return self.decoded

    def assemble(self, target : str = None) -> str:
        """
        apktool b -> returns path to rebuilt APK.
        """
        out_apk = os.path.join(self.workdir, "rebuilt.apk") if target is None else target
        self._apktool(["b", self.decoded, "-o", out_apk, "-f"], ok_required=True)

        Log.verbose(f" Rebuilt APK: {out_apk}")

        self.apk_path = out_apk
        return out_apk
    
    def apply_patches(self, version: Optional[str] = None, frida_gadget: bool = True, enable_user_certs: bool = True) -> str:

        apkdir = self.decoded

        manifest = os.path.join(apkdir, "AndroidManifest.xml")
        tree = ET.parse(manifest)
        # setup namespaces
        android_ns = self._manifest_ns(manifest)["android"]

        root = tree.getroot()
        ns = "{" + android_ns + "}"

        # Update <application>
        app_el = root.find(".//application")

        if app_el is None:
            Log.abort("Application does not have <application> tag")

        if frida_gadget:
            Log.info("Adding Frida gadget")
            # Ensure INTERNET
            has_inet = any(el.tag == "uses-permission" and el.attrib.get(ns + "name") == "android.permission.INTERNET"
                        for el in root)
            if not has_inet:
                Log.verbose("[+] Adding android.permission.INTERNET")
                up = ET.Element("uses-permission")
                up.attrib[ns + "name"] = "android.permission.INTERNET"
                root.insert(0, up)
            
            # Add extractNativeLibs = true
            app_el.attrib[ns + "extractNativeLibs"] = "true"

            # Add gadget loader
            existing = app_el.attrib.get(ns + "name")
            if existing and existing != self.GADGET_LOADER_CLASS:
                # Update existing class
                self._add_loader_to_existing_application(existing, apkdir)
            else :
                # Create new class
                app_el.attrib[ns + "name"] = self.GADGET_LOADER_CLASS

                loader_dir = os.path.dirname(os.path.realpath(__file__))
                loader_class = os.path.join(loader_dir, self.GADGET_LOADER_SOURCE)
                loader_target = os.path.join(apkdir, self.GADGET_LOADER_TARGET)
                os.makedirs(os.path.dirname(loader_target), exist_ok=True)
                shutil.copy(loader_class,loader_target )
                
            # Remove testOnly if enabled
            test_only_val = app_el.attrib.get(ns + "testOnly")
            if test_only_val is not None and str(test_only_val).lower() == "true":
                del app_el.attrib[ns + "testOnly"]

            # Write back
            tree.write(manifest, encoding="utf-8", xml_declaration=True)

            fg = FridaGadget()
            fg.copy_android_gadgets(apkdir, version=version)
        else:
            Log.warn("Not adding Frida Gadget.")

        if enable_user_certs:
            
            Log.info("Enabling user-installed CA certificates via networkSecurityConfig")
            app_el.attrib[ns + "networkSecurityConfig"] = "@xml/network_security_config"
            xml_dir = os.path.join(apkdir, "res", "xml")
            Path(xml_dir).mkdir(parents=True, exist_ok=True)
            with open(os.path.join(xml_dir, "network_security_config.xml"), "wb") as fh:
                fh.write(b'<?xml version="1.0" encoding="utf-8"?>'
                         b'<network-security-config>'
                         b'  <base-config>'
                         b'    <certificateTransparency enabled="false"/>'
                         b'    <trust-anchors>'
                         b'      <certificates src="system" />'
                         b'      <certificates src="user" />'
                         b'    </trust-anchors>'
                         b'  </base-config>'
                         b'</network-security-config>')
        else:
            Log.warn("Not adding user-installed CA certificates support.")
        
        if self.has_been_merged:

            if ns + "isSplitRequired" in app_el.attrib:
                del app_el.attrib[ns + "isSplitRequired"]
            app_el.attrib[ns + "extractNativeLibs"] = "true"

            # remove vending split meta-data under application
            to_remove = []
          
            for md in app_el.findall("meta-data"):
                name = md.attrib.get(ns + "name", "")
                if name in ("com.android.vending.splits.required", "com.android.vending.splits"):
                    to_remove.append(md)
            for md in to_remove:
                app_el.remove(md)

            # clean manifest attributes
            for k in (ns + "isSplitRequired", ns + "requiredSplitTypes", ns + "splitTypes"):
                if k in root.attrib:
                    del root.attrib[k]



        # Save manifest
        tree.write(manifest, encoding="utf-8", xml_declaration=True)
        
        return apkdir

    def merge_with(self, others: List["APK"], disable_styles_hack: bool = False) -> str:
        """
        Combine split APKs into a single, rebuild, and return path to the combined APK.
        """
        self.has_been_merged = True
        # Decode all
        decoded_dirs = []
        base = self.disassemble()
        for apk in others:
            decoded_dirs.append(apk.disassemble())

        Log.info("Merging split APKs into base")
        self._copy_splits_into_base(decoded_dirs)
        self._fix_public_resource_ids(decoded_dirs)
        if not disable_styles_hack:
            self._hack_remove_duplicate_style_entries()

        self._disable_apk_splitting()
        # Ampersand fix
        self._raw_re_replace(os.path.join(base, "res", "values", "strings.xml"),
                             r'(&amp)([^;])', r'\1;\2')

        return base

    def zipalign(self, in_place: bool = True) -> str:
        """
        zipalign -f 4. Returns aligned path.
        """
        aligned = self.apk_path if in_place else os.path.join(self.workdir, "aligned.apk")
        tmp = aligned if not in_place else os.path.join(self.workdir, ".__tmp_aligned.apk")
        self._run(["zipalign","-p", "-f", "4", self.apk_path, tmp], ok_required=True)
        if in_place:
            shutil.move(tmp, self.apk_path)
            out = self.apk_path
        else:
            out = tmp
        Log.verbose(f" Zipaligned: {out}")

        return out

    def _apktool(self, args: List[str], ok_required: bool = False):
        exe = "apktool.bat" if os.name == "nt" else "apktool"
        # feed CRLF to bypass possible pause in Windows wrapper
        cp = subprocess.run([exe, *args], input="\r\n", text=True, capture_output=True)
        Log.verbose(f"[apktool] {exe} {' '.join(args)}\n{cp.stdout}")
        if cp.returncode != 0:
            Log.verbose(cp.stderr)

        while ok_required and cp.returncode != 0:
            # Pass error to handler (action picked based on --fix-aggressive flag)
            fixed = self.error_handler.handle(cp.stderr)
            if fixed:
                cp = subprocess.run([exe, *args], input="\r\n", text=True, capture_output=True)
            else:
                Log.abort(f"apktool failed: \n\n{exe}{' '.join(args)}\n\n" + cp.stdout +"\n\n---\n\n"+ cp.stderr)

    def _run(self, args: List[str], ok_required: bool = False):
        Log.verbose(f"[{args[0]}] {' '.join(args)}")

        cp = subprocess.run(args, capture_output=True, text=True)

        if cp.returncode != 0:
            Log.verbose(cp.stderr)
        if ok_required and cp.returncode != 0:
            Log.abort(f"Command failed: {' '.join(args)}")

    def _check_exists(self, p: str):
        if not os.path.exists(p):
            raise FileNotFoundError(p)

    def _manifest_ns(self, manifest_path: str) -> dict:
        ns = {}
        for _, n in ET.iterparse(manifest_path, events=["start-ns"]):
            ns[n[0]] = n[1]
        if "android" not in ns:
            # Fallback to the default android ns when iterparse doesn't expose it
            ns["android"] = "http://schemas.android.com/apk/res/android"
        return ns

    def _copy_splits_into_base(self, splits: List[str]):
        base = self.decoded
        for apkdir in splits:
            for root, dirs, files in os.walk(apkdir):
                if root.startswith(os.path.join(apkdir, "original")):
                    continue
                # Ensure directories at destination
                for d in dirs:
                    dest = base + os.path.join(root, d)[len(apkdir):]
                    Path(dest).mkdir(parents=True, exist_ok=True)
                # Copy files (skip XML in res/, skip root manifest & apktool.yml)
                for f in files:
                    if root == apkdir and f in ("AndroidManifest.xml", "apktool.yml"):
                        continue
                    dest_file = base + os.path.join(root, f)[len(apkdir):]
                    if f.lower().endswith(".xml") and dest_file.startswith(os.path.join(base, "res")):
                        continue
                    Path(os.path.dirname(dest_file)).mkdir(parents=True, exist_ok=True)
                    shutil.move(os.path.join(root, f), dest_file)

    def _fix_public_resource_ids(self, splits: List[str]):
        base = self.decoded
        public_xml = os.path.join(base, "res", "values", "public.xml")
        if not os.path.exists(public_xml):
            return

        id_to_dummy = {}
        dummy_to_real = {}

        base_tree = ET.parse(public_xml)
        for el in base_tree.getroot():
            name = el.attrib.get("name")
            rid = el.attrib.get("id")
            if name and rid and name.startswith("APKTOOL_DUMMY_"):
                id_to_dummy[rid] = name
                dummy_to_real[name] = None

        found = 0
        for split in splits:
            px = os.path.join(split, "res", "values", "public.xml")
            if not os.path.exists(px):
                continue
            t = ET.parse(px)
            for el in t.getroot():
                rid = el.attrib.get("id")
                name = el.attrib.get("name")
                if rid in id_to_dummy:
                    dummy_to_real[id_to_dummy[rid]] = name
                    found += 1
        Log.verbose(f" Resolved {found} resource names from splits")

        updated = 0
        for el in base_tree.getroot():
            name = el.attrib.get("name")
            if name in dummy_to_real and dummy_to_real[name]:
                el.attrib["name"] = dummy_to_real[name]
                updated += 1
        base_tree.write(public_xml, encoding="utf-8", xml_declaration=True)

        # Pass over all res/*.xml to rewrite dummy refs
        changes = 0
        for root, _, files in os.walk(os.path.join(base, "res")):
            for f in files:
                if not f.lower().endswith(".xml"):
                    continue
                path = os.path.join(root, f)
                try:
                    tree = ET.parse(path)
                except ET.ParseError:
                    continue
                changed = False
                for el in tree.iter():
                    # attributes
                    for k in list(el.attrib.keys()):
                        val = el.attrib[k]
                        # @type/APKTOOL_DUMMY_xxx → @type/real_name
                        if isinstance(val, str) and val.startswith("@") and "/" in val:
                            tname = val.split("/", 1)[1]
                            if tname in dummy_to_real and dummy_to_real[tname]:
                                el.attrib[k] = val.split("/", 1)[0] + "/" + dummy_to_real[tname]
                                changed = True
                                changes += 1
                        # bare APKTOOL_DUMMY_xxx → real_name
                        elif isinstance(val, str) and val in dummy_to_real and dummy_to_real[val]:
                            el.attrib[k] = dummy_to_real[val]
                            changed = True
                            changes += 1
                    # null drawable fix (historical quirk)
                    if f == "drawables.xml" and el.get("name") and el.text is None:
                        el.text = self.NULL_DECODED_DRAWABLE_COLOR
                        changed = True
                        changes += 1
                    # element text
                    if el.text and el.text.startswith("@") and "/" in el.text:
                        tname = el.text.split("/", 1)[1]
                        if tname in dummy_to_real and dummy_to_real[tname]:
                            el.text = el.text.split("/", 1)[0] + "/" + dummy_to_real[tname]
                            changed = True
                            changes += 1
                if changed:
                    tree.write(path, encoding="utf-8", xml_declaration=True)
        Log.verbose(f" Updated {changes} dummy resource references")

    def _hack_remove_duplicate_style_entries(self):
        base = self.decoded
        styles = os.path.join(base, "res", "values", "styles.xml")
        if not os.path.exists(styles):
            return
        tree = ET.parse(styles)
        root = tree.getroot()
        dupes = []
        for style in root.findall("style"):
            seen = set()
            for item in list(style):
                nm = item.attrib.get("name")
                if nm in seen:
                    dupes.append((style, item))
                else:
                    seen.add(nm)
        if not dupes:
            return
        for style, item in dupes:
            style.remove(item)
        tree.write(styles, encoding="utf-8", xml_declaration=True)
        Log.verbose(f" Removed {len(dupes)} duplicate <item> entries from styles.xml")

    def _disable_apk_splitting(self):
        base = self.decoded
        manifest = os.path.join(base, "AndroidManifest.xml")
        tree = ET.parse(manifest)
        nsmap = self._manifest_ns(manifest)
        android_ns = nsmap["android"]
        ns = "{" + android_ns + "}"
        root = tree.getroot()

        app = root.find(".//application")
        if app is not None:
            if ns + "isSplitRequired" in app.attrib:
                del app.attrib[ns + "isSplitRequired"]
            app.attrib[ns + "extractNativeLibs"] = "true"

        # remove vending split meta-data under application
        to_remove = []
        if app is not None:
            for md in app.findall("meta-data"):
                name = md.attrib.get(ns + "name", "")
                if name in ("com.android.vending.splits.required", "com.android.vending.splits"):
                    to_remove.append(md)
            for md in to_remove:
                app.remove(md)

        # clean manifest attributes
        for k in (ns + "isSplitRequired", ns + "requiredSplitTypes", ns + "splitTypes"):
            if k in root.attrib:
                del root.attrib[k]

        tree.write(manifest, encoding="utf-8", xml_declaration=True)

    def _raw_re_replace(self, path: str, pattern: str, replacement: str):
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            s = fh.read()
        ns = re.sub(pattern, replacement, s)
        if ns != s:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(ns)


    def _add_loader_to_existing_application(self, class_name: str, apkdir: str, lib_name: str = "frida-gadget") -> None:
        """
        Merge a System.loadLibrary(<lib_name>) call into an existing Application smali class.

        - If no <clinit>()V exists: append a full static constructor that calls System.loadLibrary.
        - If <clinit>()V exists: insert the loadLibrary at the top (after .registers),
        ensuring .registers >= 1.
        - No-op if the class already loads the same library.
        """
        # --- helpers ---
        def _class_to_relpath(c: str) -> str:
            # Accept "com.pkg.App" or "Lcom/pkg/App;"
            if c.startswith("L") and c.endswith(";"):
                core = c[1:-1].replace("/", os.sep)
            else:
                core = c.replace(".", os.sep)
            return core + ".smali"

        def _find_smali_file(root: str, rel: str):
            for entry in os.listdir(root):
                if entry.startswith("smali") and os.path.isdir(os.path.join(root, entry)):
                    cand = os.path.join(root, entry, rel)
                    if os.path.exists(cand):
                        return cand
            return None

        rel = _class_to_relpath(class_name)
        smali_path = _find_smali_file(apkdir, rel)
        if not smali_path:
            raise FileNotFoundError(f"Could not locate smali for {class_name} under {apkdir}/smali*")

        with open(smali_path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()

        # Already loads library? (cheap check)
        load_pat = re.compile(
            r'(?m)^\s*const-string\s+v\d+,\s*"{}"\s*\n\s*invoke-static\s*\{{v\d+\}}\s*,\s*Ljava/lang/System;->loadLibrary\(Ljava/lang/String;\)V\s*$'
            .format(re.escape(lib_name))
        )
        if load_pat.search(src):
            # Already present; nothing to do.
            return

        # Pattern for a full static constructor block
        clinit_pat = re.compile(
            r'(?ms)^\s*\.method\s+static\s+constructor\s+<clinit>\(\)V\s*?'
            r'(.*?)'
            r'\.end\s+method\s*?$'
        )

        # If there is a <clinit>, insert after the .registers line
        m = clinit_pat.search(src)
        if m:
            clinit_block = m.group(0)

            # Find/adjust .registers
            reg_pat = re.compile(r'(?m)^\s*\.registers\s+(\d+)\s*$')
            reg_m = reg_pat.search(clinit_block)
            if reg_m:
                regs = int(reg_m.group(1))
                if regs < 1:
                    # bump to 1
                    clinit_block = reg_pat.sub(".registers 1", clinit_block, count=1)
            else:
                # No .registers? Add one right after method header
                clinit_block = re.sub(
                    r'(?m)^(\s*\.method\s+static\s+constructor\s+<clinit>\(\)V\s*$)',
                    r'\1\n    .registers 1',
                    clinit_block,
                        count=1,
                )

            # Insert the load instructions after the (possibly updated) .registers line.
            insert_after_reg = re.compile(r'(?m)^(\s*\.registers\s+\d+\s*$)')
            load_snippet = (
                f'\n'
                f'    const-string v0, "{lib_name}"\n'
                f'    invoke-static {{v0}}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n'
            )
            new_clinit = insert_after_reg.sub(r"\1" + load_snippet, clinit_block, count=1)

            # Splice back into file
            src = src.replace(clinit_block, new_clinit, 1)

        else:
            # No clinit: append a fresh one before EOF
            new_block = (
                "\n"
                ".method static constructor <clinit>()V\n"
                "    .registers 1\n"
                f"    const-string v0, \"{lib_name}\"\n"
                "    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n"
                "    return-void\n"
                ".end method\n"
            )
            src = src.rstrip() + new_block

        with open(smali_path, "w", encoding="utf-8") as fh:
            fh.write(src)

    def _fix_private_resources(self, base: str):
        # make all @android -> @*android in res/*.xml
        count = 0
        resdir = os.path.join(base, "res")
        if not os.path.isdir(resdir):
            return
        for root, _, files in os.walk(resdir):
            for f in files:
                if not f.lower().endswith(".xml"):
                    continue
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    s = fh.read()
                ns = s.replace("@android", "@*android")
                if ns != s:
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write(ns)
                    count += 1
        Log.verbose(f" Forced {count} private resource refs to public")
