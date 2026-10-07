"""
=====================================================================================
 ADAPTADOR DE MODELOS GRATUITOS (CC0/CC-BY) -> ASSETS DESTRUCTIBLES PARA UNITY
=====================================================================================
Convierte los modelos descargados con fetch_free_assets.py (Sketchfab, Poly Pizza,
URLs directas) al mismo pipeline que generate_destructible_assets.py:

  - importa .glb / .gltf / .fbx / .obj y hornea la jerarquia en espacio mundo
  - escala a la MEDIDA REAL (longitud de la ficha) y orienta el frente a -Y (= +Z Unity)
  - detecta piezas por nombre: torreta, canon, ruedas, orugas, rotores, cristales,
    puertas, cola, alas... -> piezas desmontables con pivote y eje (dst_pivot/dst_axis)
  - conserva UV y texturas originales (se embeben en el FBX); los cortes usan los
    materiales interiores del generador (acero, hormigon, astillas...)
  - mallas cerradas -> Voronoi solido; mallas abiertas -> fractura de cascara con
    espesor (placas de blindaje, chapas, paredes de una sola cara)
  - estados Intact / Damaged / Destroyed, Chunks, Debris, LODs, manifiesto JSON
  - atribucion de la licencia dentro del FBX (dst_title/dst_author/dst_license/dst_source)

 Uso:  blender --background --python adapt_free_assets.py -- [--in ThirdParty]
                 [--out ~/Unity_Destructible_Military] [--only tank,heli] [--variants Temperate,Winter]
 Ajustes por modelo (opcional): adapt_overrides.json
   {"sketchfab_<uid>": {"length": 9.5, "rot_z": 90, "forward": "+X", "skip": ["base"], "kind": "structure"}}
=====================================================================================
"""
import bpy
import bmesh
import json
import math
import os
import re
import sys
import traceback
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generate_destructible_assets as G      # noqa: E402  (mismo pipeline de destruccion)

# nombre de objeto/material -> tipo de pieza
PART_RULES = [
    (r"turret|tower|bashnya|cupola", "turret"),
    (r"gun|barrel|cannon|canon|muzzle|mantlet|autocannon|launcher", "gun"),
    (r"wheel|tire|tyre|rim\b|roadwheel|road_wheel|sprocket|idler", "wheel"),
    (r"track|tread|caterpillar|gusenic", "track"),
    (r"rotor|blade|propel|airscrew|prop_|_prop\b", "rotor"),
    (r"glass|window|windshield|windscreen|canopy|cockpit_glass|lens|visor", "glass"),
    (r"door|hatch|ramp|lid\b", "door"),
    (r"tail|boom", "tail"),
    (r"wing|stabili|aileron|flap", "wing"),
    (r"antenna|mirror|lamp|light|headlight|rack|tool|jerrycan|spare|net\b", "detail"),
]
# nombre -> clase fisica/destructiva del generador
CLASS_RULES = [
    (r"glass|window|windshield|canopy|lens", "glass"), (r"tire|tyre|rubber", "rubber"),
    (r"concrete|cement|beton", "concrete"), (r"brick", "brick"), (r"plaster|stucco", "plaster"),
    (r"wood|plank|log\b|timber|crate", "wood"), (r"sand ?bag|sack|canvas|fabric|cloth|tent|tarp|net", "fabric"),
    (r"rock|stone|boulder", "rock"), (r"leaf|leaves|foliage|grass|bush", "foliage"), (r"dirt|soil|earth|ground|mud", "earth"),
    (r"metal|steel|iron|rust|armor|armour|hull|tank|barrel", "metal"),
]
SKIP_RULES = r"ground|plane\b|floor_plane|terrain|backdrop|plinth|pedestal|display|stand\b|turntable|shadow|collider|collision|lod[1-9]"
GROUP_MASS = {"tank": 55000, "ifv": 25000, "apc": 15000, "light": 6000, "truck": 9000, "artillery": 25000, "aa": 25000,
              "heli": 8000, "jet": 15000, "drone": 150, "weapon": 6, "prop": 40, "fort": 800, "camp": 1200, "env": 0, "char": 85}


def slug(s, n=32):
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")[:n] or "asset"


def classify(name, rules, default):
    n = name.lower()
    for rx, k in rules:
        if re.search(rx, n):
            return k
    return default


def find_model(folder):
    order = (".glb", ".gltf", ".fbx", ".obj")
    found = []
    for root, _d, files in os.walk(folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in order:
                found.append((order.index(ext), -os.path.getsize(os.path.join(root, f)), os.path.join(root, f)))
    return sorted(found)[0][2] if found else None


def import_model(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def _sub_bmesh(src, faces):
    """Extrae caras a una bmesh nueva conservando UV y sombreado."""
    uv_s = src.loops.layers.uv.active
    dst = bmesh.new()
    uv_d = dst.loops.layers.uv.new("UVMap") if uv_s else None
    vm = {}
    for f in faces:
        vs = []
        for v in f.verts:
            if v not in vm:
                vm[v] = dst.verts.new(v.co)
            vs.append(vm[v])
        try:
            nf = dst.faces.new(vs)
        except ValueError:
            continue
        nf.smooth = f.smooth
        if uv_s:
            for a, b in zip(f.loops, nf.loops):
                b[uv_d].uv = a[uv_s].uv
    bmesh.ops.remove_doubles(dst, verts=dst.verts[:], dist=1e-5)
    dst.normal_update()
    return dst


def closed(bm):
    return bool(bm.edges) and all(e.is_manifold for e in bm.edges)


def collect_pieces(objs, meta, prefix, ov):
    """Objetos importados -> [(nombre_obj, tipo, Piece)] en espacio mundo, un Piece por material."""
    kind_asset = ov.get("kind", meta.get("kind", "structure"))
    skip_rx = SKIP_RULES if kind_asset != "structure" else r"collider|collision|shadow|lod[1-9]"
    if ov.get("skip"):
        skip_rx += "|" + "|".join(ov["skip"])
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    renamed = {}
    for ob in objs:
        if ob.type != 'MESH' or re.search(skip_rx, ob.name.lower()):
            continue
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(ob.matrix_world)
        if ob.matrix_world.determinant() < 0:
            me.flip_normals()
        bm = bmesh.new()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        slots = [s.material for s in ob.material_slots]
        by_mat = {}
        for f in bm.faces:
            by_mat.setdefault(f.material_index, []).append(f)
        for mi, faces in by_mat.items():
            mat = slots[mi] if mi < len(slots) else None
            if mat is not None and mat.name not in renamed:
                if not mat.name.startswith("Ext_"):
                    mat.name = ("Ext_%s_%s" % (prefix, slug(mat.name, 20)))[:60]
                renamed[mat.name] = True
            mname = mat.name if mat is not None else "Mat_Metal_Steel"
            label = "%s %s" % (ob.name, mname)
            pkind = classify(label, PART_RULES, "hull" if kind_asset == "vehicle" else "element")
            default_cls = {"vehicle": "metal", "weapon": "metal", "prop": "metal", "character": "fabric"}.get(kind_asset, "concrete")
            cls = classify(label, CLASS_RULES, default_cls)
            if pkind == "glass":
                cls = "glass"
            sub = _sub_bmesh(bm, faces)
            if not sub.faces:
                continue
            pc = G.Piece(sub, mname, cls, None, True, "" if closed(sub) else "shell")
            out.append((ob.name, pkind, pc))
        bm.free()
    return out, kind_asset


def bounds_of(pcs):
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for pc in pcs:
        a, b = pc.bounds()
        lo = Vector(map(min, lo, a))
        hi = Vector(map(max, hi, b))
    return lo, hi


def thin_end_forward(pcs, group):
    """Sin nombres utiles: el extremo 'fino' (12% final) es el canon en blindados/aviones
    y la cola en helicopteros. Devuelve '+Y' o '-Y' (lado del frente) o None."""
    front_thin = group in ("tank", "ifv", "artillery", "aa", "jet", "weapon")
    if not front_thin and group != "heli":
        return None
    vs = [v.co for pc in pcs for v in pc.bm.verts]
    if not vs:
        return None
    ys = [v.y for v in vs]
    lo, hi = min(ys), max(ys)
    L = hi - lo

    def area(sel):
        if not sel:
            return 0.0
        return (max(v.x for v in sel) - min(v.x for v in sel)) * (max(v.z for v in sel) - min(v.z for v in sel))
    a_pos = area([v for v in vs if v.y > hi - 0.12 * L])
    a_neg = area([v for v in vs if v.y < lo + 0.12 * L])
    thin_pos = a_pos < a_neg
    return ("+Y" if thin_pos else "-Y") if front_thin else ("-Y" if thin_pos else "+Y")


def normalize(items, kind_asset, meta, ov):
    """Escala a la medida real y orienta el frente hacia -Y."""
    pcs = [pc for _n, _k, pc in items]
    lo, hi = bounds_of(pcs)
    size = hi - lo
    c = (lo + hi) * 0.5
    T = Matrix.Translation(-Vector((c.x, c.y, lo.z)))
    target = float(ov.get("length", meta.get("length") or 0) or 0)
    measured = size.z if kind_asset == "character" else max(size.x, size.y)
    s = ov.get("scale") or ((target / measured) if target > 0 and measured > 1e-6 else 1.0)
    R = Matrix.Identity(4)
    if "rot_z" in ov:
        R = Matrix.Rotation(math.radians(ov["rot_z"]), 4, 'Z')
    elif kind_asset in ("vehicle", "weapon") and size.x > size.y * 1.05:
        R = Matrix.Rotation(math.radians(90), 4, 'Z')                      # eje largo -> Y
    M = R @ Matrix.Diagonal((s, s, s, 1.0)) @ T
    for pc in pcs:
        pc.transform(M)
    fw = ov.get("forward")
    if fw is None and kind_asset in ("vehicle", "weapon"):                 # frente = donde apunta el canon / cabina
        cue = [pc for _n, k, pc in items if k in ("gun", "glass")]
        if cue:
            cy = sum(pc.center().y for pc in cue) / len(cue)
            fw = "+Y" if cy > 0.05 * max(size.x, size.y) * s else "-Y"
        else:
            fw = thin_end_forward(pcs, meta.get("group", ""))
    if fw in ("+Y",):
        F = Matrix.Rotation(math.pi, 4, 'Z')
        for pc in pcs:
            pc.transform(F)
    return s


def make_parts(items, kind_asset):
    """Agrupa por tipo: piezas articuladas por objeto, el resto fusionado por tipo."""
    groups = {}
    for oname, k, pc in items:
        key = (k, oname) if k in ("turret", "gun", "wheel", "rotor", "door", "track", "tail", "wing") else (k, "_all")
        groups.setdefault(key, []).append(pc)
    if sum(1 for (k, o) in groups if o != "_all") > 48:                 # demasiadas: fusionar por tipo
        merged = {}
        for (k, o), v in groups.items():
            merged.setdefault((k, "_all"), []).extend(v)
        groups = merged
    parts, used = [], set()
    for (k, oname), pcs in sorted(groups.items(), key=lambda kv: kv[0]):
        nm = slug("%s_%s" % (k.title(), "" if oname == "_all" else oname), 40)
        while nm in used:
            nm += "_x"
        used.add(nm)
        lo, hi = bounds_of(pcs)
        c = (lo + hi) * 0.5
        kw = {}
        if k == "turret":
            kw = dict(pivot=(c.x, c.y, lo.z), axis=(0, 0, 1), joint="yaw", tags=("turret",))
        elif k == "gun":
            kw = dict(pivot=(c.x, hi.y, c.z), axis=(1, 0, 0), joint="pitch", tags=("turret",))
        elif k == "wheel":
            kw = dict(pivot=tuple(c), axis=(1, 0, 0), joint="wheel")
        elif k == "rotor":
            d = hi - lo
            kw = dict(pivot=tuple(c), axis=(0, 0, 1) if d.z < 0.3 * max(d.x, d.y) else (1, 0, 0), joint="spin")
        elif k == "door":
            kw = dict(pivot=tuple(c), axis=(0, 0, 1), joint="hinge")
        elif k in ("tail", "wing"):
            kw = dict(pivot=(c.x * 0.2, c.y * 0.2, c.z), axis=(0, 1, 0) if k == "tail" else (1, 0, 0), joint="break")
        if kind_asset != "vehicle" and k not in ("glass", "door"):
            k = "element"
        parts.append(G.Part(nm, pcs, pcs[0].cls, kind=k, **kw))
    return parts


def adapt(meta, inp, ov):
    folder = os.path.join(inp, meta["folder"])
    path = find_model(folder)
    if not path:
        raise RuntimeError("sin modelo importable en " + folder)
    G.reset_scene()
    prefix = slug(meta["id"].split("_", 1)[-1], 10)
    objs = import_model(path)
    items, kind_asset = collect_pieces(objs, meta, prefix, ov)
    for ob in objs:
        bpy.data.objects.remove(ob, do_unlink=True)
    if not items:
        raise RuntimeError("sin mallas utiles")
    s = normalize(items, kind_asset, meta, ov)
    parts = make_parts(items, kind_asset)
    name = "TP_%s_%s" % (slug(meta.get("title"), 28), slug(meta["id"].split("_", 1)[-1], 8))
    cat = "ThirdParty_" + meta.get("category", "Misc")
    credits = {k: meta.get(k, "") for k in ("title", "author", "license", "source", "query")}
    credits["scale_applied"] = round(s, 5)
    common = dict(credits=credits, embed_textures=True, ref="%s - %s (%s)" % (meta.get("title"), meta.get("author"), meta.get("license")),
                  lod=(1.0, 0.5, 0.2))
    mass = meta.get("mass") or GROUP_MASS.get(meta.get("group", ""), 0) or None
    if kind_asset == "vehicle":
        return G.Asset(name, cat, "vehicle", parts, mass=mass, **common)
    if kind_asset == "character":
        return G.Asset(name, cat, "static", parts, **common)
    small = kind_asset in ("weapon", "prop")
    lo, hi = bounds_of([pc for p in parts for pc in p.pieces])
    big = max((hi - lo).x, (hi - lo).y, (hi - lo).z)
    return G.Asset(name, cat, "structure", parts, n_impacts=1 if small else 2, dmg_r=max(0.12, big * 0.18),
                   ruin_h=0.3, spread=0.5 if small else 0.3, rubble_cell=max(1.0, big / 4), chunk_scale=0.6 if small else 0.9,
                   debris=parts[0].cls, mass=mass, **common)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(HERE, "ThirdParty"))
    ap.add_argument("--out", default=os.path.join(os.path.expanduser("~"), "Unity_Destructible_Military"))
    ap.add_argument("--only", default="")
    ap.add_argument("--variants", default="Temperate")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = ap.parse_args(argv)
    only = [o.strip().lower() for o in a.only.split(",") if o.strip()]
    G.OUTPUT_DIR = os.path.abspath(os.path.expanduser(a.out))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    G.reset_scene()
    cat_path = os.path.join(a.inp, "third_party_catalog.json")
    catalog = json.load(open(cat_path, encoding="utf-8"))
    ovp = os.path.join(HERE, "adapt_overrides.json")
    overrides = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    done, fails = [], []
    for meta in catalog:
        if meta.get("kind") == "texture":
            continue
        key = " ".join(str(meta.get(k, "")) for k in ("title", "group", "query", "category")).lower()
        if only and not any(o in key for o in only):
            continue
        for var in [v.strip() for v in a.variants.split(",") if v.strip()]:
            G.VARIANT = var
            try:
                asset = adapt(meta, a.inp, overrides.get(meta["id"], {}))
                if var != "Temperate":
                    asset.name += "_" + var
                info = G.process_asset(asset)
                info.update(variant=var, license=meta.get("license"), author=meta.get("author"), source=meta.get("source"))
                done.append(info)
            except Exception as exc:
                traceback.print_exc()
                fails.append({"id": meta.get("id"), "variant": var, "error": str(exc)})
    G.VARIANT = "Temperate"
    os.makedirs(G.OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(G.OUTPUT_DIR, "third_party_adapted.json"), "w", encoding="utf-8") as fh:
        json.dump({"assets": done, "failed": fails}, fh, indent=1, ensure_ascii=False)
    cred = os.path.join(a.inp, "CREDITS.md")
    if os.path.exists(cred):
        import shutil
        shutil.copyfile(cred, os.path.join(G.OUTPUT_DIR, "CREDITS_ThirdParty.md"))
    print("\n=== %d assets de terceros adaptados (fallidos: %d) -> %s ===" % (len(done), len(fails), G.OUTPUT_DIR))


if __name__ == "__main__":
    main()
