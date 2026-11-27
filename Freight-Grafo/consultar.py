"""Read-only Freight queries for the terminal and any local MCP client."""
import argparse
import json
import re
import site
import sqlite3
import unicodedata
from contextlib import closing, contextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parent
site.addsitedir(str(BASE / ".deps"))
STOP = set("a al and apply applies are con cual cuando cuanto de del does el en es for hay is la las los me of para por que se the un una was what which y".split())
SYNONYMS = {
    "combustible": ("fuel", "diesel"),
    "exencion": ("exemption", "waiver", "exempt"),
    "exenciones": ("exemption", "waiver", "exempt"),
    "recargo": ("surcharge", "fee"),
    "recargos": ("surcharge", "fees"),
    "manejo": ("handling",),
    "tarifa": ("rate", "rates"),
    "tarifas": ("rates", "rate"),
    "vigencia": ("effective", "valid"),
    "zonas": ("zones", "zone"),
    "zona": ("zone", "zones"),
    "cuenta": ("account",),
    "cuentas": ("accounts", "account"),
    "postal": ("postcode",),
    "tge": ('"Team Global Express"', "TGE", "Toll"),
}


@contextmanager
def database():
    with closing(sqlite3.connect((BASE / "consulta.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        yield db


def normalize(word):
    return "".join(c for c in unicodedata.normalize("NFD", word.casefold()) if not unicodedata.combining(c))


def passage(row):
    item = dict(row)
    item["extracto"] = re.sub(r"[ \t]{3,}", "  ", item["extracto"])
    return item


def result(row):
    item = passage(row)
    item["archivo"] = str((BASE / item["archivo"]).resolve())
    return item


def buscar(consulta: str, archivo: str = "", limite: int = 10) -> dict:
    """Busca términos de tarifas o excepciones. Devuelve citas originales y rutas.
    Usa términos concretos (ruta, cuenta, fecha, servicio o código de tarifa).
    archivo limita por parte de la ruta. consulta admite español e inglés.
    """
    tokens = list(dict.fromkeys(normalize(word) for word in re.findall(r"[^\W_]+", consulta)))[:24]
    tokens = [word for word in tokens if word not in STOP]
    if not tokens:
        return {"resultados": [], "mensaje": "Incluye un lugar, cargo, cuenta, fecha o nombre de archivo."}
    groups = []
    for word in tokens:
        terms = [word, *SYNONYMS.get(word, ())]
        groups.append("(" + " OR ".join(dict.fromkeys(terms)) + ")")
    sql = """
        SELECT sources.id AS documento, sources.path AS archivo, sources.status AS estado,
               evidence.location AS ubicacion, evidence.body AS extracto
        FROM evidence JOIN sources ON sources.id = evidence.source_id
        WHERE evidence MATCH ? AND instr(lower(sources.path), lower(?)) > 0
          AND (? OR evidence.location NOT IN ('ruta y nombre de archivo', 'correo · lista de adjuntos'))
        ORDER BY bm25(evidence, 2.0, 0.25, 5.0), evidence.rowid LIMIT ?
    """
    limit = max(1, min(limite, 30))
    matches = []
    strict = " AND ".join(groups)
    stages = [(f"body: ({strict})", 0, "todos_en_el_pasaje"),
              (strict, 1, "todos_en_el_archivo_o_pasaje"),
              (" OR ".join(groups), 1, "algunos_terminos")]
    with database() as db:
        for query, include_metadata, quality in stages:
            seen_passages = set()
            chosen_per_doc = {}
            for row in db.execute(sql, (query, archivo, include_metadata, limit * 16)):
                key = (row["documento"], row["ubicacion"], row["extracto"])
                if key in seen_passages or chosen_per_doc.get(row["documento"], 0) >= 3:
                    continue
                seen_passages.add(key)
                chosen_per_doc[row["documento"]] = chosen_per_doc.get(row["documento"], 0) + 1
                matches.append(result(row))
                if len(matches) >= limit:
                    break
            if matches:
                break
    return {"consulta": consulta, "coincidencia": quality if matches else "sin_resultados",
            "resultados": matches}


def documento(id: str, inicio: int = 0, limite: int = 12) -> dict:
    """Devuelve datos, relaciones y pasajes del documento por ID de buscar.
    Usa inicio para paginar. Si el archivo es duplicado, recupera el contenido canónico.
    """
    graph = json.loads((BASE / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    start = max(0, inicio)
    length = min(max(1, limite), 30)
    with database() as db:
        row = db.execute("SELECT * FROM sources WHERE id = ?", (id,)).fetchone()
        if not row:
            return {"error": "Documento no encontrado"}
        original = row
        if row["status"] == "duplicado":
            row = db.execute("SELECT * FROM sources WHERE sha256 = ? AND status != 'duplicado'", (row["sha256"],)).fetchone()
        bounds = db.execute("SELECT first_row, last_row FROM fragment_ranges WHERE source_id = ?", (row["id"],)).fetchone()
        records = db.execute(
            "SELECT location AS ubicacion, body AS extracto FROM evidence WHERE rowid BETWEEN ? AND ? ORDER BY rowid LIMIT ?",
            (bounds["first_row"] + start, bounds["last_row"], length + 1),
        ).fetchall()
        document_ids = {id, row["id"]}
        related = []
        for edge in graph["links"]:
            if edge["relation"] == "mismo_sha256":
                continue
            source, target = edge["source"], edge["target"]
            if target in document_ids:
                source, target = target, source
            if source in document_ids:
                related.append({"relacion": edge["relation"], "tema": labels[target],
                                "ubicacion": edge["source_location"]})
        return {
            "archivo": str((BASE / original["path"]).resolve()), "estado": row["status"],
            "fuente_del_texto": str((BASE / row["path"]).resolve()), "notas": json.loads(row["notes"]),
            "relaciones": [dict(entry) for entry in {tuple(mapping.items()): mapping for mapping in related}.values()],
            "pasajes": [passage(record) for record in records[:length]],
            "siguiente": start + length if len(records) > length else None,
        }


def cobertura() -> dict:
    """Resume la cobertura. Los archivos parciales y pendientes pueden exigir lectura del original."""
    counts = json.loads((BASE / "cobertura.json").read_text(encoding="utf-8"))["counts"]
    return {"estados": counts, "detalle": str(BASE / "cobertura.json")}


def explorar(tema: str, archivo: str = "", limite: int = 20) -> dict:
    """Recorre las relaciones de un tema, lugar, cuenta o transportista hacia sus documentos."""
    phrase = normalize(tema.strip())
    if not phrase:
        return {"error": "Indica un tema, lugar, cuenta o transportista"}
    graph = json.loads((BASE / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    documents = {node["id"]: node for node in graph["nodes"] if node["kind"] == "documento"}
    topics = {node["id"]: node for node in graph["nodes"]
              if node["kind"] != "documento" and phrase in normalize(node["label"])}
    related = []
    path_filter = normalize(archivo)
    for edge in graph["links"]:
        source_id, target_id = edge["source"], edge["target"]
        if target_id in documents:
            source_id, target_id = target_id, source_id
        source = documents.get(source_id)
        target = topics.get(target_id)
        if source and target and path_filter in normalize(source["source_file"]):
            related.append({"documento": source["id"], "tema": target["label"], "relacion": edge["relation"],
                            "archivo": str((BASE / source["source_file"]).resolve()), "estado": source["status"],
                            "ubicacion": edge["source_location"]})
    related.sort(key=lambda record: (record["estado"] == "duplicado", record["ubicacion"] == "ruta y nombre de archivo"))
    return {"tema": tema, "nodos": [node["label"] for node in topics.values()],
            "total_relaciones": len(related), "documentos": related[:max(1, min(limite, 50))]}


def serve():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("Freight - Grafo de tarifas", instructions=(
        "Consulta documental local. Empieza con buscar y cita archivo y ubicación. "
        "Las menciones del grafo y los extractos se deben comprobar en el original antes de afirmar "
        "vigencia, precedencia o condiciones de una tarifa. Usa documento para ampliar el contexto."
    ))
    for operation in (buscar, documento, explorar, cobertura):
        server.add_tool(operation)
    server.run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cli = parser.add_subparsers(dest="operation", required=True)
    search = cli.add_parser("buscar")
    search.add_argument("consulta")
    search.add_argument("--archivo", default="")
    search.add_argument("--limite", default=10, type=int)
    doc = cli.add_parser("documento")
    doc.add_argument("id")
    doc.add_argument("--inicio", default=0, type=int)
    doc.add_argument("--limite", default=12, type=int)
    explore = cli.add_parser("explorar")
    explore.add_argument("tema")
    explore.add_argument("--archivo", default="")
    explore.add_argument("--limite", default=20, type=int)
    cli.add_parser("cobertura")
    cli.add_parser("mcp")
    options = vars(parser.parse_args())
    op = options.pop("operation")
    if op == "mcp":
        serve()
    else:
        operations = {"buscar": buscar, "documento": documento, "explorar": explorar, "cobertura": cobertura}
        print(json.dumps(operations[op](**options), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

