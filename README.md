# KiWay Plugins for KiCad

KiWay is a parent repository for KiCad ActionPlugins that can be added to KiCad's Plugin and Content Manager (PCM). Each plugin lives in its own package directory and is indexed through `pcm/repo.json` and `pcm/pkgs.json`.

## List of Plugins

### 1. KiWay Extract Pins (v2.1.0)

A comprehensive interface documentation and test engineering tool.

- **Graph Tracing**: Build a `networkx` graph from pcbnew board data and optional KiCad XML netlists
- **Smart Paths**: Traverse passive in-path components and custom `NetTie_Path` pass-throughs
- **Test Points**: Resolve TP nets back to source IC pins/functions
- **TM/TC Tables**: Parse labels such as `DEMO_CTRL_DEMO_SENSOR_SIGNAL_SPI1_CLK_1_TD`, including `TM`, `TC`, `TA`, `TD`, `CA`, and `CD`
- **Interfaces**: Group buses, differential pairs, connectors, peripherals, and board-to-board signal maps
- **Layout Assist**: Create native KiCad PCB groups for logical interfaces
- **Docs**: Export Markdown, HTML, CSV, JSON, SVG diagrams, and automation-friendly CLI output

### 2. KiWay Bulk Label Editor (v0.1.0)

A preview-and-apply editor for repeated channel labels and component text.

- Wildcard replacement, e.g. `CH*_MAIN` -> `CH*_REDUNDANT`
- Regex replacement for advanced renaming
- Scoped edits for footprint references, values, custom fields, and PCB text

## Roadmap Plugin Ideas

- **KiWay Fanout Generator**: BGA/QFN escape fanout strategies, via grids, differential-pair fanout, length-aware escape patterns, rule-driven layer assignment, and review overlays.
- **KiWay Via Stitching**: Copper-zone aware via stitching, shielding fences, RF keepout support, return-path stitching around high-speed routes, and DRC-friendly via pattern presets.
- **KiWay Connector ICD Builder**: Multi-board connector map extraction, pin compatibility checks, mating connector BOM validation, harness CSV export, and mismatch reports.
- **KiWay Net Hygiene**: Naming convention linting, source/destination inference, duplicate label detection, power-domain checks, and orphan signal reports.
- **KiWay Test Coverage Planner**: TP coverage scoring per interface, fixture probe planning, no-test-access reports, and manufacturing test exports.

## Installation

### Method 1: Plugin Manager

1. Open **KiCad Plugin and Content Manager**
2. Click **Manage Repositories** -> **Add**
3. Add Repository: `https://raw.githubusercontent.com/wayri/KiWay/main/pcm/repo.json`
4. Save and select "KiWay Plugin Repository" from the dropdown
5. Install the desired KiWay plugin package

### Method 2: Manual Installation

1. Download a release zip from the repository releases page.
2. Extract the plugin folder into your KiCad third-party plugins directory:
   - Windows: `%UserProfile%\Documents\KiCad\9.0\3rdparty\plugins\`
   - Linux: `~/.local/share/kicad/9.0/3rdparty/plugins/`
   - macOS: `~/Library/Application Support/kicad/9.0/3rdparty/plugins/`
3. Restart KiCad.

## Building PCM Packages

Run:

```bash
python build_pcm.py
```

The builder discovers every top-level plugin directory containing `metadata.json`, creates a release zip under `releases/`, and updates `pcm/pkgs.json` plus `pcm/repo.json`.

## Documentation

- [Extract Pins Plugin Documentation](extract_pins_plugin/ReadMe.md)
- [Developer Wiki](https://github.com/wayri/KiCAD_Plugins/wiki/KiCad-Pin-Extraction-Plugin:-Developer-Documentation)
