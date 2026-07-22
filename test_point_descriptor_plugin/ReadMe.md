# KiWay Test Point Descriptor Extractor

Builds manufacturing, integration, and software-facing test-point documentation
from TP/TestPoint footprints.

It extracts descriptor fields, net names, TM/TC/TA/TD/CA/CD classification,
source/destination board tokens, and resolves each TP net to reachable IC pins.
Series resistors, capacitors, inductors, ferrites, fuses, jumpers, and explicit
`NetTie_Path` parts are reported as intermediate components. Exports include CSV,
Markdown, and HTML.

Pin functions depend on information exposed by the PCB/netlist. Blank functions
must be reviewed against the schematic. Passive traversal is a connectivity
heuristic and does not infer electrical direction, switch state, analog behavior,
or component population options.
