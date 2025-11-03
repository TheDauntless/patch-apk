## Project layout

The primary source package lives under `src/patch_apk/`. The following lists the source tree with files inside the `config`, `core`, and `utils` subfolders.

```
src/
├─ .vscode/
│  └─ PythonImportHelper-v2-Completion.json
├─ patch_apk/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ config/
│  │  ├─ __init__.py
│  │  └─ constants.py
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ apk_builder.py
│  │  └─ apk_tool.py
│  └─ utils/
│     ├─ __init__.py
│     ├─ apk_detect_proguard.py
│     ├─ cli_tools.py
│     ├─ copy_split_apks.py
│     ├─ dependencies.py
│     ├─ disable_apk_split.py
│     ├─ fix_private_resources.py
│     ├─ fix_resource_id.py
│     ├─ frida_objection.py
│     ├─ get_apk_paths.py
│     ├─ get_target_apk.py
│     ├─ raw_re_replace.py
│     ├─ remove_duplicate_style.py
│     ├─ verify_package_name.py
│     └─ data/
│        └─ patch-apk.keystore
└─ patch_apk.egg-info/
	├─ dependency_links.txt
	├─ entry_points.txt
	├─ PKG-INFO
	├─ requires.txt
	├─ SOURCES.txt
	└─ top_level.txt
```

Notes:

- Files inside `src/patch_apk/core/` are implemented in a class-based style (for example `APKTool`, `APKBuilder`, etc.).
- Files inside `src/patch_apk/utils/` are implemented as modules of helper functions (function-based utilities used across the project).

The package version is defined in `src/patch_apk/__init__.py` (`__version__`).
