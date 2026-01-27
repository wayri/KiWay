# KiWay Plugins for KiCAD

A collection of powerful plugins for KiCAD, designed to automate documentation and analysis.

## List of Plugins

### 1. KiWay Extract Pins (v2.0.0)
A comprehensive documentation and analysis tool.
- **Extract Pins**: Generate CSV/Markdown/JSON pinouts from any component
- **Signal Flow**: Trace connections between components (Source → Destination)
- **IC Analysis**: Generate charts of all pins and their destinations for specific ICs
- **Diagrams**: Create self-contained SVG block diagrams and flow charts
- **Automation**: Full CLI interface for scripting

## Installation

### Method 1: Manual Installation (Recommended)

Due to extraction issues with KiCad PCM on some Windows systems, manual installation is currently the most reliable method.

**Steps:**
1. Download the latest release: [extract_pins_plugin-2.0.0.zip](https://github.com/wayri/KiWay/releases/download/v2.0.0/extract_pins_plugin-2.0.0.zip)

2. Extract the zip file - you'll see a folder named `kiway.extract.pins`

3. **Rename** the folder from `kiway.extract.pins` to `kiway_extract_pins` (replace dots with underscores)

4. Copy the renamed folder to your KiCad plugins directory:
   - **Windows**: `%UserProfile%\Documents\KiCad\9.0\3rdparty\plugins\`
   - **Linux**: `~/.local/share/kicad/9.0/3rdparty/plugins/`
   - **macOS**: `~/Library/Application Support/kicad/9.0/3rdparty/plugins/`

5. Restart KiCad

6. Verify the plugin appears in **Tools → External Plugins → Extract Component Pins with GUI**

### Method 2: Plugin Manager (Experimental)

**Note**: PCM installation has known extraction issues on some Windows systems.

1. Open **KiCAD Plugin and Content Manager**
2. Click **Manage Repositories** → **Add**
3. Add Repository: `https://raw.githubusercontent.com/wayri/KiWay/main/pcm/repo.json`
4. Save and select "KiWay Plugin Repository" from dropdown
5. Install **KiWay Extract Pins**

If the plugin doesn't appear after PCM installation, use Method 1 (Manual Installation) instead.

## Documentation
- [Extract Pins Plugin Documentation](extract_pins_plugin/ReadMe.md)
- [Developer Wiki](https://github.com/wayri/KiCAD_Plugins/wiki/KiCad-Pin-Extraction-Plugin:-Developer-Documentation)
