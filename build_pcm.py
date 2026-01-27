import os
import json
import zipfile
import hashlib
import datetime
from pathlib import Path

# Configuration
PLUGIN_DIR = "extract_pins_plugin"
PCM_DIR = "pcm"
RELEASES_DIR = "releases"
# IMPORTANT: This must match the location where you upload the zip
REPO_URL_BASE = "https://github.com/wayri/KiWay/releases/download" 

def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def create_plugin_zip(plugin_path, version, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    zip_filename = f"{plugin_path.name}-{version}.zip"
    zip_path = os.path.join(output_dir, zip_filename)
    
    print(f"Zipping {plugin_path} to {zip_path}...")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(plugin_path):
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', '.vscode']]
            for file in files:
                if file.endswith('.pyc') or file == 'metadata.json': 
                    # Note: metadata.json MUST be at root of zip for KiCad to identify it?
                    # KiCad expects the zip to contain the plugin folder or the content directly.
                    # Usually it's nice to have root folder.
                    # Let's verify KiCad standard. 
                    # Standard: Zip contains the plugin folder ID? Or just contents?
                    # Usually `extract_pins_plugin/metadata.json`.
                    pass
                    
                file_path = os.path.join(root, file)
                # We want the zip to contain the directory "extract_pins_plugin/" at root
                arcname = os.path.relpath(file_path, start=plugin_path.parent)
                zipf.write(file_path, arcname)
    
    return zip_path, zip_filename

def main():
    base_path = Path('.')
    plugin_path = base_path / PLUGIN_DIR
    
    # Read metadata
    with open(plugin_path / "metadata.json", "r") as f:
        metadata = json.load(f)
    
    version = metadata['versions'][0]['version']
    identifier = metadata['identifier']
    
    # Create Zip
    zip_path, zip_filename = create_plugin_zip(plugin_path, version, RELEASES_DIR)
    
    # Get File Stats
    file_size = os.path.getsize(zip_path)
    sha256 = calculate_sha256(zip_path)
    timestamp = int(datetime.datetime.now().timestamp())
    
    # Construct Version Info
    version_info = metadata['versions'][0]
    version_info.update({
        "download_sha256": sha256,
        "download_size": file_size,
        "download_url": f"{REPO_URL_BASE}/v{version}/{zip_filename}",
        "install_size": 0,
        "platforms": ["windows", "linux", "macos"]
    })
    
    # Calculate install size
    install_size = 0
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for info in zipf.infolist():
            install_size += info.file_size
    version_info['install_size'] = install_size

    # Construct Package
    package = {
        "name": metadata['name'],
        "description": metadata['description'],
        "description_full": metadata['description_full'],
        "identifier": metadata['identifier'],
        "type": metadata['type'],
        "author": metadata['author'],
        "license": metadata['license'],
        "resources": metadata['resources'],
        "versions": [version_info]
    }
    
    os.makedirs(PCM_DIR, exist_ok=True)
    packages_file = Path(PCM_DIR) / "packages.json"
    repo_file = Path(PCM_DIR) / "repository.json"
    
    # --- 1. Handle packages.json (The Content) ---
    packages_data = {"packages": []}
    
    if packages_file.exists():
        try:
            with open(packages_file, 'r') as f:
                existing = json.load(f)
                if isinstance(existing.get('packages'), list):
                    packages_data = existing
        except:
            pass

    # Update/Add Package in packages.json
    packages_list = packages_data['packages']
    updated = False
    for i, pkg in enumerate(packages_list):
        if pkg['identifier'] == identifier:
            # Check/Update version
            v_exists = False
            for v_idx, v in enumerate(pkg['versions']):
                if v['version'] == version:
                    pkg['versions'][v_idx] = version_info
                    v_exists = True
                    break
            if not v_exists:
                pkg['versions'].insert(0, version_info)
            
            pkg['description'] = package['description']
            pkg['description_full'] = package['description_full']
            updated = True
            break
            
    if not updated:
        packages_list.append(package)
    
    packages_data['packages'] = packages_list
    
    # Write packages.json
    with open(packages_file, 'w') as f:
        json.dump(packages_data, f, indent=4)
        
    print(f"Updated {packages_file}")
    
    # --- 2. Handle repository.json (The Pointer) ---
    # We must calculate hash of packages.json for validation
    packages_sha256 = calculate_sha256(packages_file)
    packages_timestamp = int(datetime.datetime.now().timestamp())
    
    repository = {
        "$schema": "https://go.kicad.org/pcm/schemas/v1",
        "name": "KiWay Plugin Repository",
        "maintainer": {
            "name": "Wayri (Yawar)",
            "contact": {"github": "https://github.com/wayri"}
        },
        "packages": {
            "url": "packages.json",
            "sha256": packages_sha256,
            "update_timestamp": packages_timestamp
        }
    }
    
    # Write repository.json
    with open(repo_file, 'w') as f:
        json.dump(repository, f, indent=4)
        
    print(f"Updated {repo_file}")
    print(f"Release Zip: {zip_path}")
    print(f"SHA256: {sha256}")

if __name__ == "__main__":
    main()
