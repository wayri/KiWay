from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import sexpr
from .embed import EmbeddedBlob, decode_file_node, inject_blobs

PORTABLE_DIR = ".portable_assets"
FP_NICK = "PortableAssets"
VAULT_MANIFEST = "PA_MANIFEST.json"


def safe_name(value: str, fallback: str = "asset") -> str:
    s = re.sub(r"[^A-Za-z0-9_.+\-]+", "_", value.strip())
    s = s.strip("._")
    return s[:120] or fallback


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _version_of(root: sexpr.Node) -> str:
    n = root.child("version")
    return n.atoms[1].value if n and len(n.atoms) > 1 else "20231120"


def _value(node: Optional[sexpr.Node], index: int = 1, default: str = "") -> str:
    if node and len(node.atoms) > index:
        return node.atoms[index].value
    return default


def _prop(node: sexpr.Node, name: str) -> str:
    p = sexpr.direct_property(node, name)
    return _value(p, 2)


def _reference_from_fp(fp: sexpr.Node) -> str:
    ref = _prop(fp, "Reference")
    if ref:
        return ref
    for c in fp.children_named("fp_text"):
        if len(c.atoms) >= 3 and c.atoms[1].value == "reference":
            return c.atoms[2].value
    return ""


def _lib_link(fp: sexpr.Node) -> str:
    return fp.atoms[1].value if len(fp.atoms) >= 2 else ""


def _model_path(model: sexpr.Node) -> str:
    return model.atoms[1].value if len(model.atoms) >= 2 else ""


@dataclass
class AssetStatus:
    reference: str
    kind: str
    source: str
    status: str
    destination: str = ""
    detail: str = ""


@dataclass
class ScanReport:
    project_dir: str
    board: str
    schematics: list[str]
    footprints: int = 0
    schematic_symbols: int = 0
    model_refs: int = 0
    unresolved_models: int = 0
    missing_footprint_links: int = 0
    locks: list[str] = field(default_factory=list)
    assets: list[AssetStatus] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PortableOptions:
    embed_3d: bool = True
    snapshot_symbols: bool = True
    mirror_vault: bool = True
    per_reference_footprints: bool = True
    allow_network: bool = False
    model_search_roots: list[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    backup_dir: str
    files_written: list[str]
    footprints_localized: int
    symbols_localized: int
    models_embedded: int
    unresolved_models: list[str]
    warnings: list[str]


class ProjectContext:
    def __init__(self, project_dir: Path, board: Optional[Path] = None):
        self.project_dir = project_dir.resolve()
        pros = sorted(self.project_dir.glob("*.kicad_pro"))
        self.project_file = pros[0] if pros else None
        stem = self.project_file.stem if self.project_file else ""
        if board:
            self.board = board.resolve()
        else:
            candidate = self.project_dir / f"{stem}.kicad_pcb" if stem else None
            if candidate and candidate.exists():
                self.board = candidate
            else:
                pcbs = sorted(self.project_dir.glob("*.kicad_pcb"))
                if not pcbs:
                    raise FileNotFoundError("No .kicad_pcb file found in the project directory")
                self.board = pcbs[0]
        main_candidate = self.project_dir / f"{stem}.kicad_sch" if stem else None
        self.main_schematic = main_candidate if main_candidate and main_candidate.exists() else None
        self.schematics = self._find_schematics()
        if self.main_schematic is None and self.schematics:
            self.main_schematic = self.schematics[0]
        self.fp_table = self.project_dir / "fp-lib-table"
        self.sym_table = self.project_dir / "sym-lib-table"
        self.asset_root = self.project_dir / PORTABLE_DIR
        self.fp_dir = self.asset_root / "Portable.pretty"
        self.sym_dir = self.asset_root / "symbols"

    @classmethod
    def discover(cls, value: str | Path, board_hint: str | Path | None = None) -> "ProjectContext":
        p = Path(value).expanduser()
        if p.is_file():
            if p.suffix == ".kicad_pcb":
                return cls(p.parent, p)
            return cls(p.parent, Path(board_hint) if board_hint else None)
        return cls(p, Path(board_hint) if board_hint else None)

    def _find_schematics(self) -> list[Path]:
        result: list[Path] = []
        for p in self.project_dir.rglob("*.kicad_sch"):
            rel = p.relative_to(self.project_dir)
            parts = {x.lower() for x in rel.parts}
            if PORTABLE_DIR.lower() in parts or "backups" in parts or any(x.endswith("-backups") for x in parts):
                continue
            result.append(p)
        result.sort(key=lambda x: (0 if self.main_schematic and x == self.main_schematic else 1, len(x.parts), str(x)))
        return result

    def lock_files(self) -> list[Path]:
        found: set[Path] = set()
        patterns = ["*.lck", ".*.lck", "~*.lck", "*.lock"]
        for pattern in patterns:
            found.update(self.project_dir.glob(pattern))
        return sorted(p for p in found if p.is_file())


def project_signature(ctx: ProjectContext) -> str:
    """Hash every design input used by a portability transaction."""
    paths = [ctx.board, *ctx.schematics]
    paths.extend(
        path for path in (ctx.project_file, ctx.fp_table, ctx.sym_table)
        if path is not None and path.exists()
    )
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda item: str(item).casefold()):
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class LibraryTables:
    def __init__(self, ctx: ProjectContext):
        self.ctx = ctx
        self.fp_libs: dict[str, str] = {}
        self._load_fp_tables()

    def _load_table(self, path: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        if not path.exists():
            return out
        try:
            doc = sexpr.parse(_read(path))
            root = doc.children[0] if doc.children else None
            if not root:
                return out
            for lib in root.children_named("lib"):
                name = _value(lib.child("name"))
                uri = _value(lib.child("uri"))
                if name and uri:
                    out[name] = uri
        except Exception:
            pass
        return out

    def _global_candidates(self, filename: str) -> list[Path]:
        home = Path.home()
        candidates = [
            home / ".config" / "kicad" / "10.0" / filename,
            home / ".config" / "kicad" / "9.0" / filename,
            home / "AppData" / "Roaming" / "kicad" / "10.0" / filename,
            home / "AppData" / "Roaming" / "kicad" / "9.0" / filename,
            home / "Library" / "Preferences" / "kicad" / "10.0" / filename,
            home / "Library" / "Preferences" / "kicad" / "9.0" / filename,
        ]
        return [p for p in candidates if p.exists()]

    def _load_fp_tables(self) -> None:
        for p in self._global_candidates("fp-lib-table"):
            self.fp_libs.update(self._load_table(p))
        self.fp_libs.update(self._load_table(self.ctx.fp_table))

    def expand(self, raw: str) -> str:
        variables = dict(os.environ)
        variables["KIPRJMOD"] = str(self.ctx.project_dir)
        # KiCad's standard 3D variable is not always inherited by an external IPC process.
        if "KICAD10_3DMODEL_DIR" not in variables:
            guesses = []
            if os.name == "nt":
                pf = os.environ.get("ProgramFiles", r"C:\Program Files")
                guesses.append(Path(pf) / "KiCad" / "10.0" / "share" / "kicad" / "3dmodels")
            else:
                guesses += [Path("/usr/share/kicad/3dmodels"), Path("/usr/local/share/kicad/3dmodels")]
            for g in guesses:
                if g.exists():
                    variables["KICAD10_3DMODEL_DIR"] = str(g)
                    break
        def repl(m: re.Match[str]) -> str:
            return variables.get(m.group(1), m.group(0))
        return re.sub(r"\$\{([^}]+)\}", repl, raw)

    def footprint_source(self, lib_link: str) -> Optional[Path]:
        if ":" not in lib_link:
            return None
        nick, entry = lib_link.split(":", 1)
        uri = self.fp_libs.get(nick)
        if uri and not uri.lower().startswith(("http://", "https://")):
            d = Path(self.expand(uri)).expanduser()
            p = d / f"{entry}.kicad_mod"
            if p.exists():
                return p
        # Useful for ad-hoc project-local libraries not in fp-lib-table anymore.
        target = f"{entry}.kicad_mod"
        for p in self.ctx.project_dir.rglob(target):
            if PORTABLE_DIR not in p.parts:
                return p
        return None

    def link_exists(self, lib_link: str) -> Optional[bool]:
        if not lib_link:
            return True
        if lib_link.startswith("kicad-embed://"):
            return True
        if ":" not in lib_link:
            return False
        nick, entry = lib_link.split(":", 1)
        uri = self.fp_libs.get(nick)
        if not uri:
            return False
        if uri.lower().startswith(("http://", "https://")):
            return None
        return (Path(self.expand(uri)) / f"{entry}.kicad_mod").exists()


class ModelResolver:
    def __init__(self, ctx: ProjectContext, tables: LibraryTables, options: PortableOptions):
        self.ctx, self.tables, self.options = ctx, tables, options
        self.cache: dict[str, tuple[Optional[bytes], str, str]] = {}

    def resolve(self, raw: str, source_fp: Optional[Path] = None) -> tuple[Optional[bytes], str, str]:
        if raw in self.cache:
            return self.cache[raw]
        if raw.startswith("kicad-embed://"):
            result = (None, "already embedded", raw)
            self.cache[raw] = result
            return result
        if raw.lower().startswith(("http://", "https://")):
            if not self.options.allow_network:
                result = (None, "remote disabled", raw)
            else:
                try:
                    with urllib.request.urlopen(raw, timeout=15) as r:
                        result = (r.read(), "downloaded", raw)
                except Exception as exc:
                    result = (None, "unresolved", f"{raw}: {exc}")
            self.cache[raw] = result
            return result

        expanded = self.tables.expand(raw)
        candidates: list[Path] = []
        ep = Path(expanded).expanduser()
        if ep.is_absolute():
            candidates.append(ep)
        else:
            candidates.append(self.ctx.project_dir / ep)
            if source_fp:
                candidates.append(source_fp.parent / ep)
            for root in self.options.model_search_roots:
                candidates.append(Path(root).expanduser() / ep)
        for p in candidates:
            if p.exists() and p.is_file():
                try:
                    result = (p.read_bytes(), "resolved", str(p))
                    self.cache[raw] = result
                    return result
                except OSError:
                    pass
        result = (None, "unresolved", raw)
        self.cache[raw] = result
        return result


class Transaction:
    def __init__(self, ctx: ProjectContext):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup_dir = ctx.asset_root / "backups" / stamp
        self.ctx = ctx

    def commit(self, writes: dict[Path, bytes]) -> list[Path]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        existing: dict[Path, Optional[Path]] = {}
        for target in writes:
            if target.exists():
                try:
                    rel = target.resolve().relative_to(self.ctx.project_dir)
                except ValueError:
                    rel = Path("external") / target.name
                backup = self.backup_dir / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                existing[target] = backup
            else:
                existing[target] = None
        self._create_kicad_backup(existing)
        written: list[Path] = []
        try:
            for target, data in writes.items():
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, target)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                written.append(target)
        except Exception:
            for target in reversed(written):
                backup = existing[target]
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    shutil.copy2(backup, target)
            raise
        return written

    def _create_kicad_backup(self, existing: dict[Path, Optional[Path]]) -> Path:
        """Create a conventional project-name-backups zip before replacement."""
        stem = self.ctx.project_file.stem if self.ctx.project_file else self.ctx.board.stem
        backup_root = self.ctx.project_dir / f"{stem}-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        archive = backup_root / f"{stem}-{stamp}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
            for target, backup in existing.items():
                if backup is None or not backup.exists():
                    continue
                try:
                    name = target.resolve().relative_to(self.ctx.project_dir)
                except ValueError:
                    name = Path(target.name)
                package.write(backup, str(name).replace("\\", "/"))
        return archive


def _table_upsert(text: str, root_head: str, nick: str, uri: str, descr: str) -> str:
    entry = f'\t(lib (name {sexpr.quote(nick)})(type "KiCad")(uri {sexpr.quote(uri)})(options "")(descr {sexpr.quote(descr)}))\n'
    if not text.strip():
        return f"({root_head}\n{entry})\n"
    doc = sexpr.parse(text)
    root = sexpr.root_named(doc, root_head)
    if not root:
        raise ValueError(f"Unexpected library table format; missing ({root_head} ...)")
    for lib in root.children_named("lib"):
        if _value(lib.child("name")) == nick:
            return text[:lib.start] + entry.strip() + text[lib.end:]
    return text[:root.end - 1] + "\n" + entry + text[root.end - 1:]


def _portable_fp_name(ref: str, lib_link: str, per_reference: bool) -> str:
    entry = lib_link.split(":", 1)[-1] if lib_link else "Recovered"
    entry = safe_name(entry, "Recovered")
    if per_reference:
        return f"{safe_name(ref, 'REF')}__{entry}"
    return entry


def _embed_name(raw_path: str, data: bytes, used: dict[str, str]) -> str:
    # Content suffix makes collisions with already-embedded files and equal basenames
    # deterministic without needing to decode an existing blob first.
    original = Path(safe_name(Path(raw_path).name, "model.step"))
    digest = hashlib.sha256(data).hexdigest()
    base = f"{original.stem}__{digest[:8]}{original.suffix}"
    if base in used and used[base] != digest:
        base = f"{original.stem}__{digest[:16]}{original.suffix}"
    used[base] = digest
    return base


def _transform_footprint(
    raw: str,
    new_link: str,
    library_name: str,
    resolver: ModelResolver,
    source_fp: Optional[Path],
    embed_models: bool,
) -> tuple[str, str, list[AssetStatus], list[EmbeddedBlob]]:
    """Return (board instance block, library footprint block, statuses, newly embedded blobs)."""
    doc = sexpr.parse(raw)
    fp = doc.children[0]
    ref = _reference_from_fp(fp)
    used_names: dict[str, str] = {}
    model_reps: list[tuple[int, int, str]] = []
    blobs: list[EmbeddedBlob] = []
    statuses: list[AssetStatus] = []

    for model in fp.children_named("model"):
        path = _model_path(model)
        if not path:
            continue
        if path.startswith("kicad-embed://"):
            statuses.append(AssetStatus(ref, "3D model", path, "embedded", path))
            continue
        data, status, detail = resolver.resolve(path, source_fp)
        if data is not None and embed_models:
            name = _embed_name(path, data, used_names)
            if len(model.atoms) >= 2:
                model_reps.append(sexpr.atom_replacement(model.atoms[1], f"kicad-embed://{name}"))
            blobs.append(EmbeddedBlob(name, data, "model"))
            statuses.append(AssetStatus(ref, "3D model", path, "will embed", f"kicad-embed://{name}", detail))
        else:
            statuses.append(AssetStatus(ref, "3D model", path, status, "", detail))

    # Board block: relink library ID and model URIs, then add native footprint-level files.
    board_reps = list(model_reps)
    if len(fp.atoms) >= 2:
        board_reps.append(sexpr.atom_replacement(fp.atoms[1], new_link))
    board_raw = sexpr.apply_replacements(raw, board_reps)
    board_doc = sexpr.parse(board_raw)
    if blobs:
        board_raw = inject_blobs(board_raw, board_doc.children[0], blobs)

    # Library block: start from original coordinates/graphics to preserve the actual board instance.
    lib_reps = list(model_reps)
    if len(fp.atoms) >= 2:
        lib_reps.append(sexpr.atom_replacement(fp.atoms[1], library_name))
    board_only_heads = {"uuid", "at", "path", "autoplace_cost90", "autoplace_cost180"}
    for child in fp.children:
        if child.head in board_only_heads:
            lib_reps.append((child.start, child.end, ""))
    # locked/placed are bare direct atoms rather than child forms in some file versions.
    for atom in fp.atoms[2:]:
        if atom.value in {"locked", "placed"}:
            lib_reps.append((atom.start, atom.end, ""))
    pref = sexpr.direct_property(fp, "Reference")
    if pref and len(pref.atoms) >= 3:
        lib_reps.append(sexpr.atom_replacement(pref.atoms[2], "REF**"))
    pval = sexpr.direct_property(fp, "Value")
    if pval and len(pval.atoms) >= 3:
        lib_reps.append(sexpr.atom_replacement(pval.atoms[2], library_name))
    for pad in fp.children_named("pad"):
        for net in pad.children_named("net"):
            lib_reps.append((net.start, net.end, ""))

    lib_raw = sexpr.apply_replacements(raw, lib_reps)
    lib_doc = sexpr.parse(lib_raw)
    lfp = lib_doc.children[0]
    if not lfp.child("version"):
        # Board-contained footprints do not necessarily carry standalone-library metadata.
        insert = '\n\t(version 20240108)\n\t(generator "portable-assets")\n'
        lib_raw = lib_raw[:lfp.atoms[1].end] + insert + lib_raw[lfp.atoms[1].end:]
        lib_doc = sexpr.parse(lib_raw)
        lfp = lib_doc.children[0]
    if blobs:
        lib_raw = inject_blobs(lib_raw, lfp, blobs)
    if not lib_raw.endswith("\n"):
        lib_raw += "\n"
    return board_raw, lib_raw, statuses, blobs


def _board_data(ctx: ProjectContext) -> tuple[str, sexpr.Node, list[sexpr.Node]]:
    text = _read(ctx.board)
    doc = sexpr.parse(text)
    root = sexpr.root_named(doc, "kicad_pcb")
    if not root:
        raise ValueError(f"{ctx.board.name} is not a KiCad board")
    return text, root, root.children_named("footprint")


def _schematic_symbols(path: Path) -> tuple[str, sexpr.Node, list[sexpr.Node], Optional[sexpr.Node]]:
    text = _read(path)
    doc = sexpr.parse(text)
    root = sexpr.root_named(doc, "kicad_sch")
    if not root:
        raise ValueError(f"{path.name} is not a KiCad schematic")
    return text, root, root.children_named("symbol"), root.child("lib_symbols")


def _symbol_ref(sym: sexpr.Node) -> str:
    return _prop(sym, "Reference")


def _symbol_fp(sym: sexpr.Node) -> str:
    return _prop(sym, "Footprint")


def scan_project(ctx: ProjectContext, options: Optional[PortableOptions] = None) -> ScanReport:
    options = options or PortableOptions()
    tables = LibraryTables(ctx)
    resolver = ModelResolver(ctx, tables, options)
    board_text, _, fps = _board_data(ctx)
    report = ScanReport(str(ctx.project_dir), str(ctx.board), [str(x) for x in ctx.schematics])
    report.footprints = len(fps)
    report.locks = [str(p) for p in ctx.lock_files()]
    board_refs = {_reference_from_fp(fp): fp for fp in fps if _reference_from_fp(fp)}

    for fp in fps:
        ref = _reference_from_fp(fp)
        link = _lib_link(fp)
        src = tables.footprint_source(link)
        report.assets.append(AssetStatus(ref, "Footprint", link or "<board-only>", "available from PCB snapshot", str(src or ctx.fp_dir)))
        for model in fp.children_named("model"):
            raw = _model_path(model)
            if not raw:
                continue
            report.model_refs += 1
            data, status, detail = resolver.resolve(raw, src)
            if raw.startswith("kicad-embed://"):
                st = "embedded"
            elif data is not None:
                st = "resolvable"
            else:
                st = status
                report.unresolved_models += 1
            report.assets.append(AssetStatus(ref, "3D model", raw, st, detail=detail))

    for sch in ctx.schematics:
        _, _, syms, lib_symbols = _schematic_symbols(sch)
        report.schematic_symbols += len(syms)
        for sym in syms:
            ref = _symbol_ref(sym)
            link = _symbol_fp(sym)
            if not link or ref not in board_refs:
                continue
            exists = tables.link_exists(link)
            if exists is False:
                report.missing_footprint_links += 1
                report.assets.append(AssetStatus(ref, "Footprint link", link, "missing", "recoverable from PCB"))
            elif exists is None:
                report.assets.append(AssetStatus(ref, "Footprint link", link, "remote/unverifiable", "recoverable from PCB"))
        if lib_symbols:
            report.assets.append(AssetStatus(sch.name, "Symbol cache", "schematic lib_symbols", "portable cache present", "can snapshot to project libraries"))
    if report.locks:
        report.warnings.append("KiCad editor lock files are present. Analyze is safe, but Apply should be done after saving and closing editors to prevent an open editor from overwriting disk changes.")
    if report.unresolved_models:
        report.warnings.append(f"{report.unresolved_models} 3D model reference(s) could not be resolved; they will be left unchanged rather than broken.")
    return report


def _build_symbol_snapshots(ctx: ProjectContext, texts: dict[Path, str]) -> tuple[dict[Path, str], dict[str, bytes], int]:
    """Relink cached symbol IDs to project-local snapshot libraries and return library files."""
    grouped: dict[str, dict[str, str]] = {}
    old_to_new: dict[str, str] = {}
    count = 0

    # Collect unique cached definitions first.
    for path, text in texts.items():
        doc = sexpr.parse(text)
        root = sexpr.root_named(doc, "kicad_sch")
        if not root:
            continue
        libs = root.child("lib_symbols")
        if not libs:
            continue
        for s in libs.children_named("symbol"):
            if len(s.atoms) < 2:
                continue
            old_id = s.atoms[1].value
            if ":" in old_id:
                nick, entry = old_id.split(":", 1)
            else:
                nick, entry = "Project", old_id
            new_nick = "Portable_" + safe_name(nick, "Project")
            new_id = f"{new_nick}:{entry}"
            old_to_new[old_id] = new_id
            # Library file contains entry name only, not nickname.
            raw = text[s.start:s.end]
            local_doc = sexpr.parse(raw)
            local_s = local_doc.children[0]
            raw = sexpr.apply_replacements(raw, [sexpr.atom_replacement(local_s.atoms[1], entry)])
            grouped.setdefault(new_nick, {}).setdefault(entry, raw)

    # Rewrite cached symbol IDs and placed lib_id atoms without reformatting schematic files.
    rewritten: dict[Path, str] = {}
    for path, text in texts.items():
        doc = sexpr.parse(text)
        root = sexpr.root_named(doc, "kicad_sch")
        if not root:
            rewritten[path] = text
            continue
        reps: list[tuple[int, int, str]] = []
        libs = root.child("lib_symbols")
        if libs:
            for s in libs.children_named("symbol"):
                if len(s.atoms) >= 2 and s.atoms[1].value in old_to_new:
                    reps.append(sexpr.atom_replacement(s.atoms[1], old_to_new[s.atoms[1].value]))
        for sym in root.children_named("symbol"):
            lid = sym.child("lib_id")
            if lid and len(lid.atoms) >= 2 and lid.atoms[1].value in old_to_new:
                reps.append(sexpr.atom_replacement(lid.atoms[1], old_to_new[lid.atoms[1].value]))
        rewritten[path] = sexpr.apply_replacements(text, reps)

    libs_out: dict[str, bytes] = {}
    for nick, symbols in grouped.items():
        body = "\n\n".join("\t" + raw.replace("\n", "\n\t") for raw in symbols.values())
        content = f'(kicad_symbol_lib\n\t(version 20231120)\n\t(generator "portable-assets")\n{body}\n)\n'
        libs_out[nick] = content.encode("utf-8")
        count += len(symbols)
    return rewritten, libs_out, count


def make_portable(
    ctx: ProjectContext,
    options: Optional[PortableOptions] = None,
    progress: Optional[Callable[[str, int], None]] = None,
    ignore_locks: bool = False,
) -> ApplyResult:
    options = options or PortableOptions()
    progress = progress or (lambda _msg, _pct: None)
    locks = ctx.lock_files()
    if locks and not ignore_locks:
        raise RuntimeError(
            "KiCad project lock files are present. Save and close the Schematic/PCB editors, then click Apply again. "
            "This prevents KiCad from later overwriting the portable file edits.\n\n" + "\n".join(str(x) for x in locks)
        )

    tables = LibraryTables(ctx)
    resolver = ModelResolver(ctx, tables, options)
    progress("Reading board and schematics…", 5)
    board_text, board_root, fps = _board_data(ctx)
    sch_texts = {p: _read(p) for p in ctx.schematics}
    board_ref_to_name: dict[str, str] = {}
    fp_writes: dict[Path, bytes] = {}
    board_reps: list[tuple[int, int, str]] = []
    unresolved: list[str] = []
    model_blobs_for_manifest: dict[str, EmbeddedBlob] = {}
    model_count = 0
    asset_statuses: list[AssetStatus] = []
    name_collisions: dict[str, int] = {}

    for idx, fp in enumerate(fps):
        ref = _reference_from_fp(fp)
        link = _lib_link(fp)
        if not ref:
            continue
        base_name = _portable_fp_name(ref, link, options.per_reference_footprints)
        n = name_collisions.get(base_name, 0)
        name_collisions[base_name] = n + 1
        name = base_name if n == 0 else f"{base_name}__{n + 1}"
        new_link = f"{FP_NICK}:{name}"
        source = tables.footprint_source(link)
        raw = board_text[fp.start:fp.end]
        board_block, lib_block, statuses, blobs = _transform_footprint(raw, new_link, name, resolver, source, options.embed_3d)
        board_reps.append((fp.start, fp.end, board_block))
        fp_writes[ctx.fp_dir / f"{name}.kicad_mod"] = lib_block.encode("utf-8")
        board_ref_to_name[ref] = name
        asset_statuses.extend(statuses)
        for st in statuses:
            if st.kind == "3D model" and st.status in {"unresolved", "remote disabled"}:
                unresolved.append(f"{ref}: {st.source}")
            if st.status == "will embed":
                model_count += 1
        for b in blobs:
            key = hashlib.sha256(b.data).hexdigest()
            model_blobs_for_manifest.setdefault(key, b)
        progress(f"Snapshotting footprint {idx + 1}/{len(fps)}: {ref}", 10 + int(35 * (idx + 1) / max(1, len(fps))))

    board_final = sexpr.apply_replacements(board_text, board_reps)

    # Relink each schematic instance's Footprint property by reference.
    sch_final: dict[Path, str] = {}
    for path, text in sch_texts.items():
        doc = sexpr.parse(text)
        root = sexpr.root_named(doc, "kicad_sch")
        reps: list[tuple[int, int, str]] = []
        if root:
            for sym in root.children_named("symbol"):
                ref = _symbol_ref(sym)
                if ref in board_ref_to_name:
                    p = sexpr.direct_property(sym, "Footprint")
                    if p and len(p.atoms) >= 3:
                        reps.append(sexpr.atom_replacement(p.atoms[2], f"{FP_NICK}:{board_ref_to_name[ref]}"))
        sch_final[path] = sexpr.apply_replacements(text, reps)
    progress("Relinking schematic footprint fields…", 50)

    symbol_libs: dict[str, bytes] = {}
    symbol_count = 0
    if options.snapshot_symbols:
        sch_final, symbol_libs, symbol_count = _build_symbol_snapshots(ctx, sch_final)
        progress("Creating local symbol snapshots…", 62)

    writes: dict[Path, bytes] = {}
    writes.update(fp_writes)
    writes[ctx.board] = board_final.encode("utf-8")
    for p, t in sch_final.items():
        writes[p] = t.encode("utf-8")

    # Project library tables.
    fp_table_text = _read(ctx.fp_table) if ctx.fp_table.exists() else ""
    fp_table_text = _table_upsert(fp_table_text, "fp_lib_table", FP_NICK, "${KIPRJMOD}/.portable_assets/Portable.pretty", "Portable Assets generated project-local footprint snapshots")
    writes[ctx.fp_table] = fp_table_text.encode("utf-8")
    if symbol_libs:
        sym_table_text = _read(ctx.sym_table) if ctx.sym_table.exists() else ""
        for nick, data in symbol_libs.items():
            p = ctx.sym_dir / f"{nick}.kicad_sym"
            writes[p] = data
            sym_table_text = _table_upsert(sym_table_text, "sym_lib_table", nick, f"${{KIPRJMOD}}/.portable_assets/symbols/{nick}.kicad_sym", "Portable Assets generated symbol snapshot")
        writes[ctx.sym_table] = sym_table_text.encode("utf-8")
    progress("Updating project library tables…", 70)

    # A plain manifest exists outside the vault as well, making the transformation auditable.
    manifest = {
        "format": 1,
        "generator": "KiCad Portable Assets",
        "footprint_library": ".portable_assets/Portable.pretty",
        "symbol_directory": ".portable_assets/symbols",
        "reference_map": board_ref_to_name,
        "unresolved_models": unresolved,
        "vault_files": {},
    }
    archive_blobs: list[EmbeddedBlob] = []
    if options.mirror_vault:
        for p, data in list(fp_writes.items()) + [(ctx.sym_dir / f"{n}.kicad_sym", d) for n, d in symbol_libs.items()]:
            vault_name = ("PA_FP__" if p.suffix == ".kicad_mod" else "PA_SYM__") + p.name
            rel = str(p.relative_to(ctx.project_dir)).replace("\\", "/")
            manifest["vault_files"][vault_name] = rel
            archive_blobs.append(EmbeddedBlob(vault_name, data, "other"))
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        archive_blobs.append(EmbeddedBlob(VAULT_MANIFEST, manifest_bytes, "other"))

        # Inject source-library archive into both main schematic and board root. Active 3D links
        # remain footprint-level; root vault is for restoration/source portability.
        board_now = writes[ctx.board].decode("utf-8")
        bdoc = sexpr.parse(board_now)
        broot = sexpr.root_named(bdoc, "kicad_pcb")
        if broot:
            board_now = inject_blobs(board_now, broot, archive_blobs)
            writes[ctx.board] = board_now.encode("utf-8")
        if ctx.main_schematic and ctx.main_schematic in writes:
            sch_now = writes[ctx.main_schematic].decode("utf-8")
            sdoc = sexpr.parse(sch_now)
            sroot = sexpr.root_named(sdoc, "kicad_sch")
            if sroot:
                sch_now = inject_blobs(sch_now, sroot, archive_blobs)
                writes[ctx.main_schematic] = sch_now.encode("utf-8")
        progress("Mirroring portable libraries into KiCad Embedded Files…", 84)
    else:
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    writes[ctx.asset_root / "manifest.json"] = manifest_bytes

    # Final parse validation before touching the user's files.
    for p, data in writes.items():
        if p.suffix in {".kicad_pcb", ".kicad_sch", ".kicad_mod", ".kicad_sym"} or p.name in {"fp-lib-table", "sym-lib-table"}:
            sexpr.parse(data.decode("utf-8"))
    progress("Validated generated KiCad S-expressions; committing transaction…", 91)
    tx = Transaction(ctx)
    written = tx.commit(writes)
    progress("Portable project created.", 100)
    return ApplyResult(str(tx.backup_dir), [str(x) for x in written], len(board_ref_to_name), symbol_count, model_count, unresolved, [])


def missing_footprints(ctx: ProjectContext) -> list[AssetStatus]:
    tables = LibraryTables(ctx)
    _, _, fps = _board_data(ctx)
    board_refs = {_reference_from_fp(fp): fp for fp in fps if _reference_from_fp(fp)}
    result: list[AssetStatus] = []
    for sch in ctx.schematics:
        _, root, syms, _ = _schematic_symbols(sch)
        for sym in syms:
            ref = _symbol_ref(sym)
            link = _symbol_fp(sym)
            if not ref or ref not in board_refs or not link:
                continue
            exists = tables.link_exists(link)
            if exists is False:
                result.append(AssetStatus(ref, "Missing footprint", link, "missing", "PCB snapshot available", sch.name))
    return result


def repair_missing_footprints(
    ctx: ProjectContext,
    references: Optional[Iterable[str]] = None,
    options: Optional[PortableOptions] = None,
    progress: Optional[Callable[[str, int], None]] = None,
    ignore_locks: bool = False,
) -> ApplyResult:
    options = options or PortableOptions(snapshot_symbols=False, mirror_vault=False)
    wanted = set(references or [x.reference for x in missing_footprints(ctx)])
    if not wanted:
        return ApplyResult("", [], 0, 0, 0, [], ["No missing footprint links detected."])
    # Reuse the full portability engine would unnecessarily relink everything. Build a targeted
    # project copy of the workflow by temporarily exporting only selected board refs.
    locks = ctx.lock_files()
    if locks and not ignore_locks:
        raise RuntimeError("Save and close KiCad editors before repairing footprint links. Lock files:\n" + "\n".join(map(str, locks)))
    tables = LibraryTables(ctx)
    resolver = ModelResolver(ctx, tables, options)
    board_text, _, fps = _board_data(ctx)
    writes: dict[Path, bytes] = {}
    board_reps: list[tuple[int, int, str]] = []
    ref_to_name: dict[str, str] = {}
    unresolved: list[str] = []
    model_count = 0

    selected = [fp for fp in fps if _reference_from_fp(fp) in wanted]
    for i, fp in enumerate(selected):
        ref, link = _reference_from_fp(fp), _lib_link(fp)
        name = _portable_fp_name(ref, link, True)
        new_link = f"{FP_NICK}:{name}"
        raw = board_text[fp.start:fp.end]
        braw, lraw, statuses, _ = _transform_footprint(raw, new_link, name, resolver, tables.footprint_source(link), options.embed_3d)
        board_reps.append((fp.start, fp.end, braw))
        writes[ctx.fp_dir / f"{name}.kicad_mod"] = lraw.encode("utf-8")
        ref_to_name[ref] = name
        model_count += sum(1 for s in statuses if s.status == "will embed")
        unresolved += [f"{ref}: {s.source}" for s in statuses if s.status in {"unresolved", "remote disabled"}]
        (progress or (lambda *_: None))(f"Recovering {ref} from PCB snapshot…", int(50 * (i + 1) / max(1, len(selected))))

    writes[ctx.board] = sexpr.apply_replacements(board_text, board_reps).encode("utf-8")
    for sch in ctx.schematics:
        text, root, syms, _ = _schematic_symbols(sch)
        reps = []
        for sym in syms:
            ref = _symbol_ref(sym)
            if ref in ref_to_name:
                p = sexpr.direct_property(sym, "Footprint")
                if p and len(p.atoms) >= 3:
                    reps.append(sexpr.atom_replacement(p.atoms[2], f"{FP_NICK}:{ref_to_name[ref]}"))
        if reps:
            writes[sch] = sexpr.apply_replacements(text, reps).encode("utf-8")
    fp_table_text = _read(ctx.fp_table) if ctx.fp_table.exists() else ""
    writes[ctx.fp_table] = _table_upsert(fp_table_text, "fp_lib_table", FP_NICK, "${KIPRJMOD}/.portable_assets/Portable.pretty", "Portable Assets recovered footprint snapshots").encode("utf-8")
    for p, data in writes.items():
        if p.suffix.startswith(".kicad") or p.name == "fp-lib-table":
            sexpr.parse(data.decode("utf-8"))
    tx = Transaction(ctx)
    written = tx.commit(writes)
    (progress or (lambda *_: None))("Missing footprints repaired.", 100)
    return ApplyResult(str(tx.backup_dir), [str(x) for x in written], len(ref_to_name), 0, model_count, unresolved, [])


def restore_from_vault(ctx: ProjectContext, prefer: str = "schematic") -> list[Path]:
    candidates = []
    if prefer == "schematic" and ctx.main_schematic:
        candidates.append(ctx.main_schematic)
    candidates.append(ctx.board)
    if ctx.main_schematic and ctx.main_schematic not in candidates:
        candidates.append(ctx.main_schematic)
    for source in candidates:
        text = _read(source)
        doc = sexpr.parse(text)
        root = doc.children[0] if doc.children else None
        emb = root.child("embedded_files") if root else None
        if not emb:
            continue
        decoded: dict[str, EmbeddedBlob] = {}
        for f in emb.children_named("file"):
            name = _value(f.child("name"))
            if name.startswith("PA_"):
                try:
                    decoded[name] = decode_file_node(text, f)
                except Exception:
                    continue
        if VAULT_MANIFEST not in decoded:
            continue
        manifest = json.loads(decoded[VAULT_MANIFEST].data.decode("utf-8"))
        writes: dict[Path, bytes] = {}
        for vault_name, rel in manifest.get("vault_files", {}).items():
            blob = decoded.get(vault_name)
            if blob:
                target = (ctx.project_dir / rel).resolve()
                if ctx.project_dir not in target.parents and target != ctx.project_dir:
                    raise ValueError(f"Unsafe vault path: {rel}")
                writes[target] = blob.data
        if not writes:
            return []
        tx = Transaction(ctx)
        return tx.commit(writes)
    raise RuntimeError("No Portable Assets vault manifest was found in the schematic or board Embedded Files.")
