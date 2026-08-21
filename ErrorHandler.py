import re, os
from typing import List, Match
from Log import Log

class ErrorHandler:
    def __init__(self, fix_aggressive: bool = False):
        self.fix_aggressive = fix_aggressive

    def handle(self, stderr: str) -> bool:
        # Matches "attribue android:example not found" error
        namespace_error = re.compile(r"W:\s+(?P<path>.*?):\d+:\s+error:\s+attribute\s+android:(?P<attr>[^\s]+)\s+not found\.")
        matches = list(namespace_error.finditer(stderr))
        if matches:
            return self._handle_apktool_namespaces(matches)

        # Matches "duplicate attribute" error
        duplicates_error = re.compile(r"W:\s+(?P<path>.*?):\d+:\s+error:\s+duplicate\s+attribute\.")
        matches = list(duplicates_error.finditer(stderr))
        if matches:
            self._handle_apktool_duplicates(matches)
            return True

        # Matches "incompatible with attribute" error
        incompatible_flags_error = re.compile(r"W:\s+(?P<path>.*?):\d+:\s*error:\s*'(?P<value>[^']+)'\s*is incompatible with attribute\s*(?P<attr>\w+).*?\[(?P<allowed>[^\]]+)\]")
        matches = list(incompatible_flags_error.finditer(stderr))
        if matches:
            self._handle_apktool_incompatible_flags(matches)
            return True

        return False

    def _handle_apktool_namespaces(self, matches: List[Match]) -> bool:
        Log.warn("Detected resource namespace mismatch. This issue is likely related to https://github.com/iBotPeaches/Apktool/pull/4137\nTo solve this, you can update Apktool to 3.0.3 or higher, or run patch-apk with --fix-aggressive")

        if not self.fix_aggressive:
            return False

        Log.info("Trying to resolve automatically...")
        count = 0
        for m in matches:
            path, attr = m.group("path"), m.group("attr")
            data = ""
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read()
                if data:
                    data = data.replace(f"android:{attr}", attr)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(data)
                    count += 1

            except Exception as e:
                Log.abort(e)
        Log.info(f"Fixed {count} broken namespaces, restarting build")
        return True

    def _handle_apktool_duplicates(self, matches: List[Match]) -> bool:
        Log.warn("Detected duplicate attribute error, this issue has no known fix on Apktool side and is likely caused by heavy obfuscation\nTo solve this, you can run patch-apk with --fix-aggressive")

        if not self.fix_aggressive:
            return False

        Log.info("Trying to resolve automatically...")
        # Matches duplicates attributes, and groups the first attribute occurence (\1), the duplicate (\2) and anything in between (\3)
        dup_pattern = re.compile(r'(\b([a-zA-Z0-9_:]+)="[^"]*")(.*?)\b\2="[^"]*"')

        count = 0
        for m in matches:
            path = m.group("path")
            data = ""
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read()
                if data and dup_pattern.search(data):
                    while dup_pattern.search(data):
                        # Rewrites contents without the duplicate attribute in \2
                        data = dup_pattern.sub(r"\1\3", data)

                    with open(path, "w", encoding="utf-8") as f:
                        f.write(data)
                    count += 1

            except Exception as e:
                Log.abort(e)
        Log.info(f"Removed {count} duplicates, restarting build")
        return True

    def _handle_apktool_incompatible_flags(self, matches: List[Match]) -> bool:
        Log.warn("Detected incompatible flags error. This issue is likely related to https://github.com/iBotPeaches/Apktool/pull/4140\nTo solve this, you can update Apktool to 3.0.3 or higher, or run patch-apk with --fix-aggressive")

        if not self.fix_aggressive:
            return False

        Log.info("Trying to resolve automatically...")
        count = 0
        for m in matches:
            path, attr, value = m.group("path"), m.group("attr"), m.group("value")
            incomp_pattern = re.compile(rf'\s+(?:[a-zA-Z0-9_]+:)?{attr}="0x0"')
            data = ""
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read()
                if data:
                    data = incomp_pattern.sub("", data)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(data)
                count += 1

            except Exception as e:
                Log.abort(e)
        Log.info(f"Removed {count} incompatible flags, restarting build")
        return True
