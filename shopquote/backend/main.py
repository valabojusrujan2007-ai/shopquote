"""ShopQuote API: workspace persistence and DXF geometry analysis.

Run from this directory with: uvicorn main:app --reload
Set SHOPQUOTE_DATABASE_URL to a PostgreSQL SQLAlchemy URL for shared storage.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import JSON, Integer, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = os.environ.get("SHOPQUOTE_DATABASE_URL", "sqlite:///./shopquote.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "shopquote_workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


Base.metadata.create_all(engine)

app = FastAPI(title="ShopQuote API", version="1.0.0")

UNIT_MAP = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}
UNIT_TO_MM = {"mm": 1, "cm": 10, "m": 1000, "in": 25.4, "ft": 304.8}


def default_workspace() -> dict[str, Any]:
    materials = [
        ("mat-ms", "Mild steel · IS 2062 E250", 7850, 0, "Plate, bar"),
        ("mat-en8", "Carbon steel · EN8 / 080M40", 7850, 0, "Round bar"),
        ("mat-ss304", "Stainless steel · SS 304", 8000, 0, "Plate, bar"),
        ("mat-al6061", "Aluminium · 6061-T6", 2700, 0, "Plate, bar"),
        ("mat-brass", "Brass · C360", 8530, 0, "Round bar"),
        ("mat-copper", "Copper · ETP", 8960, 0, "Plate, bar"),
        ("mat-pom", "Acetal · POM-C", 1410, 0, "Engineering plastic"),
    ]
    machines = [
        ("mc-vmc", "VMC / CNC milling"),
        ("mc-lathe", "CNC turning centre"),
        ("mc-drill", "Drill / tap station"),
        ("mc-grind", "Grinding machine"),
        ("mc-edm", "EDM / wire EDM"),
        ("mc-manual", "Manual / inspection station"),
    ]
    operation_names = [
        ("CNC Turning", "CNC turning centre"),
        ("CNC Milling", "VMC / CNC milling"),
        ("Drilling", "Drill / tap station"),
        ("Boring", "VMC / CNC milling"),
        ("Reaming", "Drill / tap station"),
        ("Tapping", "Drill / tap station"),
        ("Grinding", "Grinding machine"),
        ("EDM", "EDM / wire EDM"),
        ("Wire EDM", "EDM / wire EDM"),
        ("Surface Grinding", "Grinding machine"),
        ("Cylindrical Grinding", "Grinding machine"),
        ("VMC Operations", "VMC / CNC milling"),
        ("HMC Operations", "VMC / CNC milling"),
        ("Welding", "Manual / inspection station"),
        ("Heat Treatment", "Manual / inspection station"),
        ("Surface Finishing", "Manual / inspection station"),
        ("Inspection", "Manual / inspection station"),
        ("Deburring", "Manual / inspection station"),
    ]
    return {
        "materials": [dict(id=i, name=n, density=d, price=p, form=f, stockSizes="") for i, n, d, p, f in materials],
        "machines": [dict(id=i, name=n, hourly=0, labour=0, energy=0) for i, n in machines],
        "operations": [dict(id=f"op-{i}", name=n, machine=m, setup=0, cycle=0) for i, (n, m) in enumerate(operation_names)],
        "projects": [],
        "settings": {"workshop": "Acme Workshop", "location": "India", "footer": ""},
        "theme": "light",
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ShopQuote API"}


@app.get("/api/workspace")
def get_workspace() -> dict[str, Any]:
    with SessionFactory() as session:
        record = session.get(Workspace, 1)
        return {"workspace": record.payload if record else default_workspace()}


@app.put("/api/workspace")
def put_workspace(payload: dict[str, Any]) -> dict[str, bool]:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Workspace data exceeds the 20 MB limit.")
    with SessionFactory() as session:
        record = session.get(Workspace, 1)
        if record is None:
            record = Workspace(id=1, payload=payload)
            session.add(record)
        else:
            record.payload = payload
        session.commit()
    return {"saved": True}


def _field(entity: Any, key: str, default: float = 0) -> float:
    try:
        value = float(entity.get(key, default))
        return value if math.isfinite(value) else default
    except (TypeError, ValueError, AttributeError):
        return default


@app.post("/api/estimate/calculate")
def calculate_estimate(data: dict[str, Any]) -> dict[str, Any]:
    """Calculate one component and batch costs from explicit user inputs."""
    quantity = max(1, int(_field(data, "quantity", 1)))
    material = data.get("material") or {}
    part = data.get("part") or {}
    extras = data.get("extras") or {}
    operations = data.get("operations") or []
    density = _field(material, "density")
    price = _field(material, "price")
    area = _field(part, "area")
    part_thickness = _field(part, "thickness")
    cad_volume_mm3 = _field(part, "volume")
    length = _field(material, "blankLength")
    width = _field(material, "blankWidth")
    stock_thickness = _field(material, "blankThickness")
    form = str(material.get("form", "Rectangular plate"))
    if form == "Round bar" or "brass bar" in form.lower() or "copper bar" in form.lower():
        stock_mm3 = math.pi * width**2 / 4 * length
    elif form == "Square bar":
        stock_mm3 = length * width**2
    elif form in ("Tube", "Hollow pipe") and width > 2 * stock_thickness > 0:
        stock_mm3 = math.pi * (width**2 - (width - 2 * stock_thickness) ** 2) / 4 * length
    elif form in ("Tube", "Hollow pipe"):
        stock_mm3 = 0
    else:
        stock_mm3 = length * width * stock_thickness
    raw_weight = stock_mm3 / 1_000_000_000 * density
    finished_volume_mm3 = cad_volume_mm3 if cad_volume_mm3 > 0 else area * part_thickness
    finished_weight = finished_volume_mm3 / 1_000_000_000 * density
    scrap_weight = max(0, raw_weight - finished_weight)
    reusable_weight = scrap_weight * min(100, max(0, _field(material, "reusablePct"))) / 100
    recyclable_weight = scrap_weight * min(100, max(0, _field(material, "recyclablePct"))) / 100
    machining_waste_weight = max(0, scrap_weight - reusable_weight - recyclable_weight)
    credit = reusable_weight * _field(material, "reusableRate") + recyclable_weight * _field(material, "recyclableRate")
    raw_cost = raw_weight * price
    net_material = max(0, raw_cost - credit)
    machine = labour = tooling = electricity = 0.0
    for operation in operations:
        setup = _field(operation, "setupMin")
        cycle = _field(operation, "cycleMin")
        hours_per_part = (setup / quantity + cycle) / 60
        machine += hours_per_part * _field(operation, "machineRate")
        labour += hours_per_part * _field(operation, "labourRate")
        electricity += hours_per_part * _field(operation, "energyRate")
        tooling += _field(operation, "tooling")
    extra_cost = sum(_field(extras, key) for key in ("cutting", "heat", "finishing", "inspection", "transport", "packaging"))
    direct = net_material + machine + labour + tooling + electricity + extra_cost
    overhead = direct * _field(extras, "overheadPct") / 100
    rejection = direct * _field(extras, "rejectionPct") / 100
    manufacturing = direct + overhead + rejection
    margin = min(99.99, max(0, _field(data, "margin"))) / 100
    pre_tax = manufacturing / (1 - margin)
    profit = pre_tax - manufacturing
    gst = pre_tax * _field(data, "gst") / 100
    unit_sell = pre_tax + gst
    return {
        "rawMaterialWeightKg": raw_weight,
        "finishedPartWeightKg": finished_weight,
        "finishedPartVolumeMm3": finished_volume_mm3,
        "scrapWeightKg": scrap_weight,
        "reusableScrapKg": reusable_weight,
        "recyclableScrapKg": recyclable_weight,
        "machiningWasteKg": machining_waste_weight,
        "scrapPercent": scrap_weight / raw_weight * 100 if raw_weight else 0,
        "materialUtilisationPercent": finished_weight / raw_weight * 100 if raw_weight else 0,
        "rawMaterialCost": raw_cost,
        "scrapCredit": credit,
        "netMaterialCost": net_material,
        "machineCost": machine,
        "labourCost": labour,
        "toolingCost": tooling,
        "electricityCost": electricity,
        "additionalCost": extra_cost,
        "manufacturingCost": manufacturing,
        "profitPerComponent": profit,
        "sellingPricePerComponent": unit_sell,
        "batchSellingPrice": unit_sell * quantity,
        "gst": gst,
    }


@app.post("/api/cad/analyse")
async def analyse_drawing(file: UploadFile = File(...)) -> dict[str, Any]:
    """Read ASCII or binary DXF and extract preview geometry without guessing solid volume."""
    extension = Path(file.filename or "").suffix.lower()
    if extension == ".dwg":
        raise HTTPException(status_code=501, detail="DWG conversion needs a configured conversion provider. Export ASCII DXF to continue.")
    if extension in (".step", ".stp"):
        raise HTTPException(status_code=501, detail="STEP solid analysis needs an Open CASCADE service. This endpoint does not estimate its geometry.")
    if extension == ".pdf":
        raise HTTPException(status_code=501, detail="PDF dimension recognition needs a configured drawing extraction service. Enter validated dimensions manually.")
    if extension != ".dxf":
        raise HTTPException(status_code=415, detail="Upload a DXF file for geometry analysis.")
    content = await file.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Maximum drawing size is 25 MB.")
    try:
        import ezdxf
        from ezdxf import recover
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Install ezdxf to enable server-side DXF analysis.") from exc

    # ezdxf.readfile detects ASCII versus binary DXF and the file's text encoding.
    # UploadFile is kept in memory up to the size limit above; the temporary file
    # is scoped to this request and removed on every exit path.
    with tempfile.TemporaryDirectory(prefix="shopquote-dxf-") as temp_dir:
        drawing_path = Path(temp_dir) / "drawing.dxf"
        drawing_path.write_bytes(content)
        try:
            document = ezdxf.readfile(drawing_path)
        except Exception as first_error:  # try ezdxf's repair reader for damaged files
            try:
                document, _auditor = recover.readfile(drawing_path)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"DXF could not be parsed: {exc or first_error}") from exc

    units_code = int(document.header.get("$INSUNITS", 0) or 0)
    unit = UNIT_MAP.get(units_code, "")
    entities: list[dict[str, Any]] = []
    coords: list[tuple[float, float, float]] = []
    closed_area = 0.0
    path_length = 0.0
    closed_count = open_count = circle_count = arc_count = line_count = 0
    solid_model_count = face_3d_count = 0
    has_3d = False
    parsed_types: Counter[str] = Counter()
    unsupported_types: Counter[str] = Counter()

    def xyz(point: Any) -> tuple[float, float, float]:
        try:
            return float(point.x), float(point.y), float(point.z)
        except AttributeError:
            return float(point[0]), float(point[1]), float(point[2])

    # Expand INSERTs, dimensions and other compound records into their visible
    # geometric children so drawings built from blocks are included.
    from ezdxf.disassemble import make_primitive, recursive_decompose

    for entity in recursive_decompose(document.modelspace()):
        kind = entity.dxftype()
        parsed_types[kind] += 1
        if kind == "LINE":
            start, end = entity.dxf.start, entity.dxf.end
            x1, y1, z1 = float(start.x), float(start.y), float(start.z)
            x2, y2, z2 = float(end.x), float(end.y), float(end.z)
            entities.append({"type": "LINE", "x1": x1, "y1": y1, "z1": z1, "x2": x2, "y2": y2, "z2": z2})
            coords.extend(((x1, y1, z1), (x2, y2, z2)))
            path_length += math.dist((x1, y1, z1), (x2, y2, z2))
            has_3d = has_3d or abs(z1) > 1e-9 or abs(z2) > 1e-9 or abs(z1 - z2) > 1e-9
            line_count += 1
        elif kind == "CIRCLE":
            center, radius = entity.dxf.center, float(entity.dxf.radius)
            x, y, z = float(center.x), float(center.y), float(center.z)
            entities.append({"type": "CIRCLE", "x": x, "y": y, "z": z, "r": radius})
            coords.extend(((x - radius, y - radius, z), (x + radius, y + radius, z)))
            has_3d = has_3d or abs(z) > 1e-9
            closed_area += math.pi * radius**2
            path_length += 2 * math.pi * radius
            closed_count += 1
            circle_count += 1
        elif kind == "ARC":
            center, radius = entity.dxf.center, float(entity.dxf.radius)
            start, end = float(entity.dxf.start_angle), float(entity.dxf.end_angle)
            x, y, z = float(center.x), float(center.y), float(center.z)
            entities.append({"type": "ARC", "x": x, "y": y, "z": z, "r": radius, "start": start, "end": end})
            has_3d = has_3d or abs(z) > 1e-9
            sweep = (end - start) % 360
            for angle in (start, end, 0, 90, 180, 270):
                delta = (angle - start) % 360
                if delta <= sweep + 1e-8:
                    radians = math.radians(angle)
                    coords.append((x + radius * math.cos(radians), y + radius * math.sin(radians), z))
            path_length += radius * math.radians(sweep)
            arc_count += 1
        elif kind == "LWPOLYLINE":
            elevation = float(entity.dxf.get("elevation", 0) or 0)
            vertices = [(float(x), float(y), float(bulge)) for x, y, bulge in entity.get_points("xyb")]
            closed = bool(entity.closed)
            if len(vertices) < 2:
                continue
            entities.append({"type": "POLY", "pts": [{"x": x, "y": y, "z": elevation, "bulge": b} for x, y, b in vertices], "closed": closed})
            coords.extend((x, y, elevation) for x, y, _ in vertices)
            has_3d = has_3d or abs(elevation) > 1e-9
            count = len(vertices) if closed else len(vertices) - 1
            area = 0.0
            for index in range(count):
                x1, y1, bulge = vertices[index]
                x2, y2, _ = vertices[(index + 1) % len(vertices)]
                chord = math.hypot(x2 - x1, y2 - y1)
                area += (x1 * y2 - x2 * y1) / 2
                if bulge and chord:
                    theta = 4 * math.atan(bulge)
                    radius = chord * (1 + bulge**2) / (4 * abs(bulge))
                    path_length += radius * abs(theta)
                    if closed:
                        area += radius**2 * (theta - math.sin(theta)) / 2
                    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                    dx, dy = x2 - x1, y2 - y1
                    offset = chord * (1 - bulge**2) / (4 * bulge)
                    cx, cy = mx - dy / chord * offset, my + dx / chord * offset
                    angle0 = math.atan2(y1 - cy, x1 - cx)
                    for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                        delta = (angle - angle0) % (2 * math.pi)
                        if (theta > 0 and delta <= theta + 1e-8) or (theta < 0 and delta >= 2 * math.pi + theta - 1e-8):
                            coords.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle), elevation))
                else:
                    path_length += chord
            if closed:
                closed_area += abs(area)
                closed_count += 1
            else:
                open_count += 1
        elif kind == "3DFACE":
            vertices = [(float(p.x), float(p.y), float(p.z)) for p in entity.wcs_vertices()]
            clean = []
            for point in vertices:
                if not clean or math.dist(point, clean[-1]) > 1e-9:
                    clean.append(point)
            if len(clean) >= 3:
                entities.append({"type": "FACE3", "pts": [{"x": x, "y": y, "z": z} for x, y, z in clean], "closed": True})
                coords.extend(clean)
                face_3d_count += 1
                has_3d = True
        elif kind == "MESH":
            mesh_vertices = [xyz(point) for point in entity.vertices]
            coords.extend(mesh_vertices)
            for face in entity.faces:
                face_points = [mesh_vertices[index] for index in face if 0 <= index < len(mesh_vertices)]
                if len(face_points) >= 3:
                    entities.append({"type": "FACE3", "pts": [{"x": x, "y": y, "z": z} for x, y, z in face_points], "closed": True})
                    face_3d_count += 1
            if mesh_vertices:
                solid_model_count += 1
                has_3d = True
        elif kind in ("3DSOLID", "BODY", "REGION", "SURFACE"):
            solid_model_count += 1
            has_3d = True
        else:
            # Convert supported curves and surfaces (for example SPLINE,
            # ELLIPSE, HATCH, MESH and 3D POLYLINE) to a bounded preview.
            try:
                primitive = make_primitive(entity, max_flattening_distance=0.1)
                path = primitive.path
                if path is not None:
                    sub_paths = path.sub_paths() if path.has_sub_paths else (path,)
                    for sub_path in sub_paths:
                        points = list(sub_path.flattening(distance=0.1, segments=8))
                        if len(points) < 2:
                            continue
                        pts = [{"x": float(p.x), "y": float(p.y), "z": float(p.z), "bulge": 0.0} for p in points]
                        closed = bool(sub_path.is_closed)
                        path_type = "POLY3" if any(abs(p["z"]) > 1e-9 for p in pts) else "POLY"
                        entities.append({"type": path_type, "pts": pts, "closed": closed, "sourceType": kind})
                        coords.extend((p["x"], p["y"], p["z"]) for p in pts)
                        has_3d = has_3d or path_type == "POLY3"
                        count = len(pts) if closed else len(pts) - 1
                        for index in range(count):
                            a, b = pts[index], pts[(index + 1) % len(pts)]
                            path_length += math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
                        if closed:
                            closed_count += 1
                            if path_type == "POLY":
                                closed_area += abs(sum(
                                    pts[i]["x"] * pts[(i + 1) % len(pts)]["y"]
                                    - pts[(i + 1) % len(pts)]["x"] * pts[i]["y"]
                                    for i in range(len(pts))
                                ) / 2)
                        else:
                            open_count += 1
                    continue
                mesh = primitive.mesh
                if mesh is not None:
                    mesh_vertices = list(mesh.vertices)
                    coords.extend(xyz(p) for p in mesh_vertices)
                    if mesh_vertices:
                        solid_model_count += 1
                        has_3d = True
                    continue
            except Exception:
                # A malformed or application-specific entity should not prevent
                # the rest of the drawing from being analysed.
                pass
            unsupported_types[kind] += 1

    if not coords and not solid_model_count:
        unsupported = ", ".join(sorted(unsupported_types)) or "none"
        raise HTTPException(status_code=422, detail=f"No measurable geometry was found in modelspace. Unhandled entity types: {unsupported}.")
    bounds = None
    z_height = None
    if coords:
        x_values, y_values, z_values = ([p[i] for p in coords] for i in range(3))
        bounds = {"minX": min(x_values), "maxX": max(x_values), "minY": min(y_values), "maxY": max(y_values), "minZ": min(z_values), "maxZ": max(z_values)}
        z_height = bounds["maxZ"] - bounds["minZ"]
    else:
        # ACIS solids may not expose faces to ezdxf, but some CAD exporters put
        # an overall envelope in the DXF header. Use it only as a bounding box.
        try:
            ext_min = document.header.get("$EXTMIN")
            ext_max = document.header.get("$EXTMAX")
            if ext_min is not None and ext_max is not None:
                bounds = {"minX": float(ext_min.x), "maxX": float(ext_max.x), "minY": float(ext_min.y), "maxY": float(ext_max.y), "minZ": float(ext_min.z), "maxZ": float(ext_max.z)}
                z_height = bounds["maxZ"] - bounds["minZ"]
        except (AttributeError, TypeError, ValueError):
            pass
    return {
        "fileName": file.filename,
        "format": "DXF",
        "units": unit,
        "unitCode": units_code,
        "bounds": bounds,
        "boundsSource": "entities" if coords else "header-extents" if bounds else "none",
        "has3D": has_3d,
        "zHeight": z_height,
        "solidModelCount": solid_model_count,
        "threeDFaceCount": face_3d_count,
        "closedArea": closed_area,
        "pathLength": path_length,
        "closedCount": closed_count,
        "openCount": open_count,
        "circleCount": circle_count,
        "arcCount": arc_count,
        "lineCount": line_count,
        "entityCount": len(entities) + solid_model_count,
        "entities": entities,
        "parsedTypes": sorted(parsed_types),
        "unsupportedTypes": sorted(unsupported_types),
        "areaNote": "Curves outside LINE/CIRCLE/ARC/LWPOLYLINE are approximated for preview. Closed 2D areas are summed; nested contours, holes and overlaps need review. ACIS solids and proxy objects do not provide extracted volume.",
    }


class ShopQuoteFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]):
        lowered = path.lower()
        if path.startswith(("backend/", ".")) or lowered.endswith((".db", ".sqlite", ".sqlite3")):
            raise StarletteHTTPException(status_code=404)
        return await super().get_response(path, scope)


app.mount("/", ShopQuoteFiles(directory=ROOT, html=True), name="shopquote-ui")
