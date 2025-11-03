import os
import patch_apk.utils.remove_duplicate_class
import shutil

def remove_duplicate_classes(apkdir):
    """
    Remove duplicate/conflicting smali classes from smali_assets directory.
    This prevents 'has already been interned' errors during APK rebuild.
    """
    smali_assets = os.path.join(apkdir, "smali_assets")
    
    if not os.path.exists(smali_assets):
        print("[+] No smali_assets directory found, skipping duplicate check")
        return
    
    print("[+] Scanning for conflicting smali classes...")
    
    # Get all smali directories except smali_assets
    main_smali_dirs = [os.path.join(apkdir, d) for d in os.listdir(apkdir) 
                       if d.startswith("smali") and d != "smali_assets" 
                       and os.path.isdir(os.path.join(apkdir, d))]
    
    if not main_smali_dirs:
        print("[+] No main smali directories found")
        return
    
    # Build a set of all class paths in main smali directories
    main_classes = set()
    for smali_dir in main_smali_dirs:
        for root, dirs, files in os.walk(smali_dir):
            for file in files:
                if file.endswith(".smali"):
                    # Get relative path from smali_dir root
                    rel_path = os.path.relpath(os.path.join(root, file), smali_dir)
                    main_classes.add(rel_path)
    
    print(f"[+] Found {len(main_classes)} classes in main smali directories")
    
    # Check smali_assets for duplicates
    duplicates_removed = 0
    for root, dirs, files in os.walk(smali_assets):
        for file in files:
            if file.endswith(".smali"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, smali_assets)
                
                # If this class exists in main smali dirs, it's a duplicate
                if rel_path in main_classes:
                    try:
                        os.remove(full_path)
                        duplicates_removed += 1
                        print(f"[+] Removed duplicate: {rel_path}")
                    except Exception as e:
                        print(f"[!] Failed to remove {rel_path}: {e}")
    
    # Clean up empty directories
    for root, dirs, files in os.walk(smali_assets, topdown=False):
        if not os.listdir(root):
            try:
                os.rmdir(root)
            except Exception:
                pass
    
    # If smali_assets is now empty, remove it entirely
    if os.path.exists(smali_assets) and not os.listdir(smali_assets):
        shutil.rmtree(smali_assets)
        print("[+] Removed empty smali_assets directory")
    
    print(f"[+] Removed {duplicates_removed} conflicting smali classes")