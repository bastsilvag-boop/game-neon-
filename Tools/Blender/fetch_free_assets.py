"""
=====================================================================================
 FREE MODERN-WARFARE ASSET FETCHER  (solo licencias libres: CC0 / CC-BY)
=====================================================================================
Busca y descarga modelos 3D GRATUITOS de guerra moderna y texturas PBR fotoescaneadas,
verificando la licencia de cada uno y registrando la atribucion. Despues ejecuta
adapt_free_assets.py en Blender para convertirlos en assets destructibles para Unity.

 Fuentes (todas gratuitas):
  sketchfab  miles de modelos CC-BY/CC0 (tanques, IFV, helicopteros, armas, edificios).
             Necesita tu token personal gratuito: https://sketchfab.com/settings/password
             ->  set SKETCHFAB_TOKEN=xxxxx   (Windows)   export SKETCHFAB_TOKEN=xxxxx (Linux/Mac)
  polypizza  low-poly CC0/CC-BY (Quaternius, Kenney, Google Poly). Key gratuita:
             https://poly.pizza/settings/api  ->  POLYPIZZA_KEY=xxxxx
  ambientcg  texturas PBR fotoescaneadas CC0 (ladrillo, hormigon, arena, nieve, metal...)
             sin key; el generador las usa automaticamente en lugar de las procedurales.
  direct     URLs directas con licencia conocida (direct_assets.json o la lista DIRECT).

 Uso:   python fetch_free_assets.py                       (todas las fuentes con key)
        python fetch_free_assets.py --sources ambientcg   (solo texturas)
        python fetch_free_assets.py --per-query 3 --max-faces 120000 --only tank,heli
 Salida: ThirdParty/<fuente>/<id>/...  +  ThirdParty/third_party_catalog.json
         + ThirdParty/CREDITS.md (atribuciones obligatorias para CC-BY: incluyelas en
           los creditos del juego).
 Python 3.8+, solo libreria estandar (tambien funciona con el Python de Blender).
=====================================================================================
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

UA = "UnityDestructibleMilitaryFactory/3.0 (asset fetcher; contact: project owner)"
ALLOWED = ("cc0", "cc-by", "by", "public-domain", "cc0-1.0", "cc-by-3.0", "cc-by-4.0")
SHARE_ALIKE = ("by-sa", "cc-by-sa", "cc-by-sa-3.0", "cc-by-sa-4.0")
BANNED_WORDS = ("lego", "toy", "cartoon", "chibi", "minecraft", "funko", "papercraft", "kids", "anime")

# (consulta, categoria, tipo de destruccion, longitud real mayor en metros, grupo)
QUERIES = [
    # --- carros de combate
    ("M1A2 Abrams tank", "Vehicles", "vehicle", 9.77, "tank"), ("Leopard 2A6 tank", "Vehicles", "vehicle", 10.97, "tank"),
    ("T-72 tank", "Vehicles", "vehicle", 9.53, "tank"), ("T-90 tank", "Vehicles", "vehicle", 9.63, "tank"),
    ("T-80 tank", "Vehicles", "vehicle", 9.65, "tank"), ("Challenger 2 tank", "Vehicles", "vehicle", 11.55, "tank"),
    ("Merkava tank", "Vehicles", "vehicle", 9.04, "tank"),
    # --- IFV / APC / ruedas
    ("BMP-2", "Vehicles", "vehicle", 6.74, "ifv"), ("BMP-3", "Vehicles", "vehicle", 7.14, "ifv"),
    ("M2 Bradley", "Vehicles", "vehicle", 6.55, "ifv"), ("CV90", "Vehicles", "vehicle", 6.47, "ifv"),
    ("BTR-80", "Vehicles", "vehicle", 7.65, "apc"), ("BTR-82A", "Vehicles", "vehicle", 7.65, "apc"),
    ("Stryker", "Vehicles", "vehicle", 6.95, "apc"), ("M113", "Vehicles", "vehicle", 4.86, "apc"),
    ("MT-LB", "Vehicles", "vehicle", 6.45, "apc"), ("Humvee", "Vehicles", "vehicle", 4.93, "light"),
    ("MRAP", "Vehicles", "vehicle", 6.27, "light"), ("GAZ Tigr", "Vehicles", "vehicle", 5.7, "light"),
    ("Toyota technical", "Vehicles", "vehicle", 5.3, "light"), ("Ural 4320 truck", "Vehicles", "vehicle", 7.37, "truck"),
    ("KamAZ military truck", "Vehicles", "vehicle", 7.9, "truck"), ("M35 truck", "Vehicles", "vehicle", 6.71, "truck"),
    # --- artilleria / defensa aerea
    ("HIMARS", "Artillery", "vehicle", 7.0, "artillery"), ("BM-21 Grad", "Artillery", "vehicle", 7.35, "artillery"),
    ("M109 howitzer", "Artillery", "vehicle", 9.7, "artillery"), ("2S19 Msta", "Artillery", "vehicle", 11.92, "artillery"),
    ("M777 howitzer", "Artillery", "vehicle", 10.7, "artillery"), ("D-30 howitzer", "Artillery", "vehicle", 8.0, "artillery"),
    ("ZSU-23-4 Shilka", "AirDefense", "vehicle", 6.54, "aa"), ("Pantsir", "AirDefense", "vehicle", 9.7, "aa"),
    ("Patriot missile launcher", "AirDefense", "vehicle", 10.0, "aa"), ("S-300 launcher", "AirDefense", "vehicle", 11.0, "aa"),
    ("ZU-23-2", "AirDefense", "vehicle", 4.57, "aa"),
    # --- aeronaves y drones
    ("AH-64 Apache", "Aircraft", "vehicle", 17.73, "heli"), ("UH-60 Black Hawk", "Aircraft", "vehicle", 19.76, "heli"),
    ("Mi-24 Hind", "Aircraft", "vehicle", 21.35, "heli"), ("Mi-8 helicopter", "Aircraft", "vehicle", 25.3, "heli"),
    ("Ka-52", "Aircraft", "vehicle", 15.96, "heli"), ("CH-47 Chinook", "Aircraft", "vehicle", 30.1, "heli"),
    ("F-16", "Aircraft", "vehicle", 15.06, "jet"), ("F-35", "Aircraft", "vehicle", 15.7, "jet"),
    ("Su-25", "Aircraft", "vehicle", 15.53, "jet"), ("A-10 Warthog", "Aircraft", "vehicle", 16.26, "jet"),
    ("MiG-29", "Aircraft", "vehicle", 17.32, "jet"), ("C-130 Hercules", "Aircraft", "vehicle", 29.8, "jet"),
    ("Bayraktar TB2", "Aircraft", "vehicle", 12.0, "drone"), ("MQ-9 Reaper", "Aircraft", "vehicle", 20.1, "drone"),
    ("Shahed 136", "Aircraft", "vehicle", 3.5, "drone"), ("FPV drone", "Aircraft", "vehicle", 0.3, "drone"),
    ("quadcopter drone", "Aircraft", "vehicle", 0.35, "drone"),
    # --- armas de infanteria (props)
    ("AK-74", "Weapons", "weapon", 0.943, "weapon"), ("AKM rifle", "Weapons", "weapon", 0.88, "weapon"),
    ("M4 carbine", "Weapons", "weapon", 0.84, "weapon"), ("M249 SAW", "Weapons", "weapon", 1.04, "weapon"),
    ("PKM machine gun", "Weapons", "weapon", 1.19, "weapon"), ("RPG-7", "Weapons", "weapon", 0.95, "weapon"),
    ("Javelin launcher", "Weapons", "weapon", 1.2, "weapon"), ("NLAW", "Weapons", "weapon", 1.02, "weapon"),
    ("Stinger MANPADS", "Weapons", "weapon", 1.52, "weapon"), ("SVD Dragunov", "Weapons", "weapon", 1.22, "weapon"),
    ("Barrett M82", "Weapons", "weapon", 1.45, "weapon"), ("M2 Browning", "Weapons", "weapon", 1.65, "weapon"),
    ("DShK", "Weapons", "weapon", 1.63, "weapon"), ("81mm mortar", "Weapons", "weapon", 1.4, "weapon"),
    ("hand grenade", "Weapons", "weapon", 0.11, "weapon"), ("anti-tank mine", "Weapons", "weapon", 0.32, "weapon"),
    ("military radio", "Props", "prop", 0.35, "prop"),
    # --- fortificacion y props
    ("sandbags", "Military", "structure", 3.0, "fort"), ("hesco barrier", "Military", "structure", 3.2, "fort"),
    ("jersey barrier", "Military", "structure", 3.0, "fort"), ("czech hedgehog", "Military", "structure", 2.0, "fort"),
    ("dragon teeth anti tank", "Military", "structure", 1.2, "fort"), ("military bunker", "Military", "structure", 6.0, "fort"),
    ("trench", "Fortifications", "structure", 10.0, "fort"), ("military tent", "Military", "structure", 6.0, "camp"),
    ("military checkpoint", "Military", "structure", 8.0, "camp"), ("watchtower military", "Military", "structure", 6.0, "camp"),
    ("ammo box", "Props", "structure", 0.45, "prop"), ("ammo crate", "Props", "structure", 0.9, "prop"),
    ("jerry can", "Props", "structure", 0.47, "prop"), ("oil barrel", "Props", "structure", 0.88, "prop"),
    ("shipping container", "Props", "structure", 6.06, "prop"), ("pallet", "Props", "structure", 1.2, "prop"),
    ("barbed wire", "Military", "structure", 3.0, "fort"), ("camouflage net", "Military", "structure", 8.0, "camp"),
    ("military radar", "AirDefense", "structure", 6.0, "camp"), ("generator military", "Props", "structure", 2.0, "prop"),
    # --- entorno de guerra
    ("ruined building", "Buildings", "structure", 15.0, "env"), ("destroyed house", "Buildings", "structure", 12.0, "env"),
    ("soviet apartment block", "Buildings", "structure", 60.0, "env"), ("middle east house", "Buildings", "structure", 12.0, "env"),
    ("burnt car", "Civilian", "vehicle", 4.5, "env"), ("destroyed tank", "Vehicles", "structure", 9.5, "env"),
    ("rubble pile", "Terrain", "structure", 5.0, "env"), ("bomb crater", "Terrain", "structure", 8.0, "env"),
    # --- personajes (sin destruccion; normalizados a 1.8 m)
    ("modern soldier rigged", "Characters", "character", 1.8, "char"),
]

# Material del generador -> busqueda en ambientCG (texturas fotoescaneadas CC0)
AMBIENTCG = {
    "Mat_Concrete_Base": "Concrete", "Mat_Concrete_Interior": "Concrete rough", "Mat_Brick_Wall": "Bricks",
    "Mat_Brick_Interior": "Bricks", "Mat_Mudbrick": "Bricks adobe", "Mat_CinderBlock": "Concrete blocks",
    "Mat_Plaster_Wall": "Plaster", "Mat_Plaster_Desert": "Plaster", "Mat_Roof_Tile": "Roofing tiles",
    "Mat_Roof_Metal": "Corrugated steel", "Mat_Wood_Plank": "Planks", "Mat_Wood_Beam": "Wood",
    "Mat_Terrain_Grass": "Grass", "Mat_Terrain_Soil": "Ground", "Mat_Terrain_Sand": "Sand", "Mat_Terrain_Snow": "Snow",
    "Mat_Snow": "Snow", "Mat_Rock_Base": "Rock", "Mat_Bark_Oak": "Bark", "Mat_Bark_Pine": "Bark",
    "Mat_Metal_Steel": "Metal", "Mat_Metal_Gunmetal": "Painted metal", "Mat_Track_Steel": "Metal plates",
    "Mat_Rebar_Rust": "Rust", "Mat_Fabric_Sandbag": "Fabric", "Mat_Fabric_Canvas": "Fabric", "Mat_Rubber_Tire": "Rubber",
}

DIRECT = [
    # Ejemplo verificable (CC-BY 4.0, Cesium): camion logistico con ruedas separadas.
    dict(id="khronos_cesium_milk_truck", title="Cesium Milk Truck", author="Cesium (Analytical Graphics)",
         license="CC-BY-4.0", source="https://github.com/KhronosGroup/glTF-Sample-Models/tree/master/2.0/CesiumMilkTruck",
         url="https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Models/master/2.0/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb",
         category="Civilian", kind="vehicle", length=6.0, group="truck"),
]


# ----------------------------------------------------------------------------------
def http(url, headers=None, data=None, timeout=60, retries=3):
    h = {"User-Agent": UA}
    h.update(headers or {})
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise
            last = e
        except Exception as e:                      # red intermitente: reintento con espera
            last = e
        time.sleep(2 ** (i + 1))
    raise last


def jget(url, headers=None):
    return json.loads(http(url, headers).decode("utf-8"))


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:48] or "asset"


def lic_ok(lic, allow_sa):
    """Solo CC0 / dominio publico / CC-BY (y CC-BY-SA con --allow-sa). Nunca NC, ND ni editorial."""
    l = (lic or "").strip().lower().replace(" ", "-").replace("_", "-")
    l = l.replace("creative-commons-", "cc-").replace("attribution", "by")
    parts = set(re.split(r"[-.]", l))
    if parts & {"nc", "nd", "noncommercial", "noderivatives", "noderivs"} or l in ("ed", "st", "editorial", "standard", "free-standard"):
        return False
    if l.startswith("cc0") or "public-domain" in l or "publicdomain" in l:
        return True
    if "sa" in parts or "sharealike" in parts:
        return allow_sa
    return l == "by" or l.startswith("cc-by") or l.startswith("by-") or l.startswith("ccby")


def banned(title):
    t = (title or "").lower()
    return any(w in t for w in BANNED_WORDS)


def save_payload(data, folder, fname):
    os.makedirs(folder, exist_ok=True)
    if fname.lower().endswith(".zip") or data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for m in z.infolist():
                p = os.path.normpath(os.path.join(folder, m.filename))
                if not p.startswith(os.path.normpath(folder)):      # zip-slip
                    continue
                if m.is_dir():
                    os.makedirs(p, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    with open(p, "wb") as fh:
                        fh.write(z.read(m))
    else:
        with open(os.path.join(folder, fname), "wb") as fh:
            fh.write(data)


def write_meta(folder, meta):
    with open(os.path.join(folder, "asset_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(folder, "LICENSE.txt"), "w", encoding="utf-8") as fh:
        fh.write("%s\nAutor: %s\nLicencia: %s\nFuente: %s\n" % (meta["title"], meta["author"], meta["license"], meta["source"]))


# ----------------------------------------------------------------------------------
def fetch_sketchfab(args, out, catalog):
    tok = os.environ.get("SKETCHFAB_TOKEN")
    if not tok:
        print("[sketchfab] sin SKETCHFAB_TOKEN: omitido (token gratuito en sketchfab.com/settings/password)")
        return
    auth = {"Authorization": "Token " + tok}
    for q, cat, kind, length, group in QUERIES:
        if args.only and group not in args.only and not any(o in q.lower() for o in args.only):
            continue
        found = []
        for lic in ("cc0", "by") + (("by-sa",) if args.allow_sa else ()):
            url = "https://api.sketchfab.com/v3/search?" + urllib.parse.urlencode(dict(
                type="models", q=q, downloadable="true", license=lic, max_face_count=args.max_faces,
                sort_by="-likeCount", count=24))
            try:
                found += jget(url).get("results", [])
            except Exception as e:
                print("  [sketchfab] busqueda fallo '%s': %s" % (q, e))
        found = [r for r in found if not banned(r.get("name"))]
        found.sort(key=lambda r: -(r.get("likeCount") or 0))
        got = 0
        for r in found:
            if got >= args.per_query:
                break
            uid = r["uid"]
            folder = os.path.join(out, "sketchfab", "%s_%s" % (slug(r.get("name", "")), uid[:8]))
            if os.path.exists(os.path.join(folder, "asset_meta.json")):
                catalog.append(json.load(open(os.path.join(folder, "asset_meta.json"), encoding="utf-8")))
                got += 1
                continue
            try:
                info = jget("https://api.sketchfab.com/v3/models/%s" % uid)
                lic = (info.get("license") or {}).get("slug") or (info.get("license") or {}).get("label", "")
                if not lic_ok(lic, args.allow_sa):
                    continue
                dl = jget("https://api.sketchfab.com/v3/models/%s/download" % uid, auth)
                arch = dl.get("glb") or dl.get("gltf")
                data = http(arch["url"], timeout=300)
                save_payload(data, folder, "model.glb" if "glb" in dl else "model.zip")
                user = info.get("user") or {}
                meta = dict(id="sketchfab_" + uid, title=info.get("name", ""), author=user.get("displayName") or user.get("username", ""),
                            license=(info.get("license") or {}).get("label", lic), source=info.get("viewerUrl", ""),
                            category=cat, kind=kind, length=length, group=group, query=q, faces=info.get("faceCount"),
                            folder=os.path.relpath(folder, out))
                write_meta(folder, meta)
                catalog.append(meta)
                got += 1
                print("  [sketchfab] %-40s %-12s %s" % (meta["title"][:40], meta["license"][:12], meta["author"]))
            except urllib.error.HTTPError as e:
                print("  [sketchfab] %s: HTTP %s" % (uid, e.code))
            except Exception as e:
                print("  [sketchfab] %s: %s" % (uid, e))


def fetch_polypizza(args, out, catalog):
    key = os.environ.get("POLYPIZZA_KEY")
    if not key:
        print("[polypizza] sin POLYPIZZA_KEY: omitido (key gratuita en poly.pizza/settings/api)")
        return
    hdr = {"X-Auth-Token": key}
    for q, cat, kind, length, group in QUERIES:
        if args.only and group not in args.only and not any(o in q.lower() for o in args.only):
            continue
        res = None
        for base in ("https://api.poly.pizza/v1.1/search/", "https://api.poly.pizza/v1/search/"):
            try:
                res = jget(base + urllib.parse.quote(q) + "?" + urllib.parse.urlencode({"Limit": 12}), hdr)
                break
            except Exception:
                continue
        if not res:
            continue
        got = 0
        for r in res.get("results", []):
            if got >= args.per_query:
                break
            lic = r.get("Licence") or r.get("License") or ""
            title = r.get("Title", "")
            if banned(title) or not lic_ok(lic, args.allow_sa):
                continue
            pid = str(r.get("ID") or r.get("Id"))
            folder = os.path.join(out, "polypizza", "%s_%s" % (slug(title), pid[:8]))
            if os.path.exists(os.path.join(folder, "asset_meta.json")):
                catalog.append(json.load(open(os.path.join(folder, "asset_meta.json"), encoding="utf-8")))
                got += 1
                continue
            try:
                save_payload(http(r["Download"], timeout=180), folder, "model.glb")
                creator = (r.get("Creator") or {}).get("Username", "")
                meta = dict(id="polypizza_" + pid, title=title, author=creator, license=lic, source="https://poly.pizza/m/" + pid,
                            category=cat, kind=kind, length=length, group=group, query=q, faces=r.get("TriCount"),
                            folder=os.path.relpath(folder, out))
                write_meta(folder, meta)
                catalog.append(meta)
                got += 1
                print("  [polypizza] %-40s %-10s %s" % (title[:40], lic[:10], creator))
            except Exception as e:
                print("  [polypizza] %s: %s" % (pid, e))


def fetch_ambientcg(args, out, catalog):
    for mat, q in AMBIENTCG.items():
        folder = os.path.join(out, "ambientcg", mat)
        if os.path.exists(os.path.join(folder, "asset_meta.json")):
            continue
        try:
            assets = []
            for qq in (q, q.split(" ")[0]):                       # busqueda exacta y luego generica
                url = "https://ambientcg.com/api/v2/full_json?" + urllib.parse.urlencode(
                    dict(type="Material", q=qq, sort="Popular", limit=1, include="downloadData"))
                assets = jget(url).get("foundAssets", [])
                if assets:
                    break
            if not assets:
                continue
            a = assets[0]
            dls = a["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
            pick = next((d for d in dls if d.get("attribute") == args.tex_res + "-JPG"), dls[0])
            save_payload(http(pick["downloadLink"], timeout=300), folder, pick.get("fileName", "tex.zip"))
            meta = dict(id="ambientcg_" + a["assetId"], title=a["assetId"], author="ambientCG (Lennart Demes)", license="CC0 1.0",
                        source="https://ambientcg.com/view?id=" + a["assetId"], category="Textures", kind="texture",
                        material=mat, folder=os.path.relpath(folder, out))
            write_meta(folder, meta)
            catalog.append(meta)
            print("  [ambientcg] %-24s <- %s" % (mat, a["assetId"]))
        except Exception as e:
            print("  [ambientcg] %s (%s): %s" % (mat, q, e))


def fetch_direct(args, out, catalog):
    entries = list(DIRECT)
    extra = os.path.join(os.path.dirname(os.path.abspath(__file__)), "direct_assets.json")
    if os.path.exists(extra):
        entries += json.load(open(extra, encoding="utf-8"))
    for e in entries:
        if not lic_ok(e["license"], args.allow_sa):
            print("  [direct] %s: licencia no permitida (%s)" % (e["id"], e["license"]))
            continue
        folder = os.path.join(out, "direct", e["id"])
        if not os.path.exists(os.path.join(folder, "asset_meta.json")):
            try:
                fname = os.path.basename(urllib.parse.urlparse(e["url"]).path) or "model.glb"
                save_payload(http(e["url"], timeout=300), folder, fname)
            except Exception as exc:
                print("  [direct] %s: %s" % (e["id"], exc))
                continue
            meta = dict(e, folder=os.path.relpath(folder, out))
            meta.pop("url", None)
            write_meta(folder, meta)
        catalog.append(json.load(open(os.path.join(folder, "asset_meta.json"), encoding="utf-8")))
        print("  [direct] %-40s %s" % (e["title"][:40], e["license"]))


def write_credits(out, catalog):
    with open(os.path.join(out, "third_party_catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1, ensure_ascii=False)
    lines = ["# Creditos de assets de terceros", "",
             "Licencias permitidas: CC0 (sin atribucion obligatoria) y CC-BY (atribucion OBLIGATORIA).", ""]
    for m in sorted(catalog, key=lambda m: (m.get("category", ""), m.get("title", ""))):
        lines.append('- "%s" por %s, licencia %s - %s' % (m.get("title"), m.get("author"), m.get("license"), m.get("source")))
    with open(os.path.join(out, "CREDITS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Descarga assets gratuitos (CC0/CC-BY) de guerra moderna")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "ThirdParty"))
    ap.add_argument("--sources", default="direct,ambientcg,polypizza,sketchfab")
    ap.add_argument("--per-query", type=int, default=2, dest="per_query")
    ap.add_argument("--max-faces", type=int, default=80000, dest="max_faces")
    ap.add_argument("--tex-res", default="2K", dest="tex_res", choices=("1K", "2K", "4K"))
    ap.add_argument("--allow-sa", action="store_true", dest="allow_sa", help="incluir CC-BY-SA (obliga a compartir igual)")
    ap.add_argument("--only", default="", help="filtra por grupo o palabra: tank,heli,weapon,fort...")
    if "--" in sys.argv:                                   # blender -b --python fetch_free_assets.py -- [args]
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = [] if "bpy" in sys.modules else sys.argv[1:]
    args = ap.parse_args(argv)
    args.only = [o.strip().lower() for o in args.only.split(",") if o.strip()]
    os.makedirs(args.out, exist_ok=True)
    catalog = []
    srcs = [s.strip() for s in args.sources.split(",")]
    for name, fn in (("direct", fetch_direct), ("ambientcg", fetch_ambientcg), ("polypizza", fetch_polypizza), ("sketchfab", fetch_sketchfab)):
        if name in srcs:
            print("== %s ==" % name)
            fn(args, args.out, catalog)
    write_credits(args.out, catalog)
    print("\n%d assets -> %s (ver CREDITS.md)" % (len(catalog), args.out))


if __name__ == "__main__":
    main()
