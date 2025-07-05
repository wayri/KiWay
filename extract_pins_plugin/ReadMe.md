# KiCad Pin Extraction Plugin with GUI

This plugin allows you to extract detailed pin and property information from components (footprints) on your KiCad PCB into user-friendly **Markdown** and **CSV** formats. It provides robust filtering, flexible sorting, and customizable output options.

---

## Installation

The current method for installation is a bit manual, it is as follows;

! - Ensure that KiCAD API is enabled (Got to Preferences Menu->Preferences->Plugins->CheckBox)
! - Also ensure the python API is detected automatically, if not provide a path to it (generally the automatic button should suffice)

1. Next got to PCB Editor, Go to Tools->Plugins->Open Plugin Directory
2. Now Copy and paste the Pin Extraction Plugin (extract_pins_plugin folder) into the plugin directory
3. Now go back to KiCAD and go to Tool->Plugins->Refresh Plugins
4. Now Check if the Plugin Has Appeared in the Plugin Menu/Plugin Toolbar (its a blue icon on white background with a IC with pins and an arrow pointing down)
![EPPFAVICON](https://github.com/wayri/KiCAD_Plugins/blob/develop/extract_pins_plugin/epp_favicon.png)
6. If it is visible, you are now ready to use the plugin, See Further below on how to use the plugin


## Features

### 1. Dynamic Selection & Details

- The plugin dialog opens immediately when launched, even if no components are initially selected on the PCB.
- You can **select/deselect components directly in the KiCad PCB editor** while this dialog is open.
- Use the **"Refresh Selection from PCB"** button within the dialog to update the list of components displayed in the dialog's "Selected Components" panel based on your current PCB selection.
- Click on any component's reference designator in the "Selected Components" list to view its detailed properties (Reference, Value, Footprint Name, Description, Layer, Position, Rotation, and custom properties like `connector-type`) in the "Selected Component Details" panel for quick review.
- **Multi-select from PCB**: If this checkbox is enabled, clicking "Refresh Selection from PCB" will *add* newly selected components from the PCB to the existing list in the dialog, rather than replacing the entire list. This allows you to build a cumulative selection.
- **Remove Selected from List**: This button allows you to remove one or more items that you have selected within the dialog's "Selected Components" list. Use standard click, Ctrl+click, or Shift+click to select multiple items in the list before clicking this button.

---

### 2. Flexible Export Options (Buttons)

- **Export Selected**: Exports data for *only* the components currently displayed in the "Selected Components" list (those selected on the PCB and refreshed into the dialog). This button is automatically enabled/disabled based on whether components are in the list.
- **Export 'J's**: Exports data for *all* components on the entire PCB whose Reference Designator starts with the letter 'J' (e.g., J1, J2, JUMP1, J_CONN).
- **Export Connectors (by Type)**: Exports data for *all* components on the entire PCB that have a custom property named `connector-type` whose value matches any of the comma-separated types you define in the "Connector Type Filter" field (e.g., "harness,backplane").

---

### 3. Advanced Filtering Options (Text Inputs with Auto-Suggest)

> These filters apply to the **Export 'J's** and **Export Connectors (by Type)** options. The filter fields provide auto-suggestions populated from data currently present on your board.

#### Footprint Name Filter

- **Purpose**: Filter components based on their full Footprint Name.
- **How it Works**: Enter a partial or full string. Only components whose full footprint name (e.g., `Connector_IDC:IDC-34_2x17_P2.54mm_Horizontal`) contains this text (case-insensitive) will be included. The field provides auto-suggestions of existing footprint names on your board.
- **Auto-Suggest Content**: All unique full footprint names found on your PCB (e.g., `Package_SO:SOIC-8_W3.9mm`, `Resistor_SMD:R_0603_1608Metric`, `Connector_Generic:CONN_01x02`).

**Example**:
- Type `SOIC` to include `Package_SO:SOIC-8_W3.9mm`.
- Type `IDC-34` to include `Connector_IDC:IDC-34_2x17_P2.54mm`.

---

#### Value Filter

- **Purpose**: Filter components based on their 'Value' field.
- **How it Works**: Enter a partial or full string. Only components whose 'Value' field (e.g., `10k`, `0.1uF`, `LED`) contains this text (case-insensitive) will be included. The field provides auto-suggestions of existing values on your board.
- **Auto-Suggest Content**: All unique component values found on your PCB (e.g., `10k`, `0.1uF`, `ATMEGA328P`, `CONN_1x03`).

**Example**:
- Type `100n` to include capacitors with value `100nF`.
- Type `CONN` to include connectors with value `CONN_1x02`.

---

#### Net Name Filter (any pin)

- **Purpose**: Filter components based on their connected net names.
- **How it Works**: Enter a partial or full string. Only components with *any* pin connected to a net whose name contains this text (case-insensitive) will be included. The field provides auto-suggestions of existing net names on your board.
- **Auto-Suggest Content**: All unique net names found on your PCB (e.g., `VCC`, `GND`, `SCL`, `Net-(R1-Pad1)`, `/USB_DP`).

**Example**:
- Type `VCC` to include all components connected to `VCC`, `VCC_3V3`, etc.
- Type `SCL` to include components on your I2C clock line.
- Type `Net-(J1-Pin1)` to filter for components connected to that specific net.

---

#### Connector Type Filter (comma-separated)

- **Purpose**: Filter components based on their custom `connector-type` property. Primarily used by the **Export Connectors (by Type)** button.
- **How it Works**: Enter one or more values, separated by commas (e.g., `harness,backplane`). Only components with a custom property `connector-type` matching any entry (case-insensitive) will be included. The field provides auto-suggestions of existing `connector-type` values on your board.
- **Auto-Suggest Content**: All unique values of `connector-type` found on your PCB (e.g., `harness`, `backplane`, `power_conn`, `board2board`).

**Example**:
- Enter `harness` to include components with `connector-type: harness`.
- Enter `power,board2board` to include both types.

---

### 4. Output Customization Checkboxes

- **Sort Components by Reference (A-Z)**: If checked, the exported tables will list components alphabetically by reference (e.g., C1, J1, U1). If unchecked, order reflects discovery sequence.
- **Highlight Same Nets in Markdown Output**: If checked, net names in the Markdown "Pin Details" tables will be color-coded. Pads connected to the same net will have the same color (requires a Markdown viewer that supports inline HTML styling).
- **Include [Property Name]**: Series of checkboxes letting you choose exactly which general properties (Reference, Value, Footprint Name, etc.) and pin details (Pad Name/Number, Net Name) are included in the output files.

---

### 5. Progress Feedback

- A progress bar and status text indicate the plugin's activity during lengthy export operations.

---

## How to Use

1. **Open your KiCad PCB design** in the PCB Editor.
2. *(Optional)* **Select one or more components** directly on your PCB that you want to export using the "Export Selected" option.
3. Go to **`Tools -> External Plugins -> Extract Component Pins with GUI`** in the KiCad PCB Editor.
4. The plugin dialog will open. You can interact with both KiCad and the dialog simultaneously.
5. **To Update the Dialog's List**: If you select/deselect components on your PCB after the dialog is open, click **"Refresh Selection from PCB"** in the dialog. The list updates to match your current PCB selection.
6. **To View Component Details**: Click any component's reference designator in the "Selected Components" list to view its detailed properties.
7. **Apply Filters**: Enter text into the "Footprint Name Filter", "Value Filter", "Net Name Filter", or "Connector Type Filter" as needed. These fields provide auto-suggestions from your board's data.
8. **Choose Output Options**: Select "Sort Components by Reference", "Highlight Same Nets in Markdown Output", and specific "Include [Property Name]" checkboxes as desired.
9. **Select Export Type**: Click one of the export buttons:
   - **"Export Selected"** to export data for currently visible components in the dialog list.
   - **"Export 'J's"** to export all components on the PCB whose reference starts with 'J'.
   - **"Export Connectors (by Type)"** to export based on the `connector-type` field and filter.
10. **Save Files**: You’ll be prompted to save the generated Markdown (.md) and CSV (.csv) files.
11. **Close Dialog**: Click "Close" when finished.

---

## Output Files

- **Markdown (.md)**: Designed for human readability and sharing.
  - Each component gets its own section (e.g., `## Component: J1`).
  - "General Properties" and "Pin Details" tables are included based on your "Include" selections.
  - Net names will be color-coded if that option was selected.

- **CSV (.csv)**: Designed for structured data analysis.
  - A flattened table where each row represents a single pin.
  - Component details repeat for each pin, with columns chosen by your "Include" selections.
  - Ideal for filtering, sorting, and data processing in spreadsheets.

---
