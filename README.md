# patch-apk - App Bundle/Split APK Aware Patcher for Objection

An APK patcher, for use with [objection](https://github.com/sensepost/objection), that supports Android app bundles/split APKs. It automates the following:

1. Finding the full package name of an Android app.
2. Finding the APK path(s) and pulling them from the device.
3. Patching the APK(s) using `objection patchapk`.
	-  Combining split APKs into a single APK where necessary.
4. Enabling support for user-installed CA certificates (e.g. Burp Suite's CA Cert).
5. Uninstalling the original app from the device.
6. Installing the patched app to the device, ready for use with objection.

### Changelog

* **7th September 2026:** 
  * Added `-c` / `--gadget-config` parameter to provide custom Frida Gadget configuration JSON
  * Added `-l` / `--script-source` parameter to bundle and run a custom Frida script with the gadget

* **11th August 2026:** 
  * Added Certificate Transparency bypass for Android 17+
  * Added `--apk` parameter to load a local APK instead of pulling from device
  * Removed objection Frida version warning

* **29th June 2026:** 
  * Updated to work on windows

* **4th April 2026:**
  * Update for compatibility with apktool 3.x which no longer has `--main-classes-only`

* **10th October 2024:**
  * Added mult-user support. If the apk file path can't be found for the default user, it will try other users
  * Remove split-apk tags from <manifest>. Doesn't seem to be documented, but Android verifies these too.
  
* **22nd February 2023:** Took over project and added various features:
  * Merged modifications from @jseigelis's fork
  * Removed support for outdated objection versions
  * Fixed bug for `--debug-output`
  * Added `--verbose` flag
  * Fixed bug with objection AndroidManifest extraction
  * Updated output format
  * Remove dependency on apksigner by using objection's signapk command

* **29th April 2021:** Implemented a fix for an issue with `apktool` where the handling of some resource XML elements changed and the `--use-aapt2` flag is required ([https://github.com/iBotPeaches/Apktool/issues/2462](https://github.com/iBotPeaches/Apktool/issues/2462)).
* **28th April 2021:** Fixed a bug with `objection` version detection when the `objection version` command output an update notice.
* **1st August 2020:** Updated for compatibility with `objection` version 1.9.3 and above and fixed a bug with line endings when retrieving package names from the Android device/emulator.
* **30th March 2020:** Fixed a bug where dummy resource IDs were assumed to all have true names. Added a hack to resolve an issue with duplicate entries in res/values/styles.xml after decompiling with apktool.
* **29th March 2020:** Added `--save-apk` parameter to save a copy of the unpatched single APK for use with other tools.
* **27th March 2020:** Initial release supporting split APKs and the `--no-enable-user-certs` flag.

## Usage
Install the target Android application on your device and connect it to your computer/VM so that `adb devices` can see it.

```
$ patch-apk.py -h
usage: patch-apk.py [-h] [--serial SERIAL] [--user USER] [--gadget-version GADGET_VERSION] [--no-user-certs] [--no-gadget] [--extract-only] [--disable-styles-hack] [--no-install] [--keep-splits] [-c GADGET_CONFIG] [-l SCRIPT_SOURCE] [--save-apk SAVE_APK] [-v] pkg_pattern

Pull, merge/patch, add gadget, build, align, sign, install.

positional arguments:
  pkg_pattern           Package name or substring

options:
  -h, --help            show this help message and exit
  --serial SERIAL       adb -s <serial>
  --user USER           Preferred user id (fallback to others if not found)
  --gadget-version GADGET_VERSION
                        Frida Gadget version (None = latest)
  --no-user-certs       Do not enable user-installed CA certs via networkSecurityConfig
  --no-gadget           Do not add Frida Gadget
  --extract-only        Only extract, merge and rebuild. Alias for --no-gadget --no-user-certs --no-install
  --disable-styles-hack
                        Skip duplicate <style><item> removal (merge step)
  --no-install          Do not install to device at the end
  --keep-splits         Keep split APKs when extracting
  -c, --gadget-config GADGET_CONFIG
                        Path to Frida Gadget configuration JSON file
  -l, --script-source SCRIPT_SOURCE
                        Path to a custom script to bundle with the gadget
  --save-apk SAVE_APK   Copy final APK to this path
  -v, --verbose
```

The package-name parameter can be the fully-qualified package name of the Android app, such as `com.google.android.youtube`, or a partial package name, such as `tube`.

Along with injecting an instrumentation gadget, the script also automatically enables support for user-installed CA certificates by injecting a network security configuration file into the APK. The injected config also disables Certificate Transparency (`<certificateTransparency enabled="false"/>`) in the base config so that intercepted traffic is not rejected by CT enforcement. To disable this functionality, pass the `--no-enable-user-certs` parameter on the command line.

### Examples

Pulling a single APK, patching with objection, and installing back to the device:

```
$ python3 patch-apk.py org.proxydroid
[*] Using package: org.proxydroid
[*] Fetching Frida gadgets
[!] No Frida Gadget version specified; using latest available (17.9.2).
[!] Specify --gadget-version 16.7.19 for compatibility with objection
[*] Pulled 1 APK(s)
[*]  - base.apk
[*] Single APK detected
[*] Disassembling base.apk with apktool
[*] Adding Frida gadget
[*] Enabling user-installed CA certificates via networkSecurityConfig
[*] Signing with apksigner
[*] Uninstalling original (user 0)
[*] Installing patched version (user 0)
```

When `patch-apk.py` is done, the installed app should be patched with objection and have support for user-installed CA certificates enabled. Launch the app on the device and run `objection start` as you normally would to connect to the agent.

**Partial Package Name Matching:** Pass a partial package name to `patch-apk.py` and it'll automatically grab the correct package name or ask you to confirm from available options.

```
$ python3 patch-apk.py proxy

[!] Multiple matching packages installed, select the package to patch.

[1] org.proxydroid
[2] com.android.proxyhandler
Choice: 

...

```

**Patching Split APKs:** Split APKs are automatically detected and combined into a single APK before patching. Split APKs can be identified by multiple APK paths being returned by the `adb shell pm path` command as shown below.

```
$ adb shell pm path org.proxydroid
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/base.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.arm64_v8a.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.en.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.fr.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.nl.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.xxhdpi.apk
```

The following shows `patch-apk.py` detecting, rebuilding, and patching a split APK. Some output has been snipped for brevity. The `-v` flag has been set to show additional info.

```
$ python3 patch-apk.py org.proxydroid

[*] Using package: org.proxydroid
[*] Fetching Frida gadgets
[!] No Frida Gadget version specified; using latest available (17.9.2).
[!] Specify --gadget-version 16.7.19 for compatibility with objection
[*] Pulled 6 APK(s)
[*]  - base.apk
[*]  - split_config.arm64_v8a.apk
[*]  - split_config.en.apk
[*]  - split_config.fr.apk
[*]  - split_config.nl.apk
[*]  - split_config.xxxhdpi.apk
[*] Split APK set detected (6)
[*] Disassembling base.apk with apktool
[*] Disassembling split_config.arm64_v8a.apk with apktool
[*] Disassembling split_config.en.apk with apktool
[*] Disassembling split_config.fr.apk with apktool
[*] Disassembling split_config.nl.apk with apktool
[*] Disassembling split_config.xxxhdpi.apk with apktool
[*] Merging split APKs into base
[*] Adding Frida gadget
[*] Enabling user-installed CA certificates via networkSecurityConfig
[*] Signing with apksigner
[*] Uninstalling original (user 0)
[*] Installing patched version (user 0)

```

After `patch-apk.py` completes, we can run `adb shell pm path` again to verify that there is now a single patched APK installed on the device.

```
$ adb shell pm path org.proxydroid
package:/data/app/org.proxydroid-9NuZnT-lK3qM_IZQEHhTgA==/base.apk
```

By default, patch-apk will inject the frida gadget and modify the network security config. It is also possible to only perform an extraction by providing the `--extract-only` flag. Any split apks will still be merged and a local copy of the APK will be produced:

```
$ python3 patch-apk.py org.proxydroid --extract-only
[*] Using package: org.proxydroid
[*] Pulled 6 APK(s)
[*]  - base.apk
[*]  - split_config.arm64_v8a.apk
[*]  - split_config.en.apk
[*]  - split_config.fr.apk
[*]  - split_config.nl.apk
[*]  - split_config.xxxhdpi.apk
[*] Split APK set detected (6)
[*] Disassembling base.apk with apktool
[*] Disassembling split_config.arm64_v8a.apk with apktool
[*] Disassembling split_config.en.apk with apktool
[*] Disassembling split_config.fr.apk with apktool
[*] Disassembling split_config.nl.apk with apktool
[*] Disassembling split_config.xxxhdpi.apk with apktool
[*] Merging split APKs into base
[*] Saved APK: org.proxydroid.apk
```

**Custom Frida Gadget Configuration (`-c` / `--gadget-config`):**

To provide custom Frida Gadget runtime parameters (e.g. listening address, interaction type, or loading scripts), pass a configuration JSON file using `-c`:

```bash
$ python3 patch-apk.py org.proxydroid -c gadget_config.json
```

Example `gadget_config.json`:
```json
{
  "interaction": {
    "type": "listen",
    "address": "0.0.0.0",
    "port": 27042,
    "on_load": "resume"
  }
}
```

To automatically load and run an embedded Frida script, specify `--script-source` / `-l`:

```bash
$ python3 patch-apk.py org.proxydroid -c gadget_config.json -l hook.js
```

In your `gadget_config.json`, reference the script path as `libfrida-gadget.script.so`:
```json
{
  "interaction": {
    "type": "script",
    "path": "libfrida-gadget.script.so",
    "on_change": "rescan"
  }
}
```

## Original research

* NickstaDB - https://nickbloor.co.uk/2020/03/29/patching-android-split-apks/

