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
                    pass
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=plugin_path.parent)
                zipf.write(file_path, arcname)
    
    return zip_path, zip_filename

def main():
    base_path = Path('.')
    plugin_path = base_path / PLUGIN_DIR
    
    with open(plugin_path / "metadata.json", "r") as f:
        metadata = json.load(f)
    
    version = metadata['versions'][0]['version']
    identifier = metadata['identifier']
    
    zip_path, zip_filename = create_plugin_zip(plugin_path, version, RELEASES_DIR)
    
    file_size = os.path.getsize(zip_path)
    sha256 = calculate_sha256(zip_path)
    
    version_info = metadata['versions'][0]
    version_info.update({
        "download_sha256": sha256,
        "download_size": file_size,
        "download_url": f"{REPO_URL_BASE}/v{version}/{zip_filename}",
        "install_size": 0,
        "platforms": ["windows", "linux", "macos"]
    })
    
    install_size = 0
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for info in zipf.infolist():
            install_size += info.file_size
    version_info['install_size'] = install_size

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
    packages_file = Path(PCM_DIR) / "pkgs.json"
    repo_file = Path(PCM_DIR) / "repo.json"
    
    # --- PACKAGES.JSON (Object Wrapper) ---
    packages_data = {"packages": []}
    
    if packages_file.exists():
        try:
            with open(packages_file, 'r') as f:
                existing = json.load(f)
                if isinstance(existing, dict) and 'packages' in existing:
                    packages_data = existing
                elif isinstance(existing, list):
                    # Migration from root list
                    packages_data['packages'] = existing
        except:
            pass

    packages_list = packages_data['packages']
    updated = False
    for i, pkg in enumerate(packages_list):
        if pkg['identifier'] == identifier:
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
    
    with open(packages_file, 'w') as f:
        json.dump(packages_data, f, indent=4)
        
    print(f"Updated {packages_file}")
    
    # --- REPOSITORY.JSON ---
    packages_timestamp = int(datetime.datetime.now().timestamp())
    
    # URL to the raw packages.json file on GitHub
    # Note: Using main branch as the stable source
    # Added timestamp query to BUST GITHUB RAW CACHE
    packages_url = f"https://raw.githubusercontent.com/wayri/KiWay/main/pcm/pkgs.json?t={packages_timestamp}"
    
    repository = {
        "$schema": "https://go.kicad.org/pcm/schemas/v1",
        "name": "KiWay Plugin Repository",
        "maintainer": {
            "name": "Wayri (Yawar)",
            "contact": {"github": "https://github.com/wayri"}
        },
        "packages": {
            "url": packages_url,
            "update_timestamp": packages_timestamp
        }
    }
    
    with open(repo_file, 'w') as f:
        json.dump(repository, f, indent=4)
        
    print(f"Updated {repo_file}")
    print(f"SHA256: {sha256}")

if __name__ == "__main__":
    main()
