# Changelog

## 0.4.0 — Variant Workbench

- Renamed the user-facing application to **KiCad Design Variant Workbench**.
- Preserved the original Variant → Default operation as a dedicated **Merge / Set Default** tab.
- Added guided Dashboard.
- Added Variant Matrix with staged named-variant edits and visual difference/staged feedback.
- Added Validate/lint tab.
- Added read-only PCB Sync Audit with CSV export and repair guidance.
- Added safer Part Substitution workflow with explicit electrical and pad/mechanical compatibility gates.
- Added Manufacturing Release generation through `kicad-cli` with variant-aware BOM/PDF/Gerber/POS/STEP outputs, ERC/DRC reports, manifest hashes, and optional ZIP.
- Added release-preview SHA-256 snapshots; release generation is refused if project inputs change after preview.
- Added `--lint` and `--pcb-sync` CLI modes.
- Changed the KiCad IPC action to start the Workbench as a detached process after discovering the active project, allowing the Workbench to stay open while KiCad is closed before file writes.
- Kept plugin identifier `kicad_variant_manager` for upgrade compatibility.
- Expanded automated tests to 41 passing cases (27 Workbench + 14 compatibility).

## 0.3.0 — Variant Manager

- Added guided operation UI.
- Added compare, rename, duplicate, delete, cleanup, and Default-swap operations.
- Added KiCad IPC project discovery launcher.

## 0.2.1

- Fixed Windows CRLF preview/apply hash mismatch.

## 0.2.0

- Initial safe Variant → Default promoter with semantic rebase, backups, hierarchy handling, and flat-project support.
