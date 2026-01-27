#!/usr/bin/env python3
# cli.py
"""
Command-Line Interface for KiWay Extract Pins Plugin.
Provides full access to all plugin features from the command line.

@author - Wayri (Yawar)
@version - 2.0.0

Usage:
    python -m extract_pins_plugin <command> [options] <pcb_file>

Wildcard Support:
    All reference and filter arguments support wildcards:
    - * matches any sequence of characters
    - ? matches any single character
    - Multiple patterns can be comma-separated

Examples:
    # Extract pins from all J* connectors
    python -m extract_pins_plugin extract --refs "J*" --format csv board.kicad_pcb

    # Extract from multiple reference patterns
    python -m extract_pins_plugin extract --refs "J*,U*,TP*" board.kicad_pcb

    # Generate signal flow between connectors and ICs
    python -m extract_pins_plugin signal-flow --source "J*" --dest "U*" board.kicad_pcb

    # Generate IC signal chart as SVG diagram
    python -m extract_pins_plugin ic-chart --ic "U1" --format svg board.kicad_pcb

    # Filter by net name patterns
    python -m extract_pins_plugin extract --refs "J*" --net-filter "SPI_*,I2C_*" board.kicad_pcb
"""

import argparse
import sys
import os
from pathlib import Path
from typing import List, Optional


def get_board(pcb_path: str):
    """Load a KiCAD PCB file and return the board object."""
    try:
        import pcbnew
    except ImportError:
        print("Error: pcbnew module not found. Run this from within KiCAD's Python environment.", file=sys.stderr)
        print("       Or add KiCAD's Python path to PYTHONPATH.", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.exists(pcb_path):
        print(f"Error: PCB file not found: {pcb_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        board = pcbnew.LoadBoard(pcb_path)
        return board
    except Exception as e:
        print(f"Error loading PCB file: {e}", file=sys.stderr)
        sys.exit(1)


def write_output(content: str, output_path: Optional[str], format_type: str):
    """Write output to file or stdout."""
    if output_path:
        # Ensure correct extension
        ext_map = {'csv': '.csv', 'md': '.md', 'markdown': '.md', 'json': '.json', 'svg': '.svg'}
        expected_ext = ext_map.get(format_type.lower(), '')
        
        path = Path(output_path)
        if expected_ext and path.suffix.lower() != expected_ext:
            output_path = str(path.with_suffix(expected_ext))
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Output written to: {output_path}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Write to stdout
        print(content)


def expand_refs(extractor, refs_str: str) -> List[str]:
    """
    Expand a comma-separated reference pattern string into actual reference designators.
    Supports wildcards: * (any chars), ? (single char)
    """
    if not refs_str:
        return []
    
    patterns = [p.strip() for p in refs_str.split(',') if p.strip()]
    expanded = []
    
    for pattern in patterns:
        if '*' in pattern or '?' in pattern:
            # It's a wildcard pattern
            fps = extractor.get_footprints_by_reference_pattern(pattern)
            expanded.extend([fp.GetReference() for fp in fps])
        else:
            # Exact reference
            expanded.append(pattern)
    
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for ref in expanded:
        if ref not in seen:
            seen.add(ref)
            result.append(ref)
    
    return result


def get_footprints_from_args(extractor, args) -> list:
    """
    Get footprints based on command arguments with full wildcard support.
    Handles --refs, --connector-types, and applies filters.
    """
    footprints = []
    
    if hasattr(args, 'refs') and args.refs:
        # Reference pattern(s) - supports wildcards and comma-separation
        patterns = [p.strip() for p in args.refs.split(',') if p.strip()]
        for pattern in patterns:
            footprints.extend(extractor.get_footprints_by_reference_pattern(pattern))
    
    if hasattr(args, 'connector_types') and args.connector_types:
        # Connector type(s) - supports wildcards
        types = [t.strip() for t in args.connector_types.split(',') if t.strip()]
        footprints.extend(extractor.get_footprints_by_connector_type(types))
    
    if not footprints and not (hasattr(args, 'refs') and args.refs) and not (hasattr(args, 'connector_types') and args.connector_types):
        # No filters specified, use all footprints
        footprints = extractor.footprints
    
    # Remove duplicates while preserving order
    seen = set()
    unique_footprints = []
    for fp in footprints:
        ref = fp.GetReference()
        if ref not in seen:
            seen.add(ref)
            unique_footprints.append(fp)
    
    return unique_footprints


def cmd_extract(args):
    """Handle the 'extract' command - extract component/pin data."""
    from .core.data_extractor import DataExtractor
    from .core.formatters import get_formatter
    
    board = get_board(args.pcb)
    extractor = DataExtractor(board)
    
    # Get footprints with wildcard support
    footprints = get_footprints_from_args(extractor, args)
    
    # Extract data with filters (all support wildcards)
    data = extractor.extract_footprint_data(
        footprints,
        ignore_unconnected=args.ignore_unconnected,
        ignore_free_pins=args.ignore_free,
        ignore_power_nets=getattr(args, 'ignore_power', False),
        value_filter=args.value_filter,  # Supports wildcards
        net_filter=args.net_filter,  # Supports wildcards, comma-separated
        sort_pins_by_net_type=getattr(args, 'sort_by_net_type', False)
    )
    
    if not data:
        print("No components found matching the criteria.", file=sys.stderr)
        sys.exit(0)
    
    # Format output
    formatter = get_formatter(args.format, highlight_nets=args.highlight)
    
    properties = None
    if args.columns:
        properties = [c.strip() for c in args.columns.split(',')]
    
    output = formatter.format_component_data(
        data,
        include_properties=properties,
        include_pins=not args.no_pins
    )
    
    write_output(output, args.output, args.format)


def cmd_unique_nets(args):
    """Handle the 'unique-nets' command - extract unique net names."""
    from .core.data_extractor import DataExtractor
    from .core.formatters import get_formatter
    
    board = get_board(args.pcb)
    extractor = DataExtractor(board)
    
    # Get footprints with wildcard support
    footprints = get_footprints_from_args(extractor, args)
    
    # Extract unique nets (net_filter supports wildcards)
    nets = extractor.extract_unique_nets(
        footprints,
        ignore_unconnected=args.ignore_unconnected,
        ignore_free_pins=args.ignore_free,
        ignore_power_nets=getattr(args, 'ignore_power', False),
        net_filter=args.net_filter,  # Supports wildcards, comma-separated
        sort_by_type=getattr(args, 'sort_by_type', False)
    )
    
    # Format output
    formatter = get_formatter(args.format)
    output = formatter.format_unique_nets(nets)
    
    write_output(output, args.output, args.format)


def cmd_signal_flow(args):
    """Handle the 'signal-flow' command - generate source/destination table."""
    from .core.data_extractor import DataExtractor
    from .core.signal_flow import SignalFlowAnalyzer
    from .core.formatters import get_formatter
    from .core.diagram_generator import SVGDiagramGenerator
    
    board = get_board(args.pcb)
    extractor = DataExtractor(board)
    analyzer = SignalFlowAnalyzer(extractor)
    
    # Expand source and destination refs (full wildcard support)
    expanded_sources = expand_refs(extractor, args.source)
    expanded_dests = expand_refs(extractor, args.dest)
    
    if not expanded_sources:
        print(f"No components found matching source pattern: {args.source}", file=sys.stderr)
        sys.exit(1)
    
    if not expanded_dests:
        print(f"No components found matching destination pattern: {args.dest}", file=sys.stderr)
        sys.exit(1)
    
    # Generate signal flow table
    data = analyzer.generate_source_destination_table(
        expanded_sources,
        expanded_dests,
        include_intermediates=args.intermediates
    )
    
    if not data:
        print("No signal connections found between specified components.", file=sys.stderr)
        sys.exit(0)
    
    # Handle SVG output
    if args.format == 'svg':
        diagram_gen = SVGDiagramGenerator()
        output = diagram_gen.generate_signal_flow_diagram(
            data,
            title=f"Signal Flow: {args.source} → {args.dest}"
        )
    else:
        formatter = get_formatter(args.format, highlight_nets=args.highlight)
        output = formatter.format_signal_flow(data)
    
    write_output(output, args.output, args.format)


def cmd_ic_chart(args):
    """Handle the 'ic-chart' command - generate IC signal chart."""
    from .core.data_extractor import DataExtractor
    from .core.signal_flow import SignalFlowAnalyzer
    from .core.formatters import get_formatter
    from .core.diagram_generator import SVGDiagramGenerator
    
    board = get_board(args.pcb)
    extractor = DataExtractor(board)
    analyzer = SignalFlowAnalyzer(extractor)
    
    # Expand IC reference (supports wildcards for batch processing)
    ic_refs = expand_refs(extractor, args.ic)
    
    if not ic_refs:
        print(f"No IC found matching pattern: {args.ic}", file=sys.stderr)
        sys.exit(1)
    
    # Parse power net patterns if provided (comma-separated wildcards)
    power_patterns = None
    if args.power_nets:
        power_patterns = [p.strip() for p in args.power_nets.split(',') if p.strip()]
    
    all_outputs = []
    
    for ic_ref in ic_refs:
        # Generate IC signal chart
        data = analyzer.generate_ic_signal_chart(
            ic_ref,
            include_power_nets=args.include_power,
            power_net_patterns=power_patterns
        )
        
        if not data:
            print(f"No data found for IC: {ic_ref}", file=sys.stderr)
            continue
        
        # Get IC value for diagram title
        ic_fp = extractor.get_footprint_by_reference(ic_ref)
        ic_value = ic_fp.GetValue() if ic_fp else ""
        
        # Handle SVG output
        if args.format == 'svg':
            diagram_gen = SVGDiagramGenerator()
            output = diagram_gen.generate_ic_signal_chart(
                ic_ref,
                ic_value,
                data,
                title=f"Signal Chart: {ic_ref}"
            )
        else:
            formatter = get_formatter(args.format, highlight_nets=args.highlight)
            output = formatter.format_signal_flow(data)
        
        all_outputs.append(output)
    
    if not all_outputs:
        print("No IC data generated.", file=sys.stderr)
        sys.exit(0)
    
    # Combine outputs
    if args.format == 'svg':
        # For SVG, write each to separate file if output specified
        if args.output and len(ic_refs) > 1:
            base_path = Path(args.output)
            for i, (ic_ref, output) in enumerate(zip(ic_refs, all_outputs)):
                out_path = base_path.with_stem(f"{base_path.stem}_{ic_ref}")
                write_output(output, str(out_path), args.format)
        else:
            write_output(all_outputs[0], args.output, args.format)
    else:
        combined = "\n\n".join(all_outputs)
        write_output(combined, args.output, args.format)


def cmd_diagram(args):
    """Handle the 'diagram' command - generate block diagram for components."""
    from .core.data_extractor import DataExtractor
    from .core.diagram_generator import SVGDiagramGenerator
    
    board = get_board(args.pcb)
    extractor = DataExtractor(board)
    
    # Expand refs with wildcard support
    refs = expand_refs(extractor, args.refs)
    
    if not refs:
        print(f"No components found matching pattern: {args.refs}", file=sys.stderr)
        sys.exit(1)
    
    diagram_gen = SVGDiagramGenerator()
    all_outputs = []
    
    for ref in refs:
        # Get component data
        fp = extractor.get_footprint_by_reference(ref)
        if not fp:
            continue
        
        # Extract pin data
        data = extractor.extract_footprint_data(
            [fp],
            ignore_unconnected=args.ignore_unconnected,
            ignore_free_pins=args.ignore_free,
            sort_pins_by_net_type=True
        )
        
        if ref not in data:
            continue
        
        comp_data = data[ref]
        pins = comp_data.get('pins', [])
        value = comp_data['general_properties'].get('Value', '')
        
        output = diagram_gen.generate_component_block(ref, value, pins)
        all_outputs.append((ref, output))
    
    if not all_outputs:
        print("No diagram generated.", file=sys.stderr)
        sys.exit(0)
    
    # Write outputs
    if args.output and len(all_outputs) > 1:
        base_path = Path(args.output)
        for ref, output in all_outputs:
            out_path = base_path.with_stem(f"{base_path.stem}_{ref}")
            write_output(output, str(out_path), 'svg')
    elif all_outputs:
        write_output(all_outputs[0][1], args.output, 'svg')


def cmd_find_path(args):
    """Handle the 'find-path' command - find signal paths between components."""
    from .core.data_extractor import DataExtractor
    from .core.signal_flow import SignalFlowAnalyzer
    from .core.formatters import get_formatter
    
    board = get_board(args.pcb)
    extractor = DataExtractor(board)
    analyzer = SignalFlowAnalyzer(extractor)
    
    # Find paths
    paths = analyzer.find_signal_path(
        args.start,
        args.end,
        max_hops=args.max_hops
    )
    
    if not paths:
        print(f"No paths found between {args.start} and {args.end}.", file=sys.stderr)
        sys.exit(0)
    
    # Format output based on format type
    if args.format == 'json':
        import json
        output = json.dumps({"paths": paths, "path_count": len(paths)}, indent=2)
    else:
        lines = [f"# Signal Paths: {args.start} → {args.end}", ""]
        lines.append(f"Found {len(paths)} path(s)")
        lines.append("")
        
        for i, path in enumerate(paths, 1):
            lines.append(f"## Path {i} ({len(path)} hop(s))")
            lines.append("")
            
            if args.format == 'csv':
                lines.append("From,From Pin,Net,To,To Pin")
                for hop in path:
                    lines.append(f"{hop['From Reference']},{hop['From Pin']},{hop['Net Name']},{hop['To Reference']},{hop['To Pin']}")
            else:
                lines.append("| From | Pin | Net | To | Pin |")
                lines.append("|------|-----|-----|-----|-----|")
                for hop in path:
                    lines.append(f"| {hop['From Reference']} | {hop['From Pin']} | {hop['Net Name']} | {hop['To Reference']} | {hop['To Pin']} |")
            
            lines.append("")
        
        output = "\n".join(lines)
    
    write_output(output, args.output, args.format)


def cmd_list(args):
    """Handle the 'list' command - list components on board."""
    from .core.data_extractor import DataExtractor
    
    board = get_board(args.pcb)
    extractor = DataExtractor(board)
    
    # Get footprints with wildcard support
    footprints = get_footprints_from_args(extractor, args)
    
    # Sort by reference
    footprints = sorted(footprints, key=lambda fp: extractor.natural_sort_key(fp.GetReference()))
    
    if args.format == 'json':
        import json
        components = []
        for fp in footprints:
            components.append({
                "reference": fp.GetReference(),
                "value": fp.GetValue(),
                "footprint": str(fp.GetFPID()),
                "connector_type": extractor.get_footprint_property(fp, "connector-type") or ""
            })
        output = json.dumps({"components": components, "count": len(components)}, indent=2)
    elif args.format == 'csv':
        lines = ["Reference,Value,Footprint,Connector Type"]
        for fp in footprints:
            ref = fp.GetReference()
            val = fp.GetValue()
            fpn = str(fp.GetFPID())
            ct = extractor.get_footprint_property(fp, "connector-type") or ""
            # Escape quotes in CSV
            lines.append(f'"{ref}","{val}","{fpn}","{ct}"')
        output = "\n".join(lines)
    else:
        lines = ["# Components on Board", "", f"Total: {len(footprints)}", ""]
        lines.append("| Reference | Value | Footprint | Connector Type |")
        lines.append("|-----------|-------|-----------|----------------|")
        for fp in footprints:
            ref = fp.GetReference()
            val = fp.GetValue()
            fpn = str(fp.GetFPID())
            ct = extractor.get_footprint_property(fp, "connector-type") or ""
            lines.append(f"| {ref} | {val} | {fpn} | {ct} |")
        output = "\n".join(lines)
    
    write_output(output, args.output, args.format)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog='kiway',
        description='KiWay Extract Pins - Extract component data and analyze signal flow from KiCAD PCB files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Wildcard Patterns:
  * matches any characters (e.g., "J*" matches J1, J2, J10, JCONN1)
  ? matches single character (e.g., "J?" matches J1, J2 but not J10)
  Comma-separate multiple patterns (e.g., "J*,U*,TP*")

Examples:
  kiway extract --refs "J*" --format csv board.kicad_pcb
  kiway extract --refs "J*,P*" --net-filter "SPI_*,I2C_*" board.kicad_pcb
  kiway signal-flow --source "J*" --dest "U*" --format md board.kicad_pcb
  kiway ic-chart --ic "U1" --format svg board.kicad_pcb
  kiway diagram --refs "U1,U2,U3" board.kicad_pcb
  kiway unique-nets --refs "J*" --sort-by-type board.kicad_pcb
  kiway list --refs "U*" board.kicad_pcb
        """
    )
    
    parser.add_argument('--version', action='version', version='KiWay 2.0.0')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Common arguments
    def add_common_args(p, include_svg=False):
        p.add_argument('pcb', help='Path to KiCAD PCB file (.kicad_pcb)')
        p.add_argument('-o', '--output', help='Output file path (stdout if not specified)')
        formats = ['csv', 'md', 'markdown', 'json']
        if include_svg:
            formats.append('svg')
        p.add_argument('-f', '--format', choices=formats,
                       default='csv', help='Output format (default: csv)')
    
    def add_filter_args(p):
        p.add_argument('--refs', help='Reference pattern(s), comma-separated with wildcards (e.g., "J*,U*")')
        p.add_argument('--connector-types', help='Connector type(s), comma-separated with wildcards')
        p.add_argument('--value-filter', help='Filter by component value (wildcards supported)')
        p.add_argument('--net-filter', help='Filter by net name (wildcards, comma-separated)')
        p.add_argument('--ignore-unconnected', action='store_true',
                       help='Ignore pins with "unconnected" net name')
        p.add_argument('--ignore-free', action='store_true',
                       help='Ignore pins with no assigned net')
        p.add_argument('--ignore-power', action='store_true',
                       help='Ignore power/ground nets')
    
    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract component and pin data')
    add_common_args(extract_parser)
    add_filter_args(extract_parser)
    extract_parser.add_argument('--columns', help='Columns to include, comma-separated')
    extract_parser.add_argument('--no-pins', action='store_true', help='Exclude pin details')
    extract_parser.add_argument('--highlight', action='store_true',
                                help='Highlight nets in markdown output')
    extract_parser.add_argument('--sort-by-net-type', action='store_true',
                                help='Sort pins with signals first, power/ground last')
    extract_parser.set_defaults(func=cmd_extract)
    
    # Unique nets command
    nets_parser = subparsers.add_parser('unique-nets', help='Extract unique net names')
    add_common_args(nets_parser)
    add_filter_args(nets_parser)
    nets_parser.add_argument('--sort-by-type', action='store_true',
                             help='Group signal nets first, then power, then ground')
    nets_parser.set_defaults(func=cmd_unique_nets)
    
    # Signal flow command
    flow_parser = subparsers.add_parser('signal-flow', help='Generate source/destination signal flow table')
    add_common_args(flow_parser, include_svg=True)
    flow_parser.add_argument('--source', required=True,
                             help='Source component(s), comma-separated (wildcards supported, e.g., "J*")')
    flow_parser.add_argument('--dest', required=True,
                             help='Destination component(s), comma-separated (wildcards supported)')
    flow_parser.add_argument('--intermediates', action='store_true',
                             help='Include intermediate components in output')
    flow_parser.add_argument('--highlight', action='store_true',
                             help='Highlight nets in markdown output')
    flow_parser.set_defaults(func=cmd_signal_flow)
    
    # IC chart command
    ic_parser = subparsers.add_parser('ic-chart', help='Generate IC signal chart')
    add_common_args(ic_parser, include_svg=True)
    ic_parser.add_argument('--ic', required=True, 
                           help='IC reference designator (wildcards supported for batch, e.g., "U*")')
    ic_parser.add_argument('--include-power', action='store_true',
                           help='Include power/ground nets')
    ic_parser.add_argument('--power-nets', 
                           help='Custom power net patterns, comma-separated (e.g., "VCC*,GND*")')
    ic_parser.add_argument('--highlight', action='store_true',
                           help='Highlight nets in markdown output')
    ic_parser.set_defaults(func=cmd_ic_chart)
    
    # Diagram command
    diagram_parser = subparsers.add_parser('diagram', help='Generate SVG block diagram for components')
    diagram_parser.add_argument('pcb', help='Path to KiCAD PCB file')
    diagram_parser.add_argument('-o', '--output', help='Output SVG file path')
    diagram_parser.add_argument('--refs', required=True,
                                help='Component reference(s), comma-separated (wildcards supported)')
    diagram_parser.add_argument('--ignore-unconnected', action='store_true',
                                help='Ignore unconnected pins')
    diagram_parser.add_argument('--ignore-free', action='store_true',
                                help='Ignore free pins')
    diagram_parser.set_defaults(func=cmd_diagram)
    
    # Find path command
    path_parser = subparsers.add_parser('find-path', help='Find signal paths between components')
    add_common_args(path_parser)
    path_parser.add_argument('--start', required=True, help='Starting component reference')
    path_parser.add_argument('--end', required=True, help='Ending component reference')
    path_parser.add_argument('--max-hops', type=int, default=10,
                             help='Maximum number of hops to search (default: 10)')
    path_parser.set_defaults(func=cmd_find_path)
    
    # List command
    list_parser = subparsers.add_parser('list', help='List components on board')
    add_common_args(list_parser)
    list_parser.add_argument('--refs', help='Reference pattern(s) to filter (wildcards supported)')
    list_parser.add_argument('--connector-types', help='Connector type(s) to filter')
    list_parser.set_defaults(func=cmd_list)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == '__main__':
    main()
