# KiWay Extract Pins Plugin

A comprehensive KiCAD plugin for extracting component/pin data and analyzing signal flow. Features both GUI and CLI interfaces.

![Version](https://img.shields.io/badge/Version-2.0.0-blue)
![KiCAD](https://img.shields.io/badge/KiCAD-9.0+-green)
![License](https://img.shields.io/badge/License-GPL--3.0-orange)

## Features

### 📊 Data Extraction
- Extract pin and net information from any component
- Filter by reference pattern (`J*`, `U*`, etc.), value, or connector type
- Export to clean **CSV**, **Markdown**, or **JSON** formats
- Support for custom `connector-type` properties

### 🔀 Signal Flow Analysis
- Generate source-to-destination signal flow tables
- Trace connections between connectors, ICs, and passives
- Find all signal paths between any two components
- Identify intermediate components in signal chains

### 📋 IC Signal Charts
- Create complete pin-to-destination mapping for ICs
- Optionally include or exclude power/ground nets
- Group and sort power nets separately from signals
- Perfect for documentation and debugging

### 📐 Block Diagrams (NEW!)
- Generate SVG block diagrams - fully self-contained, no external dependencies
- Visualize IC signal connections with color-coded net types
- Create signal flow diagrams between component groups

### ⚡ Power Net Classification
- Automatic detection of power/ground nets (VCC, VDD, GND, VSS, etc.)
- Sort and group power nets separately from signal nets
- Customizable power net patterns

### 💻 CLI Support (NEW!)
- Full command-line interface for automation
- Batch processing of multiple boards
- Integration with build systems and CI/CD
- All GUI features available from command line

---

## Installation

### Method 1: Manual Installation
1. Enable the KiCAD API: `Preferences → Preferences → Plugins → Enable`
2. Open PCB Editor → `Tools → Plugins → Open Plugin Directory`
3. Copy the `extract_pins_plugin` folder to the plugin directory
4. `Tools → Plugins → Refresh Plugins`

### Method 2: Plugin Content Manager (Coming Soon)
1. Open KiCAD → `Plugin and Content Manager`
2. Add repository: `https://github.com/wayri/KiWay/releases/latest/download/repository.json`
3. Search for "KiWay" and install

---

## Usage

### GUI Mode
1. Open your PCB in the PCB Editor
2. *(Optional)* Select components on the PCB
3. `Tools → External Plugins → Extract Component Pins with GUI`
4. Use the dialog to filter, configure, and export

### CLI Mode

```bash
# Basic extraction - all J* connectors to CSV
python -m extract_pins_plugin extract --refs "J*" --format csv board.kicad_pcb

# Multiple patterns with net filtering
python -m extract_pins_plugin extract --refs "J*,P*" --net-filter "SPI_*,I2C_*" board.kicad_pcb

# Signal flow between connectors and ICs
python -m extract_pins_plugin signal-flow --source "J*" --dest "U*" --format md board.kicad_pcb

# IC signal chart as SVG diagram
python -m extract_pins_plugin ic-chart --ic "U1" --format svg -o u1_chart.svg board.kicad_pcb

# Generate block diagrams
python -m extract_pins_plugin diagram --refs "U1,U2" -o diagrams.svg board.kicad_pcb

# Extract unique nets, grouped by type
python -m extract_pins_plugin unique-nets --refs "J*" --sort-by-type board.kicad_pcb

# Find signal paths
python -m extract_pins_plugin find-path --start "J1" --end "U1" board.kicad_pcb
```

---

## CLI Commands Reference

### `extract` - Extract component/pin data
```
--refs          Reference patterns (wildcards: *, ?)
--connector-types  Filter by connector-type property
--value-filter  Filter by component value
--net-filter    Filter by net name (comma-separated patterns)
--ignore-unconnected  Skip 'unconnected' pins
--ignore-free   Skip pins with no net
--ignore-power  Skip power/ground nets
--sort-by-net-type  Sort signals before power
--format        csv, md, json (default: csv)
```

### `signal-flow` - Source/destination table
```
--source        Source components (wildcards supported)
--dest          Destination components (wildcards supported)
--intermediates Include intermediate components
--format        csv, md, json, svg
```

### `ic-chart` - IC signal chart
```
--ic            IC reference (wildcards for batch)
--include-power Include power nets
--power-nets    Custom power net patterns
--format        csv, md, json, svg
```

### `diagram` - SVG block diagrams
```
--refs          Component references (wildcards supported)
```

### `unique-nets` - Extract unique net names
```
--sort-by-type  Group signals first, then power, then ground
```

### `find-path` - Find signal paths
```
--start         Starting component
--end           Ending component
--max-hops      Maximum hops (default: 10)
```

### `list` - List board components
```
--refs          Filter by reference pattern
```

---

## Wildcard Patterns

All reference and filter arguments support wildcards:

| Pattern | Matches |
|---------|---------|
| `J*` | J1, J2, J10, JCONN1 |
| `U?` | U1, U2, but not U10 |
| `J*,U*` | All J and U components |
| `SPI_*` | SPI_MOSI, SPI_CLK, etc. |
| `*GND*` | Any net containing GND |

---

## Output Formats

### CSV
Clean, one-row-per-pin format ideal for spreadsheet analysis.

### Markdown
Human-readable tables with optional net highlighting.

### JSON
Structured data for programmatic processing.

### SVG
Self-contained vector diagrams with:
- Color-coded net types (signal/power/ground)
- Component blocks with pin details
- Connection paths with labels
- Legend and summary

---

## License

GPL-3.0 - See [LICENSE](LICENSE) for details.

## Author

**Wayri (Yawar)**
- GitHub: [@wayri](https://github.com/wayri)
