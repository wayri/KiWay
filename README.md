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

### Method 1: Plugin Manager (Recommended)
1. Open **KiCAD Plugin and Content Manager**
2. Add Repository: `https://raw.githubusercontent.com/wayri/KiWay/main/pcm/repo.json`
3. Install **KiWay Extract Pins**

### Method 2: Manual
Copy the `extract_pins_plugin` folder to your KiCAD plugins directory:
- Windows: `Documents\KiCad\9.0\scripting\plugins\`
- Linux: `~/.local/share/kicad/9.0/scripting/plugins/`

## Documentation
- [Extract Pins Plugin Documentation](extract_pins_plugin/ReadMe.md)
- [Developer Wiki](https://github.com/wayri/KiCAD_Plugins/wiki/KiCad-Pin-Extraction-Plugin:-Developer-Documentation)
