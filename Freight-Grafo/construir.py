"""Build the Freight evidence index and its Graphify-compatible document graph."""
import csv
import hashlib
import io
import json
import logging
import re
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / ".deps"))

import extract_msg
import pymupdf
import xlrd
from bs4 import BeautifulSoup
from openpyxl import load_workbook
from striprtf.striprtf import rtf_to_text

SOURCE = BASE.parent / "Freight-Tarifas"
OUT = BASE / "graphify-out"

TOPICS = {
    "Combustible / fuel surcharge": r"fuel (?:surcharg|levy|rate)|fuel surcharge|diesel surcharge|_monthly freight fuel",
    "Zonas y códigos postales / zones and postcodes": r"postcode|postal code|zone mapping|zone (?:matrix|import|list)|\bzone map\b",
    "Exenciones / exemptions": r"\bexempt(?:ion|ed)?\b|\bwaiv(?:e|ed|er)\b",
    "Manejo manual / manual handling": r"manual handling|non.conveyable|hand unload",
    "Recargos / surcharges": r"accessorial|extra charges|additional charges|surcharge|special fees",
    "Tarifas / rate schedules": r"rate\s*(?:card|schedule|extension|sheet)|pricing schedule|rate table|tariff|base freight|\bfreight rates\b",
    "Sobredimensión / oversize": r"oversize|overlength|over.length|overdimension",
    "Regiones remotas / remote areas": r"remote (?:area|zone|mine)|outer metro|regional surcharge",
    "Extensiones y vigencia / rate extensions": r"rate extension|valid until|effective date|rates effective",
}
PLACES = re.compile(r"\b(Kangaroo Island|Karratha|Port Lincoln|Port Augusta|Mount Gambier|Alice Springs|Broken Hill|Coober Pedy|Roxby Downs|Rottnest Island|Norfolk Island|Lord Howe Island)\b", re.I)
ACCOUNTS = re.compile(r"\b(?:account(?:\s+(?:number|no\.?|code))?\s*[:#-]?\s+)([A-Z0-9]{6,12})\b", re.I)
KNOWN_ACCOUNTS = re.compile(r"\b(?:5005I2|FD6805)\b", re.I)
SUPPORTED = {".pdf", ".xlsx", ".xlsm", ".xls", ".csv", ".msg", ".docx", ".odt", ".htm", ".html", ".rtf", ".dat", ".txt"}
CARRIERS = {
    "TGE Express": "Team Global Express", "TGE Fast": "Team Global Express",
    "TGE Priority": "Team Global Express", "Toll Ipec": "Toll IPEC",
    "TOLL - TGE - Team Global Express": "Team Global Express",
    "APD - Adelaide Parcel Deliveries": "APD", "COCHRN - Cochrane's Transport": "Cochranes",
    "COURPL - Couriers Please": "Couriers Please", "EPARCEL - Australia Post": "Australia Post eParcel",
    "KTI - Kangaroo Transport Industries": "KTI", "TNT - FedEx": "TNT",
}
GENERIC_FOLDERS = {"deleteme", "_Monthly Freight Fuel Surcharges", "___HISTORICAL___", "___IMPORT_CSV_FUEL_RATES___"}
IMAGE_FORMATS = {".jpg", ".jpeg", ".png"}


@lru_cache(maxsize=1)
def ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)


def read_image(data):
    lines, _ = ocr_engine()(data)
    return "\n".join(line for _, line, _ in (lines or []))


def text(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeError:
        return data.decode("cp1252", errors="replace")


def clean(value):
    return str(value if value is not None else "").replace("\x00", "").strip()


def blocks(value, location):
    paragraph = []
    length = 0
    for line in value.splitlines():
        for pos in range(0, len(line), 1800):
            part = line[pos:pos + 1800].strip()
            if not part:
                continue
            if paragraph and length + len(part) > 1800:
                yield location, "\n".join(paragraph)
                paragraph = paragraph[-2:] if sum(map(len, paragraph[-2:])) < 230 else []
                length = sum(map(len, paragraph))
            paragraph.append(part)
            length += len(part)
    if paragraph:
        yield location, "\n".join(paragraph)


def table(rows, label):
    header = ""
    group = []
    start = 1
    row_number = 0
    for row_number, row in enumerate(rows, 1):
        values = [clean(cell) for cell in row]
        if not any(values):
            continue
        line = " | ".join(values).rstrip(" |")
        if not header:
            header = f"Fila {row_number} (primera fila con datos) | {line[:350]}"
        if not group:
            start = row_number
        group.append(f"Fila {row_number} | {line}")
        if len(group) >= 12:
            yield from blocks("\n".join([header, *group]), f"{label}, filas {start}–{row_number}")
            group = []
    if group:
        yield from blocks("\n".join([header, *group]), f"{label}, filas {start}–{row_number}")


def extract(data, suffix, location="", notes=None, depth=0):
    def at(label):
        return f"{location} · {label}" if location else label

    if suffix == ".pdf":
        pymupdf.TOOLS.mupdf_warnings(reset=True)
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            for i, page in enumerate(pdf, 1):
                value = page.get_text(sort=True)
                if not re.search(r"\w", value):
                    try:
                        value = read_image(page.get_pixmap(dpi=160).tobytes("png"))
                    except Exception as error:
                        notes.append(at(f"página {i}: error de OCR ({type(error).__name__})"))
                        continue
                    if value.strip():
                        yield from blocks(value, at(f"página {i} · OCR"))
                        notes.append(at(f"página {i}: cotejar texto OCR"))
                    else:
                        notes.append(at(f"página {i} sin texto recuperable"))
                else:
                    yield from blocks(value, at(f"página {i}"))
        if pymupdf.TOOLS.mupdf_warnings(reset=True):
            notes.append(at("MuPDF detectó incidencias de lectura"))
    elif suffix in {".xlsx", ".xlsm"} or (suffix == ".xls" and data.startswith(b"PK")):
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            for sheet in workbook.worksheets:
                sheet.reset_dimensions()
                yield from table(sheet.values, at(f"hoja «{sheet.title}»"))
        finally:
            workbook.close()
    elif suffix == ".xls" and data.startswith(bytes.fromhex("D0 CF 11 E0")):
        workbook = xlrd.open_workbook(file_contents=data, on_demand=True)
        try:
            for sheet in workbook.sheets():
                yield from table(map(sheet.row_values, range(sheet.nrows)), at(f"hoja «{sheet.name}»"))
        finally:
            workbook.release_resources()
    elif suffix in {".docx", ".odt"}:
        path = "word/document.xml" if suffix == ".docx" else "content.xml"
        with ZipFile(io.BytesIO(data)) as archive:
            xml = BeautifulSoup(archive.read(path), "xml")
            for number, element in enumerate(xml.find_all("p"), 1):
                yield from blocks(element.get_text(" ", strip=True), at(f"párrafo {number}"))
    elif suffix == ".msg":
        with extract_msg.openMsg(data) as mail:
            yield from blocks(
                f"Asunto: {mail.subject or ''}\nFecha: {mail.date or ''}\n\n{clean(mail.body)}",
                at("correo"),
            )
            for attachment in mail.attachments:
                name = attachment.getFilename() or "adjunto sin nombre"
                contents = attachment.data
                yield at("correo · lista de adjuntos"), f"Adjunto: {name}"
                ext = Path(name).suffix.lower()
                if ext not in SUPPORTED | {".zip"} or not isinstance(contents, bytes) or depth >= 2:
                    if ext not in {".jpg", ".jpeg", ".png", ".gif"}:
                        notes.append(at(f"adjunto sin extracción: {name}"))
                    continue
                try:
                    yield from extract(contents, ext, at(f"adjunto «{name}»"), notes, depth + 1)
                except Exception as error:
                    notes.append(at(f"adjunto «{name}»: {type(error).__name__}"))
    elif suffix == ".zip":
        with ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                ext = Path(member.filename).suffix.lower()
                if ext not in SUPPORTED or member.file_size > 40_000_000:
                    notes.append(at(f"archivo interno sin extracción: {member.filename}"))
                    continue
                try:
                    yield from extract(archive.read(member), ext, at(f"archivo interno «{member.filename}»"), notes, depth + 1)
                except Exception as error:
                    notes.append(at(f"archivo interno «{member.filename}»: {type(error).__name__}"))
    elif suffix in {".html", ".htm"} or (suffix == ".xls" and b"<html" in data[:4096].lower()):
        html = BeautifulSoup(text(data), "html.parser")
        for element in html(["script", "style"]):
            element.decompose()
        for number, element in enumerate(html.find_all("table"), 1):
            rows = ([cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])] for row in element.find_all("tr"))
            yield from table(rows, at(f"tabla {number}"))
            element.decompose()
        yield from blocks(html.get_text("\n", strip=True), at("texto HTML"))
    elif suffix in {".csv", ".xls"}:
        value = text(data)
        if "\x00" in value:
            notes.append(at("archivo binario sin lector"))
            return
        try:
            dialect = csv.Sniffer().sniff(value[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        yield from table(csv.reader(io.StringIO(value), dialect), at("tabla"))
    elif suffix == ".rtf":
        yield from blocks(rtf_to_text(text(data), errors="replace"), at("texto RTF"))
    elif suffix in {".dat", ".txt"}:
        yield from table(((line,) for line in text(data).splitlines()), at("texto original"))
    elif suffix in IMAGE_FORMATS:
        value = read_image(data)
        notes.append(at("cotejar texto OCR" if value else "sin texto recuperable por OCR"))
        yield from blocks(value, at("imagen · OCR"))
    else:
        notes.append(at("requiere OCR" if suffix in {".jpg", ".png"} else f"formato {suffix} sin lector"))


def scope(parts):
    for part in parts[:-1]:
        if part in CARRIERS:
            return CARRIERS[part]
        if part not in GENERIC_FOLDERS and not part.startswith("Freight Review") and part == parts[0]:
            return part
    return ""


def node_id(prefix, label):
    return f"{prefix}_{hashlib.sha256(label.casefold().encode()).hexdigest()[:24]}"


def atomic_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def build():
    OUT.mkdir(exist_ok=True)
    temp_db = BASE / "consulta.rebuild.sqlite"
    nodes, links, files, counts = {}, [], [], Counter()
    all_sources = sorted((p for p in SOURCE.rglob("*") if p.is_file()), key=lambda p: p.as_posix().casefold())
    if not all_sources:
        raise RuntimeError(f"No se encontraron archivos en {SOURCE}")

    def node(prefix, label, **attrs):
        identifier = node_id(prefix, label)
        nodes.setdefault(identifier, {"id": identifier, "label": label, "file_type": "document",
                                      "norm_label": label.casefold(), "kind": prefix, **attrs})
        return identifier

    def link(document, concept, relation, source, location):
        nodes[concept].setdefault("source_file", source)
        nodes[concept].setdefault("source_location", location)
        links.append({"source": document, "target": concept, "relation": relation, "source_file": source,
                      "source_location": location, "confidence": "EXTRACTED", "confidence_score": 1.0, "weight": 1})

    with closing(sqlite3.connect(temp_db)) as db:
        db.executescript("""
            DROP TABLE IF EXISTS sources;
            DROP TABLE IF EXISTS evidence;
            DROP TABLE IF EXISTS fragment_ranges;
            CREATE TABLE sources (id TEXT PRIMARY KEY, path TEXT, carrier TEXT, status TEXT, sha256 TEXT, notes TEXT);
            CREATE TABLE fragment_ranges (source_id TEXT PRIMARY KEY, first_row INTEGER, last_row INTEGER);
            CREATE VIRTUAL TABLE evidence USING fts5(
                title, context, body, source_id UNINDEXED, location UNINDEXED, tokenize = 'unicode61 remove_diacritics 2');
        """)
        hashes = {}
        first_row = 1
        for index, path in enumerate(all_sources, 1):
            relative = path.relative_to(SOURCE)
            source = str(Path("..") / "Freight-Tarifas" / relative).replace("\\", "/")
            identifier = node_id("documento", relative.as_posix())
            carrier = scope(relative.parts)
            notes = []
            fragments = []
            duplicate = None
            digest = ""
            try:
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                duplicate = hashes.get(digest)
                if not duplicate:
                    for fragment in extract(data, path.suffix.lower(), notes=notes):
                        fragments.append(fragment)
            except Exception as error:
                notes.append(f"{type(error).__name__}: {str(error)[:250]}")
            status = ("duplicado" if duplicate else "parcial" if fragments and notes else
                      "indexado" if fragments else "pendiente")
            if digest and not duplicate:
                hashes[digest] = (identifier, status)
            nodes[identifier] = {"id": identifier, "label": path.stem, "norm_label": path.stem.casefold(),
                                 "file_type": "document", "kind": "documento", "source_file": source,
                                 "source_location": "archivo", "status": status, "carrier": carrier}
            matches = {}
            for location, value in [("ruta y nombre de archivo", relative.as_posix()), *fragments]:
                for topic, pattern in TOPICS.items():
                    if topic not in matches and re.search(pattern, value, re.I):
                        matches[topic] = ("tema", location)
                for place in PLACES.finditer(value):
                    matches.setdefault(place.group().title(), ("lugar", location))
                for account in [*KNOWN_ACCOUNTS.findall(value), *ACCOUNTS.findall(value)]:
                    if any(c.isalpha() for c in account) and any(c.isdigit() for c in account):
                        matches.setdefault(account.upper(), ("cuenta", location))
            if carrier:
                node_type = "grupo" if carrier in {"Post International", "Machship", "Cope System Data"} else "transportista"
                link(identifier, node(node_type, carrier), "agrupado_en", source, "carpeta de origen")
            for part in relative.parts[:-1]:
                if re.fullmatch(r"20[0-9]{2}", part) and relative.parts[0] == "_Monthly Freight Fuel Surcharges":
                    link(identifier, node("ano", f"Archivo de combustible {part}"), "archivado_en", source, "carpeta de origen")
                    break
            for part in relative.parts[:-1]:
                if part.startswith("Freight Review"):
                    link(identifier, node("revision", part), "agrupado_en", source, "carpeta de origen")
                    break
            for label, (kind, location) in matches.items():
                link(identifier, node(kind, label), "menciona", source, location)
            if duplicate:
                link(identifier, duplicate[0], "mismo_sha256", source, "archivo")
                notes.append(f"Contenido canónico: {duplicate[0]} ({duplicate[1]})")
            context = " ".join([carrier, *matches, *relative.parts[:-1]])
            db.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                       (identifier, source, carrier, status, digest, json.dumps(notes, ensure_ascii=False)))
            db.executemany("INSERT INTO evidence VALUES (?, ?, ?, ?, ?)",
                           ((path.stem, context, value, identifier, location)
                            for location, value in [("ruta y nombre de archivo", relative.as_posix()), *fragments]))
            last_row = first_row + len(fragments)
            db.execute("INSERT INTO fragment_ranges VALUES (?, ?, ?)", (identifier, first_row, last_row))
            first_row = last_row + 1
            files.append({"path": source, "id": identifier, "status": status, "fragments": len(fragments),
                          "duplicate_of": duplicate[0] if duplicate else None, "notes": notes})
            counts[status] += 1
            if index % 100 == 0:
                print(f"{index} / {len(all_sources)}", flush=True)
        db.commit()
    temp_db.replace(BASE / "consulta.sqlite")
    graph = {"directed": False, "multigraph": False, "graph": {}, "nodes": list(nodes.values()),
             "links": links, "hyperedges": []}
    atomic_json(OUT / "graph.json", graph)
    atomic_json(BASE / "cobertura.json", {"counts": counts, "files": files})
    print(json.dumps({"files": len(files), "nodes": len(nodes), "links": len(links), **counts}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    build()

