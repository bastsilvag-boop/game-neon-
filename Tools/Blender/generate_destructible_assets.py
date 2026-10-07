"""
=====================================================================================
 UNITY DESTRUCTIBLE MILITARY ASSET FACTORY v4  -  Blender (bpy) 4.2+ / 5.x
=====================================================================================
Genera proceduralmente (sin addons ni texturas externas) un catalogo optimizado para
Unity, TODO destructible, con dimensiones reales publicadas y texturas PBR propias.

  Militar       caja de municion, bidon 200 L, sacos, barrera Jersey, erizo checo,
                HESCO MIL1, torre de vigilancia, bunker, contenedor 20 ft, muro de
                bloques CMU, T-wall (Bremer), dientes de dragon, concertina
  Fortificacion trinchera recta y en zigzag, pozo de tirador, nido de ametralladora,
                refugio de troncos, asentamiento de vehiculo (hull-down), pozo de
                mortero 81 mm, control de carretera, tienda GP Medium, red de camuflaje
  Vehiculos     M1A2 SEPv3, Leopard 2A7, T-90M, T-72B3, M2A4 Bradley, CV90 MkIV,
                BMP-2, M109A7, Gepard 1A2, ZSU-23-4 Shilka, Stryker, Boxer, BTR-82A,
                JLTV, HMMWV, M-ATV, FMTV, Ural-4320, technical Hilux+DShK, D9R
                blindado, sedan, autobus urbano, camion de reparto
  Aereos/AA     AH-64E, UH-60M, Ka-52, Mi-24P, Mi-8MTV, AH-6, F-35A, MQ-9, Bayraktar
                TB2, Shahed-136, quadcoptero, C-RAM Centurion, radar sobre remolque;
                naval Mark VI; artilleria M777, M142 HIMARS, BM-21 Grad
  Edificios     casa, casa 2 plantas, bloque 4 plantas, refugio HAS, compound de
                adobe (qalat), casa desertica de techo plano, granero, iglesia con
                campanario, mezquita con alminar, nave industrial, chimenea de 35 m
                (cae como un arbol), gasolinera, muro en ruinas, montones de escombro
  Mapa          calzada urbana, cruce, camino de tierra, torre de alta tension, mastil
                atirantado 40 m, deposito elevado, tanque de combustible, puente de
                3 vanos (si cae una pila cae el vano), helipuerto, pista, farola, valla
  Terreno/Veg.  terreno solido por tiles, roca, crateres, pino, roble, palmera, arbol
                seco, arbusto, hierba, poste electrico, valla
  Variantes     Temperate / Desert / Winter (remapeo de materiales + nieve acumulada)

 DESTRUCCION: Voronoi 3D exacto (chunks convexos, veta de madera, hiladas), muros de
 mamposteria que se rompen POR LAS JUNTAS (bloques sueltos), grafo de contacto para
 colapso estructural, ruinas con escombro asentado, pecios calcinados, piezas
 mecanicas desmontables con pivotes, escombros y LODs.

 JERARQUIA DE CADA FBX (mallas con transform aplicado, pivote 0,0,0 en la base)
  <Asset>               root  (dst_* = metadatos)
   |- <Asset>_Intact    estado 0      |- <Asset>_Chunks_L1 fractura (3)
   |- <Asset>_Damaged   estado 1      |- <Asset>_Chunks_L2 subfractura/bloques (4)
   |- <Asset>_Destroyed estado 2      |- <Asset>_LODs (8)   |- <Asset>_Debris (9)
 Propiedades FBX (use_custom_props) -> AssetPostprocessor.OnPostprocessGameObjectWith-
 UserProperties: dst_role, dst_class, dst_mass (kg), dst_hp, dst_anchored, dst_neighbors
 (grafo: BFS desde los anclados, lo no conectado cae), dst_parent, dst_pivot/dst_axis/
 dst_joint (coords Unity). <Asset>.json repite todo; ground_offset<0 = hundir (trincheras).
 Unity: Scale Factor 1 + Convert Units; Read/Write ON en FBX con chunks; texturas en
 Textures/ (albedo _D + normal _N, Search and Remap por nombre Mat_*); activa solo
 <Asset>_Intact al instanciar; chunks -> Rigidbody + MeshCollider convex (dst_mass).
 Nombres de vehiculos = referencia dimensional; revisa marcas antes de uso comercial.
 Uso:  blender --background --python generate_destructible_assets.py
       (o Text Editor > Run Script). Salida: ~/Unity_Destructible_Military/
 Modelos reales gratuitos (CC0/CC-BY): fetch_free_assets.py los descarga (Sketchfab, Poly
 Pizza, ambientCG) y adapt_free_assets.py los convierte a este mismo pipeline. Las texturas
 fotoescaneadas descargadas (ThirdParty/ambientcg) sustituyen a las procedurales. Ver README.md
=====================================================================================
"""
import bpy
import bmesh
import json
import math
import os
import random
import re
import sys
import time
from mathutils import Vector, Matrix, Euler, noise
from mathutils.bvhtree import BVHTree

# ----------------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Unity_Destructible_Military")
SEED = 1945
ONLY = []                 # p.ej. ["Veh_MBT_M1A2_SEPv3", "Bld_House_Small"]; vacio = todo
CHUNK_SCALE = 1.0         # multiplicador global de numero de chunks
L2_MIN_VOLUME = 0.25      # m3: chunks L1 mayores se sub-fracturan (L2)
UV_TILE = 1.0             # metros por repeticion UV (box mapping)
MAX_CHUNKS_PER_PIECE = 14
FRACTURE_MAX_FACES = 4000  # piezas mas densas (modelos descargados) se fracturan via proxy simplificado
EXPORT = True
try:                       # texturas fotoescaneadas CC0 (fetch_free_assets.py --sources ambientcg)
    PHOTO_TEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ThirdParty", "ambientcg")
except NameError:
    PHOTO_TEX_DIR = os.path.join(os.path.expanduser("~"), "ThirdParty", "ambientcg")

# nombre: (RGB, metallic, roughness, alpha, emission)
MATS = {
    "Mat_Crate_Base": ((0.20, 0.24, 0.12), 0.0, 0.85, 1, 0),
    "Mat_Crate_Metal": ((0.12, 0.12, 0.11), 0.9, 0.45, 1, 0),
    "Mat_Wood_Plank": ((0.42, 0.29, 0.17), 0.0, 0.8, 1, 0),
    "Mat_Wood_Beam": ((0.30, 0.20, 0.11), 0.0, 0.85, 1, 0),
    "Mat_Wood_Interior": ((0.78, 0.62, 0.40), 0.0, 0.9, 1, 0),
    "Mat_Wood_Charred": ((0.04, 0.035, 0.03), 0.0, 0.95, 1, 0),
    "Mat_Concrete_Base": ((0.55, 0.54, 0.51), 0.0, 0.9, 1, 0),
    "Mat_Concrete_Interior": ((0.38, 0.37, 0.35), 0.0, 1.0, 1, 0),
    "Mat_Rebar_Rust": ((0.30, 0.13, 0.06), 0.8, 0.7, 1, 0),
    "Mat_Brick_Wall": ((0.50, 0.22, 0.15), 0.0, 0.9, 1, 0),
    "Mat_Brick_Interior": ((0.62, 0.36, 0.26), 0.0, 1.0, 1, 0),
    "Mat_Plaster_Wall": ((0.80, 0.75, 0.64), 0.0, 0.9, 1, 0),
    "Mat_Roof_Tile": ((0.55, 0.20, 0.10), 0.0, 0.8, 1, 0),
    "Mat_Roof_Metal": ((0.42, 0.44, 0.45), 0.8, 0.5, 1, 0),
    "Mat_Floor_Wood": ((0.45, 0.32, 0.20), 0.0, 0.7, 1, 0),
    "Mat_Glass_Window": ((0.55, 0.70, 0.75), 0.0, 0.05, 0.35, 0),
    "Mat_Frame_Window": ((0.85, 0.85, 0.82), 0.0, 0.6, 1, 0),
    "Mat_Door_Wood": ((0.33, 0.18, 0.09), 0.0, 0.7, 1, 0),
    "Mat_Military_Olive": ((0.19, 0.22, 0.12), 0.25, 0.7, 1, 0),
    "Mat_Military_Green": ((0.12, 0.17, 0.10), 0.25, 0.7, 1, 0),
    "Mat_Military_Desert": ((0.62, 0.52, 0.36), 0.2, 0.75, 1, 0),
    "Mat_Military_Grey": ((0.36, 0.38, 0.40), 0.3, 0.6, 1, 0),
    "Mat_Military_Navy": ((0.42, 0.45, 0.48), 0.3, 0.55, 1, 0),
    "Mat_Metal_Gunmetal": ((0.10, 0.10, 0.10), 0.9, 0.4, 1, 0),
    "Mat_Metal_Steel": ((0.55, 0.55, 0.56), 1.0, 0.35, 1, 0),
    "Mat_Metal_Charred": ((0.05, 0.045, 0.04), 0.6, 0.9, 1, 0),
    "Mat_Rubber_Tire": ((0.03, 0.03, 0.03), 0.0, 0.9, 1, 0),
    "Mat_Track_Steel": ((0.16, 0.15, 0.14), 0.9, 0.6, 1, 0),
    "Mat_Glass_Canopy": ((0.25, 0.30, 0.25), 0.2, 0.05, 0.5, 0),
    "Mat_Light_Lens": ((1.0, 0.9, 0.7), 0.0, 0.2, 1, 2),
    "Mat_Rotor_Blade": ((0.08, 0.08, 0.08), 0.3, 0.5, 1, 0),
    "Mat_Fabric_Sandbag": ((0.52, 0.45, 0.30), 0.0, 1.0, 1, 0),
    "Mat_Fabric_Canvas": ((0.25, 0.27, 0.17), 0.0, 1.0, 1, 0),
    "Mat_Sand_Fill": ((0.70, 0.60, 0.42), 0.0, 1.0, 1, 0),
    "Mat_Hesco_Mesh": ((0.45, 0.46, 0.44), 0.9, 0.5, 1, 0),
    "Mat_Container_Paint": ((0.13, 0.25, 0.42), 0.4, 0.6, 1, 0),
    "Mat_Barrel_Paint": ((0.12, 0.20, 0.10), 0.5, 0.5, 1, 0),
    "Mat_Terrain_Grass": ((0.20, 0.30, 0.10), 0.0, 0.95, 1, 0),
    "Mat_Terrain_Soil": ((0.30, 0.22, 0.14), 0.0, 1.0, 1, 0),
    "Mat_Rock_Base": ((0.42, 0.41, 0.38), 0.0, 0.85, 1, 0),
    "Mat_Rock_Interior": ((0.55, 0.53, 0.49), 0.0, 0.95, 1, 0),
    "Mat_Bark_Pine": ((0.25, 0.16, 0.10), 0.0, 0.95, 1, 0),
    "Mat_Bark_Oak": ((0.28, 0.22, 0.16), 0.0, 0.95, 1, 0),
    "Mat_Bark_Palm": ((0.45, 0.38, 0.27), 0.0, 0.95, 1, 0),
    "Mat_Bark_Dead": ((0.32, 0.30, 0.27), 0.0, 0.95, 1, 0),
    "Mat_Leaves_Pine": ((0.07, 0.17, 0.08), 0.0, 0.8, 1, 0),
    "Mat_Leaves_Oak": ((0.13, 0.28, 0.08), 0.0, 0.8, 1, 0),
    "Mat_Leaves_Palm": ((0.20, 0.35, 0.10), 0.0, 0.8, 1, 0),
    "Mat_Leaves_Bush": ((0.15, 0.25, 0.09), 0.0, 0.85, 1, 0),
    "Mat_Grass_Blade": ((0.25, 0.38, 0.12), 0.0, 0.85, 1, 0),
    "Mat_Leaves_Dry": ((0.30, 0.24, 0.10), 0.0, 0.9, 1, 0),
    "Mat_FX_Scorch": ((0.03, 0.025, 0.02), 0.0, 1.0, 1, 0),
    "Mat_Snow": ((0.86, 0.88, 0.90), 0.0, 0.6, 1, 0),
    "Mat_Terrain_Snow": ((0.84, 0.86, 0.89), 0.0, 0.65, 1, 0),
    "Mat_Terrain_Sand": ((0.62, 0.48, 0.30), 0.0, 0.95, 1, 0),
    "Mat_Plaster_Desert": ((0.62, 0.50, 0.36), 0.0, 0.95, 1, 0),
    "Mat_Mudbrick": ((0.55, 0.42, 0.28), 0.0, 1.0, 1, 0),
    "Mat_CinderBlock": ((0.50, 0.50, 0.48), 0.0, 0.95, 1, 0),
    "Mat_Military_Winter": ((0.80, 0.81, 0.80), 0.2, 0.75, 1, 0),
    "Mat_Military_RuGreen": ((0.14, 0.19, 0.11), 0.25, 0.7, 1, 0),
    "Mat_Log_Wood": ((0.33, 0.24, 0.15), 0.0, 0.9, 1, 0),
    "Mat_Pole_Wood": ((0.20, 0.14, 0.09), 0.0, 0.85, 1, 0),
    "Mat_Car_Paint": ((0.30, 0.05, 0.04), 0.6, 0.35, 1, 0),
    "Mat_Civil_White": ((0.78, 0.78, 0.76), 0.5, 0.4, 1, 0),
    "Mat_Insulator": ((0.75, 0.72, 0.66), 0.0, 0.2, 1, 0),
    "Mat_Wire_Steel": ((0.40, 0.40, 0.40), 1.0, 0.4, 1, 0),
}

# Perfil fisico/destructivo por clase de material
#   dens kg/m3 | chunks base | aniso (escala del espacio Voronoi: <1 alarga, >1 aplana)
#   interior   | hp por kg   | l2 sub-fractura | rebar expuesto | grain (alargamiento veta)
PROFILES = {
    "concrete": dict(dens=2400, chunks=7, aniso=(1, 1, 1), interior="Mat_Concrete_Interior", hp=0.5, l2=True, rebar=True),
    "brick": dict(dens=1850, chunks=7, aniso=(1, 1, 1.8), interior="Mat_Brick_Interior", hp=0.35, l2=True, rebar=False),
    "plaster": dict(dens=1700, chunks=7, aniso=(1, 1, 1.6), interior="Mat_Brick_Interior", hp=0.3, l2=True, rebar=False),
    "wood": dict(dens=650, chunks=4, aniso=(1, 1, 1), interior="Mat_Wood_Interior", hp=0.8, l2=False, rebar=False, grain=0.22),
    "metal": dict(dens=7850, chunks=4, aniso=(1, 1, 1), interior="Mat_Metal_Steel", hp=2.5, l2=False, rebar=False),
    "glass": dict(dens=2500, chunks=12, aniso=(1, 1, 1), interior="Mat_Glass_Window", hp=0.05, l2=False, rebar=False),
    "rock": dict(dens=2650, chunks=9, aniso=(1, 1, 1.4), interior="Mat_Rock_Interior", hp=0.6, l2=True, rebar=False),
    "earth": dict(dens=1600, chunks=6, aniso=(1, 1, 1.2), interior="Mat_Terrain_Soil", hp=0.2, l2=False, rebar=False),
    "fabric": dict(dens=1500, chunks=2, aniso=(1, 1, 1), interior="Mat_Sand_Fill", hp=0.3, l2=False, rebar=False),
    "foliage": dict(dens=60, chunks=1, aniso=(1, 1, 1), interior=None, hp=0.1, l2=False, rebar=False),
    "rubber": dict(dens=1100, chunks=2, aniso=(1, 1, 1), interior="Mat_Rubber_Tire", hp=1.0, l2=False, rebar=False),
    "cinder": dict(dens=1400, chunks=5, aniso=(1, 1, 1.5), interior="Mat_Concrete_Interior", hp=0.4, l2=False, rebar=False),
    "mudbrick": dict(dens=1700, chunks=6, aniso=(1, 1, 1.6), interior="Mat_Mudbrick", hp=0.25, l2=False, rebar=False),
}

RNG = random.Random(SEED)
COLL = None  # coleccion activa (se asigna en reset)


# ----------------------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------------------
def V(*a):
    return Vector(a[0] if len(a) == 1 else a)


def mat4(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    r = Euler([math.radians(a) for a in rot], 'XYZ').to_matrix().to_4x4()
    return Matrix.Translation(V(loc)) @ r @ Matrix.Diagonal((*scale, 1.0))


def unity(v):
    """Blender (Z-up, frente -Y) -> Unity (Y-up, frente +Z) con -Z fwd / Y up."""
    return [round(-v[0], 4), round(v[2], 4), round(-v[1], 4)]


def unity_s(v):
    return ",".join("%.4f" % c for c in unity(v))


def bbox(bm):
    if not bm.verts:
        return V(0, 0, 0), V(0, 0, 0)
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return V(min(xs), min(ys), min(zs)), V(max(xs), max(ys), max(zs))


def sym(pts):
    """Puntos (x,y,z) con y>=0 -> espejo en Y (formas simetricas)."""
    out = []
    for x, y, z in pts:
        out.append((x, y, z))
        if abs(y) > 1e-6:
            out.append((x, -y, z))
    return out


def get_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    rgb, met, rough, alpha, emis = MATS.get(name, ((0.5, 0.5, 0.5), 0.0, 0.6, 1, 0))
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, alpha)
    if m.node_tree is None:
        try:
            m.use_nodes = True
        except Exception:
            pass
    nt = m.node_tree
    if nt is not None:
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if bsdf is None:
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        if out is None:
            out = nt.nodes.new("ShaderNodeOutputMaterial")
        if not out.inputs["Surface"].is_linked:
            nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
        bsdf.name = name + "_BSDF"
        try:
            wire_textures(m, bsdf)
        except Exception as exc:
            print("  [tex] %s: %s" % (name, exc))

        def setin(key, val):
            s = bsdf.inputs.get(key)
            if s is not None:
                s.default_value = val
        setin("Base Color", (*rgb, 1.0))
        setin("Metallic", met)
        setin("Roughness", rough)
        setin("Alpha", alpha)
        if emis:
            setin("Emission Color", (*rgb, 1.0))
            setin("Emission", (*rgb, 1.0))
            setin("Emission Strength", float(emis))
    if alpha < 1.0:
        for attr, val in (("surface_render_method", 'BLENDED'), ("blend_method", 'BLEND')):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    return m


# ----------------------------------------------------------------------------------
# PIECE: solido cerrado (bmesh) con material, clase y veta. face.material_index:
#   0 = material de la pieza, 1 = cara interior de fractura, 2 = quemadura/hollin
# ----------------------------------------------------------------------------------
class Piece:
    __slots__ = ("bm", "mat", "cls", "grain", "frac", "tag", "mason")

    def __init__(self, bm, mat, cls=None, grain=None, frac=True, tag="", mason=None):
        self.bm, self.mat, self.cls, self.grain, self.frac, self.tag = bm, mat, cls, grain, frac, tag
        self.mason = mason       # (marco local->mundo, tamano, (largo, alto) de pieza, desfase u) o None

    def copy(self, **kw):
        p = Piece(self.bm.copy(), self.mat, self.cls, self.grain, self.frac, self.tag, self.mason)
        for k, v in kw.items():
            setattr(p, k, v)
        return p

    def transform(self, M):
        bmesh.ops.transform(self.bm, matrix=M, verts=self.bm.verts[:])
        if M.determinant() < 0:
            bmesh.ops.reverse_faces(self.bm, faces=self.bm.faces[:])
        if self.mason is not None:
            F, size, unit, u0 = self.mason
            self.mason = (M @ F, size, unit, u0)
        self.bm.normal_update()
        return self

    def bounds(self):
        return bbox(self.bm)

    def center(self):
        lo, hi = bbox(self.bm)
        return (lo + hi) * 0.5

    def volume(self):
        try:
            return abs(self.bm.calc_volume())
        except Exception:
            return 0.0


def _finish(bm, mat, loc, rot, scale=(1, 1, 1), smooth=False, flat_axis=None, **kw):
    bm.normal_update()
    for f in bm.faces:
        f.smooth = smooth and not (flat_axis is not None and abs(f.normal.dot(flat_axis)) > 0.95)
    bmesh.ops.transform(bm, matrix=mat4(loc, rot, scale), verts=bm.verts[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    return Piece(bm, mat, **kw)


# ----------------------------------------------------------------------------------
# PRIMITIVAS (todas devuelven Piece cerradas; medidas en metros, Z arriba, +X frente
# interno de construccion: los vehiculos se rotan al final para mirar a -Y = +Z Unity)
# ----------------------------------------------------------------------------------
def box(size, loc=(0, 0, 0), rot=(0, 0, 0), mat="Mat_Concrete_Base", bevel=0.0, **kw):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=V(size), verts=bm.verts[:])
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=min(bevel, min(size) * 0.4),
                        segments=1, affect='EDGES', profile=0.5)
    return _finish(bm, mat, loc, rot, **kw)


def cyl(r, depth, loc=(0, 0, 0), rot=(0, 0, 0), mat="Mat_Metal_Steel", segs=12, r2=None, smooth=True, **kw):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else max(r2, 0.001), depth=depth)
    return _finish(bm, mat, loc, rot, smooth=smooth, flat_axis=V(0, 0, 1), **kw)


def strut(a, b, r, mat="Mat_Metal_Steel", segs=6, r2=None, **kw):
    """Cilindro entre dos puntos (ramas, riostras, antenas, rebar...)."""
    a, b = V(a), V(b)
    d = b - a
    L = max(d.length, 1e-4)
    q = d.normalized().to_track_quat('Z', 'Y')
    p = cyl(r, L, mat=mat, segs=segs, r2=r2, **kw)
    return p.transform(Matrix.Translation((a + b) * 0.5) @ q.to_matrix().to_4x4())


def ico(r, loc=(0, 0, 0), mat="Mat_Rock_Base", subdiv=1, scale=(1, 1, 1), rough=0.0, seed=0, smooth=False, **kw):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=r)
    if rough:
        off = V(seed * 13.17, seed * 7.31, seed * 3.77)
        for v in bm.verts:
            v.co += v.co.normalized() * r * rough * noise.noise(v.co * (2.2 / max(r, 0.05)) + off)
    return _finish(bm, mat, loc, (0, 0, 0), scale=scale, smooth=smooth, **kw)


def sphere(r, loc=(0, 0, 0), mat="Mat_Metal_Steel", segs=12, rings=7, scale=(1, 1, 1), smooth=True, **kw):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r)
    return _finish(bm, mat, loc, (0, 0, 0), scale=scale, smooth=smooth, **kw)


def hull(points, loc=(0, 0, 0), rot=(0, 0, 0), mat="Mat_Military_Olive", **kw):
    """Envolvente convexa de puntos clave: blindajes, torretas, cabinas."""
    bm = bmesh.new()
    for p in points:
        bm.verts.new(p)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
    res = bmesh.ops.convex_hull(bm, input=bm.verts[:])
    junk = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    if junk:
        bmesh.ops.delete(bm, geom=junk, context='VERTS')
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0), verts=bm.verts[:], edges=bm.edges[:])
    return _finish(bm, mat, loc, rot, **kw)


def prism(poly, depth, axis='y', offset=0.0, loc=(0, 0, 0), rot=(0, 0, 0), mat="Mat_Concrete_Base", **kw):
    """Poligono 2D extruido: 'y' perfil XZ, 'z' planta XY, 'x' seccion YZ."""
    def P(a, b, d):
        return (a, d, b) if axis == 'y' else (a, b, d) if axis == 'z' else (d, a, b)
    bm = bmesh.new()
    h = depth * 0.5
    f = [bm.verts.new(P(a, b, offset - h)) for a, b in poly]
    k = [bm.verts.new(P(a, b, offset + h)) for a, b in poly]
    n = len(poly)
    bm.faces.new(f)
    bm.faces.new(k[::-1])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((f[i], f[j], k[j], k[i]))
    return _finish(bm, mat, loc, rot, **kw)


def lathe(profile, loc=(0, 0, 0), rot=(0, 0, 0), mat="Mat_Metal_Steel", segs=12, smooth=True,
          closed=False, hollow=False, **kw):
    """Revolucion alrededor de Z. profile=[(r,z),...]; r=0 -> polo.
    closed=True: perfil cerrado sin polos (aros, neumaticos). hollow=True: solido con
    cavidad interior (bidones, cascos): normales de la cavidad hacia dentro."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r <= 1e-5:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / segs),
                                        r * math.sin(2 * math.pi * i / segs), z)) for i in range(segs)])
    _bridge_rings(bm, rings, cap=not closed, loop=closed)
    pc = _finish(bm, mat, loc, rot, smooth=smooth, flat_axis=V(0, 0, 1), **kw)
    if hollow:
        fix_cavities(pc.bm)
    return pc


def fix_cavities(bm):
    """Islas contenidas en otra isla = cavidades -> invertir sus normales."""
    seen, isl = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        seen.add(f)
        stack, comp = [f], []
        while stack:
            x = stack.pop()
            comp.append(x)
            for e in x.edges:
                for o in e.link_faces:
                    if o not in seen:
                        seen.add(o)
                        stack.append(o)
        vs = {v for g in comp for v in g.verts}
        lo = V(min(v.co.x for v in vs), min(v.co.y for v in vs), min(v.co.z for v in vs))
        hi = V(max(v.co.x for v in vs), max(v.co.y for v in vs), max(v.co.z for v in vs))
        isl.append((comp, lo, hi))
    for comp, lo, hi in isl:
        if any(all(lo2[k] < lo[k] and hi[k] < hi2[k] for k in range(3)) for c2, lo2, hi2 in isl if c2 is not comp):
            bmesh.ops.reverse_faces(bm, faces=comp)
    bm.normal_update()


def beam(a, b, w, h=None, mat="Mat_Wood_Beam", **kw):
    """Viga de seccion rectangular entre dos puntos; veta = eje dominante."""
    a, b = V(a), V(b)
    d = b - a
    q = d.normalized().to_track_quat('Z', 'Y')
    kw.setdefault("grain", "xyz"[max(range(3), key=lambda i: abs(d[i]))])
    p = box((w, h or w, max(d.length, 1e-3)), mat=mat, **kw)
    return p.transform(Matrix.Translation((a + b) * 0.5) @ q.to_matrix().to_4x4())


def _bridge_rings(bm, rings, cap=True, loop=False):
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if loop else [])
    for a, b in pairs:
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(len(b)):
                bm.faces.new((a[0], b[i], b[(i + 1) % len(b)]))
        elif len(b) == 1:
            for i in range(len(a)):
                bm.faces.new((a[i], a[(i + 1) % len(a)], b[0]))
        else:
            for i in range(len(a)):
                j = (i + 1) % len(a)
                bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap:
        if len(rings[0]) > 2:
            bm.faces.new(rings[0][::-1])
        if len(rings[-1]) > 2:
            bm.faces.new(rings[-1])


def loft(rings_pts, loc=(0, 0, 0), rot=(0, 0, 0), mat="Mat_Military_Olive", smooth=False, **kw):
    """Une anillos de puntos 3D (mismo numero, o 1 = punta). Fuselajes, cascos."""
    bm = bmesh.new()
    rings = [[bm.verts.new(p) for p in ring] for ring in rings_pts]
    _bridge_rings(bm, rings)
    return _finish(bm, mat, loc, rot, smooth=smooth, **kw)


def ell_rings(sections, segs=10):
    """sections=[(x, ry, rz, zc)] -> anillos elipticos a lo largo de X."""
    out = []
    for x, ry, rz, zc in sections:
        if ry < 1e-3 or rz < 1e-3:
            out.append([(x, 0.0, zc)])
        else:
            out.append([(x, ry * math.cos(2 * math.pi * i / segs), zc + rz * math.sin(2 * math.pi * i / segs))
                        for i in range(segs)])
    return out


def resample_loop(pts, n):
    """Remuestrea un poligono cerrado 2D a n puntos equiespaciados."""
    segs = [(V(pts[i]), V(pts[(i + 1) % len(pts)])) for i in range(len(pts))]
    total = sum((b - a).length for a, b in segs)
    out, acc, k = [], 0.0, 0
    for i in range(n):
        t = total * i / n
        while acc + (segs[k][1] - segs[k][0]).length < t and k < len(segs) - 1:
            acc += (segs[k][1] - segs[k][0]).length
            k += 1
        a, b = segs[k]
        L = max((b - a).length, 1e-6)
        out.append(a.lerp(b, min(max((t - acc) / L, 0.0), 1.0)))
    return out


def band(path, thick, width, y=0.0, mat="Mat_Track_Steel", i0=0, i1=None, **kw):
    """Banda (oruga) siguiendo un lazo 2D en XZ. i0..i1 => tramo abierto con tapas."""
    pts = [V(p) for p in path]
    n = len(pts)
    area = sum(pts[i].x * pts[(i + 1) % n].y - pts[(i + 1) % n].x * pts[i].y for i in range(n))
    sgn = 1.0 if area > 0 else -1.0
    inner = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1, d2 = (b - a).normalized(), (c - b).normalized()
        n1, n2 = V(-d1.y, d1.x) * sgn, V(-d2.y, d2.x) * sgn
        m = (n1 + n2)
        m = m.normalized() if m.length > 1e-6 else n1
        inner.append(b + m * (thick / max(m.dot(n1), 0.3)))
    closed = i1 is None
    idx = list(range(n)) if closed else [k % n for k in range(i0, i1 + 1)]
    bm = bmesh.new()
    hw = width * 0.5

    def ring(k):
        o, q = pts[k], inner[k]
        return [bm.verts.new((o.x, y - hw, o.y)), bm.verts.new((o.x, y + hw, o.y)),
                bm.verts.new((q.x, y + hw, q.y)), bm.verts.new((q.x, y - hw, q.y))]
    rings = [ring(k) for k in idx]
    m_ = len(rings)
    for s in range(m_ if closed else m_ - 1):
        a, b = rings[s], rings[(s + 1) % m_]
        for e in range(4):
            bm.faces.new((a[e], a[(e + 1) % 4], b[(e + 1) % 4], b[e]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    return _finish(bm, mat, (0, 0, 0), (0, 0, 0), **kw)


# ----------------------------------------------------------------------------------
# MOTOR DE FRACTURA: Voronoi 3D exacto por bisecciones sucesivas (sin addons).
#  - celdas de un solido convexo => chunks convexos (MeshCollider convex exacto)
#  - siembra sesgada hacia el punto de impacto (fragmentos finos cerca del impacto)
#  - espacio anisotropo: veta de madera (astillas), hiladas de ladrillo, estratos
#  - las caras de corte se marcan como interiores (material de rotura)
# ----------------------------------------------------------------------------------
SHELL_T = 0.025              # espesor (m) de las placas de fractura de mallas abiertas


def clip(bm, co, no, fill=True):
    """Recorta el lado positivo del plano y rellena el corte (soporta huecos)."""
    no = V(no).normalized()
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6,
                           plane_co=co, plane_no=no, clear_outer=True)
    if not fill:                # malla abierta (modelo externo): sin tapa, se solidifica despues
        return
    edges = [e for e in bm.edges if e.is_boundary]
    if not edges:
        return
    res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges, normal=no)
    for f in res["geom"]:
        if isinstance(f, bmesh.types.BMFace):
            f.material_index, f.smooth = 1, False
            f.normal_update()
            if f.normal.dot(no) < 0:
                f.normal_flip()


def split_piece(pc, co, no):
    """Parte una pieza por un plano -> (lado negativo, lado positivo), ambas cerradas."""
    a, b = pc.copy(), pc.copy()
    clip(a.bm, co, no)
    clip(b.bm, co, -V(no))
    return a, b


def _inside(bvh, p):
    hit = bvh.find_nearest(p)
    return hit[0] is not None and (hit[0] - p).dot(hit[1]) > 0.0


def solidify(bm, t):
    """Da espesor a una cascara abierta; las caras nuevas (canto/dorso) son interiores."""
    old = set(bm.faces)
    bm.normal_update()
    try:
        bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=t)
    except Exception:
        return
    for f in bm.faces:
        if f not in old:
            f.material_index = 1
    bm.normal_update()


def _islands(bm):
    seen, groups = set(), []
    for v in bm.verts:
        if v in seen:
            continue
        seen.add(v)
        stack, comp = [v], []
        while stack:
            x = stack.pop()
            comp.append(x)
            for e in x.link_edges:
                o = e.other_vert(x)
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
        groups.append(comp)
    if len(groups) == 1:
        return [bm.copy()]
    out = []
    for comp in groups:
        sub, vm = bmesh.new(), {}
        for v in comp:
            vm[v] = sub.verts.new(v.co)
        for f in {f for v in comp for f in v.link_faces}:
            try:
                nf = sub.faces.new([vm[v] for v in f.verts])
                nf.material_index, nf.smooth = f.material_index, f.smooth
            except ValueError:
                pass
        out.append(sub)
    return out


def chunk_count(pc, base, scale=1.0):
    vol = pc.volume()
    if vol <= 1e-6:
        return 1
    n = int(round(base * CHUNK_SCALE * scale * max(vol, 0.001) ** (1.0 / 3.0) * 1.6))
    return max(1, min(MAX_CHUNKS_PER_PIECE, n))


def aniso_for(pc, prof):
    a = list(prof.get("aniso", (1, 1, 1)))
    g = prof.get("grain")
    if g and pc.grain and pc.grain in "xyz":
        a["xyz".index(pc.grain)] *= g
    return a


def voronoi(pc, n, rng, impact=None, min_vol=2e-4):
    """Fractura Voronoi de una pieza cerrada en ~n celdas. Devuelve [Piece]."""
    prof = PROFILES.get(pc.cls, PROFILES["concrete"])
    if n < 2 or not pc.frac:
        return [pc.copy()]
    shell = pc.tag == "shell"   # malla abierta: fractura de cascara + solidificado
    S = Matrix.Diagonal((*aniso_for(pc, prof), 1.0))
    Si = S.inverted()
    work = pc.bm.copy()
    bmesh.ops.transform(work, matrix=S, verts=work.verts[:])
    work.normal_update()
    bvh = BVHTree.FromBMesh(work)
    lo, hi = bbox(work)
    size = hi - lo
    imp = (S @ V(impact)) if impact is not None else None
    sig = max(size) * 0.22
    seeds, tries = [], 0
    while len(seeds) < n and tries < n * 60:
        tries += 1
        if imp is not None and rng.random() < 0.55:
            p = imp + V(rng.gauss(0, sig), rng.gauss(0, sig), rng.gauss(0, sig))
        else:
            p = V(rng.uniform(lo.x, hi.x), rng.uniform(lo.y, hi.y), rng.uniform(lo.z, hi.z))
        if (shell or _inside(bvh, p)) and all((p - s).length > max(size) * 0.02 for s in seeds):
            seeds.append(p)
    if len(seeds) < 2:
        work.free()
        return [pc.copy()]
    out = []
    for i, s in enumerate(seeds):
        others = sorted((q for j, q in enumerate(seeds) if j != i), key=lambda q: (q - s).length_squared)
        cell = work.copy()
        for q in others:
            d = (q - s).length
            rmax = max(((v.co - s).length for v in cell.verts), default=0.0)
            if d * 0.5 > rmax:
                break  # ningun bisector restante puede tocar la celda (poda exacta)
            clip(cell, (s + q) * 0.5, (q - s) / d, fill=not shell)
            if len(cell.faces) < (1 if shell else 4):
                break
        if len(cell.faces) >= (1 if shell else 4):
            bmesh.ops.transform(cell, matrix=Si, verts=cell.verts[:])
            if shell:
                solidify(cell, SHELL_T)
            for isl in _islands(cell):
                isl.normal_update()
                p = Piece(isl, pc.mat, pc.cls, pc.grain, True, pc.tag)
                if p.volume() > min_vol:
                    out.append(p)
                else:
                    isl.free()
        cell.free()
    work.free()
    return out or [pc.copy()]


# ----------------------------------------------------------------------------------
# DEFORMACION / DANO
# ----------------------------------------------------------------------------------
def subdivide(pc, cuts=1):
    bmesh.ops.subdivide_edges(pc.bm, edges=pc.bm.edges[:], cuts=cuts, use_grid_fill=True)
    pc.bm.normal_update()
    return pc


def dent(pc, amp, freq=1.5, seed=0, center=None, radius=None):
    """Abolladuras por ruido vectorial (opcionalmente localizadas en un impacto)."""
    off = V(seed * 3.1, seed * 5.7, seed * 1.3)
    for v in pc.bm.verts:
        w = 1.0
        if center is not None:
            d = (v.co - center).length
            w = max(0.0, 1.0 - d / radius) ** 1.5
        if w > 0:
            v.co += noise.noise_vector(v.co * freq + off) * amp * w
    pc.bm.normal_update()
    return pc


def scorch(pc, center, radius, rng, prob=0.85):
    """Marca caras exteriores cercanas a un impacto con hollin (material slot 2)."""
    for f in pc.bm.faces:
        if f.material_index == 0 and (f.calc_center_median() - center).length < radius * rng.uniform(0.6, 1.0):
            if rng.random() < prob:
                f.material_index = 2


def char(pc):
    """Version calcinada (pecio): metal -> Mat_Metal_Charred, madera -> charred."""
    if pc.cls in ("wood", "foliage"):
        pc.mat = "Mat_Wood_Charred"
    elif pc.cls not in ("glass",):
        pc.mat = "Mat_Metal_Charred"
    return pc


def rebar(pc, rng, max_bars=3, min_area=0.02):
    """Varillas corrugadas dobladas que asoman de las caras de rotura del hormigon."""
    faces = sorted((f for f in pc.bm.faces if f.material_index == 1 and f.calc_area() > min_area),
                   key=lambda f: -f.calc_area())[:max_bars]
    bars = []
    for f in faces:
        c, n = f.calc_center_median(), f.normal.copy()
        L = rng.uniform(0.15, 0.45)
        side = n.cross(V(0, 0, 1))
        if side.length < 1e-3:
            side = V(1, 0, 0)
        side.normalize()
        p0 = c - n * 0.06
        p1 = c + n * L * 0.55 + side * rng.uniform(-0.05, 0.05)
        p2 = p1 + (n * 0.4 + side * rng.choice((-1, 1)) * 0.7 + V(0, 0, -0.3)).normalized() * L * 0.6
        for a, b in ((p0, p1), (p1, p2)):
            bars.append(strut(a, b, 0.008, mat="Mat_Rebar_Rust", segs=4, smooth=False, cls="metal", frac=False))
    return bars


def settle(pieces, rng, center, spread=0.35, cell=0.7, floor=None):
    """Colapso heuristico: cada pieza cae al suelo con deriva radial, giro aleatorio
    y apilamiento sobre un campo de alturas (montones de escombro creibles)."""
    hmap, out = {}, []
    for pc in sorted(pieces, key=lambda p: p.center().z):
        c = pc.center()
        h = max(c.z, 0.0)
        radial = V(c.x - center.x, c.y - center.y, 0.0)
        radial = radial.normalized() if radial.length > 1e-4 else V(1, 0, 0)
        jitter = V(rng.uniform(-1, 1), rng.uniform(-1, 1), 0) * 0.3
        tgt = V(c.x, c.y, 0) + radial * rng.uniform(0.0, spread) * (0.4 + h) + jitter
        R = Euler((rng.uniform(-math.pi, math.pi), rng.uniform(-0.6, 0.6),
                   rng.uniform(-math.pi, math.pi))).to_matrix().to_4x4()
        q = pc.copy().transform(Matrix.Translation(tgt) @ R @ Matrix.Translation(-c))
        lo, hi = q.bounds()
        key = (int(math.floor(tgt.x / cell)), int(math.floor(tgt.y / cell)))
        base = hmap.get(key, floor(tgt.x, tgt.y) if floor else 0.0)
        q.transform(Matrix.Translation((0, 0, base - lo.z - (hi.z - lo.z) * 0.15)))
        top = base + (hi.z - lo.z) * 0.6
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                k2 = (key[0] + dx, key[1] + dy)
                hmap[k2] = max(hmap.get(k2, 0.0), top * (1.0 if dx == dy == 0 else 0.55))
        out.append(q)
    return out


def mound(center, radius, height, mat, rng, cls="earth"):
    """Monticulo de escombro/polvo bajo los montones (icoesfera aplastada cortada)."""
    p = ico(1.0, mat=mat, subdiv=2, rough=0.25, seed=rng.randint(0, 999), cls=cls, frac=False)
    p.transform(Matrix.Translation(center) @ Matrix.Diagonal((radius, radius * rng.uniform(0.7, 1.0), height, 1)))
    clip(p.bm, V(center.x, center.y, center.z), V(0, 0, -1))
    for f in p.bm.faces:
        f.material_index = 0
    return p


# ----------------------------------------------------------------------------------
# GRAFO DE CONTACTO (integridad estructural)
# ----------------------------------------------------------------------------------
def contact_graph(pieces_list, tol=0.03, max_samples=48):
    """pieces_list: lista de listas de Piece (un nodo puede tener varias piezas).
    Devuelve [set(vecinos)] por nodo segun proximidad real de superficies."""
    nodes = []
    for plist in pieces_list:
        bm = bmesh.new()
        for pc in plist:
            _merge(bm, pc.bm, 0, 0, 0)
        bm.normal_update()
        lo, hi = bbox(bm)
        samples = [v.co.copy() for v in bm.verts] + [f.calc_center_median() for f in bm.faces]
        if len(samples) > max_samples:
            samples = random.Random(len(samples)).sample(samples, max_samples)
        nodes.append((lo, hi, BVHTree.FromBMesh(bm), samples))
        bm.free()
    nb = [set() for _ in nodes]
    for i in range(len(nodes)):
        lo_i, hi_i, bvh_i, s_i = nodes[i]
        for j in range(i + 1, len(nodes)):
            lo_j, hi_j, bvh_j, s_j = nodes[j]
            if any(lo_i[k] > hi_j[k] + tol or lo_j[k] > hi_i[k] + tol for k in range(3)):
                continue
            if any(bvh_j.find_nearest(p, tol)[0] is not None for p in s_i) or \
               any(bvh_i.find_nearest(p, tol)[0] is not None for p in s_j):
                nb[i].add(j)
                nb[j].add(i)
    return nb


def grounded(nb, anchored, alive):
    """BFS desde los nodos anclados vivos -> conjunto conectado al suelo."""
    seen = {i for i in alive if anchored[i]}
    stack = list(seen)
    while stack:
        x = stack.pop()
        for y in nb[x]:
            if y in alive and y not in seen:
                seen.add(y)
                stack.append(y)
    return seen


# ----------------------------------------------------------------------------------
# OBJETOS BLENDER
# ----------------------------------------------------------------------------------
def _merge(dst, src, mi0, mi1, mi2, snow=None, uvd=None, uv_done=None):
    vm = {v: dst.verts.new(v.co) for v in src.verts}
    uvs = src.loops.layers.uv.active if (uvd is not None and src.loops.layers.uv) else None
    for f in src.faces:
        try:
            nf = dst.faces.new([vm[v] for v in f.verts])
        except ValueError:
            continue
        if uvs is not None and f.material_index != 1:      # conserva el UV original (modelos externos)
            for a, b in zip(f.loops, nf.loops):
                b[uvd].uv = a[uvs].uv
            uv_done.add(nf)
        nf.material_index = (mi0, mi1, mi2)[min(f.material_index, 2)]
        if snow is not None and f.material_index == 0 and f.normal.z > SNOW_NZ:
            nf.material_index = snow                      # nieve acumulada (variante Winter)
        nf.smooth = f.smooth


def box_uv(bm, tiles=None, skip=()):
    """UV caja en metros; cada material repite su textura cada tiles[slot] metros."""
    uv = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        if f in skip:
            continue
        s = 1.0 / (tiles[f.material_index] if tiles else UV_TILE)
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            c = l.vert.co
            l[uv].uv = ((c.y * s, c.z * s) if ax == 0 else (c.x * s, c.z * s) if ax == 1 else (c.x * s, c.y * s))


def empty(name, parent=None, props=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = 'PLAIN_AXES'
    ob.empty_display_size = 0.5
    COLL.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    for k, v in (props or {}).items():
        ob[k] = v
    return ob


def make_obj(name, pieces, parent=None, props=None):
    """Fusiona piezas en UNA malla (pocos draw calls), triangula y aplica UV caja."""
    bm, slots = bmesh.new(), []
    uvd, uv_done = bm.loops.layers.uv.new("UVMap"), set()

    def slot(m):
        m = remap(m)
        if m not in slots:
            slots.append(m)
        return slots.index(m)
    for pc in pieces:
        prof = PROFILES.get(pc.cls, {})
        pc.bm.normal_update()
        has1 = any(f.material_index == 1 for f in pc.bm.faces)
        has2 = any(f.material_index == 2 for f in pc.bm.faces)
        m0 = slot(pc.mat)
        m1 = slot(prof.get("interior") or pc.mat) if has1 else m0
        m2 = slot("Mat_FX_Scorch") if has2 else m0
        sn = None
        if VARIANT == "Winter" and remap(pc.mat) not in NO_SNOW and pc.cls != "glass" and \
                any(f.material_index == 0 and f.normal.z > SNOW_NZ for f in pc.bm.faces):
            sn = slot("Mat_Snow")
        _merge(bm, pc.bm, m0, m1, m2, sn, uvd, uv_done)
    if not bm.faces:
        bm.free()
        return None
    res = bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
    for a, b in res.get("face_map", {}).items():            # triangulos heredan el "UV conservado"
        if b in uv_done:
            uv_done.add(a)
    bm.normal_update()
    box_uv(bm, [tex_tile(m) for m in slots], uv_done)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in slots:
        me.materials.append(get_mat(m))
    ob = bpy.data.objects.new(name, me)
    COLL.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    for k, v in (props or {}).items():
        ob[k] = v
    return ob


def merge_pieces(pcs):
    """Une piezas del mismo material en una sola (indices de material conservados)."""
    bm = bmesh.new()
    for pc in pcs:
        _merge(bm, pc.bm, 0, 1, 2)
    bm.normal_update()
    return Piece(bm, pcs[0].mat, pcs[0].cls, pcs[0].grain, False, pcs[0].tag)


def decimated_copy(pc, max_faces):
    """Copia simplificada (Decimate) de una pieza densa: fracturas rapidas de modelos externos."""
    if len(pc.bm.faces) <= max_faces:
        return pc.copy()
    me = bpy.data.meshes.new("_dec")
    pc.bm.to_mesh(me)
    ob = bpy.data.objects.new("_dec", me)
    COLL.objects.link(ob)
    mod = ob.modifiers.new("D", 'DECIMATE')
    mod.ratio = max(0.02, max_faces / float(len(pc.bm.faces)))
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me2)
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    bpy.data.meshes.remove(me2)
    bm.normal_update()
    return Piece(bm, pc.mat, pc.cls, pc.grain, pc.frac, pc.tag)


SHELL_MASS_T = 0.12          # espesor equivalente (m) para estimar la masa de mallas abiertas


def mass_of(pieces, override_density=None):
    m = 0.0
    for pc in pieces:
        d = override_density or PROFILES.get(pc.cls, {}).get("dens", 1000)
        if pc.tag == "shell":    # cascara (modelo externo): area x espesor equivalente
            m += sum(f.calc_area() for f in pc.bm.faces if f.material_index != 1) * SHELL_MASS_T * d
        else:
            m += pc.volume() * d
    return round(m, 2)


def hp_of(pieces, mass):
    cls = pieces[0].cls if pieces else "concrete"
    return round(max(1.0, mass * PROFILES.get(cls, {}).get("hp", 0.5)), 1)


def lod_obj(name, src_obj, ratio, parent):
    """LOD por Decimate (colapso) evaluado sin tocar el original."""
    ob = bpy.data.objects.new(name, src_obj.data.copy())
    COLL.objects.link(ob)
    ob.parent = parent
    if ratio < 0.999:
        mod = ob.modifiers.new("Decimate", 'DECIMATE')
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        old = ob.data
        ob.data = me
        bpy.data.meshes.remove(old)
    ob.data.name = name
    return ob


# ----------------------------------------------------------------------------------
# ESCENA / EXPORTACION
# ----------------------------------------------------------------------------------
def reset_scene(factory=False):
    global COLL
    if factory:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    else:
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        for me in list(bpy.data.meshes):
            bpy.data.meshes.remove(me)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    COLL = sc.collection


def export_asset(root, path_fbx, embed=False):
    if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    objs = [root] + list(root.children_recursive)
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = root
    # Aplicar TODAS las transformaciones (Location, Rotation, Scale)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    os.makedirs(os.path.dirname(path_fbx), exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=path_fbx,
        use_selection=True,
        apply_unit_scale=True,
        bake_space_transform=True,
        axis_forward='-Z',
        axis_up='Y',
        # extras compatibles (Unity): escala 1, props de usuario, sin huesos extra
        apply_scale_options='FBX_SCALE_ALL',
        object_types={'EMPTY', 'MESH'},
        use_custom_props=True,
        mesh_smooth_type='FACE',
        use_mesh_modifiers=True,
        add_leaf_bones=False,
        bake_anim=False,
        path_mode='COPY' if embed else 'RELATIVE',  # externos: texturas embebidas en el FBX
        embed_textures=embed,
    )


# ==================================================================================
# TEXTURAS PBR PROCEDURALES (numpy, tileables, a escala real) + VARIANTES ESTACIONALES
#  - Albedo + Normal map por material, guardados en OUTPUT_DIR/Textures (Unity las
#    encuentra por la carpeta "Textures" de un nivel superior al FBX).
#  - UV en metros: cada material repite su textura cada TEX_SPECS[m][2] metros.
# ==================================================================================
try:
    import numpy as np
except Exception:          # sin numpy: materiales de color plano
    np = None

TEXTURES = True
TEX_RES = 1024
VARIANTS = ["Temperate", "Desert", "Winter"]   # variantes estacionales a exportar
VARIANT = "Temperate"                           # variante activa (la fija main)
SNOW_NZ = 0.55                                  # caras con normal.z mayor -> nieve

# material -> (patron, parametros, metros por repeticion, intensidad normal)
TEX_SPECS = {
    "Mat_Crate_Base": ("planks", dict(n=6, gap=(0.02, 0.025, 0.01)), 1.0, 2.0),
    "Mat_Wood_Plank": ("planks", dict(n=5, gap=(0.03, 0.02, 0.01)), 1.0, 2.0),
    "Mat_Wood_Beam": ("planks", dict(n=2, gap=(0.03, 0.02, 0.01)), 1.0, 2.5),
    "Mat_Floor_Wood": ("planks", dict(n=8, gap=(0.03, 0.02, 0.01)), 1.0, 1.5),
    "Mat_Door_Wood": ("planks", dict(n=4, gap=(0.02, 0.01, 0.0)), 1.0, 1.5),
    "Mat_Wood_Interior": ("bark", dict(stretch=10, ridge=0.2), 0.5, 2.0),
    "Mat_Wood_Charred": ("charred", {}, 1.0, 3.0),
    "Mat_Log_Wood": ("bark", dict(stretch=8, ridge=0.5), 1.0, 4.0),
    "Mat_Pole_Wood": ("bark", dict(stretch=14, ridge=0.25), 1.0, 2.0),
    "Mat_Concrete_Base": ("concrete", {}, 2.0, 1.5),
    "Mat_Concrete_Interior": ("concrete", dict(pits=0.7, rough=1.6), 1.0, 4.0),
    "Mat_Brick_Wall": ("bricks", dict(rows=12, cols=4, mortar=0.012, mcol=(0.55, 0.52, 0.48)), 0.9, 3.0),
    "Mat_Brick_Interior": ("bricks", dict(rows=12, cols=4, mortar=0.014, mcol=(0.6, 0.58, 0.55), broken=True), 0.9, 4.0),
    "Mat_Mudbrick": ("bricks", dict(rows=8, cols=4, mortar=0.025, mcol=(0.55, 0.43, 0.30), plaster=0.45), 1.6, 3.5),
    "Mat_CinderBlock": ("bricks", dict(rows=8, cols=4, mortar=0.01, mcol=(0.62, 0.62, 0.6), pits=True), 1.6, 2.5),
    "Mat_Plaster_Wall": ("plaster", {}, 2.0, 1.5),
    "Mat_Plaster_Desert": ("plaster", dict(cracks=0.6), 2.0, 2.0),
    "Mat_Roof_Tile": ("rooftiles", dict(rows=7, cols=5), 1.4, 4.0),
    "Mat_Roof_Metal": ("corrugated", dict(period=8), 1.0, 3.0),
    "Mat_Container_Paint": ("metal_paint", dict(chips=0.25, rust=0.3), 2.0, 1.0),
    "Mat_Barrel_Paint": ("metal_paint", dict(chips=0.3, rust=0.4), 1.0, 1.0),
    "Mat_Military_Olive": ("metal_paint", dict(chips=0.12, dust=0.35), 2.5, 1.0),
    "Mat_Military_Green": ("camo", dict(cols=((0.12, 0.17, 0.10), (0.19, 0.14, 0.09), (0.03, 0.03, 0.03)), ratio=(0.52, 0.66)), 3.0, 1.0),
    "Mat_Military_Desert": ("metal_paint", dict(chips=0.1, dust=0.5), 2.5, 1.0),
    "Mat_Military_Grey": ("metal_paint", dict(chips=0.08, dust=0.15), 2.5, 0.8),
    "Mat_Military_Navy": ("metal_paint", dict(chips=0.1, rust=0.25), 3.0, 0.8),
    "Mat_Military_Winter": ("camo", dict(cols=((0.82, 0.83, 0.82), (0.22, 0.24, 0.17), (0.55, 0.56, 0.53)), ratio=(0.6, 0.55)), 3.0, 1.0),
    "Mat_Military_RuGreen": ("metal_paint", dict(chips=0.12, dust=0.3), 2.5, 1.0),
    "Mat_Metal_Gunmetal": ("metal_paint", dict(chips=0.2, dust=0.1), 1.0, 0.8),
    "Mat_Metal_Steel": ("metal_paint", dict(chips=0.0, dust=0.05, brushed=True), 1.0, 0.6),
    "Mat_Metal_Charred": ("charred", dict(metal=True), 2.0, 2.5),
    "Mat_Track_Steel": ("track", dict(links=7), 1.0, 5.0),
    "Mat_Rubber_Tire": ("rubber", {}, 0.5, 4.0),
    "Mat_Fabric_Sandbag": ("fabric", dict(weave=90), 1.0, 2.0),
    "Mat_Fabric_Canvas": ("fabric", dict(weave=60), 1.5, 1.5),
    "Mat_Sand_Fill": ("sand", dict(ripple=0.0), 1.0, 2.0),
    "Mat_Hesco_Mesh": ("metal_paint", dict(chips=0.3, rust=0.2), 1.0, 0.5),
    "Mat_Terrain_Grass": ("grass", {}, 4.0, 2.0),
    "Mat_Terrain_Soil": ("soil", {}, 2.0, 3.0),
    "Mat_Terrain_Sand": ("sand", dict(ripple=1.0), 4.0, 2.5),
    "Mat_Terrain_Snow": ("snow", {}, 4.0, 1.5),
    "Mat_Snow": ("snow", {}, 2.0, 1.5),
    "Mat_Rock_Base": ("rock", {}, 2.0, 4.0),
    "Mat_Rock_Interior": ("rock", dict(fresh=True), 1.0, 3.0),
    "Mat_Bark_Pine": ("bark", dict(stretch=6, ridge=0.6), 1.0, 5.0),
    "Mat_Bark_Oak": ("bark", dict(stretch=4, ridge=0.7), 1.0, 5.0),
    "Mat_Bark_Palm": ("bark", dict(stretch=1.2, ridge=0.8, rings=True), 1.0, 5.0),
    "Mat_Bark_Dead": ("bark", dict(stretch=8, ridge=0.5), 1.0, 4.0),
    "Mat_Leaves_Pine": ("leaves", dict(fine=2.0), 1.0, 3.0),
    "Mat_Leaves_Oak": ("leaves", {}, 1.5, 3.0),
    "Mat_Leaves_Palm": ("leaves", dict(stripes=True), 1.0, 2.0),
    "Mat_Leaves_Bush": ("leaves", {}, 1.0, 3.0),
    "Mat_Leaves_Dry": ("leaves", dict(dry=True), 1.0, 3.0),
    "Mat_Grass_Blade": ("leaves", dict(stripes=True), 0.5, 1.0),
    "Mat_FX_Scorch": ("charred", dict(soot=True), 2.0, 1.5),
    "Mat_Rebar_Rust": ("metal_paint", dict(chips=0.0, rust=1.0), 0.3, 2.0),
    "Mat_Car_Paint": ("metal_paint", dict(chips=0.05, dust=0.25), 2.0, 0.5),
    "Mat_Civil_White": ("metal_paint", dict(chips=0.08, dust=0.4), 2.0, 0.5),
}

VARIANT_REMAP = {
    "Desert": {"Mat_Terrain_Grass": "Mat_Terrain_Sand", "Mat_Military_Green": "Mat_Military_Desert",
               "Mat_Military_Olive": "Mat_Military_Desert", "Mat_Military_RuGreen": "Mat_Military_Desert",
               "Mat_Plaster_Wall": "Mat_Plaster_Desert", "Mat_Brick_Wall": "Mat_Mudbrick",
               "Mat_Leaves_Oak": "Mat_Leaves_Dry", "Mat_Leaves_Bush": "Mat_Leaves_Dry", "Mat_Grass_Blade": "Mat_Leaves_Dry",
               "Mat_Fabric_Canvas": "Mat_Fabric_Sandbag", "Mat_Roof_Tile": "Mat_Plaster_Desert",
               "Mat_Brick_Interior": "Mat_Mudbrick"},
    "Winter": {"Mat_Terrain_Grass": "Mat_Terrain_Snow", "Mat_Military_Green": "Mat_Military_Winter",
               "Mat_Military_Olive": "Mat_Military_Winter", "Mat_Military_Desert": "Mat_Military_Winter",
               "Mat_Military_RuGreen": "Mat_Military_Winter", "Mat_Leaves_Oak": "Mat_Leaves_Dry",
               "Mat_Grass_Blade": "Mat_Leaves_Dry"},
}
NO_SNOW = {"Mat_Glass_Window", "Mat_Glass_Canopy", "Mat_Light_Lens", "Mat_FX_Scorch", "Mat_Rotor_Blade"}


def remap(m):
    return VARIANT_REMAP.get(VARIANT, {}).get(m, m)


def tex_tile(m):
    return TEX_SPECS.get(m, (None, None, UV_TILE, 0))[2] if TEXTURES else UV_TILE


def _lin2srgb(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def _noise(rng, cy, cx, oct=4, gain=0.5, res=None):
    """fBm de ruido de valor PERIODICO (tileable) en [0,1]."""
    res = res or TEX_RES
    out = np.zeros((res, res), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(oct):
        ny, nx = max(1, int(cy * 2 ** o)), max(1, int(cx * 2 ** o))
        g = rng.random((ny, nx)).astype(np.float32)
        y = np.arange(res) * ny / res
        x = np.arange(res) * nx / res
        y0, x0 = y.astype(int), x.astype(int)
        fy, fx = y - y0, x - x0
        fy, fx = (fy * fy * (3 - 2 * fy))[:, None], (fx * fx * (3 - 2 * fx))[None, :]
        y1, x1 = (y0 + 1) % ny, (x0 + 1) % nx
        a, b, c, d = g[y0][:, x0], g[y0][:, x1], g[y1][:, x0], g[y1][:, x1]
        out += ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy) * amp
        tot += amp
        amp *= gain
    return out / tot


def _uv(res=None):
    res = res or TEX_RES
    t = (np.arange(res, dtype=np.float32) + 0.5) / res
    return np.meshgrid(t, t)          # u (columnas), v (filas, abajo->arriba)


def _mix(a, b, t):
    t = t[..., None] if np.ndim(t) == 2 else t
    return a * (1 - t) + b * t


def _col(c, shape):
    return np.ones(shape + (3,), np.float32) * np.array(c, np.float32)


def _pattern(kind, base, p, rng):
    """Devuelve (albedo lineal HxWx3, altura HxW) para un patron."""
    R = TEX_RES
    sh = (R, R)
    u, v = _uv()
    n1, n2 = _noise(rng, 4, 4, 5), _noise(rng, 16, 16, 4)
    col = _col(base, sh)
    h = n1 * 0.3
    if kind in ("bricks",):
        rows, cols, mw = p["rows"], p["cols"], p["mortar"]
        row = np.floor(v * rows)
        uu = u * cols + (row % 2) * 0.5
        bi = (np.floor(uu) % cols).astype(int)
        fu, fv = uu - np.floor(uu), v * rows - row
        tint = rng.uniform(0.78, 1.18, (rows, cols)).astype(np.float32)[row.astype(int), bi]
        eu, ev = mw * cols, mw * rows
        dist = np.minimum(np.minimum(fu, 1 - fu) / max(eu, 1e-4), np.minimum(fv, 1 - fv) / max(ev, 1e-4))
        brick = np.clip((dist - 0.6) * 3.0, 0, 1)
        col = col * (tint * (0.85 + 0.3 * n2))[..., None]
        if p.get("pits"):
            col *= (1 - 0.25 * (_noise(rng, 64, 64, 2) > 0.72))[..., None]
        col = _mix(_col(p["mcol"], sh) * (0.8 + 0.4 * n2)[..., None], col, brick)
        h = brick * 0.6 + n2 * 0.25 + (1 - brick) * 0.1 * n1
        if p.get("plaster"):
            pl = np.clip((_noise(rng, 3, 3, 5) - (1 - p["plaster"])) * 6, 0, 1)
            col = _mix(col, _col(base, sh) * 1.12 * (0.9 + 0.2 * n1)[..., None], pl)
            h = h * (1 - pl) + (0.55 + 0.1 * n2) * pl
        if p.get("broken"):
            col *= (0.8 + 0.3 * _noise(rng, 24, 24, 3))[..., None]
    elif kind == "planks":
        n = p["n"]
        idx = np.floor(v * n)
        tint = rng.uniform(0.8, 1.15, n).astype(np.float32)[idx.astype(int)]
        grain = _noise(rng, n * 10, 2, 4)
        fv = v * n - idx
        gap = np.clip(np.minimum(fv, 1 - fv) / 0.04, 0, 1)
        col = col * (tint * (0.8 + 0.35 * grain))[..., None] * (0.55 + 0.45 * gap)[..., None]
        knots = (_noise(rng, 16, 16, 2) > 0.87).astype(np.float32)
        col *= (1 - 0.25 * knots)[..., None]
        h = gap * 0.7 + grain * 0.3
    elif kind == "concrete":
        streak = _noise(rng, 1, 18, 3)
        pits = (_noise(rng, 80, 80, 2) > p.get("pits", 0.78)).astype(np.float32)
        col = col * (0.82 + 0.3 * n1 + 0.1 * n2)[..., None] * (1 - 0.18 * streak)[..., None]
        col *= (1 - 0.35 * pits)[..., None]
        h = n2 * 0.4 * p.get("rough", 1.0) - pits * 0.3 + n1 * 0.2
    elif kind == "plaster":
        cr = np.abs(_noise(rng, 6, 6, 4) - 0.5) < 0.012 * (1 + p.get("cracks", 0.0))
        dirt = _noise(rng, 2, 6, 3)
        col = col * (0.88 + 0.22 * n1 + 0.08 * n2)[..., None] * (1 - 0.2 * dirt)[..., None]
        col *= (1 - 0.4 * cr)[..., None]
        h = n2 * 0.35 - cr * 0.5
    elif kind == "rooftiles":
        rows, cols = p["rows"], p["cols"]
        row = np.floor(v * rows)
        uu = u * cols + (row % 2) * 0.5
        fv = v * rows - row
        fu = uu - np.floor(uu)
        tint = rng.uniform(0.8, 1.2, (rows, cols)).astype(np.float32)[row.astype(int), (np.floor(uu) % cols).astype(int)]
        shade = 0.65 + 0.45 * fv
        edge = np.clip(np.minimum(fu, 1 - fu) / 0.03, 0, 1)
        col = col * (tint * shade * (0.6 + 0.4 * edge) * (0.9 + 0.2 * n2))[..., None]
        h = fv * 0.8 * edge + n2 * 0.1
    elif kind == "corrugated":
        s = 0.5 + 0.5 * np.sin(u * 2 * np.pi * p["period"])
        rust = np.clip((_noise(rng, 3, 8, 4) - 0.62) * 4, 0, 1)
        col = _mix(col * (0.85 + 0.25 * s)[..., None], _col((0.30, 0.13, 0.05), sh), rust * 0.7)
        h = s
    elif kind == "metal_paint":
        chips = np.clip((_noise(rng, 24, 24, 3) - (1 - p.get("chips", 0.1) * 0.35)) * 12, 0, 1)
        dust = np.clip(_noise(rng, 2, 3, 4) - 0.35, 0, 1) * p.get("dust", 0.0)
        col = col * (0.9 + 0.18 * n1)[..., None]
        if p.get("brushed"):
            col *= (0.9 + 0.2 * _noise(rng, 64, 1, 2))[..., None]
        col = _mix(col, _col((0.55, 0.45, 0.32), sh), dust)
        col = _mix(col, _col((0.18, 0.17, 0.16), sh), chips)
        if p.get("rust"):
            streak = _noise(rng, 1, 14, 3)
            rust = np.clip((_noise(rng, 4, 4, 5) * 0.7 + streak * 0.3 - (1 - 0.35 * p["rust"])) * 5, 0, 1)
            col = _mix(col, _col((0.28, 0.11, 0.04), sh) * (0.7 + 0.6 * n2)[..., None], rust)
        h = n2 * 0.15 - chips * 0.3
    elif kind == "camo":
        c0, c1, c2 = p["cols"]
        r1, r2 = p.get("ratio", (0.5, 0.72))
        a = _noise(rng, 3, 4, 5)
        b = _noise(rng, 4, 3, 5)
        col = _col(c0, sh)
        col = _mix(col, _col(c1, sh), np.clip((a - r1) * 25, 0, 1))
        col = _mix(col, _col(c2, sh), np.clip((b - r2) * 25, 0, 1))
        col *= (0.9 + 0.15 * n2)[..., None]
        h = n2 * 0.1
    elif kind == "track":
        L = p["links"]
        fv = v * L - np.floor(v * L)
        pad = np.clip(np.minimum(fv - 0.08, 0.86 - fv) * 12, 0, 1)
        guide = (np.abs(u - 0.5) < 0.06).astype(np.float32)
        col = col * (0.5 + 0.6 * pad)[..., None] * (0.85 + 0.3 * n2)[..., None]
        col = _mix(col, _col((0.35, 0.33, 0.30), sh), guide * pad * 0.6)
        h = pad * 0.8 + guide * 0.3
    elif kind == "rubber":
        blk = ((np.floor(u * 12) + np.floor(v * 6)) % 2).astype(np.float32)
        col = col * (0.8 + 0.4 * n2)[..., None] * (0.85 + 0.15 * blk)[..., None]
        h = blk * 0.6 + n2 * 0.2
    elif kind == "fabric":
        w = p["weave"]
        wv = (np.sin(u * 2 * np.pi * w) * np.sin(v * 2 * np.pi * w)) * 0.5 + 0.5
        stain = np.clip(_noise(rng, 3, 3, 5) - 0.55, 0, 1) * 1.5
        col = col * (0.85 + 0.2 * wv)[..., None] * (1 - 0.35 * stain)[..., None] * (0.9 + 0.15 * n1)[..., None]
        h = wv * 0.5 + n2 * 0.2
    elif kind == "sand":
        rip = 0.5 + 0.5 * np.sin((v * 14 + _noise(rng, 2, 2, 3) * 4) * 2 * np.pi) * p.get("ripple", 1.0)
        grains = _noise(rng, 128, 128, 1)
        col = col * (0.9 + 0.12 * rip + 0.1 * grains + 0.1 * n1)[..., None]
        h = rip * 0.5 + grains * 0.2
    elif kind == "snow":
        col = col * (0.94 + 0.06 * n1 + 0.04 * n2)[..., None]
        col[..., 2] *= 1.02
        h = n1 * 0.5 + n2 * 0.2
    elif kind == "grass":
        patches = _noise(rng, 3, 3, 4)
        dry = np.clip((patches - 0.6) * 3, 0, 1)
        blades = _noise(rng, 96, 96, 2)
        col = col * (0.75 + 0.5 * blades)[..., None]
        col = _mix(col, _col((0.42, 0.38, 0.16), sh) * (0.8 + 0.4 * blades)[..., None], dry * 0.7)
        col = _mix(col, _col((0.30, 0.22, 0.14), sh), np.clip((n2 - 0.75) * 4, 0, 1) * 0.5)
        h = blades * 0.6 + n1 * 0.2
    elif kind == "soil":
        peb = (_noise(rng, 48, 48, 2) > 0.74).astype(np.float32)
        col = col * (0.8 + 0.4 * n1)[..., None]
        col = _mix(col, _col((0.42, 0.40, 0.36), sh), peb * 0.8)
        h = n2 * 0.4 + peb * 0.6
    elif kind == "rock":
        ridged = 1 - np.abs(_noise(rng, 5, 5, 5) * 2 - 1)
        crack = np.clip((ridged - 0.93) * 20, 0, 1)
        col = col * (0.75 + 0.45 * n1 + 0.1 * n2)[..., None] * (1 - 0.6 * crack)[..., None]
        if p.get("fresh"):
            col *= (0.95 + 0.15 * _noise(rng, 64, 64, 1))[..., None]
        h = n1 * 0.6 + n2 * 0.3 - crack * 0.5
    elif kind == "bark":
        st = p["stretch"]
        fib = _noise(rng, 2, 2 * st * 4, 4)
        ridge = 1 - np.abs(fib * 2 - 1)
        col = col * (0.6 + 0.6 * ridge * p["ridge"] + 0.3 * n2)[..., None]
        if p.get("rings"):
            col *= (0.8 + 0.25 * (np.sin(v * 2 * np.pi * 10) * 0.5 + 0.5))[..., None]
        h = ridge * p["ridge"] + n2 * 0.2
    elif kind == "leaves":
        cl = _noise(rng, 24 * p.get("fine", 1.0), 24 * p.get("fine", 1.0), 3)
        col = col * (0.6 + 0.7 * cl)[..., None]
        if p.get("stripes"):
            col *= (0.85 + 0.2 * np.sin(u * 2 * np.pi * 40))[..., None]
        if p.get("dry"):
            col = _mix(col, _col((0.25, 0.15, 0.07), sh), np.clip((n1 - 0.5) * 3, 0, 1) * 0.6)
        h = cl
    elif kind == "asphalt":
        agg = _noise(rng, 160, 160, 1)
        stones = np.clip((agg - 0.68) * 8, 0, 1)
        ridged = 1 - np.abs(_noise(rng, 4, 4, 5) * 2 - 1)
        crack = np.clip((ridged - 0.965) * 30, 0, 1) * p.get("cracks", 1.0)
        patch = np.clip((_noise(rng, 2, 2, 4) - 0.62) * 5, 0, 1)
        col = col * (0.8 + 0.35 * agg + 0.12 * n1)[..., None]
        col = _mix(col, _col((0.20, 0.20, 0.19), sh), stones * 0.45)
        col = _mix(col, _col((0.035, 0.035, 0.035), sh), np.clip(patch * 0.55 + crack * 0.85, 0, 1))
        h = agg * 0.35 + stones * 0.3 - crack * 0.6 + n2 * 0.15
    elif kind == "charred":
        ash = np.clip((_noise(rng, 6, 6, 4) - 0.55) * 3, 0, 1)
        ember = np.clip((n2 - 0.8) * 5, 0, 1) * (0 if p.get("soot") else 1)
        col = col * (0.6 + 0.6 * n1)[..., None]
        col = _mix(col, _col((0.25, 0.24, 0.22), sh), ash * (0.12 if p.get("soot") else 0.6 if not p.get("metal") else 0.4))
        col = _mix(col, _col((0.18, 0.06, 0.02), sh), ember * 0.6)
        h = n2 * 0.5 + ash * 0.3
    else:
        col = col * (0.85 + 0.3 * n1)[..., None]
    return np.clip(col, 0, 1), h.astype(np.float32)


def _save_img(name, rgb, path, non_color=False):
    R = rgb.shape[0]
    img = bpy.data.images.get(name) or bpy.data.images.new(name, R, R, alpha=False)
    if img.size[0] != R:
        img.scale(R, R)
    if non_color:                     # antes de escribir pixeles (cambiarlo despues vacia el buffer)
        try:
            img.colorspace_settings.name = 'Non-Color'
        except Exception:
            pass
    rgba = np.ones((R, R, 4), np.float32)
    rgba[..., :3] = rgb
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    return img


def _photo_set(mat_name, folder):
    """Texturas fotoescaneadas CC0 (ambientCG) si fueron descargadas para este material."""
    src = os.path.join(PHOTO_TEX_DIR, mat_name)
    if not os.path.isdir(src):
        return None
    files = []
    for root_, _d, fs in os.walk(src):
        files += [os.path.join(root_, f) for f in fs]
    col = next((f for f in files if re.search(r"_Color\.(jpg|png)$", f, re.I)), None)
    nrm = next((f for f in files if re.search(r"_NormalGL\.(jpg|png)$", f, re.I)), None)
    if not col or not nrm:
        return None
    import shutil
    out = []
    for f, tag in ((col, "D"), (nrm, "N")):
        dst = os.path.join(folder, "%s_%s%s" % (mat_name, tag, os.path.splitext(f)[1].lower()))
        if not os.path.exists(dst):
            shutil.copyfile(f, dst)
        im = bpy.data.images.load(dst, check_existing=True)
        if tag == "N":
            try:
                im.colorspace_settings.name = 'Non-Color'
            except Exception:
                pass
        out.append(im)
    return tuple(out)


def texture_set(mat_name):
    """Genera (o reutiliza del disco) albedo + normal de un material."""
    spec = TEX_SPECS.get(mat_name)
    if not (TEXTURES and np is not None and spec):
        return None, None
    folder = os.path.join(OUTPUT_DIR, "Textures")
    os.makedirs(folder, exist_ok=True)
    photo = _photo_set(mat_name, folder)
    if photo:
        return photo
    pd, pn = os.path.join(folder, f"{mat_name}_D.png"), os.path.join(folder, f"{mat_name}_N.png")
    if os.path.exists(pd) and os.path.exists(pn):
        imd = bpy.data.images.load(pd, check_existing=True)
        imn = bpy.data.images.load(pn, check_existing=True)
        try:
            imn.colorspace_settings.name = 'Non-Color'
        except Exception:
            pass
        return imd, imn
    kind, params, tile, strength = spec
    rgb_lin = MATS.get(mat_name, ((0.5, 0.5, 0.5),))[0]
    rng = np.random.default_rng(sum(ord(c) * (i + 1) for i, c in enumerate(mat_name)))
    col, h = _pattern(kind, rgb_lin, params, rng)
    g = strength * TEX_RES / 512.0
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * g
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * g
    nrm = np.dstack((-dx, -dy, np.ones_like(h)))
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    return (_save_img(f"{mat_name}_D", _lin2srgb(col), pd), _save_img(f"{mat_name}_N", nrm * 0.5 + 0.5, pn, True))


def wire_textures(m, bsdf):
    imd, imn = texture_set(m.name)
    if imd is None:
        return
    nt = m.node_tree
    td = nt.nodes.new("ShaderNodeTexImage")
    td.image = imd
    td.location = (-600, 300)
    nt.links.new(td.outputs["Color"], bsdf.inputs["Base Color"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = imn
    tn.location = (-600, -100)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (-300, -100)
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


# ----------------------------------------------------------------------------------
# MODELO DE DATOS
# ----------------------------------------------------------------------------------
class Part:
    """kind: element | hull | turret | gun | wheel | track | rotor | wing | tail |
    detail | glass | door | trunk | branch | foliage | tile ... ; tags: set de roles."""

    def __init__(self, name, pieces, cls=None, kind="element", pivot=None, axis=None,
                 joint="fixed", tags=(), alt=None):
        self.name, self.pieces, self.kind = name, [p for p in pieces if p is not None], kind
        self.cls = cls or (self.pieces[0].cls if self.pieces and self.pieces[0].cls else "concrete")
        for pc in self.pieces:
            if pc.cls is None:
                pc.cls = self.cls
        self.pivot = V(pivot) if pivot is not None else None
        self.axis = V(axis) if axis is not None else None
        self.joint, self.tags, self.alt = joint, set(tags) | {kind}, alt or {}
        self.mass = 0.0

    def all_pieces(self):
        return self.pieces + [p for v in self.alt.values() for p in v]


class Asset:
    def __init__(self, name, category, mode, parts, **opt):
        self.name, self.category, self.mode, self.parts, self.opt = name, category, mode, parts, opt


def asset_bounds(parts):
    lo, hi = V(1e9, 1e9, 1e9), V(-1e9, -1e9, -1e9)
    for part in parts:
        for pc in part.pieces:
            a, b = pc.bounds()
            lo = V(min(lo.x, a.x), min(lo.y, a.y), min(lo.z, a.z))
            hi = V(max(hi.x, b.x), max(hi.y, b.y), max(hi.z, b.z))
    return lo, hi


def orient_and_pivot(asset):
    """Vehiculos: frente +X -> -Y (=> +Z en Unity). Despues pivote al centro de la base."""
    M = Matrix.Rotation(-math.pi / 2, 4, 'Z') if asset.opt.get("forward_x", False) else Matrix.Identity(4)
    lo, hi = None, None
    for part in asset.parts:
        for pc in part.all_pieces():
            pc.transform(M)
        if part.pivot is not None:
            part.pivot = M @ part.pivot
        if part.axis is not None:
            part.axis = (M.to_3x3() @ part.axis).normalized()
    lo, hi = asset_bounds(asset.parts)
    T = Matrix.Translation(V(-(lo.x + hi.x) * 0.5, -(lo.y + hi.y) * 0.5, -lo.z))
    for part in asset.parts:
        for pc in part.all_pieces():
            pc.transform(T)
        if part.pivot is not None:
            part.pivot = T @ part.pivot
    asset.opt["_M"], asset.opt["_T"] = M, T
    return asset_bounds(asset.parts)


def auto_impacts(lo, hi, rng, n):
    pts = []
    for _ in range(n):
        side = rng.randrange(4)
        z = lo.z + (hi.z - lo.z) * rng.uniform(0.25, 0.7)
        if side < 2:
            pts.append(V(lo.x if side == 0 else hi.x, rng.uniform(lo.y, hi.y) * 0.8, z))
        else:
            pts.append(V(rng.uniform(lo.x, hi.x) * 0.8, lo.y if side == 2 else hi.y, z))
    return pts


def group_by_grid(pieces, cell=4.0):
    groups = {}
    for pc in pieces:
        c = pc.center()
        groups.setdefault((int(math.floor(c.x / cell)), int(math.floor(c.y / cell))), []).append(pc)
    return list(groups.values())


def scale_about(pc, s):
    c = pc.center()
    return pc.transform(Matrix.Translation(c) @ Matrix.Diagonal((s, s, s, 1)) @ Matrix.Translation(-c))


def debris_set(name, cls, parent, rng, man, n=8, size=(0.5, 0.35, 0.18)):
    mat = {"metal": "Mat_Metal_Charred", "wood": "Mat_Wood_Plank", "earth": "Mat_Terrain_Soil",
           "glass": "Mat_Glass_Window", "foliage": "Mat_Leaves_Dry"}.get(cls, PROFILES[cls]["interior"] or "Mat_Rock_Base")
    src = box((size[0], size[1], size[2] if cls != "metal" else 0.015), mat=mat, cls=cls,
              grain="x" if cls == "wood" else None)
    g = empty(f"{name}_Debris", parent, {"dst_role": "state", "dst_state": 9})
    for k, pc in enumerate(voronoi(src, n, rng)):
        lo, hi = pc.bounds()
        pc.transform(Matrix.Translation(V(k * 0.6 - n * 0.3, 0, 0) - V((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)))
        m = mass_of([pc])
        nm = f"{name}_Debris_{k:02d}"
        make_obj(nm, [pc], g, {"dst_role": "debris", "dst_class": cls, "dst_mass": m})
        man["debris"].append({"name": nm, "class": cls, "mass": m})


# ----------------------------------------------------------------------------------
# ESTADOS: ESTRUCTURAS / PROPS (fractura Voronoi + grafo + colapso)
# ----------------------------------------------------------------------------------
def structure_states(asset, root, rng, man, lo, hi):
    name, parts = asset.name, asset.parts
    size = hi - lo
    impacts = asset.opt.get("impacts") or auto_impacts(lo, hi, rng, asset.opt.get("n_impacts", 2))
    rad = asset.opt.get("dmg_r", max(0.25, 0.2 * max(size.x, size.y, size.z)))
    man["impacts"] = [unity(p) for p in impacts]
    # ---- L1
    chunks = []
    for ei, part in enumerate(parts):
        prof = PROFILES[part.cls]
        rigid = {}
        for pc in part.pieces:
            if not pc.frac:
                rigid.setdefault(pc.mat, []).append(pc)
        for pcs in rigid.values():                      # herrajes/alambres: 1 chunk rigido
            chunks.append({"pc": merge_pieces(pcs), "elem": ei})
        for pc in part.pieces:
            if not pc.frac:
                continue
            if pc.mason is not None:                        # mamposteria: rotura por juntas
                for cl, blocks in masonry_cells(pc, rng, asset.opt.get("mason_blocks", 6)):
                    chunks.append({"pc": cl, "elem": ei, "blocks": blocks})
                continue
            n = chunk_count(pc, prof["chunks"], asset.opt.get("chunk_scale", 1.0))
            if len(pc.bm.faces) > FRACTURE_MAX_FACES:                  # modelos externos densos
                pc = decimated_copy(pc, FRACTURE_MAX_FACES)
            plo, phi = pc.bounds()
            near = [p for p in impacts if all(plo[k] - 1.5 <= p[k] <= phi[k] + 1.5 for k in range(3))]
            imp = min(near, key=lambda p: (p - pc.center()).length) if near else None
            for c in voronoi(pc, n, rng, impact=imp):
                chunks.append({"pc": c, "elem": ei})
    nb = contact_graph([[c["pc"]] for c in chunks])
    gz = -asset.opt.get("ground_offset", 0.0)              # nivel del terreno (trincheras: profundidad)
    anch = [c["pc"].bounds()[0].z < gz + 0.03 for c in chunks]
    pits = [p.pieces[0].bounds() for p in parts if p.kind == "floor"]

    def floor_z(x, y):                                       # dentro de la zanja cae al fondo
        return 0.0 if any(lo_[0] - 0.6 <= x <= hi_[0] + 0.6 and lo_[1] - 0.6 <= y <= hi_[1] + 0.6 for lo_, hi_ in pits) else gz
    g1 = empty(f"{name}_Chunks_L1", root, {"dst_role": "state", "dst_state": 3})
    g2 = empty(f"{name}_Chunks_L2", root, {"dst_role": "state", "dst_state": 4})
    for ci, c in enumerate(chunks):
        pc, part = c["pc"], parts[c["elem"]]
        m = mass_of([pc])
        nm = f"{name}_C{ci:03d}"
        make_obj(nm, [pc], g1, {"dst_role": "chunk", "dst_id": ci, "dst_level": 1, "dst_parent": -1,
                                "dst_element": part.name, "dst_class": pc.cls, "dst_mass": m,
                                "dst_hp": hp_of([pc], m), "dst_anchored": int(anch[ci]),
                                "dst_neighbors": ",".join(map(str, sorted(nb[ci])))})
        rec = {"name": nm, "id": ci, "element": part.name, "class": pc.cls, "mass": m,
               "center": unity(pc.center()), "anchored": anch[ci], "neighbors": sorted(nb[ci]), "children": []}
        subs = None
        if c.get("blocks") and asset.opt.get("mason_l2") and len(c["blocks"]) > 1:
            subs = c["blocks"]                                # L2 = bloques individuales
        elif PROFILES[pc.cls]["l2"] and pc.volume() > L2_MIN_VOLUME:
            subs = voronoi(pc, rng.randint(3, 5), rng)
        if subs:
            snb = contact_graph([[s] for s in subs]) if len(subs) > 1 else [set()]
            for k, s in enumerate(subs):
                sm = mass_of([s])
                snm = f"{nm}_{k}"
                make_obj(snm, [s], g2, {"dst_role": "chunk", "dst_id": ci * 100 + k, "dst_level": 2,
                                        "dst_parent": ci, "dst_element": part.name, "dst_class": s.cls,
                                        "dst_mass": sm, "dst_hp": hp_of([s], sm),
                                        "dst_anchored": int(s.bounds()[0].z < 0.03),
                                        "dst_neighbors": ",".join(str(ci * 100 + j) for j in sorted(snb[k]))})
                rec["children"].append(snm)
        man["chunks"].append(rec)
    alls = set(range(len(chunks)))
    ctr = V((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0)

    def build_state(gname, sidx, alive, extra_lost, suffix, scorch_it):
        g = empty(f"{name}_{gname}", root, {"dst_role": "state", "dst_state": sidx})
        keep = grounded(nb, anch, alive)            # lo que pierde apoyo tambien cae
        lost = (alls - keep)
        per_elem = {}
        for ci in keep:
            pc = chunks[ci]["pc"].copy()
            if scorch_it:
                for p in impacts:
                    scorch(pc, p, rad * 1.35, rng, prob=0.6)
            per_elem.setdefault(chunks[ci]["elem"], []).append(pc)
            if PROFILES[pc.cls]["rebar"] and any(j in lost for j in nb[ci]) and rng.random() < 0.6:
                per_elem[chunks[ci]["elem"]] += rebar(pc, rng)
        for ei, pcs in per_elem.items():
            make_obj(f"{parts[ei].name}_{suffix}", pcs, g, {"dst_role": "element", "dst_class": parts[ei].cls})
        fall = []
        for ci in sorted(lost):
            if ci in extra_lost and rng.random() < 0.55:
                continue                              # pulverizado por la explosion
            if chunks[ci].get("blocks"):              # mamposteria: caen bloques sueltos
                fall += [b.copy() for b in chunks[ci]["blocks"] if rng.random() < 0.9]
                continue
            pc = chunks[ci]["pc"].copy()
            if ci in extra_lost:
                scale_about(pc, rng.uniform(0.45, 0.75))
            fall.append(pc)
        rubble = settle(fall, rng, ctr, spread=asset.opt.get("spread", 0.35), floor=floor_z)
        for k, grp in enumerate(group_by_grid(rubble, asset.opt.get("rubble_cell", 4.0))):
            extra = []
            if len(grp) > 3 and grp[0].cls in ("concrete", "brick", "plaster", "rock", "earth", "fabric", "cinder", "mudbrick"):
                blo = V(min(p.bounds()[0].x for p in grp), min(p.bounds()[0].y for p in grp), 0)
                bhi = V(max(p.bounds()[1].x for p in grp), max(p.bounds()[1].y for p in grp),
                        max(p.bounds()[1].z for p in grp))
                bc = (blo + bhi) * 0.5
                rr = max(bhi.x - blo.x, bhi.y - blo.y) * 0.45
                extra.append(mound(V(bc.x, bc.y, floor_z(bc.x, bc.y)), rr, max(0.08, (bhi.z - floor_z(bc.x, bc.y)) * 0.35),
                                   PROFILES[grp[0].cls]["interior"] or grp[0].mat, rng, grp[0].cls))
            for pc in grp:
                if PROFILES[pc.cls]["rebar"] and rng.random() < 0.25:
                    extra += rebar(pc, rng, 1)
            make_obj(f"{name}_{suffix}_Rubble_{k:02d}", grp + extra, g, {"dst_role": "rubble"})
        return len(keep), len(lost)

    # ---- Estado 1: impactos (huecos) + perdida de apoyo
    hole = {ci for ci in alls if min((chunks[ci]["pc"].center() - p).length for p in impacts) < rad * rng.uniform(0.8, 1.25)}
    k1 = build_state("Damaged", 1, alls - hole, hole, "Dmg", True)
    # ---- Estado 2: ruina (solo quedan munones anclados bajo un perfil de altura ruidoso)
    keep_h = asset.opt.get("ruin_h", 0.3) * size.z
    alive2 = set()
    for ci in alls:
        c = chunks[ci]["pc"].center()
        hloc = keep_h * (0.55 + 0.9 * (noise.noise(V(c.x * 0.35, c.y * 0.35, 7.7)) * 0.5 + 0.5))
        if c.z < hloc:
            alive2.add(ci)
    k2 = build_state("Destroyed", 2, alive2, alls - alive2, "Ruin", True)
    man["states"] = {"damaged": {"kept": k1[0], "fallen": k1[1]}, "destroyed": {"kept": k2[0], "fallen": k2[1]}}
    debris_set(name, asset.opt.get("debris", parts[0].cls), root, rng, man)


# ----------------------------------------------------------------------------------
# ESTADOS: VEHICULOS (piezas desmontables + abolladuras + pecio calcinado)
# ----------------------------------------------------------------------------------
BODY_KINDS = {"hull", "turret", "body", "cab", "fuselage", "tail", "wing", "bed"}


def vehicle_states(asset, root, rng, man, lo, hi):
    name, parts = asset.name, asset.parts
    size = hi - lo
    impacts = auto_impacts(lo, hi, rng, 2)
    man["impacts"] = [unity(p) for p in impacts]
    # ---- Estado 1: danado
    g = empty(f"{name}_Damaged", root, {"dst_role": "state", "dst_state": 1})
    for part in parts:
        if ("detail" in part.tags and rng.random() < 0.35) or ("glass" in part.tags and rng.random() < 0.6):
            continue
        pcs = [pc.copy() for pc in part.pieces]
        for pc in pcs:
            if part.kind in BODY_KINDS and len(pc.bm.faces) < 300:
                subdivide(pc)
            for p in impacts:
                dent(pc, 0.035, 2.0, rng.randint(0, 99), p, 1.6)
                scorch(pc, p, 1.4, rng)
        make_obj(f"{part.name}_Dmg", pcs, g, {"dst_role": "part", "dst_kind": part.kind})
    # ---- Estado 2: pecio
    g = empty(f"{name}_Destroyed", root, {"dst_role": "state", "dst_state": 2})
    turret_M = None
    piv = next((p.pivot for p in parts if "turret" in p.tags and p.pivot is not None), None)
    piv = piv if piv is not None else V(0, 0, hi.z)
    if any("turret" in p.tags for p in parts) and rng.random() < 0.55:
        side = V(rng.choice((-1, 1)) * size.x * 0.75, rng.uniform(-0.3, 0.3) * size.y, 0)
        turret_M = (Matrix.Translation(piv + side) @ Matrix.Rotation(math.radians(rng.uniform(20, 40)), 4, 'Y')
                    @ Matrix.Rotation(rng.uniform(0, 2 * math.pi), 4, 'Z') @ Matrix.Translation(-piv))
    elif any("turret" in p.tags for p in parts):
        turret_M = (Matrix.Translation(piv) @ Matrix.Rotation(math.radians(rng.uniform(-6, 6)), 4, 'X')
                    @ Matrix.Rotation(math.radians(rng.uniform(25, 140)), 4, 'Z') @ Matrix.Translation(-piv))
    groups = {"main": [], "turret": [], "loose": []}
    for part in parts:
        if part.tags & {"glass", "tire", "gear"} or ("detail" in part.tags and rng.random() < 0.6):
            continue
        src = part.alt.get("wreck") or part.pieces
        pcs = [char(pc.copy()) for pc in src]
        for pc in pcs:
            if part.kind in BODY_KINDS:
                if len(pc.bm.faces) < 300:
                    subdivide(pc)
                dent(pc, 0.06, 1.3, rng.randint(0, 99))
        if "turret" in part.tags and turret_M is not None:
            for pc in pcs:
                pc.transform(turret_M)
            groups["turret"] += pcs
        elif part.kind in ("rotor", "tail", "wing") and part.pivot is not None:
            ax = part.axis if part.axis is not None else V(0, 1, 0)
            if part.kind == "rotor":                      # palas dobladas: giro sobre eje horizontal
                ax = ax.cross(V(0, 0, 1)) if abs(ax.z) < 0.9 else V(1, 0, 0)
            ang = math.radians(rng.uniform(15, 50) if part.kind != "rotor" else rng.uniform(8, 25))
            c = sum((pc.center() for pc in pcs), V(0, 0, 0)) / len(pcs)
            def rot_about(a):
                return Matrix.Translation(part.pivot) @ Matrix.Rotation(a, 4, ax.normalized()) @ Matrix.Translation(-part.pivot)
            R = rot_about(ang) if (rot_about(ang) @ c).z <= (rot_about(-ang) @ c).z else rot_about(-ang)   # cae hacia el suelo
            for pc in pcs:
                pc.transform(R)
            groups["loose" if part.kind != "rotor" else "main"] += pcs
        else:
            groups["main"] += pcs
    for key, pcs in groups.items():
        if not pcs:
            continue
        mz = min(pc.bounds()[0].z for pc in pcs)
        for pc in pcs:
            pc.transform(Matrix.Translation((0, 0, -mz)))
        make_obj(f"{name}_Wreck_{key.title()}", pcs, g, {"dst_role": "wreck"})
    # ---- Chunks L1: explosion catastrofica (secciones del casco/fuselaje)
    g1 = empty(f"{name}_Chunks_L1", root, {"dst_role": "state", "dst_state": 3})
    body = [pc for p in parts if p.kind in ("hull", "body", "fuselage", "cab") for pc in p.pieces]
    secs = []
    for pc in body:
        src = decimated_copy(pc, FRACTURE_MAX_FACES) if len(pc.bm.faces) > FRACTURE_MAX_FACES else pc.copy()
        secs += voronoi(char(src), max(2, min(5, chunk_count(pc, 2))), rng)
    nb = contact_graph([[s] for s in secs]) if len(secs) > 1 else [set()]
    tot = sum(s.volume() for s in secs) or 1.0
    hull_mass = sum(p.mass for p in parts if p.kind in ("hull", "body", "fuselage", "cab"))
    for ci, s in enumerate(secs):
        m = round(hull_mass * s.volume() / tot, 1)
        nm = f"{name}_C{ci:03d}"
        make_obj(nm, [s], g1, {"dst_role": "chunk", "dst_id": ci, "dst_level": 1, "dst_mass": m,
                               "dst_class": "metal", "dst_neighbors": ",".join(map(str, sorted(nb[ci])))})
        man["chunks"].append({"name": nm, "id": ci, "mass": m, "center": unity(s.center()),
                              "neighbors": sorted(nb[ci])})
    debris_set(name, "metal", root, rng, man, n=10, size=(0.9, 0.6, 0.02))


# ----------------------------------------------------------------------------------
# ESTADOS: VEGETACION (tala con astillado por veta, copas que se desprenden)
# ----------------------------------------------------------------------------------
def tree_states(asset, root, rng, man, lo, hi):
    name, parts = asset.name, asset.parts
    cut = asset.opt.get("cut_h", 0.6)
    trunk = [p for p in parts if p.kind == "trunk"]
    crown = [p for p in parts if p.kind == "branch"]
    leaves = [pc for p in parts if p.kind == "foliage" for pc in p.pieces]
    stump, zone, log = [], [], []
    for p in trunk:
        for pc in p.pieces:
            a, b = split_piece(pc, V(0, 0, cut - 0.22), V(0, 0, 1))
            z, c = split_piece(b, V(0, 0, cut + 0.22), V(0, 0, 1))
            stump.append(a)
            zone += voronoi(z, 7, rng)
            log.append(c)
    spl_lo = [s for s in zone if s.center().z < cut]
    spl_hi = [s for s in zone if s.center().z >= cut]
    branch_pcs = [pc for p in crown for pc in p.pieces]
    # ---- Chunks L1: tocon, astillas, tronco (con ramas) y cada mata de follaje
    nodes = [("Stump", stump), ("Log", log + branch_pcs)] + \
            [(f"Splinter_{k}", [s]) for k, s in enumerate(zone)] + \
            [(f"Leaves_{k}", [pc]) for k, pc in enumerate(leaves)]
    nb = contact_graph([n[1] for n in nodes])
    g1 = empty(f"{name}_Chunks_L1", root, {"dst_role": "state", "dst_state": 3})
    for ci, (nm, pcs) in enumerate(nodes):
        m = mass_of(pcs)
        an = min(pc.bounds()[0].z for pc in pcs) < 0.03
        props = {"dst_role": "chunk", "dst_id": ci, "dst_level": 1, "dst_class": pcs[0].cls,
                 "dst_mass": m, "dst_anchored": int(an), "dst_neighbors": ",".join(map(str, sorted(nb[ci])))}
        if nm == "Log":
            props.update({"dst_pivot": unity_s(V(0, 0, cut)), "dst_joint": "hinge_break"})
        make_obj(f"{name}_{nm}", pcs, g1, props)
        man["chunks"].append({"name": f"{name}_{nm}", "id": ci, "mass": m, "anchored": an,
                              "neighbors": sorted(nb[ci]), "center": unity(pcs[0].center())})
    imp = V(rng.uniform(-0.2, 0.2), -0.3, cut + 0.4)
    # ---- Estado 1: ramas/follaje arrancados y tronco chamuscado
    g = empty(f"{name}_Damaged", root, {"dst_role": "state", "dst_state": 1})
    tr = [pc.copy() for p in trunk for pc in p.pieces]
    for pc in tr:
        scorch(pc, imp, 0.8, rng)
    make_obj(f"{name}_Trunk_Dmg", tr + [pc.copy() for pc in branch_pcs if rng.random() > 0.3], g, {"dst_role": "element"})
    keep_l = [pc.copy() for pc in leaves if rng.random() > 0.4]
    if keep_l:
        make_obj(f"{name}_Leaves_Dmg", keep_l, g, {"dst_role": "element"})
    # ---- Estado 2: talado
    g = empty(f"{name}_Destroyed", root, {"dst_role": "state", "dst_state": 2})
    make_obj(f"{name}_Stump_Ruin", [pc.copy() for pc in stump + spl_lo], g, {"dst_role": "element"})
    ang = rng.uniform(0, 2 * math.pi)
    axis = V(math.cos(ang), math.sin(ang), 0)
    P = V(0, 0, cut)
    R = Matrix.Translation(P) @ Matrix.Rotation(math.radians(rng.uniform(80, 88)), 4, axis) @ Matrix.Translation(-P)
    fallen = [pc.copy().transform(R) for pc in log + spl_hi + branch_pcs]
    fl = []
    for pc in leaves:
        q = pc.copy().transform(R)
        if rng.random() < 0.25:
            continue
        fl.append(scale_about(q, rng.uniform(0.7, 0.95)))
    allp = fallen + fl
    if allp:
        mz = min(pc.bounds()[0].z for pc in allp)
        for pc in allp:
            pc.transform(Matrix.Translation((0, 0, -mz)))
        make_obj(f"{name}_Log_Ruin", fallen, g, {"dst_role": "element"})
        if fl:
            make_obj(f"{name}_Leaves_Ruin", fl, g, {"dst_role": "element"})
    debris_set(name, "wood", root, rng, man, n=8, size=(0.7, 0.09, 0.06))


def plant_states(asset, root, rng, man, lo, hi):
    """Arbustos/hierba: matas independientes, pisoteado y quemado."""
    name = asset.name
    pcs = [pc for p in asset.parts for pc in p.pieces]
    g1 = empty(f"{name}_Chunks_L1", root, {"dst_role": "state", "dst_state": 3})
    for k, pc in enumerate(pcs):
        make_obj(f"{name}_C{k:03d}", [pc.copy()], g1, {"dst_role": "chunk", "dst_id": k, "dst_mass": mass_of([pc])})
    for sidx, (gname, sz, mat) in enumerate((("Damaged", 0.45, None), ("Destroyed", 0.18, "Mat_Leaves_Dry")), 1):
        g = empty(f"{name}_{gname}", root, {"dst_role": "state", "dst_state": sidx})
        out = []
        for pc in pcs:
            q = pc.copy()
            q.transform(Matrix.Rotation(math.radians(rng.uniform(-35, 35)), 4, 'X') @ Matrix.Diagonal((1, 1, sz, 1)))
            if mat:
                q.mat = mat if q.cls == "foliage" else "Mat_Wood_Charred"
            out.append(q)
        make_obj(f"{name}_{gname}_Mesh", out, g, {"dst_role": "element"})


# ----------------------------------------------------------------------------------
# ESTADOS: TERRENO (tiles solidos + crateres deformando la superficie)
# ----------------------------------------------------------------------------------
def crater_field(pcs, craters, rng):
    for pc in pcs:
        for v in pc.bm.verts:
            if v.co.z < 0.05:
                continue
            for (cx, cy, R, D) in craters:
                r = math.hypot(v.co.x - cx, v.co.y - cy) / R
                if r < 1.0:
                    v.co.z -= D * (1.0 - r * r)
                if 0.7 < r < 1.6:
                    v.co.z += D * 0.35 * math.exp(-((r - 1.0) / 0.2) ** 2)
            v.co.z = max(v.co.z, 0.1)
        pc.bm.normal_update()
        for f in pc.bm.faces:                         # hollin solo en el cuenco, borde irregular
            if f.normal.z <= 0.3:
                continue
            c = f.calc_center_median()
            for cx, cy, R, D in craters:
                r = math.hypot(c.x - cx, c.y - cy) / R
                if r < 0.55 or (r < 1.05 and rng.random() < (1.05 - r) * 1.6):
                    f.material_index = 2
                    break


def terrain_states(asset, root, rng, man, lo, hi):
    name = asset.name
    for sidx, (gname, nc) in enumerate((("Damaged", 2), ("Destroyed", 7)), 1):
        craters = [(rng.uniform(lo.x + 3, hi.x - 3), rng.uniform(lo.y + 3, hi.y - 3),
                    rng.uniform(1.8, 4.0), rng.uniform(0.6, 1.4)) for _ in range(nc)]
        man.setdefault("craters", {})[gname] = [[unity(V(c[0], c[1], 0)), c[2], c[3]] for c in craters]
        g = empty(f"{name}_{gname}", root, {"dst_role": "state", "dst_state": sidx})
        for part in asset.parts:
            pcs = [pc.copy() for pc in part.pieces]
            crater_field(pcs, craters, rng)
            make_obj(f"{part.name}_{gname[:3]}", pcs, g, {"dst_role": "element", "dst_class": "earth"})
    debris_set(name, "earth", root, rng, man, n=10, size=(0.6, 0.5, 0.35))


# ----------------------------------------------------------------------------------
# PIPELINE POR ASSET
# ----------------------------------------------------------------------------------
STATE_FN = {"structure": structure_states, "vehicle": vehicle_states, "tree": tree_states,
            "plant": plant_states, "terrain": terrain_states}


def process_asset(asset):
    t0 = time.time()
    reset_scene()
    rng = random.Random("%d:%s" % (SEED, asset.name))
    name, parts = asset.name, asset.parts
    seen = {}
    for p in parts:                                   # nombres unicos dentro del FBX
        k = seen.get(p.name, 0)
        seen[p.name] = k + 1
        if k:
            p.name = "%s_%d" % (p.name, k)
    lo, hi = orient_and_pivot(asset)
    for p in parts:
        p.mass = mass_of(p.pieces)
    if asset.opt.get("mass"):                          # masa real publicada (vehiculos)
        s = sum(p.mass for p in parts) or 1.0
        for p in parts:
            p.mass = round(p.mass / s * asset.opt["mass"], 1)
    total = round(sum(p.mass for p in parts), 1)
    root = empty(name, None, {"dst_role": "asset", "dst_category": asset.category, "dst_mode": asset.mode,
                              "dst_mass": total, "dst_manifest": name + ".json", "dst_version": 3,
                              "dst_variant": VARIANT})
    man = {"asset": name, "category": asset.category, "mode": asset.mode, "mass_kg": total,
           "unity": {"forward": "+Z", "up": "+Y", "pivot": "base center = (0,0,0)", "units": "m"},
           "bounds_unity": [unity(lo), unity(hi)], "reference": asset.opt.get("ref", ""),
           "variant": VARIANT, "ground_offset": asset.opt.get("ground_offset", 0.0),
           "elements": [], "chunks": [], "debris": [], "states": {}}
    if asset.opt.get("holes"):                                 # hueco a recortar en el Terrain (trincheras, pozos)
        TM = asset.opt["_T"] @ asset.opt["_M"]
        man["terrain_holes"] = []
        for cx, cy, L, w, ang in asset.opt["holes"]:
            c = TM @ V(cx, cy, 0)
            d = (TM.to_3x3() @ V(math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0)).normalized()
            man["terrain_holes"].append({"center_xz": [round(-c.x, 4), round(-c.y, 4)], "axis_xz": [round(-d.x, 4), round(-d.y, 4)],
                                         "length": round(L, 3), "width": round(w, 3)})
    cred = asset.opt.get("credits")
    if cred:                                                   # atribucion (CC-BY) dentro del FBX
        man["credits"] = cred
        for k in ("title", "author", "license", "source"):
            root["dst_" + k] = str(cred.get(k, ""))[:250]
    g0 = empty(f"{name}_Intact", root, {"dst_role": "state", "dst_state": 0})
    nb = contact_graph([p.pieces for p in parts]) if 1 < len(parts) < 400 else [set() for _ in parts]
    role = "part" if asset.mode == "vehicle" else "element"
    for i, part in enumerate(parts):
        an = min(pc.bounds()[0].z for pc in part.pieces) < -asset.opt.get("ground_offset", 0.0) + 0.03
        props = {"dst_role": role, "dst_kind": part.kind, "dst_class": part.cls, "dst_mass": part.mass,
                 "dst_hp": hp_of(part.pieces, part.mass), "dst_anchored": int(an), "dst_joint": part.joint,
                 "dst_tags": ",".join(sorted(part.tags)),
                 "dst_neighbors": ",".join(parts[j].name for j in sorted(nb[i]))}
        rec = {"name": part.name, "kind": part.kind, "class": part.cls, "mass": part.mass,
               "anchored": an, "joint": part.joint, "neighbors": [parts[j].name for j in sorted(nb[i])]}
        if part.pivot is not None:
            props["dst_pivot"] = unity_s(part.pivot)
            rec["pivot"] = unity(part.pivot)
        if part.axis is not None:
            props["dst_axis"] = unity_s(part.axis)
            rec["axis"] = unity(part.axis)
        make_obj(part.name, part.pieces, g0, props)
        man["elements"].append(rec)
    if asset.mode in STATE_FN:
        STATE_FN[asset.mode](asset, root, rng, man, lo, hi)
    # ---- LODs (malla fusionada; Unity crea el LODGroup solo por los sufijos _LODn)
    ratios = asset.opt.get("lod", (1.0, 0.5, 0.22))
    if ratios:
        gl = empty(f"{name}_LODs", root, {"dst_role": "state", "dst_state": 8})
        base = make_obj(f"{name}_LODsrc", [pc for p in parts for pc in p.pieces], None)
        man["lods"] = []
        for k, r in enumerate(ratios):
            ob = lod_obj(f"{name}_LOD{k}", base, r, gl)
            man["lods"].append({"name": ob.name, "ratio": r, "tris": len(ob.data.polygons)})
        me = base.data
        bpy.data.objects.remove(base, do_unlink=True)
        bpy.data.meshes.remove(me)
    tris = sum(len(o.data.polygons) for o in root.children_recursive if o.type == 'MESH')
    man["stats"] = {"objects": len(root.children_recursive) + 1, "triangles_total": tris,
                    "build_seconds": round(time.time() - t0, 2), "blender": bpy.app.version_string}
    folder = os.path.join(OUTPUT_DIR, asset.category)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1)
    if EXPORT:
        export_asset(root, os.path.join(folder, name + ".fbx"), embed=asset.opt.get("embed_textures", False))
    print("[OK] %-28s %-9s objs=%4d tris=%6d  %.1fs" % (name, asset.category, man["stats"]["objects"],
                                                        tris, time.time() - t0))
    return {"asset": name, "category": asset.category, "fbx": f"{asset.category}/{name}.fbx",
            "manifest": f"{asset.category}/{name}.json", "mass_kg": total, "triangles": tris}


# ==================================================================================
# BUILDERS: PROPS MILITARES (dimensiones reales de referencia)
# ==================================================================================
def build_crate(name):
    """Caja de municion de madera 0.90 x 0.45 x 0.36 m, tablas con veta + herrajes."""
    L, W, H, t = 0.90, 0.45, 0.36, 0.02
    hw = H - 2 * t
    M = "Mat_Crate_Base"
    base = [box((L, W / 3 - 0.004, t), (0, (i - 1) * W / 3, t / 2), mat=M, cls="wood", grain="x") for i in range(3)]
    for sy in (-1, 1):
        for k in (0.25, 0.75):
            base.append(box((L, t, hw / 2 - 0.003), (0, sy * (W / 2 - t / 2), t + hw * k), mat=M, cls="wood", grain="x"))
    for sx in (-1, 1):
        for k in (0.25, 0.75):
            base.append(box((t, W - 2 * t, hw / 2 - 0.003), (sx * (L / 2 - t / 2), 0, t + hw * k), mat=M, cls="wood", grain="y"))
        for sy in (-1, 1):
            base.append(box((0.04, 0.04, hw), (sx * (L / 2 - 0.04), sy * (W / 2 + 0.02), t + hw / 2), mat=M, cls="wood", grain="z"))
    lid = [box((L, W / 2 - 0.003, t), (0, (i - 0.5) * W / 2, H - t / 2), mat=M, cls="wood", grain="x") for i in range(2)]
    lid += [box((0.05, W, t), (sx * L / 3, 0, H + t / 2), mat=M, cls="wood", grain="y") for sx in (-1, 1)]
    hw_p = [box((0.04, 0.012, 0.07), (sx * L / 4, -W / 2 - 0.026, H - 0.04), mat="Mat_Crate_Metal", cls="metal", frac=False) for sx in (-1, 1)]
    hw_p += [box((0.012, 0.14, 0.03), (sx * (L / 2 + 0.006), 0, H * 0.6), mat="Mat_Crate_Metal", cls="metal", frac=False) for sx in (-1, 1)]
    return Asset(name, "Military", "structure", [
        Part("Crate_Box", base, "wood"),
        Part("Crate_Lid", lid, "wood", kind="door", pivot=(0, W / 2, H), axis=(1, 0, 0), joint="hinge"),
        Part("Crate_Hardware", hw_p, "metal", kind="detail")],
        n_impacts=1, dmg_r=0.22, ruin_h=0.4, spread=0.8, rubble_cell=1.0, debris="wood", lod=(1.0, 0.6),
        ref="Caja de municion de madera generica (OTAN), 90x45x36 cm")


def build_barrel(name):
    """Bidon de acero 200 L: D 0.572 m, H 0.851 m, pared hueca + aros de rodadura."""
    R, H, t = 0.286, 0.851, 0.004
    shell = lathe([(0, 0), (R, 0), (R, H), (0, H), (0, H - t), (R - t, H - t), (R - t, t), (0, t)],
                  mat="Mat_Barrel_Paint", segs=16, hollow=True, cls="metal", smooth=True)
    hoops = [lathe([(R - 0.001, z), (R + 0.012, z), (R + 0.012, z + 0.022), (R - 0.001, z + 0.022)], mat="Mat_Barrel_Paint",
                   segs=16, closed=True, cls="metal", frac=False) for z in (H * 0.32, H * 0.66)]
    chimes = [lathe([(R - 0.002, z), (R + 0.006, z), (R + 0.006, z + 0.015), (R - 0.002, z + 0.015)], mat="Mat_Metal_Steel",
                    segs=16, closed=True, cls="metal", frac=False) for z in (0.0, H - 0.015)]
    caps = [cyl(0.03, 0.02, (x, 0.12, H + 0.01), mat="Mat_Metal_Steel", segs=8, cls="metal", frac=False) for x in (-0.15, 0.15)]
    return Asset(name, "Military", "structure", [
        Part("Barrel_Shell", [shell], "metal"),
        Part("Barrel_Hoops", hoops + chimes, "metal", kind="detail"),
        Part("Barrel_Caps", caps, "metal", kind="detail")],
        n_impacts=1, dmg_r=0.2, ruin_h=0.35, spread=1.2, rubble_cell=1.0, debris="metal", mass=185.0,
        lod=(1.0, 0.5), ref="Bidon ISO 200 L (55 gal), 572 x 851 mm, lleno de combustible")


def build_sandbags(name):
    """Muro de sacos terreros: 4 hiladas trabadas, saco lleno ~0.60 x 0.30 x 0.14 m."""
    rng = random.Random(name)
    parts, L, D, Hb = [], 0.60, 0.30, 0.14
    for row in range(4):
        off = (L / 2) * (row % 2)
        n = 5 - (row % 2)
        for i in range(n):
            x = -1.2 + off + i * (L + 0.01)
            p = box((L * rng.uniform(0.95, 1.02), D * rng.uniform(0.95, 1.05), Hb), (x, rng.uniform(-0.02, 0.02), Hb / 2 + row * Hb * 0.92),
                    (rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-4, 4)), mat="Mat_Fabric_Sandbag", bevel=0.04, cls="fabric")
            parts.append(Part(f"Sandbag_R{row}_{i}", [p], "fabric"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=0.45, ruin_h=0.3, spread=0.6,
                 rubble_cell=1.5, debris="fabric", lod=(1.0, 0.6), ref="Sacos terreros polipropileno 36x66 cm (llenos)")


def build_jersey(name):
    """Barrera Jersey de hormigon: 3.0 m x 0.61 base x 0.81 alto, cabeza 0.15 m."""
    prof = [(-0.305, 0), (0.305, 0), (0.305, 0.075), (0.19, 0.33), (0.075, 0.81), (-0.075, 0.81), (-0.19, 0.33), (-0.305, 0.075)]
    body = prism(prof, 3.0, axis='x', mat="Mat_Concrete_Base", cls="concrete")
    lugs = [box((0.12, 0.62, 0.08), (x, 0, 0.04), mat="Mat_Concrete_Interior", cls="concrete", frac=False) for x in (-1.2, 1.2)]
    return Asset(name, "Military", "structure", [Part("Jersey_Body", [body], "concrete"), Part("Jersey_Feet", lugs, "concrete", kind="detail")],
                 n_impacts=1, dmg_r=0.55, ruin_h=0.45, spread=0.5, rubble_cell=1.5, debris="concrete", lod=(1.0, 0.6),
                 ref="Barrera New Jersey F-shape 32in (0.81 m)")


def build_hedgehog(name):
    """Erizo checo: 3 angulares de acero 2.0 m (L 120x120x12) mutuamente perpendiculares."""
    Lb, a, t = 2.0, 0.12, 0.012
    Lsec = [(0, 0), (a, 0), (a, t), (t, t), (t, a), (0, a)]
    R = V(1, 1, 1).normalized().rotation_difference(V(0, 0, 1)).to_matrix().to_4x4()
    parts = []
    for i, ax in enumerate("xyz"):
        p = prism([(u - a / 2, v - a / 2) for u, v in Lsec], Lb, axis='x', mat="Mat_Metal_Gunmetal", cls="metal")
        if ax == 'y':
            p.transform(Matrix.Rotation(math.pi / 2, 4, 'Z'))
        elif ax == 'z':
            p.transform(Matrix.Rotation(-math.pi / 2, 4, 'Y'))
        parts.append(Part(f"Hedgehog_Beam_{ax.upper()}", [p.transform(R)], "metal"))
    gus = [box((0.22, 0.22, 0.012), rot=r, mat="Mat_Metal_Steel", cls="metal", frac=False).transform(R)
           for r in ((0, 0, 0), (90, 0, 0), (0, 90, 0))]
    parts.append(Part("Hedgehog_Gussets", gus, "metal", kind="detail"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=0.4, ruin_h=0.3, spread=0.8,
                 rubble_cell=2.0, debris="metal", lod=(1.0, 0.6), ref="Erizo checo (Cesky jezek), acero laminado")


def build_hesco(name):
    """HESCO MIL1: celdas 1.06 x 1.06 x 1.37 m, malla electrosoldada + geotextil + relleno."""
    C, H, parts = 1.06, 1.37, []
    for i in range(3):
        x = (i - 1) * C
        parts.append(Part(f"Hesco_Fill_{i}", [box((C - 0.03, C - 0.03, H - 0.04), (x, 0, (H - 0.04) / 2), mat="Mat_Fabric_Sandbag", cls="earth")], "earth"))
        wires = []
        for k in range(5):
            u = -C / 2 + C * k / 4
            for sy in (-1, 1):
                wires.append(strut((x + u, sy * C / 2, 0), (x + u, sy * C / 2, H), 0.006, "Mat_Hesco_Mesh", 4, cls="metal", frac=False, smooth=False))
                wires.append(strut((x + sy * C / 2, u, 0), (x + sy * C / 2, u, H), 0.006, "Mat_Hesco_Mesh", 4, cls="metal", frac=False, smooth=False))
            z = H * k / 4
            for sy in (-1, 1):
                wires.append(strut((x - C / 2, sy * C / 2, z), (x + C / 2, sy * C / 2, z), 0.006, "Mat_Hesco_Mesh", 4, cls="metal", frac=False, smooth=False))
                wires.append(strut((x + sy * C / 2, -C / 2, z), (x + sy * C / 2, C / 2, z), 0.006, "Mat_Hesco_Mesh", 4, cls="metal", frac=False, smooth=False))
        parts.append(Part(f"Hesco_Cage_{i}", wires, "metal", kind="detail"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=0.7, ruin_h=0.45, spread=0.4,
                 rubble_cell=1.5, debris="earth", lod=(1.0, 0.5), ref="HESCO Concertainer MIL1 (1.37 x 1.06 x 1.06 m/celda)")


def build_watchtower(name):
    """Torre de vigilancia de madera: 6 m de patas, plataforma 3x3 m a 4.5 m, techo a 4 aguas."""
    W, Hp, Hr = 3.0, 4.5, 2.0
    parts = []
    legs = [((sx * (W / 2 + 0.35), sy * (W / 2 + 0.35), 0), (sx * W / 2 * 0.92, sy * W / 2 * 0.92, Hp + Hr)) for sx in (-1, 1) for sy in (-1, 1)]
    for i, (a, b) in enumerate(legs):
        parts.append(Part(f"Tower_Leg_{i}", [beam(a, b, 0.2, mat="Mat_Wood_Beam", cls="wood")], "wood"))

    def leg_at(i, z):
        a, b = V(legs[i][0]), V(legs[i][1])
        return a.lerp(b, z / (Hp + Hr))
    for lvl, (z0, z1) in enumerate(((0.3, 2.2), (2.2, 4.3))):
        for side, (i, j) in enumerate(((0, 1), (1, 3), (3, 2), (2, 0))):
            br = [beam(leg_at(i, z0), leg_at(j, z1), 0.1, mat="Mat_Wood_Beam", cls="wood"),
                  beam(leg_at(j, z0), leg_at(i, z1), 0.1, mat="Mat_Wood_Beam", cls="wood")]
            parts.append(Part(f"Tower_Brace_L{lvl}_S{side}", br, "wood"))
    planks = [box((W + 0.4, 0.28, 0.05), (0, -W / 2 + 0.15 + k * 0.3, Hp + 0.025), mat="Mat_Wood_Plank", cls="wood", grain="x") for k in range(11)]
    planks += [box((W + 0.4, 0.15, 0.18), (0, sy * (W / 2 - 0.2), Hp - 0.09), mat="Mat_Wood_Beam", cls="wood", grain="x") for sy in (-1, 1)]
    parts.append(Part("Tower_Platform", planks, "wood"))
    for side, (sx, sy, rx) in enumerate(((0, -1, 0), (0, 1, 0), (-1, 0, 90), (1, 0, 90))):
        rail = [box((W + 0.4, 0.06, 0.08), (sx * (W / 2 + 0.17), sy * (W / 2 + 0.17), Hp + h), (0, 0, rx), mat="Mat_Wood_Plank", cls="wood",
                    grain="x" if rx == 0 else "y") for h in (0.5, 1.0)]
        parts.append(Part(f"Tower_Rail_{side}", rail, "wood"))
    roof = hull([(sx * (W / 2 + 0.5), sy * (W / 2 + 0.5), Hp + Hr) for sx in (-1, 1) for sy in (-1, 1)] +
                [(sx * (W / 2 + 0.5), sy * (W / 2 + 0.5), Hp + Hr + 0.08) for sx in (-1, 1) for sy in (-1, 1)] +
                [(0, 0, Hp + Hr + 1.1)], mat="Mat_Roof_Metal", cls="metal")
    parts.append(Part("Tower_Roof", [roof], "metal"))
    lad = [beam((-0.25, -W / 2 - 1.2, 0), (-0.25, -W / 2 - 0.05, Hp), 0.07, mat="Mat_Wood_Beam", cls="wood"),
           beam((0.25, -W / 2 - 1.2, 0), (0.25, -W / 2 - 0.05, Hp), 0.07, mat="Mat_Wood_Beam", cls="wood")]
    for k in range(1, 15):
        f = k / 15.0
        y = -W / 2 - 1.2 + f * 1.15
        lad.append(box((0.5, 0.05, 0.04), (0, y, f * Hp), mat="Mat_Wood_Plank", cls="wood", grain="x"))
    parts.append(Part("Tower_Ladder", lad, "wood"))
    return Asset(name, "Military", "structure", parts, n_impacts=2, dmg_r=0.9, ruin_h=0.25, spread=0.5,
                 rubble_cell=3.0, debris="wood", lod=(1.0, 0.6), ref="Torre de vigilancia de campo (FOB) de madera")


def build_bunker(name):
    """Bunker/pastillero de hormigon armado 5 x 4 x 2.4 m, muros 0.5 m, tronera frontal."""
    L, D, H, t = 5.0, 4.0, 2.4, 0.5
    C = dict(mat="Mat_Concrete_Base", cls="concrete")
    sill, slit = 1.15, 0.35
    front = [box((1.5, t, H), (-L / 2 + 0.75, -D / 2 + t / 2, H / 2), **C), box((1.5, t, H), (L / 2 - 0.75, -D / 2 + t / 2, H / 2), **C),
             box((L - 3.0, t, sill), (0, -D / 2 + t / 2, sill / 2), **C),
             box((L - 3.0, t, H - sill - slit), (0, -D / 2 + t / 2, sill + slit + (H - sill - slit) / 2), **C)]
    back = [box((1.8, t, H), (-L / 2 + 0.9, D / 2 - t / 2, H / 2), **C), box((L - 2.7, t, H), (L / 2 - (L - 2.7) / 2, D / 2 - t / 2, H / 2), **C),
            box((0.9, t, H - 1.9), (-L / 2 + 2.25, D / 2 - t / 2, 1.9 + (H - 1.9) / 2), **C)]
    sides = [[box((t, D - 2 * t, H), (sx * (L / 2 - t / 2), 0, H / 2), **C)] for sx in (-1, 1)]
    roof = [box((L + 0.6, D + 0.6, 0.5), (0, 0, H + 0.25), **C)]
    floor = [box((L, D, 0.15), (0, 0, 0.075), **C)]
    bags = [box((0.6, 0.3, 0.14), (-1.8 + i * 0.62, -D / 2 - 0.1, H + 0.57), mat="Mat_Fabric_Sandbag", bevel=0.04, cls="fabric") for i in range(6)]
    return Asset(name, "Military", "structure", [
        Part("Bunker_Floor", floor), Part("Bunker_Wall_Front", front), Part("Bunker_Wall_Back", back),
        Part("Bunker_Wall_L", sides[0]), Part("Bunker_Wall_R", sides[1]), Part("Bunker_Roof", roof),
        Part("Bunker_Sandbags", bags, "fabric")],
        n_impacts=2, dmg_r=1.0, ruin_h=0.45, spread=0.3, rubble_cell=2.5, debris="concrete", lod=(1.0, 0.7),
        ref="Pastillero de hormigon armado tipo FOB, muros 0.5 m")


def zigzag_wall(length, height, depth=0.035, pitch=0.28, thick=0.03):
    """Planta (XY) de chapa corrugada trapezoidal extruida en Z."""
    n = max(2, int(length / pitch))
    top, bot = [], []
    for i in range(n + 1):
        x = -length / 2 + length * i / n
        y = depth if i % 2 else 0.0
        top.append((x, y))
        bot.append((x, y - thick))
    return top + bot[::-1]


def build_container(name):
    """Contenedor ISO 20 ft: 6.058 x 2.438 x 2.591 m, chapa corrugada, puertas con bisagra."""
    L, W, H = 6.058, 2.438, 2.591
    P = dict(mat="Mat_Container_Paint", cls="metal")
    parts = []
    frame = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            frame.append(box((0.16, 0.16, H), (sx * (L / 2 - 0.08), sy * (W / 2 - 0.08), H / 2), mat="Mat_Metal_Gunmetal", cls="metal"))
        frame.append(box((0.16, W - 0.32, 0.16), (sx * (L / 2 - 0.08), 0, H - 0.08), mat="Mat_Metal_Gunmetal", cls="metal"))
        frame.append(box((0.16, W - 0.32, 0.2), (sx * (L / 2 - 0.08), 0, 0.1), mat="Mat_Metal_Gunmetal", cls="metal"))
    for sy in (-1, 1):
        frame.append(box((L - 0.32, 0.12, 0.2), (0, sy * (W / 2 - 0.06), 0.1), mat="Mat_Metal_Gunmetal", cls="metal"))
        frame.append(box((L - 0.32, 0.1, 0.12), (0, sy * (W / 2 - 0.05), H - 0.06), mat="Mat_Metal_Gunmetal", cls="metal"))
    parts.append(Part("Container_Frame", frame, "metal"))
    for side, sy in enumerate((-1, 1)):
        w = prism(zigzag_wall(L - 0.32, H - 0.32), H - 0.32, axis='z', **P)
        w.transform(Matrix.Translation((0, sy * (W / 2 - 0.05), H / 2)) @ (Matrix.Rotation(math.pi, 4, 'Z') if sy > 0 else Matrix.Identity(4)))
        parts.append(Part(f"Container_Side_{side}", [w], "metal"))
    endw = prism(zigzag_wall(W - 0.32, H - 0.32), H - 0.32, axis='z', **P)
    endw.transform(Matrix.Translation((L / 2 - 0.06, 0, H / 2)) @ Matrix.Rotation(math.pi / 2, 4, 'Z'))
    parts.append(Part("Container_End", [endw], "metal"))
    parts.append(Part("Container_Roof", [box((L - 0.32, W - 0.2, 0.04), (0, 0, H - 0.04), **P)], "metal"))
    parts.append(Part("Container_Floor", [box((L - 0.32, W - 0.24, 0.04), (0, 0, 0.2), mat="Mat_Wood_Plank", cls="wood", grain="x")], "wood"))
    for k, sy in enumerate((-1, 1)):
        dw = (W - 0.32) / 2
        y0 = sy * (W / 2 - 0.16)
        door = [box((0.05, dw, H - 0.36), (-L / 2 + 0.05, y0 - sy * dw / 2, H / 2), **P)]
        door += [cyl(0.018, H - 0.5, (-L / 2 + 0.0, y0 - sy * dw * f, H / 2), mat="Mat_Metal_Steel", segs=6, cls="metal", frac=False) for f in (0.3, 0.7)]
        parts.append(Part(f"Container_Door_{k}", door, "metal", kind="door", pivot=(-L / 2 + 0.03, y0, H / 2), axis=(0, 0, 1), joint="hinge"))
    return Asset(name, "Military", "structure", parts, n_impacts=2, dmg_r=0.9, ruin_h=0.35, spread=0.4,
                 rubble_cell=3.0, debris="metal", mass=2300.0, lod=(1.0, 0.6), ref="ISO 668 1CC 20 ft (6.058 x 2.438 x 2.591 m)")


# ==================================================================================
# BUILDERS: VEHICULOS TERRESTRES (construidos mirando a +X; se reorientan a -Y)
# Dimensiones de referencia publicadas (fabricante / fichas tecnicas, 2024-2026)
# ==================================================================================
TRACKED = {
    "Veh_MBT_M1A2_SEPv3": dict(L=7.92, W=3.66, H=2.44, Hh=1.55, mass=66800, nw=7, wr=0.32, tw=0.635, turret="abrams",
                                TL=4.6, TW=3.5, tx=-0.35, gun=5.3, gr=0.085, paint="Mat_Military_Desert",
                                ref="General Dynamics M1A2 SEPv3: casco 7.92 m, ancho 3.66 m, alto 2.44 m, 66.8 t, 120 mm L/44"),
    "Veh_MBT_Leopard2A7": dict(L=7.72, W=3.77, H=2.64, Hh=1.6, mass=67000, nw=7, wr=0.35, tw=0.635, turret="wedge",
                               TL=4.5, TW=3.5, tx=-0.3, gun=6.6, gr=0.085, paint="Mat_Military_Green",
                               ref="KNDS Leopard 2 A7: L 10.97 m (canon), ancho 3.77-4.0 m, alto 2.64 m, <69 t, 120 mm L/55"),
    "Veh_MBT_T90M": dict(L=6.86, W=3.78, H=2.23, Hh=1.35, mass=48000, nw=6, wr=0.38, tw=0.58, turret="dome",
                         TL=3.4, TW=3.0, tx=0.15, gun=6.0, gr=0.09, paint="Mat_Military_Olive", era=True,
                         ref="UVZ T-90M: casco 6.86 m, 9.63 m con canon, ancho 3.78 m, alto 2.23 m, 48 t, 125 mm"),
    "Veh_IFV_M2A4_Bradley": dict(L=6.55, W=3.28, H=2.98, Hh=2.0, mass=36300, nw=6, wr=0.30, tw=0.53, turret="ifv",
                                 TL=2.2, TW=2.0, tx=0.2, ty=-0.25, gun=2.6, gr=0.045, paint="Mat_Military_Desert", tow=True, ramp=True,
                                 ref="BAE M2A4 Bradley: L 6.55 m, ancho 3.28 m, alto ~3.0 m, 36.3 t, 25 mm M242 + TOW"),
    "Veh_IFV_CV90_MkIV": dict(L=6.47, W=3.19, H=2.75, Hh=1.75, mass=37000, nw=7, wr=0.30, tw=0.53, turret="ifv",
                              TL=2.6, TW=2.3, tx=-0.4, gun=3.2, gr=0.07, paint="Mat_Military_Green", ramp=True,
                              ref="BAE Hagglunds CV90 MkIV: L 6.47 m, ancho 3.19 m, alto 2.5 m (casco), 37 t, 30/40 mm"),
    "Veh_SPG_M109A7_Paladin": dict(L=6.8, W=3.9, H=3.3, Hh=1.65, mass=35380, nw=7, wr=0.32, tw=0.55, turret="box",
                                   TL=3.9, TW=3.1, tx=-0.8, gun=6.1, gr=0.11, paint="Mat_Military_Desert", brake=True,
                                   ref="BAE M109A7 Paladin: L 9.7 m (canon), ancho 3.9 m, alto 3.3 m, 35.4 t, 155 mm L/39"),
    "Veh_SPAAG_Gepard_1A2": dict(L=7.0, W=3.71, H=3.29, Hh=1.55, mass=47500, nw=7, wr=0.35, tw=0.55, turret="spaag",
                                 TL=3.2, TW=2.5, tx=-0.4, gun=3.2, gr=0.045, paint="Mat_Military_Green",
                                 ref="KNDS Gepard 1A2: L 7.68 m, ancho 3.71 m, alto 3.29 m (4.23 m radar arriba), 47.5 t, 2x35 mm"),
}


def track_layout(L, wr, nw, th=0.08):
    x0, x1 = -L / 2 + 0.85, L / 2 - 0.95
    xs = [x0 + (x1 - x0) * i / (nw - 1) for i in range(nw)]
    zc = wr + th
    idl = (L / 2 - 0.42, zc + 0.24, 0.27)
    spr = (-L / 2 + 0.42, zc + 0.30, 0.31)
    pts = [(x0 - 0.15, 0.0), (x1 + 0.15, 0.0)]
    for a in range(-50, 91, 20):
        t = math.radians(a)
        pts.append((idl[0] + (idl[2] + th) * math.cos(t), idl[1] + (idl[2] + th) * math.sin(t)))
    for a in range(90, 251, 20):
        t = math.radians(a)
        pts.append((spr[0] + (spr[2] + th) * math.cos(t), spr[1] + (spr[2] + th) * math.sin(t)))
    ztop = max(p[1] for p in pts)
    return resample_loop(pts, 48), xs, zc, idl, spr, ztop


def build_tracked(name):
    s = TRACKED[name]
    L, W, H, Hh, wr, tw, P = s["L"], s["W"], s["H"], s["Hh"], s["wr"], s["tw"], s["paint"]
    rng = random.Random(name)
    path, xs, zc, idl, spr, ztop = track_layout(L, wr, s["nw"])
    parts, th = [], 0.08
    yt = W / 2 - tw / 2 - 0.02
    # --- tren de rodaje y orugas
    for side, sy in (("L", 1), ("R", -1)):
        wh = []
        for x in xs:
            wh.append(cyl(wr, tw * 0.8, (x, sy * yt, zc), (90, 0, 0), mat="Mat_Track_Steel", segs=14, cls="metal"))
            wh.append(cyl(wr * 0.45, tw * 0.86, (x, sy * yt, zc), (90, 0, 0), mat=P, segs=8, cls="metal", frac=False))
        for (x, z, r) in (idl, spr):
            wh.append(cyl(r, tw * 0.7, (x, sy * yt, z), (90, 0, 0), mat="Mat_Metal_Gunmetal", segs=12, cls="metal"))
        for k in range(3):
            wh.append(cyl(0.09, tw * 0.5, (xs[1] + (xs[-2] - xs[1]) * k / 2, sy * yt, ztop - th - 0.09), (90, 0, 0),
                          mat="Mat_Metal_Gunmetal", segs=8, cls="metal", frac=False))
        parts.append(Part(f"RoadWheels_{side}", wh, "metal", kind="wheel", pivot=(0, sy * yt, zc), axis=(0, 1, 0), joint="wheel"))
        segs = [band(path, th, tw, sy * yt, mat="Mat_Track_Steel", i0=k * 6, i1=k * 6 + 6, cls="metal") for k in range(8)]
        broken = []
        for k, sg in enumerate(segs):
            if sg.center().z < ztop * 0.45 or k % 3:
                broken.append(sg.copy())
            else:
                q = sg.copy().transform(Matrix.Translation((-L * 0.25 - k * 0.3, sy * tw * 1.3, 0)))
                q.transform(Matrix.Translation((0, 0, -q.bounds()[0].z)))
                broken.append(q)
        parts.append(Part(f"Track_{side}", [band(path, th, tw, sy * yt, mat="Mat_Track_Steel", cls="metal")], "metal",
                          kind="track", alt={"wreck": broken}))
        skirt = [box((L * 0.86, 0.05, ztop - 0.35), (0.05, sy * (W / 2 - 0.025), (ztop + 0.35) / 2 + 0.05), mat=P, cls="metal")]
        parts.append(Part(f"SideSkirt_{side}", skirt, "metal", kind="detail"))
    # --- casco: sponsones (ancho total) + casco inferior entre orugas
    zb = ztop + 0.04
    gl = s.get("glacis", 1.6 if s["turret"] in ("abrams", "wedge", "dome") else 1.1)
    up = hull(sym([(L / 2, W / 2 - 0.01, zb), (L / 2, W / 2 - 0.05, zb + 0.22), (L / 2 - gl, W / 2 - 0.05, Hh),
                   (-L / 2 + 0.15, W / 2 - 0.05, Hh), (-L / 2, W / 2 - 0.05, Hh - 0.2), (-L / 2, W / 2 - 0.01, zb)]), mat=P, cls="metal")
    win = W / 2 - tw - 0.06
    low = hull(sym([(L / 2 - 0.05, win, zb + 0.02), (L / 2 - 0.7, win, 0.42), (-L / 2 + 0.5, win, 0.42),
                    (-L / 2 + 0.1, win, zb + 0.02)]), mat=P, cls="metal")
    hp = [up, low]
    if s.get("era"):
        for k in range(5):
            hp.append(box((0.5, 0.42, 0.08), (L / 2 - 0.35 - k * 0.28, (k - 2) * 0.55, zb + 0.15 + k * 0.08), (0, -18, 0), mat=P, cls="metal", frac=False))
    parts.append(Part("Hull", hp, "metal", kind="hull"))
    if s.get("ramp"):
        parts.append(Part("RearRamp", [box((0.08, win * 1.6, Hh - 0.6), (-L / 2 - 0.02, 0, (Hh + 0.6) / 2), mat=P, cls="metal")], "metal",
                          kind="door", pivot=(-L / 2, 0, 0.6), axis=(0, 1, 0), joint="hinge"))
    parts.append(Part("Hull_Lights", [box((0.08, 0.18, 0.1), (L / 2 - 0.1, sy * (W / 2 - 0.3), zb + 0.3), mat="Mat_Light_Lens",
                                          cls="glass", frac=False) for sy in (-1, 1)], "glass", kind="glass"))
    # --- torreta
    TL, TW, tx, ty = s["TL"], s["TW"], s["tx"], s.get("ty", 0.0)
    z0, TH = Hh, (H - Hh) * (0.78 if s["turret"] != "spaag" else 0.62)
    st = s["turret"]
    if st in ("abrams", "wedge"):
        tp = sym([(tx + TL * 0.5, TW * 0.30, z0), (tx + TL * 0.5, TW * 0.27, z0 + TH * 0.8), (tx + TL * 0.18, TW * 0.5, z0),
                  (tx + TL * 0.14, TW * 0.48, z0 + TH), (tx - TL * 0.5, TW * 0.44, z0 + 0.05), (tx - TL * 0.5, TW * 0.42, z0 + TH * 0.95)])
    elif st == "dome":
        tp = []
        for zf, rf in ((0.0, 1.0), (0.55, 0.92), (1.0, 0.62)):
            for i in range(14):
                a = 2 * math.pi * i / 14
                tp.append((tx + math.cos(a) * TL * 0.5 * rf, math.sin(a) * TW * 0.5 * rf, z0 + TH * zf))
    elif st == "bmp":                                   # torreta conica baja (BMP)
        tp = []
        for zf, rf in ((0.0, 1.0), (0.6, 0.78), (1.0, 0.5)):
            for i in range(12):
                a = 2 * math.pi * i / 12
                tp.append((tx + math.cos(a) * TL * 0.5 * rf, math.sin(a) * TW * 0.5 * rf, z0 + TH * 0.8 * zf))
    elif st == "ifv":
        tp = sym([(tx + TL / 2, TW * 0.32, z0), (tx + TL / 2 - 0.25, TW * 0.28, z0 + TH), (tx - TL / 2, TW / 2, z0), (tx - TL / 2 + 0.1, TW * 0.46, z0 + TH)])
    else:
        tp = sym([(tx + TL / 2, TW * 0.46, z0), (tx + TL / 2 - 0.35, TW * 0.46, z0 + TH), (tx - TL / 2, TW / 2, z0), (tx - TL / 2, TW / 2, z0 + TH)])
    tur = [hull([(x, y + ty, z) for x, y, z in tp], mat=P, cls="metal")]
    if st == "wedge":
        xf = tx + TL * 0.5
        for sy in (-1, 1):
            tur.append(hull([(xf, sy * TW * 0.46, z0 + 0.05), (xf, sy * TW * 0.46, z0 + TH * 0.85), (xf, sy * 0.36, z0 + 0.05),
                             (xf, sy * 0.36, z0 + TH * 0.85), (xf + 0.8, sy * 0.42, z0 + 0.12), (xf + 0.8, sy * 0.42, z0 + TH * 0.7)], mat=P, cls="metal"))
    if s.get("era"):
        for sy in (-1, 1):
            for k in range(3):
                tur.append(box((0.45, 0.32, TH * 0.6), (tx + TL * 0.42 - k * 0.12, sy * (0.45 + k * 0.32), z0 + TH * 0.38),
                               (0, 0, sy * (15 + k * 18)), mat=P, cls="metal", frac=False))
    tur.append(box((TL * 0.35, TW * 0.7, TH * 0.6), (tx - TL * 0.5 - TL * 0.12, ty, z0 + TH * 0.45), mat="Mat_Metal_Gunmetal", cls="metal", frac=False))
    tpiv = (tx, ty, z0)
    parts.append(Part("Turret", tur, "metal", kind="turret", pivot=tpiv, axis=(0, 0, 1), joint="yaw"))
    # --- armamento principal
    xt, zg = tx + TL * 0.5 - 0.3, z0 + TH * 0.45
    gp = [box((0.6, 0.75 if s["gr"] > 0.06 else 0.4, TH * 0.55), (xt + 0.15, ty, zg), mat=P, cls="metal")]
    g = s["gun"]
    if st == "shilka":                                   # 4 canones 2A7 de 23 mm en dos pares
        gp = [box((0.7, TW * 0.7, TH * 0.55), (tx + TL / 2 - 0.1, ty, z0 + TH * 0.55), mat=P, cls="metal")]
        for sy in (-1, 1):
            for dz in (-0.12, 0.12):
                gp.append(cyl(s["gr"], g, (tx + TL / 2 + g / 2, ty + sy * 0.42, z0 + TH * 0.55 + dz), (0, 90, 0),
                              mat="Mat_Metal_Gunmetal", segs=6, cls="metal"))
    elif st == "spaag":
        gp = []
        for sy in (-1, 1):
            yy = sy * (TW / 2 + 0.28)
            gp.append(box((1.6, 0.42, 0.55), (tx + 0.3, yy, z0 + TH * 0.6), mat=P, cls="metal"))
            gp.append(cyl(s["gr"], g, (tx + 1.0 + g / 2, yy, z0 + TH * 0.6), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal"))
        gp.append(sphere(0.55, (tx + TL / 2 + 0.25, 0, z0 + TH * 0.7), mat="Mat_Military_Grey", scale=(0.5, 1, 1), cls="metal"))
    else:
        gp.append(cyl(s["gr"], g, (xt + 0.4 + g / 2, ty, zg), (0, 90, 0), mat=P if s["gr"] > 0.06 else "Mat_Metal_Gunmetal",
                      segs=10, r2=s["gr"] * 0.85, cls="metal"))
        if s["gr"] > 0.06:
            gp.append(cyl(s["gr"] * 1.6, 0.7, (xt + 0.4 + g * 0.45, ty, zg), (0, 90, 0), mat=P, segs=10, cls="metal"))
        if s.get("brake"):
            gp.append(box((0.45, s["gr"] * 4, s["gr"] * 2.6), (xt + 0.4 + g, ty, zg), mat="Mat_Metal_Gunmetal", cls="metal"))
    parts.append(Part("MainGun", gp, "metal", kind="gun", tags=("turret",), pivot=(xt, ty, zg), axis=(0, 1, 0), joint="pitch"))
    # --- detalles de torreta: escotillas, ametralladora, lanzahumos, antenas, misiles/radar
    dt = [cyl(0.36, 0.22, (tx - 0.3, ty + TW * 0.2, z0 + TH + 0.11), mat=P, segs=10, cls="metal"),
          cyl(0.3, 0.06, (tx - 0.3, ty - TW * 0.22, z0 + TH + 0.03), mat=P, segs=10, cls="metal"),
          box((0.9, 0.12, 0.14), (tx - 0.1, ty + TW * 0.2, z0 + TH + 0.32), mat="Mat_Metal_Gunmetal", cls="metal"),
          cyl(0.015, 1.4, (tx - 0.2, ty + TW * 0.2, z0 + TH + 0.32), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal")]
    for sy in (-1, 1):
        for k in range(4):
            dt.append(cyl(0.045, 0.28, (tx + TL * 0.2 - k * 0.1, ty + sy * TW * 0.47, z0 + TH * 0.75), (0, -35, sy * 70),
                          mat="Mat_Metal_Gunmetal", segs=6, cls="metal"))
        dt.append(strut((tx - TL * 0.4, ty + sy * TW * 0.35, z0 + TH), (tx - TL * 0.4, ty + sy * TW * 0.35, z0 + TH + 2.2), 0.008,
                        "Mat_Metal_Gunmetal", 4, cls="metal"))
    if s.get("atgm"):
        dt.append(cyl(0.07, 1.25, (tx, ty + TW * 0.3, z0 + TH * 0.95), (0, 90, 0), mat="Mat_Military_RuGreen", segs=8, cls="metal"))
    if st == "shilka":
        dt.append(strut((tx - TL * 0.35, 0, z0 + TH), (tx - TL * 0.35, 0, z0 + TH + 0.3), 0.06, "Mat_Metal_Gunmetal", 8, cls="metal"))
        dt.append(cyl(0.65, 0.08, (tx - TL * 0.35, 0, z0 + TH + 0.55), (75, 0, 90), mat="Mat_Military_RuGreen", segs=14, cls="metal"))
    if s.get("tow"):
        dt.append(box((1.2, 0.45, 0.5), (tx - 0.2, ty + TW / 2 + 0.25, z0 + TH * 0.65), mat=P, cls="metal"))
    if st == "spaag":
        dt.append(strut((tx - TL * 0.4, 0, z0 + TH), (tx - TL * 0.4, 0, H - 0.1), 0.08, "Mat_Metal_Gunmetal", 8, cls="metal"))
        dt.append(box((0.35, 1.9, 0.5), (tx - TL * 0.4, 0, H + 0.1), (0, 15, 0), mat="Mat_Military_Grey", cls="metal"))
    parts.append(Part("Turret_Details", dt, "metal", kind="detail", tags=("turret",)))
    return Asset(name, "Vehicles", "vehicle", parts, forward_x=True, mass=s["mass"], ref=s["ref"], lod=(1.0, 0.5, 0.2))


WHEELED = {
    "Veh_APC_Stryker_M1126": dict(L=6.95, W=2.72, H=2.64, mass=16470, axles=(2.55, 1.35, -0.55, -1.75), wr=0.58, style="apc",
                                  paint="Mat_Military_Desert", ref="GDLS Stryker M1126 ICV: L 6.95 m, ancho 2.72 m, alto 2.64 m, 16.5 t, 8x8"),
    "Veh_APC_Boxer": dict(L=7.93, W=2.99, H=2.38, mass=36500, axles=(2.85, 1.55, -0.75, -2.05), wr=0.63, style="apc",
                          paint="Mat_Military_Green", ref="ARTEC Boxer: L 7.93 m, ancho 2.99 m, alto techo 2.38 m, 36.5 t, 8x8"),
    "Veh_LTV_JLTV": dict(L=6.2, W=2.5, H=2.6, mass=7000, axles=(1.95, -1.4), wr=0.48, style="luv", paint="Mat_Military_Desert",
                         ref="Oshkosh JLTV: L 6.2 m, ancho 2.5 m, alto 2.6 m, 6.4 t vacio"),
    "Veh_LUV_HMMWV_M1151": dict(L=4.93, W=2.31, H=1.99, mass=3700, axles=(1.6, -1.7), wr=0.45, style="luv", low=True,
                                paint="Mat_Military_Desert", ref="AM General HMMWV M1151: L 4.93 m, ancho 2.31 m, alto 1.99 m, batalla 3.30 m"),
    "Veh_MRAP_M-ATV": dict(L=6.27, W=2.49, H=2.7, mass=12500, axles=(1.95, -1.7), wr=0.6, style="mrap", paint="Mat_Military_Desert",
                           ref="Oshkosh M-ATV: L 6.27 m, ancho 2.49 m, alto 2.7 m, 12.5 t"),
    "Veh_Truck_FMTV_M1083": dict(L=6.94, W=2.44, H=2.85, mass=8900, axles=(2.35, -1.05, -2.45), wr=0.58, style="truck",
                                 paint="Mat_Military_Green", ref="FMTV M1083 6x6: L 6.94 m, ancho 2.44 m, alto 2.85 m, batalla 4.1 m, 8.9 t"),
}


def tire_wheel(x, y, z, r, w, nm, rim_mat):
    ri = r * 0.6
    hw = w / 2
    tire = lathe([(ri, -hw), (r * 0.94, -hw), (r, -hw * 0.6), (r, hw * 0.6), (r * 0.94, hw), (ri, hw)], (x, y, z), (90, 0, 0),
                 mat="Mat_Rubber_Tire", segs=16, closed=True, cls="rubber")
    rim = cyl(ri * 1.01, w * 0.8, (x, y, z), (90, 0, 0), mat=rim_mat, segs=10, cls="metal")
    hub = cyl(ri * 0.35, w * 0.95, (x, y, z), (90, 0, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal", frac=False)
    return Part(nm, [tire, rim, hub], "rubber", kind="wheel", pivot=(x, y, z), axis=(0, 1, 0), joint="wheel",
                alt={"wreck": [rim.copy(), hub.copy()]})


def glass_panel(p0, p1, p2, p3, t=0.02):
    """Ventana como placa fina (cuadrilatero con espesor)."""
    pts = [V(p) for p in (p0, p1, p2, p3)]
    n = (pts[1] - pts[0]).cross(pts[3] - pts[0]).normalized() * t
    return hull([tuple(p) for p in pts] + [tuple(p + n) for p in pts], mat="Mat_Glass_Window", cls="glass")


def build_wheeled(name):
    s = WHEELED[name]
    L, W, H, wr, P, st = s["L"], s["W"], s["H"], s["wr"], s["paint"], s["style"]
    parts = []
    tw = wr * 0.75
    yw = W / 2 - tw / 2 - 0.02
    for i, x in enumerate(s["axles"]):
        for side, sy in (("L", 1), ("R", -1)):
            parts.append(tire_wheel(x, sy * yw, wr, wr, tw, f"Wheel_{i}{side}", P))
    zb = wr * 0.75
    glass, doors, det = [], [], []
    if st == "apc":
        hz_ = H - (0.55 if s.get("btr") else 0.15)
        rw = W / 2 - (0.4 if s.get("btr") else 0.05)          # BTR: costados superiores inclinados
        body = hull(sym([(L / 2, W / 2 - (0.6 if s.get("btr") else 0.25), zb + 0.35), (L / 2 - 0.9, rw, hz_), (-L / 2, rw, hz_ + 0.05),
                         (L / 2 - 0.9, W / 2 - 0.02, zb + 0.95), (-L / 2 + 0.1, W / 2 - 0.02, zb + 0.95),
                         (-L / 2, W / 2 - 0.12, zb), (L / 2 - 0.5, W / 2 - 0.4, zb - 0.1), (L / 2 - 0.2, W / 2 - 0.15, zb + 0.15),
                         (L / 2 - 0.7, 0.4, zb - 0.35), (-L / 2 + 0.3, 0.4, zb - 0.35)]), mat=P, cls="metal")
        parts.append(Part("Hull", [body], "metal", kind="hull"))
        if s.get("btr"):                                     # torreta BPPU con 2A72 de 30 mm
            tz = H - 0.55
            tp = []
            for zf, rf in ((0.0, 1.0), (0.7, 0.8), (1.0, 0.55)):
                for i in range(12):
                    a = 2 * math.pi * i / 12
                    tp.append((0.9 + math.cos(a) * 0.85 * rf, math.sin(a) * 0.85 * rf, tz + 0.55 * zf))
            rws = [hull(tp, mat=P, cls="metal"), cyl(0.04, 2.5, (0.9 + 1.4, 0, tz + 0.3), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal")]
            rpiv = (0.9, 0, tz)
        else:
            rws = [box((0.9, 0.7, 0.45), (-0.2, 0.3, H + 0.2), mat=P, cls="metal"),
                   cyl(0.035, 1.6, (0.6, 0.3, H + 0.3), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal"),
                   box((0.3, 0.3, 0.25), (0.1, 0.0, H + 0.38), mat="Mat_Glass_Canopy", cls="glass", frac=False)]
            rpiv = (-0.2, 0.3, H)
        parts.append(Part("RWS" if not s.get("btr") else "Turret", rws, "metal", kind="turret", pivot=rpiv, axis=(0, 0, 1), joint="yaw"))
        doors.append(Part("RearRamp", [box((0.08, W * 0.55, H - zb - 0.4), (-L / 2 - 0.03, 0, (H + zb) / 2 - 0.1), mat=P, cls="metal")], "metal",
                          kind="door", pivot=(-L / 2, 0, zb), axis=(0, 1, 0), joint="hinge"))
        for sy in (-1, 1):
            glass.append(glass_panel((L / 2 - 0.78, sy * 0.3, H - 0.3), (L / 2 - 0.78, sy * 0.75, H - 0.3), (L / 2 - 0.86, sy * 0.75, H - 0.18),
                                     (L / 2 - 0.86, sy * 0.3, H - 0.18)))
    else:
        hood_l = {"luv": L * 0.33, "mrap": L * 0.3, "truck": L * 0.22}[st]
        cab_l = {"luv": L * 0.38, "mrap": L * 0.42, "truck": L * 0.26}[st]
        hz = H * (0.62 if st == "luv" else 0.6)
        if s.get("low"):
            hz = H * 0.6
        xf = L / 2
        chassis = [box((L * 0.95, W * 0.5, 0.25), (0, 0, zb + 0.05), mat="Mat_Metal_Gunmetal", cls="metal")]
        hood = hull(sym([(xf, W / 2 - 0.12, zb + 0.2), (xf, W / 2 - 0.2, hz - 0.1), (xf - hood_l, W / 2 - 0.05, hz),
                         (xf - hood_l, W / 2 - 0.05, zb + 0.1), (xf - 0.1, W / 2 - 0.15, zb)]), mat=P, cls="metal")
        xc0, xc1 = xf - hood_l, xf - hood_l - cab_l
        roof = H - (0.55 if st != "truck" else 0.05) if not s.get("low") else H - 0.05
        cab = hull(sym([(xc0, W / 2 - 0.05, zb + 0.1), (xc0, W / 2 - 0.08, hz), (xc0 - 0.45, W / 2 - 0.15, roof), (xc1, W / 2 - 0.12, roof),
                        (xc1, W / 2 - 0.05, zb + 0.1)] + ([(xc0 - 0.3, 0.3, zb - 0.25), (xc1 + 0.3, 0.3, zb - 0.25)] if st == "mrap" else [])),
                   mat=P, cls="metal")
        parts.append(Part("Body_Hood", [hood] + chassis, "metal", kind="body"))
        parts.append(Part("Cab", [cab], "metal", kind="cab"))
        glass.append(glass_panel((xc0 - 0.02, -W / 2 + 0.3, hz + 0.05), (xc0 - 0.02, W / 2 - 0.3, hz + 0.05),
                                 (xc0 - 0.4, W / 2 - 0.35, roof - 0.06), (xc0 - 0.4, -W / 2 + 0.35, roof - 0.06)))
        nd = 2 if st == "truck" else 4
        dl = cab_l / (nd // 2)
        for k in range(nd):
            sy = 1 if k % 2 == 0 else -1
            x0 = xc0 - 0.05 - (k // 2) * dl
            d = [box((dl - 0.08, 0.06, roof - zb - 0.45), (x0 - dl / 2, sy * (W / 2 - 0.02), (roof + zb) / 2 - 0.1), mat=P, cls="metal")]
            glass.append(glass_panel((x0 - 0.1, sy * (W / 2 + 0.015), hz + 0.08), (x0 - dl + 0.15, sy * (W / 2 + 0.015), hz + 0.08),
                                     (x0 - dl + 0.15, sy * (W / 2 - 0.01), roof - 0.15), (x0 - 0.1, sy * (W / 2 - 0.01), roof - 0.15)))
            doors.append(Part(f"Door_{k}", d, "metal", kind="door", pivot=(x0, sy * W / 2, zb + 0.5), axis=(0, 0, 1), joint="hinge"))
        if st == "truck":
            bed_l = xc1 - (-L / 2) - 0.25
            bx = xc1 - 0.25 - bed_l / 2
            bed = [box((bed_l, W, 0.12), (bx, 0, zb + 0.55), mat="Mat_Wood_Plank", cls="wood", grain="x")]
            bed += [box((bed_l, 0.05, 0.6), (bx, sy * (W / 2 - 0.025), zb + 0.9), mat=P, cls="metal") for sy in (-1, 1)]
            bed += [box((0.05, W, 0.6), (bx - bed_l / 2, 0, zb + 0.9), mat=P, cls="metal")]
            parts.append(Part("CargoBed", bed, "metal", kind="bed"))
            cover = []
            ch = H - zb - 1.2                               # lona sobre arcos
            for k in range(4):
                cover.append(box((bed_l / 4 + 0.02, W - 0.04, 0.03), (bx - bed_l / 2 + bed_l * (k + 0.5) / 4, 0, H - 0.05),
                                 mat="Mat_Fabric_Canvas", cls="fabric"))
            cover.append(box((0.03, W - 0.04, ch), (bx + bed_l / 2 - 0.03, 0, H - 0.05 - ch / 2), mat="Mat_Fabric_Canvas", cls="fabric"))
            for sy in (-1, 1):
                cover.append(box((bed_l - 0.1, 0.03, ch), (bx, sy * (W / 2 - 0.04), H - 0.05 - ch / 2), mat="Mat_Fabric_Canvas", cls="fabric"))
            parts.append(Part("CanvasCover", cover, "fabric", kind="detail"))
            det.append(cyl(0.28, 0.9, (xc1 + 0.4, W / 2 - 0.35, zb + 0.2), (0, 90, 0), mat=P, segs=10, cls="metal"))
            spare = tire_wheel(xc1 - 0.2, 0, roof - wr - 0.05, wr, tw, "SpareWheel", P)
            spare.kind, spare.joint, spare.tags = "detail", "fixed", {"detail", "tire"}
            parts.append(spare)
        else:
            bed_l = xc1 - (-L / 2)
            bed = [box((bed_l, W - 0.1, 0.5), (xc1 - bed_l / 2, 0, zb + 0.35), mat=P, cls="metal")]
            bed += [box((bed_l, 0.05, 0.45), (xc1 - bed_l / 2, sy * (W / 2 - 0.08), zb + 0.8), mat=P, cls="metal") for sy in (-1, 1)]
            parts.append(Part("CargoBed", bed, "metal", kind="bed"))
            ring_z = roof + 0.05
            tur = [cyl(0.55, 0.12, (xc0 - cab_l * 0.55, 0, ring_z), mat=P, segs=12, cls="metal")]
            gx = xc0 - cab_l * 0.55
            tur += [box((0.06, 1.0, 0.55), (gx + 0.55, 0, ring_z + 0.35), mat=P, cls="metal"),
                    cyl(0.03, 1.5, (gx + 0.7, 0, ring_z + 0.45), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal")]
            tur += [box((0.5, 0.06, 0.5), (gx + 0.25, sy * 0.5, ring_z + 0.35), mat=P, cls="metal") for sy in (-1, 1)]
            parts.append(Part("GunnerTurret", tur, "metal", kind="turret", pivot=(xc0 - cab_l * 0.55, 0, ring_z), axis=(0, 0, 1), joint="yaw"))
        for sy in (-1, 1):
            det.append(box((0.06, 0.2, 0.12), (xf + 0.01, sy * (W / 2 - 0.25), hz - 0.25), mat="Mat_Light_Lens", cls="glass", frac=False))
            det.append(box((0.04, 0.25, 0.3), (xc0 - 0.1, sy * (W / 2 + 0.2), hz + 0.25), mat="Mat_Metal_Gunmetal", cls="metal"))
    det.append(strut((-L / 2 + 0.4, W / 2 - 0.3, H - 0.2), (-L / 2 + 0.4, W / 2 - 0.3, H + 1.8), 0.008, "Mat_Metal_Gunmetal", 4, cls="metal"))
    det.append(box((0.35, W * 0.6, 0.15), (L / 2 - 0.05, 0, zb + 0.05), mat="Mat_Metal_Gunmetal", cls="metal"))
    parts.append(Part("Details", det, "metal", kind="detail"))
    if glass:
        parts.append(Part("Windows", glass, "glass", kind="glass"))
    parts += doors
    return Asset(name, "Vehicles", "vehicle", parts, forward_x=True, mass=s["mass"], ref=s["ref"], lod=(1.0, 0.5, 0.2))


# ==================================================================================
# BUILDERS: AERONAVES, NAVAL, ARTILLERIA
# ==================================================================================
HELIS = {
    "Air_Heli_AH-64E_Apache": dict(FL=15.0, FW=1.0, FH=1.9, rotor=14.63, blades=4, trotor=2.79, H=4.95, mass=6838, tandem=True,
                                   stubs=5.2, paint="Mat_Military_Olive", ref="Boeing AH-64E: L 17.7 m (rotores), rotor 14.63 m, alto 4.95 m"),
    "Air_Heli_UH-60M_BlackHawk": dict(FL=15.26, FW=2.36, FH=2.2, rotor=16.36, blades=4, trotor=3.35, H=5.13, mass=6894,
                                      paint="Mat_Military_Olive", ref="Sikorsky UH-60M: fuselaje 15.26 m, ancho 2.36 m, rotor 16.36 m, cola 3.35 m, alto 5.13 m"),
    "Air_Heli_Ka-52_Alligator": dict(FL=14.2, FW=1.5, FH=2.0, rotor=14.5, blades=3, coax=True, H=4.93, mass=7800, stubs=4.6,
                                     paint="Mat_Military_Grey", ref="Kamov Ka-52: L 15.5 m, rotores coaxiales 14.5 m, alto 4.93 m"),
}


def blade(root, length, chord, z, ang, mat="Mat_Rotor_Blade", thick=0.04, droop=0.0):
    a = math.radians(ang)
    d = V(math.cos(a), math.sin(a), 0)
    p0 = V(root) + d * 0.3
    p1 = V(root) + d * length + V(0, 0, -droop)
    b = beam(p0, p1, chord, thick, mat=mat, cls="metal", grain=None)
    return b


def build_heli(name):
    s = HELIS[name]
    FL, FW, FH, P = s["FL"], s["FW"], s["FH"], s["paint"]
    k = s.get("k", 1.0)                                # escala longitudinal de las estaciones (fuselajes > 15 m)
    parts = []
    gz = 0.55                                          # altura del tren
    x0 = FL * 0.5
    secs = [(x0, 0.05, 0.05, gz + FH * 0.45), (x0 - 0.6 * k, FW * 0.3, FH * 0.3, gz + FH * 0.45),
            (x0 - 1.8 * k, FW * 0.45, FH * 0.45, gz + FH * 0.5), (x0 - 4.0 * k, FW * 0.5, FH * 0.5, gz + FH * 0.52),
            (x0 - 6.5 * k, FW * 0.5, FH * 0.5, gz + FH * 0.55), (x0 - 8.0 * k, FW * 0.3, FH * 0.32, gz + FH * 0.68)]
    fus = loft(ell_rings(secs, 12), mat=P, cls="metal", smooth=True)
    parts.append(Part("Fuselage", [fus], "metal", kind="fuselage"))
    xb = x0 - 8.0 * k
    tail_secs = [(xb + 0.3, FW * 0.3, FH * 0.32, gz + FH * 0.68), (-FL * 0.5 + 0.6, 0.18, 0.22, gz + FH * 0.75), (-FL * 0.5, 0.12, 0.15, gz + FH * 0.78)]
    boom = loft(ell_rings(tail_secs, 8), mat=P, cls="metal", smooth=True)
    xt = -FL * 0.5 + 0.4
    fin = prism([(xt - 0.6, gz + FH * 0.7), (xt + 0.6, gz + FH * 0.7), (xt + 0.1, gz + FH * 0.7 + 1.8), (xt - 0.6, gz + FH * 0.7 + 1.9)], 0.14, axis='y', mat=P, cls="metal")
    stab = prism([(xt + 0.9, 1.6), (xt + 0.4, 1.6), (xt + 0.4, -1.6), (xt + 0.9, -1.6)], 0.08, axis='z', offset=gz + FH * 0.75, mat=P, cls="metal")
    tparts = [boom, fin, stab]
    if s.get("coax"):
        tparts = [boom, stab] + [prism([(xt - 0.3, gz + FH * 0.4), (xt + 0.6, gz + FH * 0.4), (xt + 0.4, gz + FH + 0.9), (xt - 0.3, gz + FH + 0.9)],
                                       0.1, axis='y', offset=sy * 1.6, mat=P, cls="metal") for sy in (-1, 1)]
    parts.append(Part("TailBoom", tparts, "metal", kind="tail", pivot=(xb + 0.3, 0, gz + FH * 0.68), axis=(0, 1, 0), joint="break"))
    hub_z = s["H"] - 0.45
    mast = [cyl(0.18, hub_z - (gz + FH), (x0 - 4.5 * k, 0, (hub_z + gz + FH) / 2), mat="Mat_Metal_Gunmetal", segs=10, cls="metal")]
    eng = [hull(sym([(x0 - 2.6 * k, FW * 0.35, gz + FH * 0.9), (x0 - 3.2 * k, FW * 0.3, gz + FH + 0.55), (x0 - 7.0 * k, FW * 0.3, gz + FH + 0.5),
                     (x0 - 7.8 * k, FW * 0.25, gz + FH * 0.8)]), mat=P, cls="metal")]
    if s.get("tandem"):
        for sy in (-1, 1):
            eng.append(cyl(0.38, 2.6, (x0 - 5.0 * k, sy * (FW * 0.5 + 0.3), gz + FH * 0.9), (0, 90, 0), mat=P, segs=10, cls="metal"))
    parts.append(Part("EngineDeck", eng + mast, "metal", kind="body"))
    rot_list = [(hub_z, 0)] + ([(hub_z - 0.9, 60)] if s.get("coax") else [])
    for ri, (hz, off) in enumerate(rot_list):
        rp = [cyl(0.32, 0.25, (x0 - 4.5 * k, 0, hz), mat="Mat_Metal_Gunmetal", segs=10, cls="metal")]
        for k in range(s["blades"]):
            rp.append(blade((x0 - 4.5 * k, 0, hz), s["rotor"] / 2, 0.53, hz, off + k * 360 / s["blades"], droop=0.15))
        parts.append(Part(f"MainRotor_{ri}", rp, "metal", kind="rotor", pivot=(x0 - 4.5 * k, 0, hz), axis=(0, 0, 1), joint="spin"))
    if not s.get("coax"):
        tr = [cyl(0.12, 0.15, (xt, 0.25, gz + FH * 0.7 + 1.3), (90, 0, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal")]
        for k in range(4):
            a = math.radians(k * 90 + 20)
            c = V(xt, 0.32, gz + FH * 0.7 + 1.3)
            tr.append(beam(c, c + V(math.cos(a), 0, math.sin(a)) * s["trotor"] / 2, 0.22, 0.03, mat="Mat_Rotor_Blade", cls="metal", grain=None))
        parts.append(Part("TailRotor", tr, "metal", kind="rotor", tags=("tail",), pivot=(xt, 0.32, gz + FH * 0.7 + 1.3), axis=(0, 1, 0), joint="spin"))
    # cabina acristalada
    if s.get("tandem"):
        can = hull(sym([(x0 - 0.7 * k, 0.3, gz + FH * 0.65), (x0 - 1.6 * k, 0.42, gz + FH * 1.05), (x0 - 3.6 * k, 0.45, gz + FH * 1.15),
                        (x0 - 4.2 * k, 0.4, gz + FH * 0.9), (x0 - 3.9 * k, 0.45, gz + FH * 0.7)]), mat="Mat_Glass_Canopy", cls="glass")
    else:
        can = hull(sym([(x0 - 0.5 * k, FW * 0.25, gz + FH * 0.55), (x0 - 1.3 * k, FW * 0.42, gz + FH * 0.95), (x0 - 2.3 * k, FW * 0.45, gz + FH * 0.98),
                        (x0 - 2.4 * k, FW * 0.47, gz + FH * 0.5), (x0 - 1.0 * k, FW * 0.35, gz + FH * 0.35)]), mat="Mat_Glass_Canopy", cls="glass")
    parts.append(Part("Canopy", [can], "glass", kind="glass"))
    gear = []
    for sy in (-1, 1):
        gear.append(strut((x0 - 3.0 * k, sy * FW * 0.45, gz + 0.3), (x0 - 3.0 * k, sy * (FW * 0.5 + 0.6), 0.32), 0.05, "Mat_Metal_Gunmetal", 6, cls="metal"))
        gear.append(cyl(0.3, 0.2, (x0 - 3.0 * k, sy * (FW * 0.5 + 0.65), 0.3), (90, 0, 0), mat="Mat_Rubber_Tire", segs=10, cls="rubber"))
    gear.append(cyl(0.18, 0.12, (-FL * 0.5 + 1.5, 0, 0.18 + gz * 0.4), (90, 0, 0), mat="Mat_Rubber_Tire", segs=8, cls="rubber"))
    gear.append(strut((-FL * 0.5 + 1.5, 0, 0.3 + gz * 0.4), (-FL * 0.5 + 1.6, 0, gz + FH * 0.72), 0.04, "Mat_Metal_Gunmetal", 6, cls="metal"))
    parts.append(Part("LandingGear", gear, "metal", kind="gear"))
    if s.get("stubs"):
        for side, sy in (("L", 1), ("R", -1)):
            span = s["stubs"] / 2
            w = [prism([(x0 - 5.6 * k, 0), (x0 - 4.6 * k, 0), (x0 - 4.8 * k, span), (x0 - 5.6 * k, span)], 0.12, axis='z', offset=gz + FH * 0.75, mat=P, cls="metal")]
            w[0].transform(Matrix.Diagonal((1, sy, 1, 1)))
            for k in (0.55, 0.95):
                w.append(cyl(0.2, 1.6, (x0 - 5.1 * k, sy * span * k, gz + FH * 0.55), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal"))
            parts.append(Part(f"StubWing_{side}", w, "metal", kind="wing", pivot=(x0 - 5.1 * k, sy * FW * 0.5, gz + FH * 0.75), axis=(1, 0, 0), joint="break"))
        parts.append(Part("ChinGun", [box((0.5, 0.45, 0.35), (x0 - 1.2 * k, 0, gz + 0.25), mat="Mat_Metal_Gunmetal", cls="metal"),
                                      cyl(0.04, 1.7, (x0 - 0.1 * k, 0, gz + 0.2), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal")],
                          "metal", kind="detail", pivot=(x0 - 1.2 * k, 0, gz + 0.25), axis=(0, 0, 1), joint="yaw"))
    else:
        for side, sy in (("L", 1), ("R", -1)):
            d = [box((1.6, 0.05, FH * 0.75), (x0 - 4.0 * k, sy * (FW * 0.5 + 0.01), gz + FH * 0.45), mat=P, cls="metal")]
            parts.append(Part(f"CabinDoor_{side}", d, "metal", kind="door", pivot=(x0 - 4.0 * k, sy * FW * 0.5, gz + FH * 0.45), axis=(1, 0, 0), joint="slide"))
    return Asset(name, "Aircraft", "vehicle", parts, forward_x=True, mass=s["mass"], ref=s["ref"], lod=(1.0, 0.5, 0.2))


def build_f35(name):
    """F-35A: L 15.7 m, envergadura 10.7 m, alto 4.38 m, 13.3 t vacio."""
    P, gz = "Mat_Military_Grey", 1.35
    parts = []
    secs = [(7.85, 0.02, 0.02, gz + 0.55), (6.6, 0.35, 0.3, gz + 0.6), (4.6, 0.75, 0.5, gz + 0.75), (2.0, 1.15, 0.6, gz + 0.8),
            (-2.0, 1.25, 0.58, gz + 0.8), (-5.5, 0.85, 0.5, gz + 0.75), (-7.2, 0.62, 0.55, gz + 0.75)]
    fus = loft(ell_rings(secs, 10), mat=P, cls="metal")
    for v in fus.bm.verts:                         # seccion facetada tipo "chine"
        v.co.z = gz + 0.78 + (v.co.z - gz - 0.78) * (0.72 if v.co.z > gz + 0.78 else 1.0)
    fus.bm.normal_update()
    intakes = [hull(sym([(3.3, 1.0, gz + 0.5), (3.3, 1.45, gz + 0.95), (0.5, 1.45, gz + 0.95), (0.5, 1.0, gz + 0.45)]), mat=P, cls="metal")]
    parts.append(Part("Fuselage", [fus] + intakes, "metal", kind="fuselage"))
    parts.append(Part("Canopy", [hull(sym([(5.6, 0.1, gz + 1.05), (4.6, 0.45, gz + 1.2), (3.0, 0.45, gz + 1.35), (2.0, 0.3, gz + 1.15),
                                           (5.2, 0.38, gz + 1.0), (2.2, 0.42, gz + 1.0)]), mat="Mat_Glass_Canopy", cls="glass")], "glass", kind="glass"))
    for side, sy in (("L", 1), ("R", -1)):
        w = prism([(1.8, 0.9), (-3.4, 0.9), (-4.4, 5.35), (-2.7, 5.35)], 0.16, axis='z', offset=gz + 0.7, mat=P, cls="metal")
        w.transform(Matrix.Diagonal((1, sy, 1, 1)))
        parts.append(Part(f"Wing_{side}", [w], "metal", kind="wing", pivot=(-1.0, sy * 1.1, gz + 0.7), axis=(1, 0, 0), joint="break"))
        fin = prism([(-4.6, 0), (-6.6, 0), (-7.2, 2.1), (-6.0, 2.1)], 0.1, axis='y', mat=P, cls="metal")
        fin.transform(Matrix.Translation((0, sy * 0.95, gz + 1.15)) @ Matrix.Rotation(math.radians(-sy * 25), 4, 'X'))
        stab = prism([(-5.6, 0.5), (-7.6, 0.5), (-7.9, 3.4), (-6.9, 3.4)], 0.08, axis='z', offset=gz + 0.7, mat=P, cls="metal")
        stab.transform(Matrix.Diagonal((1, sy, 1, 1)))
        parts.append(Part(f"Tail_{side}", [fin, stab], "metal", kind="tail", pivot=(-6.0, sy * 0.9, gz + 0.9), axis=(1, 0, 0), joint="break"))
    parts.append(Part("Nozzle", [lathe([(0.55, 0), (0.6, 0.6), (0.5, 1.3), (0.45, 1.3), (0.0, 1.25)], (-7.1, 0, gz + 0.75), (0, -90, 0),
                                       mat="Mat_Metal_Gunmetal", segs=12, cls="metal")], "metal", kind="detail"))
    gear = [strut((5.2, 0, gz + 0.3), (5.3, 0, 0.3), 0.06, "Mat_Metal_Gunmetal", 6, cls="metal"),
            cyl(0.3, 0.2, (5.3, 0, 0.3), (90, 0, 0), mat="Mat_Rubber_Tire", segs=10, cls="rubber")]
    for sy in (-1, 1):
        gear += [strut((-1.6, sy * 1.2, gz + 0.4), (-1.7, sy * 1.6, 0.38), 0.07, "Mat_Metal_Gunmetal", 6, cls="metal"),
                 cyl(0.38, 0.28, (-1.7, sy * 1.6, 0.38), (90, 0, 0), mat="Mat_Rubber_Tire", segs=10, cls="rubber")]
    parts.append(Part("LandingGear", gear, "metal", kind="gear"))
    return Asset(name, "Aircraft", "vehicle", parts, forward_x=True, mass=13290, lod=(1.0, 0.5, 0.2),
                 ref="Lockheed Martin F-35A: L 15.7 m, envergadura 10.7 m, alto 4.38 m, 13.3 t vacio")


def build_mq9(name):
    """MQ-9 Reaper: L 11 m, envergadura 20.1 m, alto 3.8 m, helice propulsora 4 palas."""
    P, gz = "Mat_Military_Grey", 0.95
    parts = []
    secs = [(5.5, 0.05, 0.05, gz + 0.45), (5.0, 0.42, 0.45, gz + 0.5), (3.8, 0.5, 0.55, gz + 0.55), (0.5, 0.45, 0.45, gz + 0.5),
            (-3.5, 0.3, 0.32, gz + 0.5), (-4.9, 0.22, 0.22, gz + 0.5)]
    parts.append(Part("Fuselage", [loft(ell_rings(secs, 10), mat=P, cls="metal", smooth=True)], "metal", kind="fuselage"))
    for side, sy in (("L", 1), ("R", -1)):
        w = prism([(0.9, 0.3), (-0.4, 0.3), (-0.15, 10.05), (0.45, 10.05)], 0.14, axis='z', offset=gz + 0.9, mat=P, cls="metal")
        w.transform(Matrix.Diagonal((1, sy, 1, 1)))
        hf = [cyl(0.09, 1.6, (0.3, sy * 4.5, gz + 0.55), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal"),
              cyl(0.09, 1.6, (0.3, sy * 6.5, gz + 0.55), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal")]
        parts.append(Part(f"Wing_{side}", [w] + hf, "metal", kind="wing", pivot=(0.25, sy * 0.4, gz + 0.9), axis=(1, 0, 0), joint="break"))
    vt = []
    for sy in (-1, 1):
        t = prism([(-3.6, 0), (-4.6, 0), (-4.9, 2.0), (-4.3, 2.0)], 0.08, axis='y', mat=P, cls="metal")
        t.transform(Matrix.Translation((0, 0, gz + 0.6)) @ Matrix.Rotation(math.radians(sy * 45), 4, 'X'))
        vt.append(t)
    vt.append(prism([(-3.9, 0), (-4.7, 0), (-4.8, -0.9), (-4.4, -0.9)], 0.08, axis='y', offset=0, mat=P, cls="metal").transform(Matrix.Translation((0, 0, gz + 0.4))))
    parts.append(Part("Tail_V", vt, "metal", kind="tail", pivot=(-3.8, 0, gz + 0.5), axis=(0, 1, 0), joint="break"))
    pr = [cyl(0.12, 0.25, (-5.05, 0, gz + 0.5), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal")]
    for k in range(4):
        a = math.radians(k * 90 + 45)
        pr.append(beam(V(-5.1, 0, gz + 0.5), V(-5.1, math.cos(a) * 1.0, gz + 0.5 + math.sin(a) * 1.0), 0.16, 0.03, mat="Mat_Rotor_Blade", cls="metal", grain=None))
    parts.append(Part("Propeller", pr, "metal", kind="rotor", pivot=(-5.1, 0, gz + 0.5), axis=(1, 0, 0), joint="spin"))
    parts.append(Part("SensorBall", [sphere(0.3, (4.6, 0, gz + 0.02), mat="Mat_Glass_Canopy", cls="glass")], "glass", kind="glass"))
    gear = [strut((4.0, 0, gz + 0.1), (4.0, 0, 0.18), 0.04, "Mat_Metal_Gunmetal", 6, cls="metal"),
            cyl(0.18, 0.12, (4.0, 0, 0.18), (90, 0, 0), mat="Mat_Rubber_Tire", segs=8, cls="rubber")]
    for sy in (-1, 1):
        gear += [strut((0.0, sy * 0.3, gz + 0.2), (0.0, sy * 1.1, 0.2), 0.04, "Mat_Metal_Gunmetal", 6, cls="metal"),
                 cyl(0.2, 0.12, (0.0, sy * 1.15, 0.2), (90, 0, 0), mat="Mat_Rubber_Tire", segs=8, cls="rubber")]
    parts.append(Part("LandingGear", gear, "metal", kind="gear"))
    return Asset(name, "Aircraft", "vehicle", parts, forward_x=True, mass=3000, lod=(1.0, 0.5, 0.2),
                 ref="General Atomics MQ-9A: L 11 m, envergadura 20.1 m, alto 3.8 m")


def build_markvi(name):
    """Patrullera Mark VI: eslora 25.8 m, manga 6.2 m, calado 1.2 m, 72 t, 2x Mk38 25 mm."""
    L, B, P = 25.8, 6.2, "Mat_Military_Navy"
    rings = []
    for f in (0.0, 0.12, 0.3, 0.55, 0.8, 1.0):
        x = L / 2 - f * L
        hw = B / 2 * (0.15 + 0.85 * min(1.0, f / 0.45) ** 0.6) if f < 1.0 else B / 2 * 0.95
        keel = 0.0 if f > 0.2 else 0.0 + (0.2 - f) * 5.0
        deck = 2.6 + (0.6 if f < 0.2 else 0.0) * (0.2 - f) * 5
        rings.append([(x, 0.0, keel), (x, hw * 0.8, keel + 0.7), (x, hw, 1.6), (x, hw, deck), (x, -hw, deck), (x, -hw, 1.6), (x, -hw * 0.8, keel + 0.7)])
    hullp = loft(rings, mat=P, cls="metal")
    aft, fwd = split_piece(hullp, V(-1.5, 0, 0), V(1, 0, 0))       # casco partido en dos
    brk = lambda ang: Matrix.Translation((-1.5, 0, 0)) @ Matrix.Rotation(math.radians(ang), 4, 'Y') @ Matrix.Translation((1.5, 0, 0))
    wreck = [aft.transform(brk(-7)), fwd.transform(brk(10))]
    parts = [Part("Hull", [hullp], "metal", kind="hull", alt={"wreck": wreck})]
    house = hull(sym([(2.5, 2.4, 2.6), (1.6, 2.2, 5.0), (-5.5, 2.3, 5.0), (-6.0, 2.5, 2.6)]), mat=P, cls="metal")
    parts.append(Part("Pilothouse", [house, box((4.0, 4.4, 0.15), (-2.0, 0, 5.1), mat=P, cls="metal")], "metal", kind="cab"))
    parts.append(Part("Windows", [glass_panel((2.45, -2.0, 2.9), (2.45, 2.0, 2.9), (1.75, 1.9, 4.6), (1.75, -1.9, 4.6), 0.03)], "glass", kind="glass"))
    mast = [strut((-3.0, 0, 5.1), (-3.0, 0, 8.5), 0.12, "Mat_Metal_Steel", 8, cls="metal"),
            cyl(0.6, 0.5, (-3.0, 0, 8.0), mat="Mat_Frame_Window", segs=12, cls="metal"),
            box((2.2, 0.15, 0.15), (-3.0, 0, 7.2), (0, 0, 90), mat="Mat_Metal_Steel", cls="metal")]
    parts.append(Part("Mast_Radar", mast, "metal", kind="detail", pivot=(-3.0, 0, 5.1), axis=(0, 1, 0), joint="break"))
    for k, x in enumerate((7.0, -9.5)):
        g = [cyl(0.7, 0.5, (x, 0, 3.0), mat=P, segs=12, cls="metal"), box((1.4, 1.1, 0.9), (x, 0, 3.7), mat=P, cls="metal"),
             cyl(0.06, 2.3, (x + 1.8, 0, 3.75), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal")]
        parts.append(Part(f"Mk38_Mount_{k}", g, "metal", kind="turret" if k == 0 else "detail", pivot=(x, 0, 2.75), axis=(0, 0, 1), joint="yaw"))
    rail = [strut((x0, sy * (B / 2 - 0.1), 2.65), (x0 - 4.0, sy * (B / 2 - 0.1), 2.65), 0.025, "Mat_Metal_Steel", 4, cls="metal")
            for sy in (-1, 1) for x0 in (11.0, 7.0, -6.5)]
    parts.append(Part("Railings", rail, "metal", kind="detail"))
    return Asset(name, "Naval", "vehicle", parts, forward_x=True, mass=72000, waterline=1.2, lod=(1.0, 0.5, 0.2),
                 ref="SAFE Boats Mark VI: eslora 25.8 m, manga 6.2 m, calado 1.2 m, 72 t (linea de flotacion z=1.2 m)")


def build_m777(name):
    """Obus M777A2 155 mm en bateria: L 10.64 m, ancho 4.35 m, tubo 5.08 m (L/39), 4.2 t."""
    P, parts = "Mat_Military_Desert", []
    body = [hull(sym([(1.1, 0.5, 0.35), (1.1, 0.45, 1.0), (-1.2, 0.55, 0.35), (-1.2, 0.5, 1.05)]), mat=P, cls="metal"),
            box((1.2, 1.2, 0.08), (0.4, 0, 0.04), mat=P, cls="metal")]
    parts.append(Part("Carriage", body, "metal", kind="body"))
    zg, el = 1.25, math.radians(12)
    d = V(math.cos(el), 0, math.sin(el))
    piv = V(-0.4, 0, zg)
    tube = strut(piv - d * 1.2, piv + d * 5.08, 0.105, "Mat_Metal_Gunmetal", 12, r2=0.09, cls="metal")
    brake = box((0.55, 0.42, 0.28), tuple(piv + d * 5.08), (0, -12, 0), mat="Mat_Metal_Gunmetal", cls="metal")
    cradle = strut(piv - d * 1.3, piv + d * 1.2, 0.2, P, 8, cls="metal")
    rec = [strut(piv + V(0, sy * 0.24, 0.05) - d * 1.0, piv + V(0, sy * 0.24, 0.05) + d * 1.6, 0.07, "Mat_Metal_Steel", 8, cls="metal") for sy in (-1, 1)]
    parts.append(Part("Barrel", [tube, brake, cradle] + rec, "metal", kind="gun", tags=("turret",), pivot=tuple(piv), axis=(0, 1, 0), joint="pitch"))
    for side, sy in (("L", 1), ("R", -1)):
        a = math.radians(sy * 28)
        end = V(-1.0 - 4.6 * math.cos(a), 4.6 * math.sin(a), 0.15)
        tr = [beam(V(-1.0, sy * 0.3, 0.45), end, 0.2, 0.28, mat=P, cls="metal"),
              box((0.15, 0.7, 0.5), tuple(end + V(-0.1, 0, -0.1)), (0, 0, math.degrees(a)), mat="Mat_Metal_Gunmetal", cls="metal")]
        parts.append(Part(f"Trail_{side}", tr, "metal", kind="tail", pivot=(-1.0, sy * 0.3, 0.45), axis=(0, 0, 1), joint="hinge"))
        parts.append(tire_wheel(-0.5, sy * 1.2, 0.5, 0.5, 0.3, f"Wheel_{side}", P))
    return Asset(name, "Artillery", "vehicle", parts, forward_x=True, mass=4200, lod=(1.0, 0.5, 0.2),
                 ref="BAE M777A2 LW155: en bateria L 10.64 m, ancho 4.35 m; tubo 5.08 m; 4.2 t")


# ==================================================================================
# BUILDERS: EDIFICIOS (elementos estructurales independientes -> colapso por grafo)
# ==================================================================================
def wall_run(p0, p1, z0, h, t, openings, mat, cls, unit=None):
    """Muro recto con vanos [(u_centro, ancho, alfeizar, alto)] -> machones, antepechos
    y dinteles como solidos convexos (cada uno se fractura por separado)."""
    p0, p1 = V(p0), V(p1)
    d = p1 - p0
    L = d.length
    ang = math.degrees(math.atan2(d.y, d.x))
    dn = d.normalized()

    def seg(ua, ub, za, zb):
        c = p0 + dn * ((ua + ub) / 2)
        if unit:                                   # mamposteria: se rompera por juntas
            return mbox((ub - ua, t, zb - za), (c.x, c.y, z0 + (za + zb) / 2), (0, 0, ang), mat=mat, cls=cls, unit=unit, u0=ua)
        return box((ub - ua, t, zb - za), (c.x, c.y, z0 + (za + zb) / 2), (0, 0, ang), mat=mat, cls=cls)
    out, u = [], 0.0
    for uc, w, sill, hh in sorted(openings):
        a, b = uc - w / 2, uc + w / 2
        if a - u > 0.05:
            out.append(seg(u, a, 0, h))
        if sill > 0.05:
            out.append(seg(a, b, 0, sill))
        if h - (sill + hh) > 0.05:
            out.append(seg(a, b, sill + hh, h))
        u = b
    if L - u > 0.05:
        out.append(seg(u, L, 0, h))
    return out


def window_part(nm, p0, p1, z0, t, uc, w, sill, hh):
    p0, p1 = V(p0), V(p1)
    dn = (p1 - p0).normalized()
    ang = math.degrees(math.atan2(dn.y, dn.x))
    c = p0 + dn * uc
    zc = z0 + sill + hh / 2
    pane = box((w - 0.1, 0.02, hh - 0.1), (c.x, c.y, zc), (0, 0, ang), mat="Mat_Glass_Window", cls="glass")
    fr = []
    for dz in (-1, 1):
        fr.append(box((w, 0.08, 0.06), (c.x, c.y, zc + dz * (hh / 2 - 0.03)), (0, 0, ang), mat="Mat_Frame_Window", cls="wood", frac=False))
    for du in (-1, 1):
        q = c + dn * (du * (w / 2 - 0.03))
        fr.append(box((0.06, 0.08, hh - 0.12), (q.x, q.y, zc), (0, 0, ang), mat="Mat_Frame_Window", cls="wood", frac=False))
    return Part(nm, [pane] + fr, "glass", kind="glass")


def door_part(nm, p0, p1, z0, uc, w, hh):
    p0, p1 = V(p0), V(p1)
    dn = (p1 - p0).normalized()
    ang = math.degrees(math.atan2(dn.y, dn.x))
    c = p0 + dn * uc
    hinge = c - dn * (w / 2)
    leaf = box((w - 0.04, 0.05, hh - 0.02), (c.x, c.y, z0 + hh / 2), (0, 0, ang), mat="Mat_Door_Wood", cls="wood",
               grain="z")
    return Part(nm, [leaf], "wood", kind="door", pivot=(hinge.x, hinge.y, z0), axis=(0, 0, 1), joint="hinge")


def build_house(name, W, D, floors, fh=2.8, t=0.25, wall_mat="Mat_Plaster_Wall", wcls="plaster", roof="gable",
                pitch=30, balcony=False, columns=False, nwin=(2, 1), parapet=False, unit=None):
    parts, slab_t = [], 0.2
    z = 0.0
    parts.append(Part("Slab_F0", [box((W + 0.3, D + 0.3, slab_t), (0, 0, slab_t / 2), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    z = slab_t
    cs = 0.4 if columns else 0.0
    for f in range(floors):
        tag = f"F{f}"
        # muros: los de X cubren toda la longitud; los de Y van entre ellos (sin solapes)
        runs = {
            "S": ((-W / 2 + cs, -D / 2 + t / 2), (W / 2 - cs, -D / 2 + t / 2)),
            "N": ((W / 2 - cs, D / 2 - t / 2), (-W / 2 + cs, D / 2 - t / 2)),
            "W": ((-W / 2 + t / 2, D / 2 - max(t, cs)), (-W / 2 + t / 2, -D / 2 + max(t, cs))),
            "E": ((W / 2 - t / 2, -D / 2 + max(t, cs)), (W / 2 - t / 2, D / 2 - max(t, cs))),
        }
        for side, (a, b) in runs.items():
            L = (V(b) - V(a)).length
            n = nwin[0] if side in "SN" else nwin[1]
            ops = []
            for k in range(n):
                uc = L * (k + 1) / (n + 1)
                ops.append((uc, 1.2, 0.9, 1.3))
            door = None
            if f == 0 and side == "S":
                ops = [o for o in ops if abs(o[0] - L / 2) > 1.2] + [(L / 2, 1.0, 0.0, 2.1)]
                door = (L / 2, 1.0, 2.1)
            parts.append(Part(f"Wall_{tag}_{side}", wall_run(a, b, z, fh, t, ops, wall_mat, wcls, unit), wcls))
            for k, (uc, w, sill, hh) in enumerate(ops):
                if sill > 0:
                    parts.append(window_part(f"Win_{tag}_{side}{k}", a, b, z, t, uc, w, sill, hh))
            if door:
                parts.append(door_part(f"Door_{tag}_{side}", a, b, z, door[0], door[1], door[2]))
        if columns:
            for sx in (-1, 1):
                for sy in (-1, 1):
                    parts.append(Part(f"Col_{tag}_{'W' if sx < 0 else 'E'}{'S' if sy < 0 else 'N'}",
                                      [box((cs, cs, fh), (sx * (W / 2 - cs / 2), sy * (D / 2 - cs / 2), z + fh / 2), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
        z += fh
        top = (f == floors - 1)
        if not top or roof == "flat":
            parts.append(Part(f"Slab_F{f + 1}", [box((W + 0.2, D + 0.2, slab_t), (0, 0, z + slab_t / 2), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
            if balcony and not top:
                b = [box((2.6, 1.2, slab_t), (0, -D / 2 - 0.6, z + slab_t / 2), mat="Mat_Concrete_Base", cls="concrete")]
                parts.append(Part(f"Balcony_F{f + 1}", b, "concrete"))
                rail = [strut((x, -D / 2 - 1.15, z + slab_t), (x, -D / 2 - 1.15, z + slab_t + 1.0), 0.02, "Mat_Metal_Steel", 4, cls="metal", frac=False)
                        for x in (-1.25, -0.6, 0.0, 0.6, 1.25)]
                rail.append(strut((-1.28, -D / 2 - 1.15, z + slab_t + 1.0), (1.28, -D / 2 - 1.15, z + slab_t + 1.0), 0.025, "Mat_Metal_Steel", 4, cls="metal", frac=False))
                parts.append(Part(f"Railing_F{f + 1}", rail, "metal", kind="detail"))
            z += slab_t
    if roof == "gable":
        p = math.radians(pitch)
        ov = 0.45
        rise = (D / 2) * math.tan(p)
        for k, sy in enumerate((-1, 1)):
            run = D / 2 + ov
            yc = sy * run / 2
            zc = z + rise - (run / 2) * math.tan(p) + 0.09 / math.cos(p)
            slab = box((W + 2 * ov, run / math.cos(p) + 0.05, 0.18), (0, yc, zc + 0.03), (sy * -pitch, 0, 0), mat="Mat_Roof_Tile", cls="wood")
            parts.append(Part(f"Roof_{'S' if sy < 0 else 'N'}", [slab], "wood"))
        for sx in (-1, 1):
            g = prism([(-D / 2, 0), (D / 2, 0), (0, rise)], t, axis='x', offset=sx * (W / 2 - t / 2), mat=wall_mat, cls=wcls)
            g.transform(Matrix.Translation((0, 0, z)))
            parts.append(Part(f"Gable_{'W' if sx < 0 else 'E'}", [g], wcls))
        parts.append(Part("Chimney", [box((0.6, 0.6, rise + 1.0), (W * 0.25, D * 0.15, z + (rise + 1.0) / 2), mat="Mat_Brick_Wall", cls="brick")], "brick"))
    elif parapet:
        par = [box((W + 0.2, 0.2, 0.9), (0, sy * (D / 2), z + 0.45), mat=wall_mat, cls=wcls) for sy in (-1, 1)]
        par += [box((0.2, D - 0.2, 0.9), (sx * (W / 2), 0, z + 0.45), mat=wall_mat, cls=wcls) for sx in (-1, 1)]
        parts.append(Part("Parapet", par, wcls))
        parts.append(Part("Roof_Tank", [cyl(0.8, 1.6, (W * 0.25, D * 0.2, z + 0.8 + 0.1), mat="Mat_Metal_Steel", segs=12, cls="metal")], "metal", kind="detail"))
    return parts


def build_house_small(name):
    parts = build_house(name, 8.0, 6.0, 1, nwin=(2, 1))
    return Asset(name, "Buildings", "structure", parts, n_impacts=2, dmg_r=1.3, ruin_h=0.3, spread=0.3, rubble_cell=3.0,
                 debris="plaster", lod=(1.0,), ref="Vivienda unifamiliar 8x6 m, muros 25 cm, cubierta a dos aguas 30 deg")


def build_house_two(name):
    parts = build_house(name, 9.0, 7.5, 2, fh=2.9, wall_mat="Mat_Brick_Wall", wcls="brick", balcony=True, nwin=(3, 2))
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=1.5, ruin_h=0.25, spread=0.3, rubble_cell=3.0, chunk_scale=0.85,
                 debris="brick", lod=(1.0,), ref="Vivienda 2 plantas de ladrillo 9x7.5 m con balcon")


def build_apartment(name):
    parts = build_house(name, 14.0, 10.0, 4, fh=3.0, wall_mat="Mat_Plaster_Wall", wcls="brick", roof="flat", balcony=True,
                        columns=True, nwin=(3, 2), parapet=True)
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=2.2, ruin_h=0.22, spread=0.25, rubble_cell=4.0, chunk_scale=0.65,
                 debris="concrete", lod=(1.0,), ref="Bloque de 4 plantas, porticos de hormigon + cerramiento de ladrillo, 14x10 m")


def arc_pts(R, n, x0=0.0):
    return [(R * math.cos(math.pi * i / n), R * math.sin(math.pi * i / n)) for i in range(n + 1)]


def build_has(name):
    """Refugio endurecido de aviones (HAS): boveda de hormigon 0.6 m, 14 m de luz, 22 m de fondo."""
    R, Lh, th, n = 7.0, 22.0, 0.6, 14
    parts = []
    arc = arc_pts(R, n)
    nseg = 8
    for k in range(nseg):
        y0 = -Lh / 2 + Lh * k / nseg
        seg = band(arc, th, Lh / nseg, y0 + Lh / nseg / 2, mat="Mat_Concrete_Base", i0=0, i1=n, cls="concrete")
        parts.append(Part(f"Vault_{k}", [seg], "concrete"))
    back = prism(arc, 0.5, axis='y', offset=Lh / 2 + 0.25, mat="Mat_Concrete_Base", cls="concrete")
    parts.append(Part("BackWall", [back], "concrete"))
    dw, dh = 9.0, 5.2
    zx = lambda x: math.sqrt(max(R * R - x * x, 0.0))
    left = [(-R, 0), (-dw / 2, 0), (-dw / 2, zx(dw / 2))] + sorted([p for p in arc if -R < p[0] < -dw / 2], key=lambda p: p[0], reverse=True)
    right = [(dw / 2, 0), (R, 0)] + sorted([p for p in arc if dw / 2 < p[0] < R], key=lambda p: p[0], reverse=True) + [(dw / 2, zx(dw / 2))]
    top = [(-dw / 2, dh), (dw / 2, dh), (dw / 2, zx(dw / 2))] + sorted([p for p in arc if -dw / 2 < p[0] < dw / 2], key=lambda p: p[0], reverse=True) + [(-dw / 2, zx(dw / 2))]
    fw = [prism(poly, 0.5, axis='y', offset=-Lh / 2 - 0.25, mat="Mat_Concrete_Base", cls="concrete") for poly in (left, right, top)]
    parts.append(Part("FrontFrame", fw, "concrete"))
    for k, sx in enumerate((-1, 1)):
        leaf = box((dw / 2 - 0.05, 0.25, dh - 0.05), (sx * dw / 4, -Lh / 2 - 0.65, dh / 2), mat="Mat_Military_Grey", cls="metal")
        parts.append(Part(f"BlastDoor_{k}", [leaf], "metal", kind="door", pivot=(sx * dw / 2, -Lh / 2 - 0.65, 0), axis=(1, 0, 0), joint="slide"))
    parts.append(Part("Floor", [box((2 * R + 1.0, Lh + 1.5, 0.3), (0, 0, 0.15), mat="Mat_Concrete_Interior", cls="concrete")], "concrete"))
    for p in parts:
        if p.name.startswith(("Vault", "BackWall", "FrontFrame", "BlastDoor")):
            for pc in p.pieces:
                pc.transform(Matrix.Translation((0, 0, 0.3)))
    return Asset(name, "Buildings", "structure", parts, n_impacts=2, dmg_r=2.5, ruin_h=0.3, spread=0.2, rubble_cell=4.0, chunk_scale=0.8,
                 debris="concrete", lod=(1.0,), ref="Hardened Aircraft Shelter (tipo OTAN 3a gen), boveda de hormigon armado")


# ==================================================================================
# BUILDERS: TERRENO
# ==================================================================================
def terrain_height(x, y):
    return (1.3 * noise.noise(V(x * 0.045, y * 0.045, 0.37)) + 0.45 * noise.noise(V(x * 0.16, y * 0.16, 4.1))
            + 0.12 * noise.noise(V(x * 0.6, y * 0.6, 9.3)))


def build_terrain(name, S=32.0, tile=8.0, res=0.5, depth=3.0):
    """Terreno solido en tiles cerrados (superficie + faldon + base): se pueden
    deformar (crateres), intercambiar por tile y su interior muestra tierra."""
    parts, q = [], int(round(tile / res))
    n = int(round(S / tile))
    for ti in range(n):
        for tj in range(n):
            x0, y0 = -S / 2 + ti * tile, -S / 2 + tj * tile
            bm = bmesh.new()
            g = [[bm.verts.new((x0 + i * res, y0 + j * res, depth + terrain_height(x0 + i * res, y0 + j * res)))
                  for j in range(q + 1)] for i in range(q + 1)]
            for i in range(q):
                for j in range(q):
                    f = bm.faces.new((g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]))
                    f.smooth = True
            ring = [g[i][0] for i in range(q + 1)] + [g[q][j] for j in range(1, q + 1)] + \
                   [g[i][q] for i in range(q - 1, -1, -1)] + [g[0][j] for j in range(q - 1, 0, -1)]
            bot = [bm.verts.new((v.co.x, v.co.y, 0.0)) for v in ring]
            for k in range(len(ring)):
                f = bm.faces.new((ring[k], bot[k], bot[(k + 1) % len(ring)], ring[(k + 1) % len(ring)]))
                f.material_index = 1
            fb = bm.faces.new(bot[::-1])
            fb.material_index = 1
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            pc = Piece(bm, "Mat_Terrain_Grass", "earth", None, False)
            parts.append(Part(f"Tile_{ti}_{tj}", [pc], "earth", kind="tile"))
    return Asset(name, "Terrain", "terrain", parts, lod=(1.0, 0.5, 0.25),
                 ref="Tile %dx%d m, resolucion %.1f m, espesor solido %.1f m (superficie ~z=%.1f)" % (S, S, res, depth, depth))


def build_rock(name):
    parts = [Part("Boulder", [ico(1.6, (0, 0, 1.0), mat="Mat_Rock_Base", subdiv=2, rough=0.35, seed=3, scale=(1.3, 1.0, 0.75), cls="rock")], "rock")]
    for k, (x, y, r) in enumerate(((1.9, 0.9, 0.6), (-1.7, -0.8, 0.45))):
        parts.append(Part(f"Stone_{k}", [ico(r, (x, y, r * 0.6), mat="Mat_Rock_Base", subdiv=1, rough=0.3, seed=7 + k, scale=(1.2, 1, 0.8), cls="rock")], "rock"))
    return Asset(name, "Terrain", "structure", parts, n_impacts=1, dmg_r=0.9, ruin_h=0.4, spread=0.6, rubble_cell=2.0,
                 debris="rock", lod=(1.0, 0.5, 0.25), ref="Roca granitica ~4 x 3 x 1.5 m")


def build_craters(name):
    """Estampas de crater (S/M/L) centradas en el origen: hundir 'D' en el terreno."""
    parts = []
    for tag, R, D in (("S", 1.2, 0.5), ("M", 2.5, 1.0), ("L", 4.5, 1.8)):
        prof = [(0, 0.0), (0.35 * R, 0.08 * D), (0.75 * R, 0.6 * D), (R, 1.35 * D), (1.3 * R, 1.1 * D), (1.7 * R, D), (1.7 * R, -0.05)]
        pc = lathe(prof, mat="Mat_Terrain_Soil", segs=20, smooth=True, cls="earth", frac=False)
        for f in pc.bm.faces:
            c = f.calc_center_median()
            if math.hypot(c.x, c.y) < 0.85 * R and f.normal.z > 0.2:
                f.material_index = 2
        parts.append(Part(f"Crater_{tag}", [pc], "earth", kind="decal"))
    return Asset(name, "Terrain", "static", parts, lod=(1.0, 0.5), ref="Crateres de impacto S/M/L (R 1.2/2.5/4.5 m)")


# ==================================================================================
# BUILDERS: VEGETACION (tronco con veta vertical -> astillas al talar)
# ==================================================================================
def build_pine(name):
    rng = random.Random(name)
    trunk = lathe([(0.28, 0), (0.22, 0.5), (0.15, 6.0), (0.05, 11.5), (0, 12.2)], mat="Mat_Bark_Pine", segs=8, cls="wood", grain="z")
    leaves = []
    for k in range(6):
        z = 3.0 + k * 1.5
        r = 2.7 - k * 0.38
        leaves.append(cyl(r, 2.3, (rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), z + 1.0), (rng.uniform(-4, 4), rng.uniform(-4, 4), rng.uniform(0, 60)),
                          mat="Mat_Leaves_Pine", segs=9, r2=0.08, smooth=False, cls="foliage", frac=False))
    return Asset(name, "Vegetation", "tree", [Part("Trunk", [trunk], "wood", kind="trunk"), Part("Foliage", leaves, "foliage", kind="foliage")],
                 cut_h=0.7, lod=(1.0, 0.5, 0.2), ref="Pino silvestre ~12 m")


def build_oak(name):
    rng = random.Random(name)
    trunk = lathe([(0.45, 0), (0.36, 0.4), (0.3, 2.5), (0.22, 4.3), (0, 4.6)], mat="Mat_Bark_Oak", segs=9, cls="wood", grain="z")
    br, leaves = [], []
    for k in range(5):
        a = 2 * math.pi * k / 5 + rng.uniform(-0.3, 0.3)
        z0 = rng.uniform(3.2, 4.2)
        tip = V(math.cos(a) * rng.uniform(1.8, 2.6), math.sin(a) * rng.uniform(1.8, 2.6), z0 + rng.uniform(1.5, 2.3))
        br.append(strut((0, 0, z0), tip, 0.13, "Mat_Bark_Oak", 6, r2=0.06, cls="wood", grain="z"))
        leaves.append(ico(rng.uniform(1.5, 2.0), tuple(tip + V(0, 0, 0.4)), mat="Mat_Leaves_Oak", subdiv=1, rough=0.25, seed=k, smooth=True, cls="foliage", frac=False))
    leaves.append(ico(2.2, (0, 0, 6.6), mat="Mat_Leaves_Oak", subdiv=1, rough=0.25, seed=9, smooth=True, cls="foliage", frac=False))
    return Asset(name, "Vegetation", "tree", [Part("Trunk", [trunk], "wood", kind="trunk"), Part("Branches", br, "wood", kind="branch"),
                                              Part("Foliage", leaves, "foliage", kind="foliage")],
                 cut_h=0.8, lod=(1.0, 0.5, 0.2), ref="Roble ~8.5 m, copa 7 m")


def build_palm(name):
    rng = random.Random(name)
    rings = []
    for k in range(9):
        t = k / 8.0
        c = V(0.9 * t * t, 0, 9.0 * t)
        r = 0.24 - 0.08 * t
        rings.append([(c.x + r * math.cos(2 * math.pi * i / 8), r * math.sin(2 * math.pi * i / 8), c.z) for i in range(8)])
    trunk = loft(rings, mat="Mat_Bark_Palm", smooth=True, cls="wood", grain="z")
    top = V(0.9, 0, 9.0)
    fronds = []
    for k in range(9):
        a = 2 * math.pi * k / 9 + rng.uniform(-0.15, 0.15)
        d = V(math.cos(a), math.sin(a), 0)
        side = V(-d.y, d.x, 0)
        secs = []
        for i in range(7):
            u = i / 6.0
            p = top + d * (3.6 * u) + V(0, 0, 0.9 * math.sin(u * math.pi * 0.8) - 1.6 * u * u)
            w = 0.05 + 0.5 * math.sin(u * math.pi)
            secs.append([tuple(p + side * w), tuple(p + V(0, 0, 0.04)), tuple(p - side * w), tuple(p - V(0, 0, 0.03))])
        fronds.append(loft(secs, mat="Mat_Leaves_Palm", cls="foliage", frac=False))
    nuts = [sphere(0.12, tuple(top + V(math.cos(a) * 0.25, math.sin(a) * 0.25, -0.3)), mat="Mat_Bark_Palm", segs=8, rings=5, cls="foliage", frac=False)
            for a in (0.3, 2.2, 4.1)]
    return Asset(name, "Vegetation", "tree", [Part("Trunk", [trunk], "wood", kind="trunk"), Part("Fronds", fronds + nuts, "foliage", kind="foliage")],
                 cut_h=0.9, lod=(1.0, 0.5, 0.2), ref="Palmera datilera ~10 m")


def build_dead_tree(name):
    rng = random.Random(name)
    trunk = lathe([(0.38, 0), (0.3, 0.5), (0.22, 3.0), (0.1, 6.0), (0, 6.6)], mat="Mat_Bark_Dead", segs=8, smooth=False, cls="wood", grain="z")
    br = []
    for k in range(6):
        a = rng.uniform(0, 2 * math.pi)
        z0 = rng.uniform(2.0, 5.2)
        r0 = V(0, 0, z0)
        mid = r0 + V(math.cos(a), math.sin(a), 0) * rng.uniform(0.8, 1.4) + V(0, 0, rng.uniform(0.4, 1.0))
        tip = mid + V(math.cos(a + 0.5), math.sin(a + 0.5), 0) * rng.uniform(0.5, 1.0) + V(0, 0, rng.uniform(0.3, 0.9))
        br += [strut(r0, mid, 0.08, "Mat_Bark_Dead", 5, r2=0.05, cls="wood", grain="z"), strut(mid, tip, 0.05, "Mat_Bark_Dead", 5, r2=0.015, cls="wood", grain="z")]
    return Asset(name, "Vegetation", "tree", [Part("Trunk", [trunk], "wood", kind="trunk"), Part("Branches", br, "wood", kind="branch")],
                 cut_h=0.6, lod=(1.0, 0.5, 0.2), ref="Arbol seco ~7 m")


def build_bush(name):
    rng = random.Random(name)
    cl = [ico(rng.uniform(0.45, 0.7), (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(0.45, 0.8)), mat="Mat_Leaves_Bush",
              subdiv=1, rough=0.3, seed=k, smooth=True, cls="foliage", frac=False) for k in range(6)]
    st = [strut((0, 0, 0), (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0.6), 0.03, "Mat_Bark_Oak", 4, cls="wood", frac=False) for _ in range(4)]
    return Asset(name, "Vegetation", "plant", [Part("Bush", cl + st, "foliage", kind="foliage")], lod=(1.0, 0.5, 0.25), ref="Arbusto ~1.6 m")


def build_grass(name):
    rng = random.Random(name)
    blades = []
    for k in range(16):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, 0.25)
        b = V(math.cos(a) * r, math.sin(a) * r, 0)
        tip = b + V(math.cos(a) * rng.uniform(0.1, 0.35), math.sin(a) * rng.uniform(0.1, 0.35), rng.uniform(0.35, 0.75))
        side = V(-math.sin(a), math.cos(a), 0) * 0.02
        blades.append(hull([tuple(b + side), tuple(b - side), tuple(b + V(math.cos(a), math.sin(a), 0) * 0.012), tuple(tip)],
                           mat="Mat_Grass_Blade", cls="foliage", frac=False))
    return Asset(name, "Vegetation", "plant", [Part("Grass", blades, "foliage", kind="foliage")], lod=(1.0, 0.5), ref="Mata de hierba ~0.6 m")


# ==================================================================================
# MAMPOSTERIA: los muros de bloque/adobe se rompen POR LAS JUNTAS (hiladas a matajunta)
#  - L1 = grupos irregulares escalonados de bloques; L2 = bloques sueltos
#  - la ruina deja caer bloques individuales (montones como en la realidad)
# ==================================================================================
def mbox(size, loc=(0, 0, 0), rot=(0, 0, 0), mat="Mat_CinderBlock", cls="cinder", unit=(0.4, 0.2), u0=0.0, **kw):
    """Caja de mamposteria: geometria intacta ligera + descriptor de aparejo."""
    p = box(size, loc, rot, mat=mat, cls=cls, **kw)
    p.mason = (mat4(loc, rot), V(size), unit, u0)
    return p


def _box_faces(bm, x0, x1, y0, y1, z0, z1, ext):
    """Bloque cerrado; ext(cx,cy,cz,n) decide si cada cara es exterior (0) o junta rota (1)."""
    vs = [bm.verts.new(c) for c in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                    (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
    quads = (((0, 3, 2, 1), (0, 0, -1)), ((4, 5, 6, 7), (0, 0, 1)), ((0, 1, 5, 4), (0, -1, 0)),
             ((2, 3, 7, 6), (0, 1, 0)), ((1, 2, 6, 5), (1, 0, 0)), ((3, 0, 4, 7), (-1, 0, 0)))
    for idx, n in quads:
        f = bm.faces.new([vs[i] for i in idx])
        c = sum((vs[i].co for i in idx), V(0, 0, 0)) / 4
        f.material_index = 0 if ext(c, n) else 1
        f.smooth = False


def masonry_cells(pc, rng, mean_blocks=6, gap=0.004):
    """Devuelve [(cluster Piece, [bloques Piece])] siguiendo hiladas y llagas reales."""
    F, size, (ul, uh), u0 = pc.mason
    L, T, H = size
    zb_w = (F @ V(0, 0, -H / 2)).z
    courses, k = [], int(math.floor((zb_w + 1e-6) / uh))
    while True:
        za, zc = k * uh - zb_w - H / 2, (k + 1) * uh - zb_w - H / 2
        lo, hi = max(za, -H / 2), min(zc, H / 2)
        if hi - lo > 1e-3:
            courses.append((lo, hi, k))
        if zc >= H / 2 - 1e-6:
            break
        k += 1
    blocks = []
    for (z0, z1, k) in courses:
        off = (k % 2) * ul * 0.5
        j = int(math.floor((u0 - off) / ul))
        while True:
            ua, ub = off + j * ul, off + (j + 1) * ul
            a, b = max(ua, u0), min(ub, u0 + L)
            if b - a > 1e-3:
                blocks.append((k, a - u0 - L / 2, b - u0 - L / 2, z0, z1))
            if ub >= u0 + L - 1e-6:
                break
            j += 1
    nseed = max(1, int(round(len(blocks) / mean_blocks)))
    seeds = [(rng.uniform(-L / 2, L / 2), rng.uniform(-H / 2, H / 2)) for _ in range(nseed)]
    groups = {}
    for b in blocks:
        cx, cz = (b[1] + b[2]) / 2, (b[3] + b[4]) / 2
        s = min(range(nseed), key=lambda i: (seeds[i][0] - cx) ** 2 + ((seeds[i][1] - cz) * 1.7) ** 2)
        groups.setdefault(s, []).append(b)

    def ext(c, n):
        return (abs(abs(c.y) - T / 2) < 1e-4 and abs(n[1]) > 0.5) or (abs(abs(c.x) - L / 2) < 1e-4 and abs(n[0]) > 0.5) \
            or (abs(abs(c.z) - H / 2) < 1e-4 and abs(n[2]) > 0.5)
    out = []
    for grp in groups.values():
        bm = bmesh.new()
        rows = {}
        for b in grp:
            rows.setdefault(b[0], []).append(b)
        for k, row in rows.items():                       # tramos contiguos por hilada = menos caras
            row.sort(key=lambda b: b[1])
            run = list(row[0])
            for b in row[1:]:
                if abs(b[1] - run[2]) < 1e-4:
                    run[2] = b[2]
                else:
                    _box_faces(bm, run[1], run[2], -T / 2, T / 2, run[3], run[4], ext)
                    run = list(b)
            _box_faces(bm, run[1], run[2], -T / 2, T / 2, run[3], run[4], ext)
        bmesh.ops.transform(bm, matrix=F, verts=bm.verts[:])
        bm.normal_update()
        bl = []
        for b in grp:
            bb = bmesh.new()
            _box_faces(bb, b[1] + gap, b[2] - gap, -T / 2, T / 2, b[3] + gap * 0.5, b[4] - gap * 0.5, ext)
            bmesh.ops.transform(bb, matrix=F, verts=bb.verts[:])
            bb.normal_update()
            bl.append(Piece(bb, pc.mat, pc.cls, None, True, pc.tag))
        out.append((Piece(bm, pc.mat, pc.cls, None, True, pc.tag), bl))
    return out


# ==================================================================================
# BUILDERS: MUROS, COMPOUND DESERTICO, FORTIFICACIONES DE CAMPANA, PROPS
# ==================================================================================
def build_cinder_wall(name):
    """Muro de bloque de hormigon (CMU 390x190x190 + junta 10 mm), 6 m x 2 m, zapata."""
    parts = [Part("Footing", [box((6.4, 0.45, 0.25), (0, 0, 0.125), mat="Mat_Concrete_Base", cls="concrete")], "concrete")]
    for k in range(3):
        parts.append(Part(f"BlockWall_{k}", [mbox((2.0, 0.19, 2.0), (-2.0 + k * 2.0, 0, 0.25 + 1.0), u0=k * 2.0)], "cinder"))
    parts.append(Part("CapBeam", [box((6.0, 0.24, 0.1), (0, 0, 2.3), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=0.7, ruin_h=0.3, spread=0.5, rubble_cell=1.5,
                 debris="cinder", mason_l2=True, lod=(1.0,), ref="Bloque CMU 390x190x190 mm (modulo 400x200), aparejo a matajunta")


def build_twall(name):
    """T-wall / Bremer: 3.66 m de alto, tramos de 1.52 m, base en T de 1.2 m."""
    parts = []
    for k in range(3):
        x = (k - 1) * 1.54
        base = box((1.52, 1.2, 0.45), (x, 0, 0.225), mat="Mat_Concrete_Base", cls="concrete")
        slab = prism([(-0.16, 0.45), (0.16, 0.45), (0.1, 3.66), (-0.1, 3.66)], 1.52, axis='x', offset=x, mat="Mat_Concrete_Base", cls="concrete")
        loops = [strut((x + dx - 0.1, 0, 3.62), (x + dx, 0, 3.8), 0.02, "Mat_Rebar_Rust", 4, cls="metal", frac=False) for dx in (-0.4, 0.5)]
        parts.append(Part(f"TWall_{k}", [base, slab] + loops, "concrete"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=0.9, ruin_h=0.3, spread=0.4, rubble_cell=2.0,
                 debris="concrete", lod=(1.0,), ref="Bremer/T-wall 12 ft (3.66 m), tramos 5 ft (1.52 m)")


def build_dragons_teeth(name):
    parts = [Part("Strip", [box((5.4, 1.4, 0.2), (0, 0, 0.1), mat="Mat_Concrete_Base", cls="concrete")], "concrete")]
    for k in range(4):
        x = -2.0 + k * 1.33
        t = hull([(x + sx * 0.45, sy * 0.45, 0.2) for sx in (-1, 1) for sy in (-1, 1)] +
                 [(x + sx * 0.15, sy * 0.15, 1.2) for sx in (-1, 1) for sy in (-1, 1)], mat="Mat_Concrete_Base", cls="concrete")
        parts.append(Part(f"Tooth_{k}", [t], "concrete"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=0.6, ruin_h=0.5, spread=0.4, rubble_cell=1.5,
                 debris="concrete", lod=(1.0,), ref="Dientes de dragon de hormigon armado ~1 m")


def build_concertina(name):
    """Concertina de alambre de puas: bobinas de 0.9 m, 9 m estiradas, piquetes cada 3 m."""
    parts, R, L, loops = [], 0.45, 9.0, 30
    for seg in range(3):
        wire = []
        x0 = -L / 2 + seg * L / 3
        n = loops // 3 * 8
        prev = None
        for i in range(n + 1):
            t = i / n
            a = 2 * math.pi * loops / 3 * t
            p = V(x0 + t * L / 3, R * math.cos(a), R + R * math.sin(a) + 0.02)
            if prev is not None:
                wire.append(strut(prev, p, 0.006, "Mat_Wire_Steel", 3, cls="metal", frac=False, smooth=False))
            prev = p
        wire.append(strut((x0 + 0.1, 0, 0), (x0 + 0.1, 0, 1.0), 0.02, "Mat_Metal_Gunmetal", 4, cls="metal", frac=False))
        parts.append(Part(f"Concertina_{seg}", wire, "metal", kind="detail"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=0.8, ruin_h=0.4, spread=0.6, rubble_cell=2.0,
                 debris="metal", lod=(1.0, 0.5), ref="Concertina M-1 (bobina ~0.9 m) con piquetes")


def build_utility_pole(name):
    """Poste de madera creosotada 10.5 m + cruceta 2.4 m + aisladores (se parte como un arbol)."""
    pole = lathe([(0.16, 0), (0.15, 3.0), (0.11, 10.5), (0, 10.55)], mat="Mat_Pole_Wood", segs=8, cls="wood", grain="z")
    arm = [box((2.4, 0.1, 0.12), (0, 0, 9.9), mat="Mat_Pole_Wood", cls="wood", grain="x"),
           strut((-0.8, 0, 9.85), (0, 0, 9.3), 0.025, "Mat_Wire_Steel", 4, cls="metal"),
           strut((0.8, 0, 9.85), (0, 0, 9.3), 0.025, "Mat_Wire_Steel", 4, cls="metal")]
    arm += [cyl(0.05, 0.16, (x, 0, 10.04), mat="Mat_Insulator", segs=8, cls="glass", frac=False) for x in (-1.05, 0.0, 1.05)]
    arm += [box((0.5, 0.4, 0.7), (0, -0.3, 8.2), mat="Mat_Metal_Steel", cls="metal")]
    return Asset(name, "Props", "tree", [Part("Pole", [pole], "wood", kind="trunk"), Part("Crossarm", arm, "wood", kind="branch")],
                 cut_h=1.0, lod=(1.0, 0.5), ref="Poste de distribucion clase 35 ft (~10.5 m) con cruceta de 8 ft")


def build_fence(name):
    rng = random.Random(name)
    parts = []
    for s in range(3):
        x0 = -4.5 + s * 3.0
        pcs = [box((0.1, 0.1, 1.3), (x0, 0, 0.65), mat="Mat_Wood_Beam", cls="wood", grain="z")]
        pcs += [box((3.0, 0.04, 0.09), (x0 + 1.5, 0.06, z), mat="Mat_Wood_Plank", cls="wood", grain="x") for z in (0.35, 0.95)]
        for k in range(12):
            h = rng.uniform(1.05, 1.15)
            pcs.append(box((0.09, 0.02, h), (x0 + 0.12 + k * 0.24, 0.09, h / 2 + 0.05), mat="Mat_Wood_Plank", cls="wood", grain="z"))
        parts.append(Part(f"Fence_{s}", pcs, "wood"))
    return Asset(name, "Props", "structure", parts, n_impacts=1, dmg_r=0.8, ruin_h=0.35, spread=0.6, rubble_cell=2.0,
                 debris="wood", lod=(1.0,), ref="Valla de madera rural, tramos de 3 m")


def build_compound(name):
    """Compound/qalat de adobe 22 x 18 m: muro de 2.6 m (ladrillos 0.45 x 0.22),
    pilastras, porton metalico, casa de techo plano con pretil y escalera a azotea."""
    W, D, H, t = 22.0, 18.0, 2.6, 0.45
    U = (0.45, 0.22)
    M = dict(mat="Mat_Mudbrick", cls="mudbrick", unit=U)
    parts = []
    gate_w = 3.6
    runs = {"S": ((-W / 2, -D / 2), (W / 2, -D / 2)), "N": ((W / 2, D / 2), (-W / 2, D / 2)),
            "W": ((-W / 2, D / 2 - t), (-W / 2, -D / 2 + t)), "E": ((W / 2, -D / 2 + t), (W / 2, D / 2 - t))}
    for side, (a, b) in runs.items():
        a, b = V(a), V(b)
        L = (b - a).length
        dn = (b - a).normalized()
        ang = math.degrees(math.atan2(dn.y, dn.x))
        cuts = [(L / 2 - gate_w / 2, L / 2 + gate_w / 2)] if side == "S" else []
        spans, u = [], 0.0
        for c0, c1 in cuts:
            spans.append((u, c0))
            u = c1
        spans.append((u, L))
        for k, (s0, s1) in enumerate(spans):
            nseg = max(1, int(round((s1 - s0) / 4.0)))
            for j in range(nseg):
                ua, ub = s0 + (s1 - s0) * j / nseg, s0 + (s1 - s0) * (j + 1) / nseg
                c = a + dn * ((ua + ub) / 2)
                parts.append(Part(f"Wall_{side}{k}_{j}", [mbox((ub - ua, t, H), (c.x, c.y, H / 2), (0, 0, ang), u0=ua, **M)], "mudbrick"))
                p = a + dn * ub
                if ub < s1 - 0.01 or (cuts and abs(ub - cuts[0][0]) < 0.01):
                    parts.append(Part(f"Pilaster_{side}{k}_{j}", [mbox((0.7, 0.7, H + 0.3), (p.x, p.y, (H + 0.3) / 2), (0, 0, ang), u0=ub, **M)], "mudbrick"))
    for k, sx in enumerate((-1, 1)):
        leaf = [box((gate_w / 2 - 0.05, 0.06, 2.3), (sx * gate_w / 4, -D / 2, 1.2), mat="Mat_Military_Navy", cls="metal")]
        leaf += [box((gate_w / 2 - 0.1, 0.08, 0.06), (sx * gate_w / 4, -D / 2, z), mat="Mat_Metal_Gunmetal", cls="metal", frac=False) for z in (0.4, 1.2, 2.0)]
        parts.append(Part(f"Gate_{k}", leaf, "metal", kind="door", pivot=(sx * gate_w / 2, -D / 2, 0), axis=(0, 0, 1), joint="hinge"))
    # casa principal (techo plano, pretil, ventanas pequenas)
    hx, hy, HW, HD, HH = 3.0, 4.5, 10.0, 6.5, 3.0
    hruns = {"S": ((hx - HW / 2, hy - HD / 2 + t / 2), (hx + HW / 2, hy - HD / 2 + t / 2)),
             "N": ((hx + HW / 2, hy + HD / 2 - t / 2), (hx - HW / 2, hy + HD / 2 - t / 2)),
             "W": ((hx - HW / 2 + t / 2, hy + HD / 2 - t), (hx - HW / 2 + t / 2, hy - HD / 2 + t)),
             "E": ((hx + HW / 2 - t / 2, hy - HD / 2 + t), (hx + HW / 2 - t / 2, hy + HD / 2 - t))}
    for side, (a, b) in hruns.items():
        L = (V(b) - V(a)).length
        ops = [(L * 0.25, 0.9, 1.1, 0.9), (L * 0.75, 0.9, 1.1, 0.9)] if side in "SN" else [(L / 2, 0.8, 1.1, 0.9)]
        if side == "S":
            ops = [(L * 0.2, 0.9, 1.1, 0.9), (L * 0.5, 1.0, 0.0, 2.1), (L * 0.8, 0.9, 1.1, 0.9)]
        pcs = wall_run(a, b, 0.0, HH, t, ops, "Mat_Mudbrick", "mudbrick", U)
        parts.append(Part(f"House_Wall_{side}", pcs, "mudbrick"))
        for k, (uc, w, sill, hh) in enumerate(ops):
            if sill > 0:
                parts.append(window_part(f"House_Win_{side}{k}", a, b, 0.0, t, uc, w, sill, hh))
            else:
                parts.append(door_part(f"House_Door_{side}", a, b, 0.0, uc, w, hh))
    parts.append(Part("House_Roof", [box((HW + 0.3, HD + 0.3, 0.25), (hx, hy, HH + 0.125), mat="Mat_Plaster_Desert", cls="concrete")], "concrete"))
    par = [mbox((HW + 0.3, 0.25, 0.6), (hx, hy + sy * (HD / 2), HH + 0.55), u0=0.0, **M) for sy in (-1, 1)]
    par += [mbox((0.25, HD - 0.2, 0.6), (hx + sx * (HW / 2), hy, HH + 0.55), (0, 0, 90), u0=0.0, **M) for sx in (-1, 1)]
    parts.append(Part("House_Parapet", par, "mudbrick"))
    stairs = [box((1.0, 0.3, 0.2 * (k + 1)), (hx - HW / 2 - 0.6, hy - HD / 2 + 0.6 + k * 0.3, 0.1 * (k + 1)), mat="Mat_Concrete_Base", cls="concrete")
              for k in range(15)]
    parts.append(Part("House_Stairs", stairs, "concrete"))
    parts.append(Part("Roof_Tank", [cyl(0.55, 1.1, (hx + 3.0, hy + 1.5, HH + 0.8), mat="Mat_Civil_White", segs=12, cls="metal")], "metal", kind="detail"))
    # almacen en esquina
    sx0, sy0 = -W / 2 + 2.6, D / 2 - 2.6
    store = [mbox((4.6, 0.4, 2.4), (sx0, sy0 - 2.1, 1.2), u0=0.0, **M), mbox((0.4, 3.8, 2.4), (sx0 + 2.1, sy0 + 0.1, 1.2), (0, 0, 90), u0=0.0, **M)]
    parts.append(Part("Store_Walls", store, "mudbrick"))
    parts.append(Part("Store_Roof", [box((4.9, 4.9, 0.2), (sx0, sy0, 2.5), mat="Mat_Wood_Beam", cls="wood", grain="x")], "wood"))
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=1.6, ruin_h=0.35, spread=0.3, rubble_cell=3.0,
                 debris="mudbrick", lod=(1.0,), ref="Qalat/compound afgano-iraqui: muros de adobe 2.6 m, ladrillos ~45x22 cm")


def build_desert_house(name):
    """Casa urbana de 2 plantas, bloque revocado, techo plano con pretil y caseton de escalera."""
    parts = build_house(name, 9.0, 8.0, 2, fh=3.0, wall_mat="Mat_Plaster_Desert", wcls="cinder", roof="flat",
                        balcony=True, nwin=(2, 2), parapet=True, unit=(0.4, 0.2))
    z = 0.2 + 2 * 3.0 + 2 * 0.2
    hut = [mbox((2.6, 0.2, 2.2), (2.0, 2.0 + sy * 1.3, z + 1.1), u0=0.0, mat="Mat_Plaster_Desert", cls="cinder") for sy in (-1, 1)]
    hut += [mbox((2.4, 0.2, 2.2), (2.0 + 1.3, 2.0, z + 1.1), (0, 0, 90), u0=0.0, mat="Mat_Plaster_Desert", cls="cinder")]
    parts.append(Part("RoofHut_Walls", hut, "cinder"))
    parts.append(Part("RoofHut_Slab", [box((2.9, 2.9, 0.15), (2.0, 2.0, z + 2.27), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    parts.append(Part("Sat_Dish", [cyl(0.45, 0.06, (-3.0, -2.5, z + 1.2), (60, 0, 0), mat="Mat_Civil_White", segs=12, cls="metal"),
                                   strut((-3.0, -2.5, z + 0.1), (-3.0, -2.5, z + 1.1), 0.03, "Mat_Metal_Steel", 4, cls="metal")], "metal", kind="detail"))
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=1.6, ruin_h=0.25, spread=0.3, rubble_cell=3.0,
                 chunk_scale=0.85, debris="cinder", lod=(1.0,), ref="Vivienda urbana de Oriente Medio: bloque + revoco, losa plana")


def build_barn(name):
    parts = build_house(name, 10.0, 7.0, 1, fh=3.4, wall_mat="Mat_Wood_Plank", wcls="wood", pitch=40, nwin=(1, 0))
    return Asset(name, "Buildings", "structure", parts, n_impacts=2, dmg_r=1.4, ruin_h=0.3, spread=0.35, rubble_cell=3.0,
                 debris="wood", lod=(1.0,), ref="Granero/cobertizo rural de madera, cubierta a 40 deg")


# ---------------------------------- trincheras ----------------------------------------
TRENCH_HOLES = []        # rectangulos (cx, cy, largo, ancho, angulo) del ultimo trench_path_parts -> agujeros del Terrain


def trench_path_parts(path, depth=1.6, w=1.0, lining="planks", berm=True, top_bags=False, caps=(True, True)):
    """Trinchera a lo largo de una polilinea: revestimiento (tablas o sacos), postes,
    tarima, parapeto y parados de tierra. Base (fondo) en z=0; terreno en z=depth.
    Cierra los extremos y deja en TRENCH_HOLES el hueco a recortar en el terreno de Unity."""
    parts = []
    del TRENCH_HOLES[:]
    last = len(path) - 2
    for k in range(len(path) - 1):
        a, b = V((*path[k], 0)), V((*path[k + 1], 0))
        d = b - a
        L = d.length
        dn = d.normalized()
        nrm = V(-dn.y, dn.x, 0)
        ang = math.degrees(math.atan2(dn.y, dn.x))
        mid = (a + b) / 2
        e0, e1 = (w / 2 if k > 0 else 0.0), (w / 2 if k < last else 0.0)      # solape en los quiebros
        hc = mid + dn * ((e1 - e0) / 2)
        TRENCH_HOLES.append((hc.x, hc.y, L + e0 + e1, w + 0.12, ang))
        lin = []
        for end, q0, sg in ((k == 0 and caps[0], a, -1), (k == last and caps[1], b, 1)):   # testeros (extremos cerrados)
            if not end:
                continue
            q = q0 + dn * sg * 0.03
            if lining == "planks":
                lin += [box((0.05, w + 0.12, 0.24), (q.x, q.y, 0.125 + z * 0.25), (0, 0, ang), mat="Mat_Wood_Plank", cls="wood", grain="y")
                        for z in range(int(depth / 0.25))]
            else:
                q = q0 + dn * sg * 0.18
                lin += [box((0.3, w + 0.2, 0.13), (q.x, q.y, 0.07 + z * 0.14), (0, 0, ang), mat="Mat_Fabric_Sandbag", bevel=0.03, cls="fabric")
                        for z in range(int(depth / 0.14))]
        for sgn in (-1, 1):
            c = mid + nrm * sgn * (w / 2 + 0.03)
            if lining == "planks":
                for z in range(int(depth / 0.25)):
                    lin.append(box((L + 0.06, 0.05, 0.24), (c.x, c.y, 0.125 + z * 0.25), (0, 0, ang), mat="Mat_Wood_Plank", cls="wood", grain="x"))
                for j in range(int(L / 1.4) + 1):
                    q = a + dn * min(L, j * 1.4) + nrm * sgn * (w / 2 + 0.09)
                    lin.append(box((0.1, 0.1, depth + 0.2), (q.x, q.y, (depth + 0.2) / 2), (0, 0, ang), mat="Mat_Log_Wood", cls="wood", grain="z"))
            else:
                for z in range(int(depth / 0.14)):
                    n = max(1, int(L / 0.6))
                    for j in range(n):
                        q = a + dn * (L * (j + 0.5 + 0.5 * (z % 2)) / (n + 0.5)) + nrm * sgn * (w / 2 + 0.18)
                        lin.append(box((0.58, 0.3, 0.13), (q.x, q.y, 0.07 + z * 0.14), (0, 0, ang), mat="Mat_Fabric_Sandbag", bevel=0.03, cls="fabric"))
        parts.append(Part(f"Revetment_{k}", lin, "wood" if lining == "planks" else "fabric"))
        if top_bags:                                         # hilada de sacos en el borde
            n = max(1, int(L / 0.62))
            bags = [box((0.58, 0.3, 0.14), tuple(a + dn * (L * (j + 0.5) / n) + nrm * sgn * (w / 2 + 0.2) + V(0, 0, depth + 0.07)),
                        (0, 0, ang), mat="Mat_Fabric_Sandbag", cls="fabric") for sgn in (-1, 1) for j in range(n)]
            parts.append(Part(f"TopBags_{k}", bags, "fabric"))
        duck = [box((L, w - 0.1, 0.05), (mid.x, mid.y, 0.1), (0, 0, ang), mat="Mat_Wood_Plank", cls="wood", grain="x")]
        parts.append(Part(f"Duckboard_{k}", duck, "wood", kind="floor"))
        if berm:
            for sgn, hgt, wid in ((1, 0.45, 1.1), (-1, 0.25, 0.8)):            # parapeto / parados
                prof = [(-wid / 2, 0), (wid / 2, 0), (wid * 0.3, hgt), (-wid * 0.3, hgt)]
                bp = prism(prof, L + 0.4, axis='x', mat="Mat_Terrain_Soil", cls="earth")
                bp.transform(Matrix.Translation(mid + nrm * sgn * (w / 2 + 0.25 + wid / 2) + V(0, 0, depth)) @ Matrix.Rotation(math.radians(ang), 4, 'Z'))
                parts.append(Part(f"Berm_{k}_{'F' if sgn > 0 else 'R'}", [bp], "earth"))
    return parts


def build_trench_straight(name):
    parts = trench_path_parts([(-4.0, 0.0), (4.0, 0.0)])
    parts.append(Part("Parapet_Sandbags", [box((0.6, 0.3, 0.14), (-3.0 + k * 0.62, 1.05, 1.6 + 0.45 + 0.07), mat="Mat_Fabric_Sandbag", bevel=0.03, cls="fabric")
                                           for k in range(10)], "fabric"))
    return Asset(name, "Fortifications", "structure", parts, n_impacts=1, dmg_r=1.0, ruin_h=0.45, spread=0.3, rubble_cell=2.0,
                 debris="earth", ground_offset=-1.6, holes=list(TRENCH_HOLES), lod=(1.0,), ref="Trinchera de tirador revestida: 1.6 m de profundidad, 1 m de ancho")


def build_trench_zigzag(name):
    path = [(-8, 0), (-4.5, 0), (-3.5, 1.6), (0.5, 1.6), (1.5, 0), (5.0, 0), (6.0, 1.6), (9.0, 1.6)]
    parts = trench_path_parts(path, lining="planks", top_bags=True)
    return Asset(name, "Fortifications", "structure", parts, n_impacts=2, dmg_r=1.0, ruin_h=0.45, spread=0.3, rubble_cell=2.0,
                 debris="earth", ground_offset=-1.6, holes=list(TRENCH_HOLES), lod=(1.0,), ref="Trinchera en zigzag (bahias de tiro y traveses), tablestacado + sacos")


def build_foxhole(name):
    """Posicion de 2 tiradores: 1.8 x 0.8 m, 1.4 m (axila), parapeto 0.45 m alto x 1 m."""
    parts = trench_path_parts([(-0.9, 0.0), (0.9, 0.0)], depth=1.4, w=0.8, lining="planks")
    logs = [cyl(0.1, 1.6, (-0.4 + k * 0.21, 0.0, 1.4 + 0.5), (90, 0, 0), mat="Mat_Log_Wood", segs=8, cls="wood", grain="y") for k in range(4)]
    parts.append(Part("OverheadCover_Logs", logs, "wood"))
    parts.append(Part("OverheadCover_Soil", [box((1.0, 1.7, 0.4), (-0.1, 0, 1.4 + 0.8), mat="Mat_Terrain_Soil", cls="earth")], "earth"))
    return Asset(name, "Fortifications", "structure", parts, n_impacts=1, dmg_r=0.8, ruin_h=0.5, spread=0.3, rubble_cell=1.5,
                 debris="earth", ground_offset=-1.4, holes=list(TRENCH_HOLES), lod=(1.0,), ref="Pozo de tirador para 2 (FM 21-75): parapeto frontal 18 in")


def build_mg_nest(name):
    """Nido de ametralladora: anillo de sacos (3 hiladas, R 1.6 m) con tronera."""
    parts, R = [], 1.6
    pit = trench_path_parts([(-0.8, 0.0), (0.8, 0.0)], depth=0.6, w=1.6, lining="planks", berm=False)
    parts += pit
    for row in range(4):
        n = 18
        for i in range(n):
            a = 2 * math.pi * (i + 0.5 * (row % 2)) / n
            if row >= 2 and abs(math.degrees(a) - 90) < 20:
                continue                                        # tronera de tiro al frente
            p = V(math.cos(a) * R, math.sin(a) * R, 0.6 + 0.07 + row * 0.13)
            bag = box((0.58, 0.3, 0.14), tuple(p), (0, 0, math.degrees(a) + 90), mat="Mat_Fabric_Sandbag", bevel=0.03, cls="fabric")
            parts.append(Part(f"Bag_{row}_{i}", [bag], "fabric"))
    gun = [box((0.9, 0.12, 0.12), (0, 1.0, 1.15), (0, 0, 90), mat="Mat_Metal_Gunmetal", cls="metal"),
           cyl(0.02, 0.7, (0, 1.6, 1.17), (90, 0, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal")]
    gun += [strut((0, 0.8, 1.1), (sx * 0.35, 0.6 + abs(sx) * 0.1, 0.6), 0.015, "Mat_Metal_Gunmetal", 4, cls="metal") for sx in (-1, 0, 1)]
    parts.append(Part("MG_Tripod", gun, "metal", kind="detail"))
    return Asset(name, "Fortifications", "structure", parts, n_impacts=1, dmg_r=0.9, ruin_h=0.35, spread=0.5, rubble_cell=1.5,
                 debris="fabric", ground_offset=-0.6, holes=list(TRENCH_HOLES), lod=(1.0,), ref="Nido de ametralladora de sacos terreros, anillo de 3.2 m")


def build_dugout(name):
    """Refugio de troncos 4 x 3 m, 2 m de fondo: paredes de troncos apilados, techo de
    troncos + 0.6 m de tierra, rampa de acceso."""
    W, D, H = 4.0, 3.0, 2.0
    parts = []
    rows = int(H / 0.23)
    for side, (a, b) in {"S": ((-W / 2, -D / 2), (W / 2, -D / 2)), "N": ((-W / 2, D / 2), (W / 2, D / 2)),
                         "W": ((-W / 2, -D / 2), (-W / 2, D / 2)), "E": ((W / 2, -D / 2), (W / 2, D / 2))}.items():
        a, b = V((*a, 0)), V((*b, 0))
        dr = (b - a).normalized()
        door = side == "S"                                       # hueco de puerta de 1 m
        logs = []
        for k in range(rows):
            z = V(0, 0, 0.12 + k * 0.23)
            spans = [(a - dr * 0.15, b + dr * 0.15)]
            if door and k < rows - 1:
                spans = [(a - dr * 0.15, a.lerp(b, 0.37)), (a.lerp(b, 0.63), b + dr * 0.15)]
            for p0, p1 in spans:
                logs.append(strut(p0 + z, p1 + z, 0.12, "Mat_Log_Wood", 8, cls="wood",
                                  grain="x" if abs(dr.x) > abs(dr.y) else "y", smooth=True))
        parts.append(Part(f"LogWall_{side}", logs, "wood"))
    roof = [cyl(0.13, D + 0.8, (-W / 2 + 0.2 + k * 0.26, 0, H + 0.13), (90, 0, 0), mat="Mat_Log_Wood", segs=8, cls="wood", grain="y")
            for k in range(int(W / 0.26))]
    parts.append(Part("LogRoof", roof, "wood"))
    parts.append(Part("EarthCover", [hull([(sx * (W / 2 + 0.8), sy * (D / 2 + 0.8), H + 0.26) for sx in (-1, 1) for sy in (-1, 1)] +
                                          [(sx * (W / 2 - 0.4), sy * (D / 2 - 0.4), H + 0.9) for sx in (-1, 1) for sy in (-1, 1)],
                                          mat="Mat_Terrain_Soil", cls="earth")], "earth"))
    parts.append(Part("Floor", [box((W - 0.1, D - 0.1, 0.05), (0, 0, 0.025), mat="Mat_Wood_Plank", cls="wood", grain="x")], "wood", kind="floor"))
    entry = trench_path_parts([(0.0, -D / 2 - 0.1), (0.0, -D / 2 - 3.0)], depth=H, w=1.1, berm=False, caps=(False, True))
    parts += [p for p in entry if not p.name.startswith("Duckboard")]
    ramp = [box((1.0, 0.3, 0.16), (0, -D / 2 - 0.35 - k * 0.3, 0.12 + k * 0.21), mat="Mat_Wood_Plank", cls="wood", grain="x") for k in range(9)]
    parts.append(Part("EntranceSteps", ramp, "wood"))
    return Asset(name, "Fortifications", "structure", parts, n_impacts=1, dmg_r=1.3, ruin_h=0.45, spread=0.3, rubble_cell=2.0,
                 debris="wood", ground_offset=-2.0, holes=list(TRENCH_HOLES), lod=(1.0,),
                 ref="Refugio (dugout) de troncos con cubierta de tierra 0.6 m")


def build_revetment(name):
    """Asentamiento de vehiculo: berma en U de 1.8 m (casco abajo, hull-down)."""
    parts = []
    for k, (cx, cy, L, ang) in enumerate(((0, 4.0, 12.0, 0), (-6.0, 0.5, 7.0, 90), (6.0, 0.5, 7.0, 90))):
        prof = [(-2.2, 0), (2.2, 0), (0.7, 1.8), (-0.7, 1.8)]
        b = prism(prof, L, axis='x', mat="Mat_Terrain_Soil", cls="earth")
        b.transform(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.radians(ang), 4, 'Z'))
        parts.append(Part(f"Berm_{k}", [b], "earth"))
    return Asset(name, "Fortifications", "structure", parts, n_impacts=2, dmg_r=1.5, ruin_h=0.5, spread=0.25, rubble_cell=3.0,
                 debris="earth", lod=(1.0, 0.5), ref="Asentamiento de vehiculo hull-down, berma de 1.8 m")


# ==================================================================================
# BUILDERS: VEHICULOS DE LAS REFERENCIAS (fichas publicadas)
# ==================================================================================
TRACKED.update({
    "Veh_MBT_T-72B3": dict(L=6.95, W=3.59, H=2.23, Hh=1.35, mass=46000, nw=6, wr=0.375, tw=0.58, turret="dome",
                           TL=3.3, TW=2.9, tx=0.1, gun=6.0, gr=0.09, paint="Mat_Military_RuGreen", era=True,
                           ref="UVZ T-72B3: casco 6.95 m, 9.53 m con canon, ancho 3.59 m, alto 2.23 m, ~46 t, 125 mm"),
    "Veh_IFV_BMP-2": dict(L=6.735, W=3.15, H=2.45, Hh=1.6, mass=14300, nw=6, wr=0.33, tw=0.40, turret="bmp", glacis=2.3,
                          TL=1.9, TW=1.9, tx=0.4, gun=2.4, gr=0.04, paint="Mat_Military_RuGreen", atgm=True,
                          ref="BMP-2: L 6.735 m, ancho 3.15 m, alto 2.45 m, 14.3 t, 30 mm 2A42 + 9M113 Konkurs"),
    "Veh_SPAAG_ZSU-23-4_Shilka": dict(L=6.535, W=3.125, H=2.576, Hh=1.4, mass=19000, nw=6, wr=0.33, tw=0.38, turret="shilka",
                                      TL=2.9, TW=2.9, tx=0.1, gun=2.0, gr=0.03, paint="Mat_Military_RuGreen",
                                      ref="ZSU-23-4 Shilka: L 6.535 m, ancho 3.125 m, alto 2.576 m (3.572 m radar), 19 t, 4x23 mm"),
})

WHEELED.update({
    "Veh_APC_BTR-82A": dict(L=7.65, W=2.9, H=2.8, mass=15400, axles=(2.6, 1.25, -0.55, -1.9), wr=0.6, style="apc", btr=True,
                            paint="Mat_Military_RuGreen", ref="BTR-82A: L 7.65 m, ancho 2.9 m, alto 2.8 m, 15.4 t, 30 mm 2A72"),
})


def build_pickup(name, technical=True):
    """Pick-up tipo Hilux/LC79 (L 5.3 m, ancho 1.85 m, alto 1.8 m) con DShK 12.7 mm en pedestal."""
    L, W, H, wr = 5.3, 1.85, 1.8, 0.38
    P = "Mat_Civil_White"
    parts = []
    for i, x in enumerate((1.6, -1.55)):
        for side, sy in (("L", 1), ("R", -1)):
            parts.append(tire_wheel(x, sy * (W / 2 - 0.15), wr, wr, 0.27, f"Wheel_{i}{side}", "Mat_Metal_Gunmetal"))
    zb = 0.55
    hood = hull(sym([(L / 2, W / 2 - 0.1, zb + 0.1), (L / 2, W / 2 - 0.15, 1.05), (L / 2 - 1.2, W / 2 - 0.05, 1.15),
                     (L / 2 - 1.2, W / 2 - 0.02, zb), (L / 2 - 0.1, W / 2 - 0.08, zb - 0.05)]), mat=P, cls="metal")
    cab = hull(sym([(L / 2 - 1.2, W / 2 - 0.02, zb), (L / 2 - 1.2, W / 2 - 0.05, 1.15), (L / 2 - 1.85, W / 2 - 0.12, H),
                    (L / 2 - 2.95, W / 2 - 0.12, H), (L / 2 - 3.05, W / 2 - 0.05, 1.1), (L / 2 - 3.05, W / 2 - 0.02, zb)]), mat=P, cls="metal")
    chassis = box((L * 0.92, 0.9, 0.18), (0, 0, zb - 0.05), mat="Mat_Metal_Gunmetal", cls="metal")
    parts.append(Part("Body_Hood", [hood, chassis], "metal", kind="body"))
    parts.append(Part("Cab", [cab], "metal", kind="cab"))
    xb0, xb1 = L / 2 - 3.1, -L / 2
    bed = [box((xb0 - xb1, W - 0.08, 0.08), ((xb0 + xb1) / 2, 0, zb + 0.32), mat="Mat_Metal_Gunmetal", cls="metal")]
    bed += [box((xb0 - xb1, 0.05, 0.45), ((xb0 + xb1) / 2, sy * (W / 2 - 0.03), zb + 0.58), mat=P, cls="metal") for sy in (-1, 1)]
    bed += [box((0.05, W - 0.08, 0.45), (xb1 + 0.03, 0, zb + 0.58), mat=P, cls="metal")]
    parts.append(Part("CargoBed", bed, "metal", kind="bed"))
    glass = [glass_panel((L / 2 - 1.22, -0.7, 1.17), (L / 2 - 1.22, 0.7, 1.17), (L / 2 - 1.8, 0.7, H - 0.04), (L / 2 - 1.8, -0.7, H - 0.04))]
    for sy in (-1, 1):
        glass.append(glass_panel((L / 2 - 1.9, sy * (W / 2 - 0.08), 1.18), (L / 2 - 2.9, sy * (W / 2 - 0.08), 1.18),
                                 (L / 2 - 2.9, sy * (W / 2 - 0.12), H - 0.08), (L / 2 - 1.95, sy * (W / 2 - 0.12), H - 0.08)))
    parts.append(Part("Windows", glass, "glass", kind="glass"))
    for k, sy in enumerate((1, -1)):
        parts.append(Part(f"Door_{k}", [box((1.0, 0.04, 0.55), (L / 2 - 2.45, sy * (W / 2 - 0.0), zb + 0.4), mat=P, cls="metal")], "metal",
                          kind="door", pivot=(L / 2 - 1.95, sy * W / 2, zb + 0.4), axis=(0, 0, 1), joint="hinge"))
    det = [box((0.06, 0.25, 0.12), (L / 2 + 0.01, sy * 0.6, 0.85), mat="Mat_Light_Lens", cls="glass", frac=False) for sy in (-1, 1)]
    det += [box((0.12, W - 0.1, 0.15), (L / 2 + 0.02, 0, zb + 0.08), mat="Mat_Metal_Gunmetal", cls="metal")]
    parts.append(Part("Details", det, "metal", kind="detail"))
    if technical:
        gx = (xb0 + xb1) / 2 + 0.2
        g = [strut((gx, 0, zb + 0.36), (gx, 0, zb + 1.35), 0.06, "Mat_Metal_Gunmetal", 8, cls="metal"),
             box((0.9, 0.18, 0.2), (gx + 0.15, 0, zb + 1.45), mat="Mat_Metal_Gunmetal", cls="metal"),
             cyl(0.025, 1.3, (gx + 1.2, 0, zb + 1.47), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal"),
             cyl(0.05, 0.12, (gx + 1.85, 0, zb + 1.47), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal"),
             box((0.04, 0.7, 0.55), (gx + 0.45, 0, zb + 1.55), mat="Mat_Military_Olive", cls="metal")]
        parts.append(Part("DShK_Mount", g, "metal", kind="turret", pivot=(gx, 0, zb + 1.35), axis=(0, 0, 1), joint="yaw"))
    return Asset(name, "Vehicles", "vehicle", parts, forward_x=True, mass=2400 if technical else 2100, lod=(1.0, 0.5, 0.2),
                 ref="Pick-up Toyota Hilux/LC79 (5.3 x 1.85 x 1.8 m) + ametralladora DShK 12.7 mm")


def build_sedan(name):
    """Turismo civil (L 4.6 m, ancho 1.78 m, alto 1.45 m) - pecio calcinado tipico de escenario."""
    L, W, H, wr = 4.6, 1.78, 1.45, 0.31
    P = "Mat_Car_Paint"
    parts = []
    for i, x in enumerate((1.4, -1.35)):
        for side, sy in (("L", 1), ("R", -1)):
            parts.append(tire_wheel(x, sy * (W / 2 - 0.12), wr, wr, 0.2, f"Wheel_{i}{side}", "Mat_Metal_Steel"))
    body = hull(sym([(L / 2, W / 2 - 0.15, 0.35), (L / 2, W / 2 - 0.2, 0.75), (L / 2 - 1.1, W / 2 - 0.05, 0.9), (-L / 2 + 0.9, W / 2 - 0.05, 0.92),
                     (-L / 2, W / 2 - 0.12, 0.85), (-L / 2, W / 2 - 0.12, 0.4), (L / 2 - 0.3, W / 2 - 0.05, 0.25), (-L / 2 + 0.3, W / 2 - 0.05, 0.25)]),
                mat=P, cls="metal")
    cabin = hull(sym([(L / 2 - 1.15, W / 2 - 0.1, 0.9), (L / 2 - 1.9, W / 2 - 0.2, H), (-L / 2 + 1.3, W / 2 - 0.2, H), (-L / 2 + 0.85, W / 2 - 0.1, 0.92)]),
                 mat=P, cls="metal")
    parts.append(Part("Body", [body], "metal", kind="body"))
    parts.append(Part("Cabin", [cabin], "metal", kind="cab"))
    glass = [glass_panel((L / 2 - 1.17, -0.68, 0.92), (L / 2 - 1.17, 0.68, 0.92), (L / 2 - 1.88, 0.62, H - 0.03), (L / 2 - 1.88, -0.62, H - 0.03)),
             glass_panel((-L / 2 + 0.87, -0.66, 0.93), (-L / 2 + 0.87, 0.66, 0.93), (-L / 2 + 1.28, 0.6, H - 0.03), (-L / 2 + 1.28, -0.6, H - 0.03))]
    parts.append(Part("Windows", glass, "glass", kind="glass"))
    det = [box((0.04, 0.3, 0.1), (L / 2 + 0.01, sy * 0.6, 0.62), mat="Mat_Light_Lens", cls="glass", frac=False) for sy in (-1, 1)]
    parts.append(Part("Lights", det, "glass", kind="detail"))
    return Asset(name, "Civilian", "vehicle", parts, forward_x=True, mass=1300, lod=(1.0, 0.5, 0.2), ref="Turismo sedan 4.6 x 1.78 x 1.45 m")


def build_d9r(name):
    """Bulldozer blindado Caterpillar D9R (IDF): L 8.1 m, hoja 4.5 m, alto 4 m, 62 t."""
    P = "Mat_Military_Desert"
    parts = []
    tw, W = 0.61, 3.4
    yt = W / 2 - tw / 2
    pts = [(-2.0, 0.0), (1.4, 0.0), (1.75, 0.35), (1.55, 0.75), (-0.5, 1.75), (-1.1, 1.8), (-1.55, 1.5), (-2.25, 0.35)]
    path = resample_loop(pts, 44)
    for side, sy in (("L", 1), ("R", -1)):
        segs = [band(path, 0.09, tw, sy * yt, mat="Mat_Track_Steel", i0=k * 5, i1=k * 5 + 5, cls="metal") for k in range(8)]
        parts.append(Part(f"Track_{side}", [band(path, 0.09, tw, sy * yt, mat="Mat_Track_Steel", cls="metal")], "metal", kind="track",
                          alt={"wreck": [sg.copy() for k, sg in enumerate(segs) if k % 3]}))
        wh = [cyl(0.24, tw * 0.8, (x, sy * yt, 0.33), (90, 0, 0), mat="Mat_Track_Steel", segs=10, cls="metal") for x in (-1.6, -1.0, -0.4, 0.2, 0.8)]
        wh += [cyl(0.55, tw * 0.6, (-0.8, sy * yt, 1.3), (90, 0, 0), mat="Mat_Metal_Gunmetal", segs=12, cls="metal")]
        parts.append(Part(f"Undercarriage_{side}", wh, "metal", kind="wheel", pivot=(-0.8, sy * yt, 1.3), axis=(0, 1, 0), joint="wheel"))
    body = [hull(sym([(2.3, 1.1, 1.1), (2.3, 1.0, 2.3), (0.4, 1.2, 2.5), (0.4, 1.35, 1.1)]), mat=P, cls="metal"),
            box((2.2, 2.0, 1.0), (-0.9, 0, 1.6), mat=P, cls="metal")]
    parts.append(Part("Hull_Engine", body, "metal", kind="hull"))
    cab = hull(sym([(0.4, 1.15, 2.1), (0.25, 1.05, 3.95), (-1.6, 1.05, 4.0), (-1.75, 1.2, 2.1)]), mat=P, cls="metal")
    parts.append(Part("ArmoredCab", [cab], "metal", kind="cab"))
    parts.append(Part("CabWindows", [glass_panel((0.36, -0.8, 2.6), (0.36, 0.8, 2.6), (0.24, 0.75, 3.6), (0.24, -0.75, 3.6), 0.05)] +
                      [glass_panel((-0.1, sy * 1.14, 2.7), (-1.3, sy * 1.14, 2.7), (-1.3, sy * 1.06, 3.6), (-0.1, sy * 1.06, 3.6), 0.05) for sy in (-1, 1)],
                      "glass", kind="glass"))
    blade = prism([(3.25, 0.0), (3.55, 0.0), (3.75, 0.6), (3.7, 1.4), (3.95, 1.9), (3.7, 1.95), (3.45, 1.45), (3.4, 0.6)], 4.5, axis='y', mat=P, cls="metal")
    arms = [beam((2.0, sy * 1.75, 0.9), (3.4, sy * 1.75, 0.8), 0.25, 0.3, mat="Mat_Metal_Gunmetal", cls="metal") for sy in (-1, 1)]
    arms += [strut((1.6, sy * 0.9, 2.1), (3.45, sy * 0.9, 1.5), 0.09, "Mat_Metal_Steel", 8, cls="metal") for sy in (-1, 1)]
    parts.append(Part("Blade", [blade] + arms, "metal", kind="body", pivot=(2.0, 0, 0.9), axis=(0, 1, 0), joint="pitch"))
    rip = [box((0.3, 1.2, 0.35), (-2.6, 0, 1.0), mat=P, cls="metal"), beam((-2.6, 0, 0.9), (-2.9, 0, 0.0), 0.15, 0.25, mat="Mat_Metal_Gunmetal", cls="metal")]
    parts.append(Part("Ripper", rip, "metal", kind="detail", pivot=(-2.3, 0, 1.0), axis=(0, 1, 0), joint="pitch"))
    parts.append(Part("Exhaust", [strut((1.4, -0.6, 2.4), (1.4, -0.6, 3.4), 0.08, "Mat_Metal_Gunmetal", 8, cls="metal")], "metal", kind="detail"))
    return Asset(name, "Vehicles", "vehicle", parts, forward_x=True, mass=62000, lod=(1.0, 0.5, 0.2),
                 ref="Caterpillar D9R blindado (IDF): L 8.1 m, hoja 4.5 m, alto 4 m, 62 t")


def build_cram(name):
    """C-RAM Centurion: Phalanx terrestre (LPWS) sobre semirremolque, con grupo electrogeno."""
    parts, L, W = [], 11.0, 2.6
    deck = [box((L, W, 0.25), (0, 0, 1.35), mat="Mat_Military_Desert", cls="metal")]
    deck += [box((L * 0.95, 0.25, 0.4), (0, sy * 0.5, 1.05), mat="Mat_Metal_Gunmetal", cls="metal") for sy in (-1, 1)]
    parts.append(Part("Trailer_Deck", deck, "metal", kind="hull"))
    for i, x in enumerate((-3.4, -4.6)):
        for side, sy in (("L", 1), ("R", -1)):
            parts.append(tire_wheel(x, sy * (W / 2 - 0.25), 0.52, 0.52, 0.32, f"Wheel_{i}{side}", "Mat_Metal_Gunmetal"))
    legs = [strut((4.0, sy * 0.9, 1.2), (4.0, sy * 0.9, 0.05), 0.06, "Mat_Metal_Gunmetal", 6, cls="metal") for sy in (-1, 1)]
    legs += [box((0.3, 0.3, 0.04), (4.0, sy * 0.9, 0.02), mat="Mat_Metal_Gunmetal", cls="metal") for sy in (-1, 1)]
    parts.append(Part("Landing_Legs", legs, "metal", kind="detail"))
    gen = [box((1.8, 1.9, 1.3), (3.9, 0, 2.13), mat="Mat_Military_Desert", cls="metal"), box((1.4, 1.9, 1.1), (-4.5, 0, 2.03), mat="Mat_Military_Desert", cls="metal")]
    parts.append(Part("Generator_Cabinets", gen, "metal", kind="body"))
    base = [cyl(0.8, 0.5, (0.0, 0, 1.73), mat="Mat_Civil_White", segs=14, cls="metal"), box((1.4, 1.6, 0.9), (0.0, 0, 2.4), mat="Mat_Civil_White", cls="metal")]
    parts.append(Part("Mount_Base", base, "metal", kind="body"))
    dome = [cyl(0.55, 1.2, (0.0, 0, 3.5), mat="Mat_Civil_White", segs=16, cls="metal"), sphere(0.55, (0.0, 0, 4.1), mat="Mat_Civil_White", segs=16, rings=6,
                                                                                            scale=(1, 1, 0.6), cls="metal")]
    gun = [cyl(0.2, 0.9, (0.8, 0, 2.95), (0, 80, 0), mat="Mat_Metal_Gunmetal", segs=10, cls="metal"),
           cyl(0.12, 1.8, (1.7, 0, 3.05), (0, 84, 0), mat="Mat_Metal_Gunmetal", segs=6, cls="metal"),
           cyl(0.42, 0.9, (-0.7, 0, 2.95), (0, 90, 0), mat="Mat_Civil_White", segs=12, cls="metal")]
    parts.append(Part("Phalanx_Turret", dome + gun, "metal", kind="turret", pivot=(0.0, 0, 2.85), axis=(0, 0, 1), joint="yaw"))
    return Asset(name, "AirDefense", "vehicle", parts, forward_x=True, mass=15000, lod=(1.0, 0.5, 0.2),
                 ref="Centurion C-RAM (LPWS): conjunto 19.81 m con tractora, ancho 3.65 m, alto 4.26 m, 24 t")


def build_littlebird(name):
    """MH-6/AH-6 Little Bird: L 9.8 m (rotores), rotor 8.3 m (5 palas), alto ~3 m, patines."""
    P, parts = "Mat_Military_Grey", []
    gz = 0.45
    egg = loft(ell_rings([(2.0, 0.05, 0.05, gz + 0.85), (1.75, 0.55, 0.6, gz + 0.85), (0.9, 0.72, 0.8, gz + 0.9), (-0.4, 0.6, 0.72, gz + 0.95),
                          (-1.2, 0.35, 0.45, gz + 1.05), (-1.5, 0.15, 0.2, gz + 1.15)], 12), mat=P, cls="metal", smooth=True)
    parts.append(Part("Fuselage", [egg], "metal", kind="fuselage"))
    parts.append(Part("Canopy", [hull(sym([(1.95, 0.1, gz + 0.9), (1.6, 0.58, gz + 1.35), (0.8, 0.7, gz + 1.6), (0.8, 0.72, gz + 0.6), (1.7, 0.5, gz + 0.55)]),
                                      mat="Mat_Glass_Canopy", cls="glass")], "glass", kind="glass"))
    boom = loft(ell_rings([(-1.3, 0.16, 0.18, gz + 1.15), (-4.6, 0.08, 0.09, gz + 1.3)], 8), mat=P, cls="metal", smooth=True)
    fin = prism([(-4.3, gz + 1.2), (-4.75, gz + 1.2), (-4.85, gz + 2.0), (-4.55, gz + 2.0)], 0.06, axis='y', mat=P, cls="metal")
    stab = prism([(-4.5, 0.6), (-4.8, 0.6), (-4.8, -0.6), (-4.5, -0.6)], 0.05, axis='z', offset=gz + 2.0, mat=P, cls="metal")
    tr = [blade((-4.6, -0.12, gz + 1.45), 0.7, 0.1, 0, a, thick=0.02) for a in (0, 180)]
    for b in tr:
        b.transform(Matrix.Translation((-4.6, -0.12, gz + 1.45)) @ Matrix.Rotation(math.pi / 2, 4, 'X') @ Matrix.Translation((4.6, 0.12, -gz - 1.45)))
    parts.append(Part("TailBoom", [boom, fin, stab] + tr, "metal", kind="tail", pivot=(-1.3, 0, gz + 1.15), axis=(0, 1, 0), joint="break"))
    hub_z = gz + 2.3
    rp = [cyl(0.18, 0.5, (0.2, 0, hub_z - 0.2), mat="Mat_Metal_Gunmetal", segs=10, cls="metal")]
    rp += [blade((0.2, 0, hub_z), 4.15, 0.18, hub_z, k * 72, droop=0.1) for k in range(5)]
    parts.append(Part("MainRotor", rp, "metal", kind="rotor", pivot=(0.2, 0, hub_z), axis=(0, 0, 1), joint="spin"))
    sk = []
    for sy in (-1, 1):
        sk.append(strut((1.6, sy * 0.95, 0.05), (-1.4, sy * 0.95, 0.05), 0.04, "Mat_Metal_Gunmetal", 6, cls="metal"))
        sk += [strut((x, sy * 0.95, 0.05), (x, sy * 0.5, gz + 0.35), 0.035, "Mat_Metal_Gunmetal", 6, cls="metal") for x in (0.9, -0.6)]
    parts.append(Part("Skids", sk, "metal", kind="gear"))
    wpn = [beam((-0.1, -1.3, gz + 0.55), (-0.1, 1.3, gz + 0.55), 0.1, 0.08, mat="Mat_Metal_Gunmetal", cls="metal")]
    wpn += [cyl(0.1, 1.2, (0.1, sy * 1.25, gz + 0.4), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal") for sy in (-1, 1)]
    parts.append(Part("WeaponPylons", wpn, "metal", kind="wing", pivot=(-0.1, 0, gz + 0.55), axis=(1, 0, 0), joint="break"))
    return Asset(name, "Aircraft", "vehicle", parts, forward_x=True, mass=1400, lod=(1.0, 0.5, 0.2),
                 ref="Boeing MH-6/AH-6 Little Bird: 9.8 m, rotor 8.3 m, alto ~3 m, 1.4 t max")


def build_shahed(name):
    """Municion merodeadora Shahed-136: L 3.5 m, envergadura 2.5 m, 200 kg, helice propulsora."""
    P, parts = "Mat_Military_Grey", []
    fus = loft(ell_rings([(1.75, 0.02, 0.02, 0.35), (1.4, 0.16, 0.16, 0.35), (0.6, 0.2, 0.2, 0.35), (-1.5, 0.17, 0.17, 0.35),
                          (-1.7, 0.08, 0.08, 0.35)], 10), mat=P, cls="metal", smooth=True)
    parts.append(Part("Fuselage", [fus], "metal", kind="fuselage"))
    for side, sy in (("L", 1), ("R", -1)):
        w = prism([(0.75, 0.15), (-1.55, 0.15), (-1.6, 1.25), (-1.05, 1.25)], 0.06, axis='z', offset=0.33, mat=P, cls="metal")
        w.transform(Matrix.Diagonal((1, sy, 1, 1)))
        fin = prism([(-1.0, 0.0), (-1.6, 0.0), (-1.65, 0.38), (-1.3, 0.38)], 0.03, axis='y', offset=sy * 1.25, mat=P, cls="metal")
        fin.transform(Matrix.Translation((0, 0, 0.12)))
        parts.append(Part(f"Wing_{side}", [w, fin], "metal", kind="wing", pivot=(-0.4, sy * 0.18, 0.33), axis=(1, 0, 0), joint="break"))
    pr = [cyl(0.05, 0.12, (-1.78, 0, 0.35), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal")]
    pr += [beam(V(-1.82, 0, 0.35), V(-1.82, math.cos(a) * 0.38, 0.35 + math.sin(a) * 0.38), 0.07, 0.015, mat="Mat_Rotor_Blade", cls="metal", grain=None)
           for a in (0.4, 0.4 + math.pi)]
    parts.append(Part("Propeller", pr, "metal", kind="rotor", pivot=(-1.8, 0, 0.35), axis=(1, 0, 0), joint="spin"))
    parts.append(Part("Warhead", [cyl(0.15, 0.6, (1.2, 0, 0.35), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=10, cls="metal")], "metal", kind="detail"))
    return Asset(name, "Aircraft", "vehicle", parts, forward_x=True, mass=200, lod=(1.0, 0.5),
                 ref="HESA Shahed-136/Geran-2: L 3.5 m, envergadura 2.5 m, 200 kg, motor MD-550")


def build_quad(name):
    """Dron FPV/quadcoptero de reconocimiento (~35 cm diagonal), helices de 2 palas."""
    parts = [Part("Body", [box((0.2, 0.12, 0.07), (0, 0, 0.12), mat="Mat_Metal_Gunmetal", bevel=0.01, cls="metal")], "metal", kind="fuselage")]
    for k, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        tip = V(sx * 0.14, sy * 0.14, 0.13)
        arm = [beam((0, 0, 0.12), tip, 0.02, 0.012, mat="Mat_Metal_Gunmetal", cls="metal", grain=None),
               cyl(0.016, 0.03, tuple(tip + V(0, 0, 0.02)), mat="Mat_Metal_Steel", segs=8, cls="metal"),
               strut(tip, tip - V(0, 0, 0.12), 0.005, "Mat_Metal_Gunmetal", 4, cls="metal")]
        prop = [beam(tip + V(-0.065, -0.012, 0.04), tip + V(0.065, 0.012, 0.04), 0.018, 0.003, mat="Mat_Rotor_Blade", cls="metal", grain=None)]
        parts.append(Part(f"Arm_{k}", arm, "metal", kind="wing", pivot=(0, 0, 0.12), axis=(1, 0, 0), joint="break"))
        parts.append(Part(f"Prop_{k}", prop, "metal", kind="rotor", pivot=tuple(tip + V(0, 0, 0.04)), axis=(0, 0, 1), joint="spin"))
    parts.append(Part("Camera", [sphere(0.025, (0.11, 0, 0.09), mat="Mat_Glass_Canopy", segs=8, rings=5, cls="glass")], "glass", kind="glass"))
    return Asset(name, "Aircraft", "vehicle", parts, forward_x=True, mass=0.9, lod=(1.0, 0.5), ref="Quadcoptero FPV/recon clase 5-7 in (~0.9 kg)")


# ==================================================================================
# BUILDERS v4: INFRAESTRUCTURA DE MAPA (medidas reales)
# ==================================================================================
MATS.update({
    "Mat_Asphalt": ((0.09, 0.09, 0.09), 0.0, 0.9, 1, 0),
    "Mat_Road_Paint": ((0.85, 0.85, 0.82), 0.0, 0.6, 1, 0),
    "Mat_Paving": ((0.45, 0.44, 0.42), 0.0, 0.9, 1, 0),
    "Mat_Steel_Galvanized": ((0.55, 0.57, 0.58), 0.9, 0.45, 1, 0),
    "Mat_Bus_Paint": ((0.75, 0.62, 0.12), 0.5, 0.4, 1, 0),
    "Mat_Tent_Canvas": ((0.33, 0.33, 0.22), 0.0, 1.0, 1, 0),
    "Mat_Camo_Net": ((0.18, 0.22, 0.12), 0.0, 1.0, 1, 0),
    "Mat_Aircraft_Grey": ((0.46, 0.48, 0.50), 0.3, 0.45, 1, 0),
})
TEX_SPECS.update({
    "Mat_Asphalt": ("asphalt", {}, 3.0, 2.0),
    "Mat_Road_Paint": ("metal_paint", dict(chips=0.45, dust=0.35), 1.0, 0.5),
    "Mat_Paving": ("bricks", dict(rows=10, cols=5, mortar=0.006, mcol=(0.3, 0.3, 0.29)), 1.0, 2.0),
    "Mat_Steel_Galvanized": ("metal_paint", dict(chips=0.0, dust=0.25, brushed=True, rust=0.15), 1.0, 0.6),
    "Mat_Bus_Paint": ("metal_paint", dict(chips=0.15, dust=0.3), 2.0, 0.5),
    "Mat_Tent_Canvas": ("fabric", dict(weave=50), 2.0, 1.5),
    "Mat_Camo_Net": ("camo", dict(cols=((0.18, 0.22, 0.12), (0.30, 0.26, 0.15), (0.08, 0.10, 0.06)), ratio=(0.45, 0.6)), 2.0, 2.0),
    "Mat_Aircraft_Grey": ("metal_paint", dict(chips=0.04, dust=0.12), 2.0, 0.4),
})
VARIANT_REMAP["Desert"].update({"Mat_Camo_Net": "Mat_Fabric_Sandbag", "Mat_Tent_Canvas": "Mat_Fabric_Sandbag"})
VARIANT_REMAP["Winter"].update({"Mat_Camo_Net": "Mat_Military_Winter"})


def _road_marks(L, W, z):
    m = [box((3.0, 0.12, 0.01), (-L / 2 + 1.5 + k * 6.0, 0, z), mat="Mat_Road_Paint", cls="concrete", frac=False) for k in range(int(L / 6))]
    m += [box((L, 0.15, 0.01), (0, sy * (W / 2 - 0.3), z), mat="Mat_Road_Paint", cls="concrete", frac=False) for sy in (-1, 1)]
    return m


def build_road_asphalt(name):
    """Calzada urbana 12 m: 2 carriles de 3.5 m, bordillo 15 cm, aceras de 2.5 m."""
    L, W, side = 12.0, 7.0, 2.5
    parts = [Part("Asphalt", [box((L, W, 0.12), (0, 0, 0.06), mat="Mat_Asphalt", cls="concrete")], "concrete"),
             Part("Markings", _road_marks(L, W, 0.125), "concrete", kind="detail")]
    for k, sy in enumerate((-1, 1)):
        parts.append(Part(f"Curb_{k}", [box((L, 0.3, 0.27), (0, sy * (W / 2 + 0.15), 0.135), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
        parts.append(Part(f"Sidewalk_{k}", [box((L, side, 0.22), (0, sy * (W / 2 + 0.3 + side / 2), 0.11), mat="Mat_Paving", cls="concrete")], "concrete"))
    return Asset(name, "Map", "structure", parts, n_impacts=1, dmg_r=1.8, ruin_h=1.0, spread=0.15, rubble_cell=3.0,
                 debris="concrete", lod=(1.0,), ref="Via urbana: 2 carriles x 3.5 m, bordillo 0.15 m, acera 2.5 m (modulo 12 m)")


def build_road_intersection(name):
    S, W = 14.0, 7.0
    parts = [Part("Asphalt", [box((S, S, 0.12), (0, 0, 0.06), mat="Mat_Asphalt", cls="concrete")], "concrete")]
    zebra = []
    for ang in (0, 90, 180, 270):
        R = Matrix.Rotation(math.radians(ang), 4, 'Z')
        for k in range(7):
            zebra.append(box((2.5, 0.5, 0.01), (S / 2 - 1.6, -W / 2 + 0.5 + k * 1.0, 0.125), mat="Mat_Road_Paint", cls="concrete", frac=False).transform(R))
    parts.append(Part("Crosswalks", zebra, "concrete", kind="detail"))
    for k, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        c = [box((3.5, 3.5, 0.22), (sx * (S / 2 + 1.75), sy * (S / 2 + 1.75), 0.11), mat="Mat_Paving", cls="concrete")]
        parts.append(Part(f"Corner_{k}", c, "concrete"))
    return Asset(name, "Map", "structure", parts, n_impacts=1, dmg_r=2.0, ruin_h=1.0, spread=0.15, rubble_cell=3.0,
                 debris="concrete", lod=(1.0,), ref="Cruce urbano 14 x 14 m con pasos de cebra")


def build_road_dirt(name):
    """Camino de tierra 12 x 4 m con roderas de vehiculo."""
    prof = [(-2.0, 0), (2.0, 0), (2.0, 0.08), (1.0, 0.08), (0.85, 0.03), (0.55, 0.03), (0.4, 0.08), (-0.4, 0.08),
            (-0.55, 0.03), (-0.85, 0.03), (-1.0, 0.08), (-2.0, 0.08)]
    p = prism(prof, 12.0, axis='x', mat="Mat_Terrain_Soil", cls="earth")
    return Asset(name, "Map", "structure", [Part("DirtRoad", [p], "earth")], n_impacts=1, dmg_r=1.5, ruin_h=1.0, spread=0.1,
                 rubble_cell=3.0, debris="earth", lod=(1.0,), ref="Camino de tierra 4 m con roderas (modulo 12 m)")


def lattice_tower(H, b0, b1, levels, n_legs=4, mat="Mat_Steel_Galvanized", leg_w=0.25, strut_r=0.05):
    """Torre de celosia: patas inclinadas + riostras en X por nivel. Devuelve [Part] por nivel."""
    def corner(i, z):
        t = z / H
        b = b0 + (b1 - b0) * t
        a = 2 * math.pi * i / n_legs + (math.pi / 4 if n_legs == 4 else math.pi / 2)
        return V(math.cos(a) * b * (1.414 if n_legs == 4 else 1.0), math.sin(a) * b * (1.414 if n_legs == 4 else 1.0), z)
    parts = []
    for k in range(levels):
        z0, z1 = H * k / levels, H * (k + 1) / levels
        pcs = [beam(corner(i, z0), corner(i, z1), leg_w, mat=mat, cls="metal", grain=None, frac=False) for i in range(n_legs)]
        for i in range(n_legs):
            j = (i + 1) % n_legs
            pcs.append(strut(corner(i, z0), corner(j, z1), strut_r, mat, 4, cls="metal", frac=False, smooth=False))
            pcs.append(strut(corner(j, z0), corner(i, z1), strut_r, mat, 4, cls="metal", frac=False, smooth=False))
            pcs.append(strut(corner(i, z1), corner(j, z1), strut_r, mat, 4, cls="metal", frac=False, smooth=False))
        parts.append(Part(f"Level_{k}", pcs, "metal"))
    return parts, corner


def build_pylon(name):
    """Torre de alta tension (celosia) 30 m con 3 crucetas y cadenas de aisladores."""
    H = 30.0
    parts, corner = lattice_tower(H, 3.6, 0.9, 8)
    for k, (z, half) in enumerate(((H * 0.68, 6.0), (H * 0.8, 4.8), (H * 0.92, 3.6))):
        arm = [beam((-half, 0, z), (half, 0, z), 0.35, 0.5, mat="Mat_Steel_Galvanized", cls="metal", grain=None, frac=False)]
        for sx in (-1, 1):
            arm.append(strut((sx * half * 0.95, 0, z), (sx * half * 0.95, 0, z - 2.2), 0.08, "Mat_Insulator", 8, cls="glass", frac=False))
            arm.append(strut((sx * 1.0, 0, z - 0.6), (sx * half * 0.7, 0, z), 0.05, "Mat_Steel_Galvanized", 4, cls="metal", frac=False))
        parts.append(Part(f"Crossarm_{k}", arm, "metal"))
    parts.append(Part("Footings", [box((1.2, 1.2, 0.5), tuple(corner(i, 0) + V(0, 0, 0.0)), mat="Mat_Concrete_Base", cls="concrete") for i in range(4)],
                      "concrete"))
    return Asset(name, "Map", "structure", parts, n_impacts=1, dmg_r=3.0, ruin_h=0.25, spread=0.6, rubble_cell=5.0,
                 debris="metal", lod=(1.0, 0.6), ref="Torre de alta tension de celosia ~30 m (110-220 kV)")


def build_radio_mast(name):
    """Mastil de comunicaciones atirantado 40 m (seccion triangular) con antenas y vientos."""
    H = 40.0
    parts, corner = lattice_tower(H, 0.9, 0.9, 10, n_legs=3, leg_w=0.12, strut_r=0.025)
    ant = [cyl(0.25, 1.6, (0.9 * math.cos(a), 0.9 * math.sin(a), H - 2.0), mat="Mat_Civil_White", segs=8, cls="metal", frac=False)
           for a in (0.3, 2.4, 4.5)]
    ant += [box((0.3, 1.2, 2.2), (1.2, 0, H - 6.0), mat="Mat_Civil_White", cls="metal", frac=False),
            cyl(0.6, 0.3, (0, -1.3, H - 9.0), (90, 0, 0), mat="Mat_Civil_White", segs=12, cls="metal", frac=False)]
    parts.append(Part("Antennas", ant, "metal", kind="detail"))
    guys = []
    for i in range(3):
        a = 2 * math.pi * i / 3 + math.pi / 2
        anchor = V(math.cos(a) * 24.0, math.sin(a) * 24.0, 0.2)
        for z in (H * 0.45, H * 0.9):
            guys.append(strut(anchor, corner(i, z), 0.015, "Mat_Wire_Steel", 3, cls="metal", frac=False, smooth=False))
        guys.append(box((1.0, 1.0, 0.4), tuple(anchor), mat="Mat_Concrete_Base", cls="concrete", frac=False))
    parts.append(Part("GuyWires", guys, "metal", kind="detail"))
    parts.append(Part("Equipment_Shelter", [box((3.0, 2.4, 2.6), (4.0, 3.0, 1.3), mat="Mat_Civil_White", cls="metal")], "metal"))
    return Asset(name, "Map", "structure", parts, n_impacts=1, dmg_r=3.0, ruin_h=0.2, spread=0.6, rubble_cell=6.0,
                 debris="metal", lod=(1.0, 0.6), ref="Mastil de telecomunicaciones atirantado 40 m")


def build_water_tower(name):
    """Deposito de agua elevado: 4 columnas de 12 m + tanque de 6 m de diametro."""
    parts, H, R = [], 12.0, 3.0
    for i, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        parts.append(Part(f"Column_{i}", [beam((sx * 2.4, sy * 2.4, 0), (sx * 2.0, sy * 2.0, H), 0.35, mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    br = []
    for z in (4.0, 8.0):
        for (a, b) in (((2.2, 2.2), (2.2, -2.2)), ((2.2, -2.2), (-2.2, -2.2)), ((-2.2, -2.2), (-2.2, 2.2)), ((-2.2, 2.2), (2.2, 2.2))):
            br.append(beam((a[0], a[1], z), (b[0], b[1], z), 0.25, mat="Mat_Concrete_Base", cls="concrete"))
    parts.append(Part("Bracing", br, "concrete"))
    tank = lathe([(0, 0), (R, 0), (R, 4.0), (0, 4.0), (0, 3.8), (R - 0.12, 3.8), (R - 0.12, 0.12), (0, 0.12)], (0, 0, H), mat="Mat_Steel_Galvanized",
                 segs=20, hollow=True, cls="metal")
    roof = cyl(R + 0.15, 1.2, (0, 0, H + 4.6), mat="Mat_Steel_Galvanized", segs=20, r2=0.3, cls="metal")
    parts.append(Part("Tank", [tank, box((5.2, 5.2, 0.3), (0, 0, H - 0.15), mat="Mat_Concrete_Base", cls="concrete")], "metal"))
    parts.append(Part("Roof", [roof], "metal"))
    lad = [strut((2.6, -0.25, 0.0), (2.2, -0.25, H), 0.03, "Mat_Steel_Galvanized", 4, cls="metal", frac=False),
           strut((2.6, 0.25, 0.0), (2.2, 0.25, H), 0.03, "Mat_Steel_Galvanized", 4, cls="metal", frac=False)]
    parts.append(Part("Ladder", lad, "metal", kind="detail"))
    return Asset(name, "Map", "structure", parts, n_impacts=2, dmg_r=2.0, ruin_h=0.3, spread=0.5, rubble_cell=4.0,
                 debris="concrete", lod=(1.0, 0.6), ref="Deposito elevado ~110 m3 sobre columnas de 12 m")


def build_fuel_tank(name):
    """Tanque de almacenamiento de combustible 16 m x 10 m con cubeto de contencion."""
    R, H = 8.0, 10.0
    shell = lathe([(0, 0), (R, 0), (R, H), (0, H), (0, H - 0.1), (R - 0.05, H - 0.1), (R - 0.05, 0.1), (0, 0.1)], mat="Mat_Civil_White",
                  segs=28, hollow=True, cls="metal")
    roof = cyl(R + 0.1, 1.0, (0, 0, H + 0.5), mat="Mat_Civil_White", segs=28, r2=0.8, cls="metal")
    parts = [Part("Shell", [shell], "metal"), Part("Roof", [roof], "metal")]
    st = []
    for k in range(20):
        a = math.radians(k * 9)
        st.append(box((1.0, 0.3, 0.06), (math.cos(a) * (R + 0.6), math.sin(a) * (R + 0.6), 0.5 * (k + 1)), (0, 0, math.degrees(a) + 90),
                      mat="Mat_Steel_Galvanized", cls="metal", frac=False))
    parts.append(Part("Stairs", st, "metal", kind="detail"))
    bund = []
    for k in range(16):
        a0, a1 = 2 * math.pi * k / 16, 2 * math.pi * (k + 1) / 16
        p0 = V(math.cos(a0), math.sin(a0), 0) * (R + 4.5)
        p1 = V(math.cos(a1), math.sin(a1), 0) * (R + 4.5)
        bund.append(beam(p0 + V(0, 0, 0.6), p1 + V(0, 0, 0.6), 0.3, 1.2, mat="Mat_Concrete_Base", cls="concrete", grain=None))
    parts.append(Part("Bund_Wall", bund, "concrete"))
    return Asset(name, "Map", "structure", parts, n_impacts=2, dmg_r=3.0, ruin_h=0.3, spread=0.4, rubble_cell=5.0,
                 debris="metal", lod=(1.0, 0.6), ref="Tanque API 650 de ~2000 m3 (16 m x 10 m) con cubeto")


def build_bridge(name):
    """Puente de vigas de hormigon 36 m (3 vanos de 12 m), tablero a 6 m: si cae una pila, cae el vano."""
    Hd, W, span = 6.0, 9.0, 12.0
    parts = []
    for k in range(3):
        x = -span + k * span
        deck = [box((span - 0.05, W, 0.45), (x, 0, Hd + 0.225), mat="Mat_Concrete_Base", cls="concrete"),
                box((span - 0.05, W - 2.0, 0.08), (x, 0, Hd + 0.49), mat="Mat_Asphalt", cls="concrete", frac=False)]
        deck += [box((span - 0.05, 0.5, 1.1), (x, gy, Hd - 0.55), mat="Mat_Concrete_Base", cls="concrete") for gy in (-3.0, 0.0, 3.0)]
        parts.append(Part(f"Span_{k}", deck, "concrete"))
        rail = [box((span - 0.05, 0.3, 0.9), (x, sy * (W / 2 - 0.15), Hd + 0.9), mat="Mat_Concrete_Base", cls="concrete") for sy in (-1, 1)]
        parts.append(Part(f"Parapet_{k}", rail, "concrete"))
    seat = Hd - 1.1                                              # cota de apoyo de las vigas
    for k, sx in enumerate((-1, 1)):                             # estribos: asiento de 1 m + muro de guarda
        x = sx * span * 1.5
        ab = [box((3.0, W + 1.0, seat), (x + sx * 0.5, 0, seat / 2), mat="Mat_Concrete_Base", cls="concrete"),
              box((0.6, W + 1.0, Hd + 0.45 - seat), (x + sx * 0.3 + sx * 0.05, 0, (seat + Hd + 0.45) / 2), mat="Mat_Concrete_Base", cls="concrete")]
        parts.append(Part(f"Abutment_{k}", ab, "concrete"))
    for k, x in enumerate((-span / 2, span / 2)):                # pilas: 2 fustes + dintel bajo las vigas
        pier = [box((1.6, 1.6, seat - 0.8), (x, gy, (seat - 0.8) / 2), mat="Mat_Concrete_Base", cls="concrete") for gy in (-2.8, 2.8)]
        pier.append(box((2.0, W, 0.8), (x, 0, seat - 0.4), mat="Mat_Concrete_Base", cls="concrete"))
        parts.append(Part(f"Pier_{k}", pier, "concrete"))
    return Asset(name, "Map", "structure", parts, n_impacts=2, dmg_r=2.5, ruin_h=0.45, spread=0.2, rubble_cell=5.0,
                 debris="concrete", lod=(1.0,), ref="Puente de vigas de hormigon, 3 vanos de 12 m, tablero de 9 m a 6 m de altura")


def build_helipad(name):
    p = [Part("Pad", [box((20.0, 20.0, 0.3), (0, 0, 0.15), mat="Mat_Concrete_Base", cls="concrete")], "concrete")]
    mk = [box((0.8, 6.0, 0.01), (sx * 1.8, 0, 0.305), mat="Mat_Road_Paint", cls="concrete", frac=False) for sx in (-1, 1)]
    mk.append(box((2.8, 0.8, 0.01), (0, 0, 0.305), mat="Mat_Road_Paint", cls="concrete", frac=False))
    mk.append(lathe([(7.0, 0.3), (7.5, 0.3), (7.5, 0.31), (7.0, 0.31)], mat="Mat_Road_Paint", segs=32, closed=True, cls="concrete", frac=False))
    p.append(Part("Markings", mk, "concrete", kind="detail"))
    return Asset(name, "Map", "structure", p, n_impacts=1, dmg_r=3.0, ruin_h=1.0, spread=0.1, rubble_cell=5.0,
                 debris="concrete", lod=(1.0,), ref="Helipuerto de campana 20 x 20 m, H de 6 m")


def build_runway(name):
    """Tramo de pista 60 x 45 m (hormigon 0.4 m) con eje discontinuo y bordes."""
    L, W = 60.0, 45.0
    parts = []
    for k in range(4):                                          # losas independientes (crateres por losa)
        parts.append(Part(f"Slab_{k}", [box((L, W / 4, 0.4), (0, -W / 2 + W / 8 + k * W / 4, 0.2), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    mk = [box((30.0, 0.9, 0.01), (-L / 2 + 15.0, 0, 0.405), mat="Mat_Road_Paint", cls="concrete", frac=False)]
    mk += [box((L, 0.9, 0.01), (0, sy * (W / 2 - 1.0), 0.405), mat="Mat_Road_Paint", cls="concrete", frac=False) for sy in (-1, 1)]
    parts.append(Part("Markings", mk, "concrete", kind="detail"))
    return Asset(name, "Map", "structure", parts, n_impacts=2, dmg_r=4.0, ruin_h=1.0, spread=0.1, rubble_cell=6.0,
                 debris="concrete", chunk_scale=0.6, lod=(1.0,), ref="Pista OTAN 45 m de ancho, losas de hormigon de 0.4 m (tramo de 60 m)")


def build_street_lamp(name):
    pole = lathe([(0.12, 0), (0.1, 1.0), (0.06, 8.0), (0, 8.05)], mat="Mat_Steel_Galvanized", segs=8, cls="metal", grain="z")
    arm = [strut((0, 0, 7.8), (1.6, 0, 8.3), 0.04, "Mat_Steel_Galvanized", 6, cls="metal"),
           box((0.6, 0.25, 0.12), (1.85, 0, 8.25), mat="Mat_Steel_Galvanized", cls="metal"),
           box((0.5, 0.2, 0.03), (1.85, 0, 8.18), mat="Mat_Light_Lens", cls="glass", frac=False)]
    return Asset(name, "Props", "tree", [Part("Pole", [pole], "metal", kind="trunk"), Part("Lamp", arm, "metal", kind="branch")],
                 cut_h=0.8, lod=(1.0, 0.5), ref="Farola de vial 8 m con brazo de 1.6 m")


def build_billboard(name):
    posts = [beam((sx * 2.5, 0, 0), (sx * 2.5, 0, 6.0), 0.3, mat="Mat_Steel_Galvanized", cls="metal") for sx in (-1, 1)]
    panel = box((8.0, 0.25, 3.0), (0, 0, 6.5), mat="Mat_Container_Paint", cls="metal")
    walk = box((8.0, 0.8, 0.06), (0, -0.55, 4.9), mat="Mat_Steel_Galvanized", cls="metal", frac=False)
    return Asset(name, "Props", "structure", [Part("Posts", posts, "metal"), Part("Panel", [panel, walk], "metal")],
                 n_impacts=1, dmg_r=1.5, ruin_h=0.4, spread=0.5, rubble_cell=3.0, debris="metal", lod=(1.0,),
                 ref="Valla publicitaria 8 x 3 m sobre postes de 6 m")


# ==================================================================================
# BUILDERS v4 (2): MAS VEHICULOS, AERONAVES Y ESTRUCTURAS DE GUERRA (medidas reales)
# ==================================================================================
MATS.update({
    "Mat_Sign_Red": ((0.55, 0.04, 0.03), 0.2, 0.5, 1, 0),
    "Mat_Dome_Tile": ((0.10, 0.32, 0.30), 0.1, 0.35, 1, 0),
})
TEX_SPECS.update({
    "Mat_Sign_Red": ("metal_paint", dict(chips=0.1, dust=0.2), 1.0, 0.4),
    "Mat_Dome_Tile": ("plaster", dict(cracks=0.3), 2.0, 0.6),
})

TRUCKS = {
    "Veh_Truck_Ural-4320": dict(L=7.37, W=2.5, H=2.87, mass=8050, axles=(2.43, -1.09, -2.49), wr=0.6, style="hood", roof=2.6,
                                paint="Mat_Military_RuGreen", cargo="canvas",
                                ref="Ural-4320 6x6: L 7.37 m, ancho 2.5 m, alto 2.87 m, batalla 3.525 + 1.4 m, 8 t vacio"),
    "Art_MLRS_BM-21_Grad": dict(L=7.35, W=2.4, H=3.09, mass=13700, axles=(2.42, -1.1, -2.5), wr=0.6, style="hood", roof=2.38,
                                paint="Mat_Military_RuGreen", cargo="grad",
                                ref="BM-21 Grad sobre Ural-375D: L 7.35 m, ancho 2.4 m, alto 3.09 m, 40 tubos de 122 mm, 13.7 t"),
    "Art_MLRS_M142_HIMARS": dict(L=6.94, W=2.44, H=3.18, mass=16250, axles=(2.35, -1.05, -2.45), wr=0.56, style="cabover", roof=2.95,
                                 paint="Mat_Military_Desert", cargo="himars", armored=True,
                                 ref="M142 HIMARS (chasis FMTV 6x6): L 6.94 m, ancho 2.44 m, alto 3.18 m, contenedor de 6 GMLRS, 16.25 t"),
    "Civ_Truck_Box": dict(L=7.2, W=2.3, H=3.3, mass=5500, axles=(2.55, -1.65), wr=0.46, style="cabover", roof=2.7,
                          paint="Mat_Civil_White", cargo="box", civil=True,
                          ref="Camion de reparto 7.5 t con caja: L 7.2 m, ancho 2.3 m, alto 3.3 m, batalla 4.2 m"),
    "Civ_Bus_City": dict(L=12.0, W=2.55, H=3.05, mass=11500, axles=(3.3, -2.6), wr=0.48, style="bus",
                         paint="Mat_Bus_Paint", civil=True,
                         ref="Autobus urbano 12 m: ancho 2.55 m, alto 3.05 m, batalla 5.9 m, 11.5 t vacio"),
}


def _plate(pts, t, mat, cls="metal", **kw):
    """Placa fina a partir de 4 esquinas (planos de cola, faldones, cristales grandes)."""
    P = [V(p) for p in pts]
    n = (P[1] - P[0]).cross(P[3] - P[0]).normalized() * (t / 2)
    return hull([tuple(p + n) for p in P] + [tuple(p - n) for p in P], mat=mat, cls=cls, **kw)


def _move(parts, d):
    M = Matrix.Translation(V(d))
    for p in parts:
        for pc in p.all_pieces():
            pc.transform(M)
        if p.pivot is not None:
            p.pivot = M @ p.pivot
    return parts


def build_truck_x(name):
    """Camiones de capo (Ural/BM-21), de cabina avanzada (HIMARS, reparto) y autobus. Frente +X."""
    s = TRUCKS[name]
    L, W, H, wr, P, st = s["L"], s["W"], s["H"], s["wr"], s["paint"], s["style"]
    civil = s.get("civil", False)
    parts, glass, doors, det = [], [], [], []
    tw = wr * 0.8
    yw = W / 2 - tw / 2 - 0.02
    for i, x in enumerate(s["axles"]):
        for side, sy in (("L", 1), ("R", -1)):
            parts.append(tire_wheel(x, sy * yw, wr, wr, tw, f"Wheel_{i}{side}", "Mat_Metal_Gunmetal" if civil else P))
    zb = wr * 0.85
    xf = L / 2
    if st == "bus":
        zf = 0.32                                            # piso bajo
        body = hull(sym([(xf, W / 2 - 0.08, zf), (xf, W / 2 - 0.1, H - 0.35), (xf - 0.35, W / 2 - 0.04, H), (-xf + 0.2, W / 2 - 0.04, H),
                         (-xf, W / 2 - 0.06, H - 0.3), (-xf, W / 2 - 0.06, zf), (xf - 0.1, W / 2 - 0.04, zf), (-xf + 0.1, W / 2 - 0.04, zf)]),
                    mat=P, cls="metal")
        parts.append(Part("Body", [body], "metal", kind="hull"))
        door_x = [(xf - 0.95, 1.2), (0.0, 1.3)]               # puertas del lado derecho (-Y): delantera y central
        zw0, zw1 = 1.15, H - 0.32
        n = 8
        x0w, x1w = xf - 0.4, -xf + 0.5
        for sy in (-1, 1):
            for k in range(n):
                a = x0w + (x1w - x0w) * k / n - 0.04
                b = x0w + (x1w - x0w) * (k + 1) / n + 0.04
                if sy < 0 and any(min(a, b) < dx + dw / 2 and max(a, b) > dx - dw / 2 for dx, dw in door_x):
                    continue
                glass.append(glass_panel((a, sy * (W / 2 - 0.02), zw0), (b, sy * (W / 2 - 0.02), zw0),
                                         (b, sy * (W / 2 - 0.035), zw1), (a, sy * (W / 2 - 0.035), zw1)))
        glass.append(glass_panel((xf + 0.012, -W / 2 + 0.15, 0.95), (xf + 0.012, W / 2 - 0.15, 0.95),
                                 (xf + 0.012, W / 2 - 0.15, H - 0.42), (xf + 0.012, -W / 2 + 0.15, H - 0.42)))
        glass.append(glass_panel((-xf - 0.012, -W / 2 + 0.25, 1.45), (-xf - 0.012, W / 2 - 0.25, 1.45),
                                 (-xf - 0.012, W / 2 - 0.25, H - 0.45), (-xf - 0.012, -W / 2 + 0.25, H - 0.45)))
        for k, (dx, dw) in enumerate(door_x):
            leaf = [box((dw, 0.05, H - 0.62 - zf), (dx, -(W / 2 - 0.01), zf + (H - 0.62 - zf) / 2), mat=P, cls="metal"),
                    glass_panel((dx - dw / 2 + 0.1, -W / 2 - 0.02, 0.9), (dx + dw / 2 - 0.1, -W / 2 - 0.02, 0.9),
                                (dx + dw / 2 - 0.1, -W / 2 - 0.02, H - 0.75), (dx - dw / 2 + 0.1, -W / 2 - 0.02, H - 0.75))]
            doors.append(Part(f"Door_{k}", leaf, "metal", kind="door", pivot=(dx, -W / 2, zf), axis=(1, 0, 0), joint="slide"))
        det += [box((2.2, 1.6, 0.3), (-1.0, 0, H + 0.15), mat="Mat_Civil_White", cls="metal"),          # climatizador
                box((0.06, 1.6, 0.25), (xf + 0.01, 0, H - 0.25), mat="Mat_Light_Lens", cls="glass", frac=False),
                box((0.3, W * 0.98, 0.35), (xf + 0.08, 0, zf + 0.2), mat="Mat_Metal_Gunmetal", cls="metal"),
                box((0.3, W * 0.98, 0.35), (-xf - 0.08, 0, zf + 0.2), mat="Mat_Metal_Gunmetal", cls="metal")]
        for sy in (-1, 1):
            det.append(box((0.05, 0.3, 0.15), (xf + 0.01, sy * (W / 2 - 0.3), 0.75), mat="Mat_Light_Lens", cls="glass", frac=False))
            det.append(strut((xf - 0.1, sy * (W / 2 - 0.05), H - 0.5), (xf + 0.25, sy * (W / 2 + 0.2), H - 0.7), 0.02, "Mat_Metal_Gunmetal", 4, cls="metal"))
    else:
        roof = s["roof"]
        parts.append(Part("Chassis", [box((L * 0.92, W * 0.42, 0.25), (-0.12, 0, zb), mat="Mat_Metal_Gunmetal", cls="metal")], "metal", kind="body"))
        if st == "hood":
            hood_l, cab_l, hz = 1.7, 1.5, 1.95
            xc0 = xf - hood_l
            xc1 = xc0 - cab_l
            hood = hull(sym([(xf, W / 2 - 0.62, zb + 0.3), (xf, W / 2 - 0.62, hz - 0.08), (xf - 0.25, W / 2 - 0.58, hz),
                             (xc0, W / 2 - 0.5, hz + 0.02), (xc0, W / 2 - 0.5, zb + 0.25)]), mat=P, cls="metal")
            fend = []
            for sy in (-1, 1):
                fx = s["axles"][0]
                fend.append(box((1.5, 0.58, 0.06), (fx, sy * (W / 2 - 0.29), 2 * wr + 0.12), mat=P, cls="metal"))
                fend.append(box((0.06, 0.58, 0.45), (fx - 0.78, sy * (W / 2 - 0.29), 2 * wr - 0.1), mat=P, cls="metal"))
            parts.append(Part("Body_Hood", [hood] + fend, "metal", kind="body"))
            cab = hull(sym([(xc0, W / 2 - 0.1, zb + 0.3), (xc0, W / 2 - 0.1, hz + 0.1), (xc0 - 0.25, W / 2 - 0.13, roof),
                            (xc1, W / 2 - 0.13, roof), (xc1, W / 2 - 0.1, zb + 0.3)]), mat=P, cls="metal")
            parts.append(Part("Cab", [cab], "metal", kind="cab"))

            def fxw(z):
                return xc0 - 0.25 * (z - (hz + 0.1)) / max(roof - hz - 0.1, 1e-3) + 0.015
            z0g, z1g = hz + 0.15, roof - 0.1
            for sy in (-1, 1):
                glass.append(glass_panel((fxw(z0g), sy * 0.06, z0g), (fxw(z0g), sy * (W / 2 - 0.2), z0g),
                                         (fxw(z1g), sy * (W / 2 - 0.22), z1g), (fxw(z1g), sy * 0.06, z1g)))
            dx0, dx1 = xc0 - 0.2, xc1 + 0.15
        else:                                                    # cabina avanzada (FMTV/HIMARS, reparto)
            cab_l = 2.05 if s.get("armored") else 1.75
            xc1 = xf - cab_l
            cab = hull(sym([(xf, W / 2 - 0.08, zb + 0.15), (xf - 0.12, W / 2 - 0.1, roof - 0.1), (xf - 0.35, W / 2 - 0.12, roof),
                            (xc1, W / 2 - 0.08, roof), (xc1, W / 2 - 0.05, zb + 0.15)]), mat=P, cls="metal")
            parts.append(Part("Cab", [cab], "metal", kind="cab"))

            def fxw(z):
                return xf - 0.12 * (z - (zb + 0.15)) / max(roof - 0.1 - zb - 0.15, 1e-3) + 0.015
            z0g, z1g = zb + (1.25 if s.get("armored") else 1.0), roof - 0.22
            ww = W / 2 - (0.35 if s.get("armored") else 0.18)
            glass.append(glass_panel((fxw(z0g), -ww, z0g), (fxw(z0g), ww, z0g), (fxw(z1g), ww, z1g), (fxw(z1g), -ww, z1g)))
            det.append(box((0.25, W * 0.96, 0.3), (xf + 0.08, 0, zb + 0.05), mat="Mat_Metal_Gunmetal", cls="metal"))
            dx0, dx1 = xf - 0.3, xc1 + 0.25
        for k, sy in enumerate((1, -1)):                         # puertas con ventanilla
            dl = dx0 - dx1
            leaf = [box((dl, 0.06, roof - zb - 0.55), ((dx0 + dx1) / 2, sy * (W / 2 - 0.06), (roof + zb) / 2 - 0.1), mat=P, cls="metal"),
                    glass_panel((dx0 - 0.1, sy * (W / 2 - 0.02), roof - 1.05), (dx1 + 0.1, sy * (W / 2 - 0.02), roof - 1.05),
                                (dx1 + 0.1, sy * (W / 2 - 0.05), roof - 0.25), (dx0 - 0.1, sy * (W / 2 - 0.05), roof - 0.25))]
            doors.append(Part(f"Door_{k}", leaf, "metal", kind="door", pivot=(dx0, sy * W / 2, zb + 0.5), axis=(0, 0, 1), joint="hinge"))
            det.append(box((0.04, 0.22, 0.32), (dx0 + 0.1, sy * (W / 2 + 0.22), roof - 0.55), mat="Mat_Metal_Gunmetal", cls="metal"))
            det.append(strut((dx0 + 0.02, sy * (W / 2 - 0.08), roof - 0.4), (dx0 + 0.1, sy * (W / 2 + 0.12), roof - 0.5), 0.015,
                             "Mat_Metal_Gunmetal", 4, cls="metal", frac=False))
            det.append(box((0.05, 0.22, 0.14), (xf + 0.02, sy * (W / 2 - 0.3), zb + 0.55), mat="Mat_Light_Lens", cls="glass", frac=False))
            det.append(cyl(0.25, 0.9, (s["axles"][1] + 1.2, sy * (W / 2 - 0.32), zb + 0.05), (0, 90, 0), mat=P, segs=10, cls="metal"))
        deck_z = zb + 0.55
        cargo = s["cargo"]
        xd0, xd1 = xc1 - (0.7 if cargo == "canvas" else 0.15), -L / 2
        if cargo in ("canvas", "box", "himars", "grad"):
            deck = [box((xd0 - xd1, W - 0.06, 0.18), ((xd0 + xd1) / 2, 0, deck_z - 0.09), mat="Mat_Metal_Gunmetal" if civil else P, cls="metal")]
            parts.append(Part("RearDeck", deck, "metal", kind="bed"))
        if cargo == "canvas":
            bx, bl = (xd0 + xd1) / 2, xd0 - xd1
            bed = [box((bl, 0.05, 0.75), (bx, sy * (W / 2 - 0.025), deck_z + 0.375), mat="Mat_Wood_Plank", cls="wood", grain="x") for sy in (-1, 1)]
            bed += [box((0.05, W, 0.75), (xd1 + 0.025, 0, deck_z + 0.375), mat="Mat_Wood_Plank", cls="wood", grain="y"),
                    box((0.05, W, 0.9), (xd0 - 0.025, 0, deck_z + 0.45), mat="Mat_Wood_Plank", cls="wood", grain="y")]
            parts.append(Part("CargoBed", bed, "wood", kind="bed"))
            ch = H - deck_z - 0.75
            cover = [box((bl / 4 + 0.02, W - 0.04, 0.03), (xd1 + bl * (k + 0.5) / 4, 0, H - 0.015), mat="Mat_Fabric_Canvas", cls="fabric") for k in range(4)]
            cover += [box((bl - 0.1, 0.03, ch), (bx, sy * (W / 2 - 0.04), H - ch / 2), mat="Mat_Fabric_Canvas", cls="fabric") for sy in (-1, 1)]
            cover.append(box((0.03, W - 0.04, ch), (xd1 + 0.04, 0, H - ch / 2), mat="Mat_Fabric_Canvas", cls="fabric"))
            parts.append(Part("CanvasCover", cover, "fabric", kind="detail"))
            spare = tire_wheel(0, 0, 0, wr, tw, "SpareWheel", P)          # de canto tras la cabina, mirando atras
            M = Matrix.Translation((xc1 - 0.33, 0, zb + 0.15 + wr)) @ Matrix.Rotation(math.pi / 2, 4, 'Z')
            for pc in spare.all_pieces():
                pc.transform(M)
            spare.pivot, spare.axis = M @ spare.pivot, (M.to_3x3() @ spare.axis).normalized()
            spare.kind, spare.joint, spare.tags = "detail", "fixed", {"detail", "tire"}
            parts.append(spare)
        elif cargo == "box":
            bl, bx = xd0 - xd1 - 0.05, (xd0 + xd1) / 2
            hb = H - deck_z
            shell = [box((bl, 0.04, hb), (bx, sy * (W / 2 - 0.02), deck_z + hb / 2), mat="Mat_Civil_White", cls="metal") for sy in (-1, 1)]
            shell += [box((bl, W, 0.04), (bx, 0, H - 0.02), mat="Mat_Civil_White", cls="metal"),
                      box((0.04, W, hb), (xd0 - 0.02, 0, deck_z + hb / 2), mat="Mat_Civil_White", cls="metal")]
            parts.append(Part("CargoBox", shell, "metal", kind="bed"))
            doors.append(Part("RollerDoor", [box((0.05, W - 0.1, hb - 0.1), (xd1 - 0.02, 0, deck_z + hb / 2), mat="Mat_Roof_Metal", cls="metal")],
                              "metal", kind="door", pivot=(xd1, 0, H - 0.1), axis=(0, 0, 1), joint="slide"))
        elif cargo == "himars":
            px = (xd0 + xd1) / 2
            base = [cyl(0.95, 0.3, (px, 0, deck_z + 0.15), mat=P, segs=16, cls="metal"),
                    box((3.0, 2.1, 0.35), (px, 0, deck_z + 0.47), mat=P, cls="metal")]
            base += [box((1.0, 0.15, 0.8), (px + 1.1, sy * 0.7, deck_z + 1.05), mat=P, cls="metal") for sy in (-1, 1)]
            parts.append(Part("Launcher_Turntable", base, "metal", kind="turret", pivot=(px, 0, deck_z), axis=(0, 0, 1), joint="yaw"))
            pz = deck_z + 1.55
            pod = [box((4.3, 1.2, 1.05), (px - 0.4, 0, pz), mat=P, cls="metal")]
            for r in range(2):
                for c in range(3):
                    pod.append(cyl(0.135, 0.06, (px - 2.56, (c - 1) * 0.36, pz - 0.23 + r * 0.46), (0, 90, 0),
                                   mat="Mat_Metal_Charred", segs=10, cls="metal", frac=False))
            parts.append(Part("Launcher_Pod", pod, "metal", kind="gun", tags=("turret",), pivot=(px + 1.75, 0, pz - 0.5), axis=(0, 1, 0), joint="pitch"))
        elif cargo == "grad":
            lx = -L / 2 + 1.3
            base = [cyl(0.7, 0.35, (lx, 0, deck_z + 0.175), mat=P, segs=14, cls="metal"),
                    box((1.1, 1.4, 0.45), (lx + 0.1, 0, deck_z + 0.58), mat=P, cls="metal")]
            parts.append(Part("Launcher_Mount", base, "metal", kind="turret", pivot=(lx, 0, deck_z), axis=(0, 0, 1), joint="yaw"))
            tz0, sp = roof + 0.13, 0.155
            tubes = []
            for r in range(4):
                for c in range(10):
                    tubes.append(cyl(0.07, 3.0, (lx + 0.95, (c - 4.5) * sp, tz0 + r * sp), (0, 90, 0), mat="Mat_Military_RuGreen",
                                     segs=8, cls="metal", frac=False))
            tubes += [box((0.12, 10 * sp + 0.1, 4 * sp + 0.1), (lx + 0.95 + dx, 0, tz0 + 1.5 * sp), mat=P, cls="metal") for dx in (-1.2, 0.0, 1.2)]
            tubes.append(box((0.5, 0.5, tz0 - deck_z - 0.7), (lx + 0.1, 0, (tz0 + deck_z + 0.7) / 2), mat=P, cls="metal"))
            parts.append(Part("Launcher_Tubes", tubes, "metal", kind="gun", tags=("turret",), pivot=(lx + 0.1, 0, tz0), axis=(0, 1, 0), joint="pitch"))
        det.append(strut((xc1 + 0.15, -W / 2 + 0.25, roof - 0.3), (xc1 + 0.15, -W / 2 + 0.25, roof + 0.5), 0.05, "Mat_Metal_Gunmetal", 6, cls="metal"))
    parts.append(Part("Details", det, "metal", kind="detail"))
    if glass:
        parts.append(Part("Windows", glass, "glass", kind="glass"))
    parts += doors
    cat = "Artillery" if name.startswith("Art_") else "Civilian" if civil else "Vehicles"
    return Asset(name, cat, "vehicle", parts, forward_x=True, mass=s["mass"], ref=s["ref"], lod=(1.0, 0.5, 0.2))


HELIS.update({
    "Air_Heli_Mi-24P_Hind": dict(FL=17.5, FW=1.7, FH=2.0, rotor=17.3, blades=5, trotor=3.9, H=4.65, mass=8500, tandem=True, stubs=6.5,
                                 k=17.5 / 15.0, paint="Mat_Military_RuGreen",
                                 ref="Mil Mi-24P: fuselaje 17.5 m, rotor 17.3 m (5 palas), alas 6.5 m, cabina en tandem, 8.5 t vacio"),
    "Air_Heli_Mi-8MTV": dict(FL=18.4, FW=2.5, FH=2.3, rotor=21.29, blades=5, trotor=3.91, H=4.75, mass=7489, k=18.4 / 15.0,
                             paint="Mat_Military_RuGreen", ref="Mil Mi-8MTV: L 18.42 m (sin rotores), rotor 21.29 m, alto 4.76 m, 7.5 t vacio"),
})


def build_tb2(name):
    """Bayraktar TB2: L 6.5 m, envergadura 12 m, doble viga de cola con V invertida, helice propulsora."""
    P, gz = "Mat_Military_Grey", 0.62
    zc = gz + 0.32
    secs = [(3.25, 0.04, 0.04, zc), (2.95, 0.2, 0.22, zc), (2.2, 0.3, 0.32, zc + 0.02), (0.2, 0.3, 0.3, zc + 0.02),
            (-0.9, 0.2, 0.2, zc + 0.05), (-1.3, 0.1, 0.1, zc + 0.05)]
    parts = [Part("Fuselage", [loft(ell_rings(secs, 10), mat=P, cls="metal", smooth=True),
                               sphere(0.17, (2.45, 0, gz + 0.02), mat="Mat_Glass_Canopy", segs=10, rings=6, cls="glass")], "metal", kind="fuselage")]
    wz = zc + 0.3
    for side, sy in (("L", 1), ("R", -1)):
        w = prism([(0.75, 0.0), (0.15, 0.0), (0.32, 6.0), (0.6, 6.0)], 0.09, axis='z', offset=wz, mat=P, cls="metal")
        w.transform(Matrix.Diagonal((1, sy, 1, 1)))
        parts.append(Part(f"Wing_{side}", [w], "metal", kind="wing", pivot=(0.45, sy * 0.25, wz), axis=(1, 0, 0), joint="break"))
    tail = [strut((0.4, sy * 1.2, wz), (-3.25, sy * 1.2, wz + 0.04), 0.06, P, 8, cls="metal") for sy in (-1, 1)]
    for sy in (-1, 1):                                    # V invertida: de cada viga hacia abajo y al centro
        tail.append(_plate([(-2.75, sy * 1.2, wz + 0.04), (-3.35, sy * 1.2, wz + 0.04), (-3.4, 0.0, wz - 0.62), (-2.95, 0.0, wz - 0.62)],
                           0.05, P))
    parts.append(Part("TailBooms", tail, "metal", kind="tail", pivot=(0.4, 0, wz), axis=(0, 1, 0), joint="break"))
    prop = [cyl(0.08, 0.2, (-1.42, 0, zc + 0.05), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal")]
    for a in (0, 180):
        prop.append(beam((-1.47, 0, zc + 0.05), (-1.47, 0.85 * math.cos(math.radians(a)), zc + 0.05 + 0.85 * math.sin(math.radians(a))),
                         0.12, 0.025, mat="Mat_Rotor_Blade", cls="metal", grain=None))
    parts.append(Part("Propeller", prop, "metal", kind="rotor", pivot=(-1.45, 0, zc + 0.05), axis=(1, 0, 0), joint="spin"))
    gear = [strut((2.2, 0, zc - 0.25), (2.25, 0, 0.17), 0.025, "Mat_Metal_Gunmetal", 6, cls="metal"),
            cyl(0.15, 0.08, (2.25, 0, 0.15), (90, 0, 0), mat="Mat_Rubber_Tire", segs=10, cls="rubber")]
    for sy in (-1, 1):
        gear.append(strut((0.1, sy * 0.25, zc - 0.25), (-0.05, sy * 0.85, 0.17), 0.025, "Mat_Metal_Gunmetal", 6, cls="metal"))
        gear.append(cyl(0.16, 0.09, (-0.05, sy * 0.88, 0.16), (90, 0, 0), mat="Mat_Rubber_Tire", segs=10, cls="rubber"))
    parts.append(Part("LandingGear", gear, "metal", kind="gear"))
    pyl = []
    for sy in (-1, 1):                                    # 2 municiones MAM-L bajo cada ala
        for k, yy in enumerate((1.6, 2.6)):
            pyl.append(box((0.3, 0.06, 0.12), (0.45, sy * yy, wz - 0.1), mat=P, cls="metal", frac=False))
            pyl.append(cyl(0.05, 1.0, (0.45, sy * yy, wz - 0.22), (0, 90, 0), mat="Mat_Metal_Gunmetal", segs=8, cls="metal", frac=False))
    parts.append(Part("Munitions", pyl, "metal", kind="detail"))
    return Asset(name, "Aircraft", "vehicle", parts, forward_x=True, mass=650,
                 ref="Baykar Bayraktar TB2: L 6.5 m, envergadura 12 m, MTOW 650 kg, 4 MAM-L", lod=(1.0, 0.5, 0.2))


# ----------------------------------- edificios ----------------------------------------
def _gable(Wx, Dy, z, pitch, t, wall_mat, wcls, roof_mat="Mat_Roof_Tile", rcls="wood", ov=0.45, tag=""):
    """Cubierta a dos aguas (cumbrera en X) + hastiales, como en build_house."""
    p = math.radians(pitch)
    rise = (Dy / 2) * math.tan(p)
    out = []
    for sy in (-1, 1):
        run = Dy / 2 + ov
        zc = z + rise - (run / 2) * math.tan(p) + 0.09 / math.cos(p)
        slab = box((Wx + 2 * ov, run / math.cos(p) + 0.05, 0.18), (0, sy * run / 2, zc + 0.03), (sy * -pitch, 0, 0), mat=roof_mat, cls=rcls)
        out.append(Part(f"Roof{tag}_{'S' if sy < 0 else 'N'}", [slab], rcls))
    for sx in (-1, 1):
        g = prism([(-Dy / 2, 0), (Dy / 2, 0), (0, rise)], t, axis='x', offset=sx * (Wx / 2 - t / 2), mat=wall_mat, cls=wcls)
        g.transform(Matrix.Translation((0, 0, z)))
        out.append(Part(f"Gable{tag}_{'W' if sx < 0 else 'E'}", [g], wcls))
    return out, rise


def _box_runs(cx, cy, Lx, Ly, t):
    """Muros perimetrales sin solapes: S/N cubren todo el largo, W/E van entre ellos."""
    x0, x1, y0, y1 = cx - Lx / 2, cx + Lx / 2, cy - Ly / 2, cy + Ly / 2
    return {"S": ((x0, y0 + t / 2), (x1, y0 + t / 2)), "N": ((x1, y1 - t / 2), (x0, y1 - t / 2)),
            "W": ((x0 + t / 2, y1 - t), (x0 + t / 2, y0 + t)), "E": ((x1 - t / 2, y0 + t), (x1 - t / 2, y1 - t))}


def _run_len(ab):
    return (V(ab[1]) - V(ab[0])).length


def build_church(name):
    """Iglesia de mamposteria revocada: nave 20 x 11 m (muros 0.6 m, 9 m) + campanario 4.6 m de lado, 24 m + aguja."""
    parts, t, unit = [], 0.6, (1.0, 0.5)
    Ln, Wn, Hn, z0 = 20.0, 11.0, 9.0, 0.2
    parts.append(Part("Floor", [box((Ln + 0.2, Wn + 0.2, z0), (0, 0, z0 / 2), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    for side, ab in _box_runs(0, 0, Ln, Wn, t).items():
        L = _run_len(ab)
        if side in "SN":
            ops = [(uc, 1.3, 3.2, 4.2) for uc in ((6.5, 10.5, 14.5, 18.0) if side == "S" else (2.0, 5.5, 9.5, 13.5))]
        elif side == "W":
            ops = [(L / 2, 2.0, 0.0, 3.6), (L / 2 - 2.8, 1.0, 3.6, 2.8), (L / 2 + 2.8, 1.0, 3.6, 2.8)]
        else:
            ops = [(L / 2 - 2.2, 1.2, 3.2, 4.0), (L / 2 + 2.2, 1.2, 3.2, 4.0)]
        parts.append(Part(f"Nave_Wall_{side}", wall_run(ab[0], ab[1], z0, Hn, t, ops, "Mat_Plaster_Wall", "brick", unit), "brick"))
        for k, (uc, w, sill, hh) in enumerate(ops):
            if sill > 0:
                parts.append(window_part(f"Win_{side}{k}", ab[0], ab[1], z0, t, uc, w, sill, hh))
            else:
                parts.append(door_part(f"Door_{side}_L", ab[0], ab[1], z0, uc - w / 4, w / 2, hh))
                parts.append(door_part(f"Door_{side}_R", ab[0], ab[1], z0, uc + w / 4, w / 2, hh))
    roof, rise = _gable(Ln, Wn, z0 + Hn, 40, t, "Mat_Plaster_Wall", "brick", ov=0.4)
    parts += roof
    # campanario adosado al muro sur, junto a la fachada
    S, lv, tx, ty = 4.6, 4.8, -Ln / 2 + 2.3, -Wn / 2 - 2.3
    for k in range(5):
        z = z0 + k * lv
        pcs = []
        for side, ab in _box_runs(tx, ty, S, S, t).items():
            L = _run_len(ab)
            if k == 0:
                ops = [(L / 2, 1.4, 0.0, 2.6)] if side == "W" else []
            elif k == 4:
                ops = [(L / 2, 1.5, 1.0, 2.8)]
            else:
                ops = [(L / 2, 0.5, 1.8, 1.4)] if side != "N" else []
            pcs += wall_run(ab[0], ab[1], z, lv, t, ops, "Mat_Plaster_Wall", "brick", unit)
            if k == 0 and side == "W":
                parts.append(door_part("Tower_Door", ab[0], ab[1], z, L / 2, 1.4, 2.6))
        parts.append(Part(f"Tower_L{k}", pcs, "brick"))
    zt = z0 + 5 * lv
    parts.append(Part("Belfry_Floor", [box((S - 2 * t, S - 2 * t, 0.2), (tx, ty, z0 + 4 * lv + 0.1), mat="Mat_Floor_Wood", cls="wood", grain="x")], "wood"))
    bell = lathe([(0, 1.0), (0.18, 0.98), (0.3, 0.8), (0.33, 0.4), (0.45, 0.05), (0.47, 0.0), (0.38, 0.0), (0.3, 0.35), (0.27, 0.75),
                  (0.15, 0.9), (0, 0.92)], (tx, ty, z0 + 4 * lv + 1.1), mat="Mat_Metal_Gunmetal", segs=16, cls="metal")
    yoke = box((0.25, S - 2 * t, 0.25), (tx, ty, z0 + 4 * lv + 2.25), mat="Mat_Wood_Beam", cls="wood", grain="y")
    parts.append(Part("Bell", [bell, yoke], "metal", kind="detail"))
    spire = [box((S + 0.3, S + 0.3, 0.35), (tx, ty, zt + 0.175), mat="Mat_Plaster_Wall", cls="brick"),
             hull([(tx - S / 2, ty - S / 2, zt + 0.35), (tx + S / 2, ty - S / 2, zt + 0.35), (tx + S / 2, ty + S / 2, zt + 0.35),
                   (tx - S / 2, ty + S / 2, zt + 0.35), (tx, ty, zt + 8.5)], mat="Mat_Roof_Metal", cls="metal"),
             box((0.12, 0.12, 1.6), (tx, ty, zt + 9.2), mat="Mat_Metal_Steel", cls="metal", frac=False),
             box((0.9, 0.12, 0.12), (tx, ty, zt + 9.5), mat="Mat_Metal_Steel", cls="metal", frac=False)]
    parts.append(Part("Spire", spire, "metal"))
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=2.2, ruin_h=0.3, spread=0.35, rubble_cell=4.0,
                 chunk_scale=0.9, debris="brick", lod=(1.0, 0.6),
                 ref="Iglesia rural de mamposteria revocada: nave 20 x 11 x 9 m, campanario 24 m + aguja 8.5 m")


def build_mosque(name):
    """Mezquita de barrio: sala de oracion 15 x 15 m (bloque revocado, 6.5 m), cupula de 8.4 m sobre tambor y alminar de 29 m."""
    parts, t, unit = [], 0.4, (0.4, 0.2)
    Ls, Hs, z0 = 15.0, 6.5, 0.2
    parts.append(Part("Floor", [box((Ls + 0.2, Ls + 0.2, z0), (0, 0, z0 / 2), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    for side, ab in _box_runs(0, 0, Ls, Ls, t).items():
        L = _run_len(ab)
        ops = [(L * f, 1.2, 1.4, 2.6) for f in (0.2, 0.5, 0.8)]
        if side == "S":
            ops = [(L * 0.2, 1.2, 1.4, 2.6), (L * 0.5, 2.0, 0.0, 3.0), (L * 0.8, 1.2, 1.4, 2.6)]
        parts.append(Part(f"Wall_{side}", wall_run(ab[0], ab[1], z0, Hs, t, ops, "Mat_Plaster_Desert", "cinder", unit), "cinder"))
        for k, (uc, w, sill, hh) in enumerate(ops):
            if sill > 0:
                parts.append(window_part(f"Win_{side}{k}", ab[0], ab[1], z0, t, uc, w, sill, hh))
            else:
                parts.append(door_part(f"Door_{side}_L", ab[0], ab[1], z0, uc - w / 4, w / 2, hh))
                parts.append(door_part(f"Door_{side}_R", ab[0], ab[1], z0, uc + w / 4, w / 2, hh))
    zr = z0 + Hs
    parts.append(Part("Roof_Slab", [box((Ls + 0.2, Ls + 0.2, 0.3), (0, 0, zr + 0.15), mat="Mat_Concrete_Base", cls="concrete")], "concrete"))
    par = [box((Ls + 0.2, 0.2, 0.6), (0, sy * (Ls / 2), zr + 0.6), mat="Mat_Plaster_Desert", cls="cinder") for sy in (-1, 1)]
    par += [box((0.2, Ls - 0.2, 0.6), (sx * (Ls / 2), 0, zr + 0.6), mat="Mat_Plaster_Desert", cls="cinder") for sx in (-1, 1)]
    parts.append(Part("Parapet", par, "cinder"))
    zd = zr + 0.3
    parts.append(Part("Dome_Drum", [lathe([(4.2, 0), (4.2, 1.4), (3.9, 1.4), (3.9, 0)], (0, 0, zd), mat="Mat_Plaster_Desert", segs=24,
                                          closed=True, smooth=False, cls="concrete")], "concrete"))
    prof = [(4.2 * math.cos(math.radians(a)), 4.2 * math.sin(math.radians(a))) for a in range(0, 90, 15)] + [(0, 4.2), (0, 3.95)]
    prof += [(3.95 * math.cos(math.radians(a)), 3.95 * math.sin(math.radians(a))) for a in range(75, -1, -15)]
    parts.append(Part("Dome", [lathe(prof, (0, 0, zd + 1.4), mat="Mat_Dome_Tile", segs=24, closed=True, cls="concrete")], "concrete"))
    mx, my = Ls / 2 + 1.5, -Ls / 2 + 1.3                     # alminar junto a la esquina SE
    lv = 5.5
    for k in range(4):
        parts.append(Part(f"Minaret_L{k}", [lathe([(1.3, 0), (1.3, lv), (0.95, lv), (0.95, 0)], (mx, my, k * lv), mat="Mat_Plaster_Desert",
                                                  segs=16, closed=True, smooth=False, cls="concrete")], "concrete"))
    zb_ = 4 * lv
    gal = [lathe([(2.0, 0), (2.0, 0.3), (0.95, 0.3), (0.95, 0)], (mx, my, zb_), mat="Mat_Plaster_Desert", segs=16, closed=True, smooth=False, cls="concrete"),
           lathe([(2.0, 0.3), (2.0, 1.1), (1.92, 1.1), (1.92, 0.3)], (mx, my, zb_), mat="Mat_Plaster_Desert", segs=16, closed=True, smooth=False, cls="concrete")]
    parts.append(Part("Minaret_Balcony", gal, "concrete"))
    top = [lathe([(0.9, 0), (0.9, 3.2), (0.7, 3.2), (0.7, 0)], (mx, my, zb_ + 0.3), mat="Mat_Plaster_Desert", segs=12, closed=True, smooth=False, cls="concrete"),
           lathe([(1.05, 0), (0, 3.0)], (mx, my, zb_ + 3.5), mat="Mat_Dome_Tile", segs=12, cls="concrete"),
           strut((mx, my, zb_ + 6.4), (mx, my, zb_ + 7.4), 0.04, "Mat_Metal_Steel", 6, cls="metal", frac=False),
           sphere(0.15, (mx, my, zb_ + 7.1), mat="Mat_Metal_Steel", segs=8, rings=5, cls="metal", frac=False)]
    parts.append(Part("Minaret_Top", top, "concrete"))
    parts.append(Part("Loudspeakers", [box((0.3, 0.25, 0.25), (mx + sx * 1.0, my + sy * 1.0, zb_ - 0.6), mat="Mat_Civil_White", cls="metal", frac=False)
                                       for sx in (-1, 1) for sy in (-1, 1)], "metal", kind="detail"))
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=2.0, ruin_h=0.3, spread=0.35, rubble_cell=4.0,
                 chunk_scale=0.9, debris="cinder", lod=(1.0, 0.6),
                 ref="Mezquita de barrio: sala 15 x 15 x 6.5 m, cupula 8.4 m sobre tambor, alminar 29 m con balcon a 22 m")


def build_factory(name):
    """Nave industrial de porticos de acero 30 x 18 m (alero 8 m, cumbrera 10 m), zocalo de ladrillo, chapa y vidrio."""
    Lx, Wy, He, Hr, bays, z0 = 30.0, 18.0, 8.0, 10.0, 5, 0.25
    bx = Lx / bays
    parts = [Part("Floor", [box((Lx + 0.4, Wy + 0.4, z0), (0, 0, z0 / 2), mat="Mat_Concrete_Base", cls="concrete")], "concrete")]
    th = math.degrees(math.atan2(Hr - He, Wy / 2))
    run = math.hypot(Wy / 2, Hr - He) + 0.35
    for k in range(bays + 1):
        x = -Lx / 2 + 0.2 + k * (Lx - 0.4) / bays
        fr = [box((0.3, 0.45, He), (x, sy * (Wy / 2 - 0.3), z0 + He / 2), mat="Mat_Steel_Galvanized", cls="metal") for sy in (-1, 1)]
        fr += [beam((x, sy * (Wy / 2 - 0.3), z0 + He + 0.2), (x, 0, z0 + Hr), 0.3, 0.55, mat="Mat_Steel_Galvanized", cls="metal", grain=None)
               for sy in (-1, 1)]
        parts.append(Part(f"Frame_{k}", fr, "metal"))
    for k in range(bays):
        xc = -Lx / 2 + bx * (k + 0.5)
        for sy, sd in ((-1, "S"), (1, "N")):
            parts.append(Part(f"Roof_{sd}{k}", [box((bx, run, 0.08), (xc, sy * Wy / 4, z0 + (He + Hr) / 2 + 0.42), (sy * -th, 0, 0),
                                                    mat="Mat_Roof_Metal", cls="metal")], "metal"))
            yw = sy * (Wy / 2)
            parts.append(Part(f"Base_{sd}{k}", [box((bx, 0.25, 1.2), (xc, yw, z0 + 0.6), mat="Mat_Brick_Wall", cls="brick")], "brick"))
            clad = [box((bx, 0.06, 4.3), (xc, yw + sy * 0.05, z0 + 1.2 + 2.15), mat="Mat_Roof_Metal", cls="metal"),
                    box((bx, 0.06, 1.0), (xc, yw + sy * 0.05, z0 + 7.0 + 0.5), mat="Mat_Roof_Metal", cls="metal")]
            parts.append(Part(f"Clad_{sd}{k}", clad, "metal"))
            parts.append(Part(f"Win_{sd}{k}", [box((bx - 0.1, 0.03, 1.5), (xc, yw + sy * 0.05, z0 + 5.5 + 0.75), mat="Mat_Glass_Window", cls="glass")],
                              "glass", kind="glass"))
    rz = lambda y: He + (Hr - He) * (1 - abs(y) / (Wy / 2))          # noqa: E731  (cota de cubierta en y)
    for sx, sd in ((-1, "W"), (1, "E")):
        xe = sx * (Lx / 2 + 0.05)
        if sx < 0:
            parts.append(Part("Base_W", [box((0.25, Wy, 1.2), (sx * Lx / 2, 0, z0 + 0.6), mat="Mat_Brick_Wall", cls="brick")], "brick"))
            g = prism([(-Wy / 2, 1.2), (Wy / 2, 1.2), (Wy / 2, He), (0, Hr), (-Wy / 2, He)], 0.06, axis='x', offset=xe, mat="Mat_Roof_Metal", cls="metal")
            g.transform(Matrix.Translation((0, 0, z0)))
            parts.append(Part("Clad_W", [g], "metal"))
        else:
            dw = 2.5
            for k, sy in enumerate((-1, 1)):
                parts.append(Part(f"Base_E{k}", [box((0.25, Wy / 2 - dw, 1.2), (sx * Lx / 2, sy * (Wy / 2 + dw) / 2, z0 + 0.6),
                                                     mat="Mat_Brick_Wall", cls="brick")], "brick"))
                prof = [(sy * dw, 1.2), (sy * Wy / 2, 1.2), (sy * Wy / 2, He), (sy * dw, rz(dw))]
                g = prism(prof if sy > 0 else prof[::-1], 0.06, axis='x', offset=xe, mat="Mat_Roof_Metal", cls="metal")
                g.transform(Matrix.Translation((0, 0, z0)))
                parts.append(Part(f"Clad_E{k}", [g], "metal"))
            g = prism([(-dw, 5.2), (dw, 5.2), (dw, rz(dw)), (0, Hr), (-dw, rz(dw))], 0.06, axis='x', offset=xe, mat="Mat_Roof_Metal", cls="metal")
            g.transform(Matrix.Translation((0, 0, z0)))
            parts.append(Part("Clad_E_Top", [g], "metal"))
            parts.append(Part("RollerDoor", [box((0.08, 2 * dw, 5.0), (Lx / 2 + 0.14, 0, z0 + 2.5), mat="Mat_Roof_Metal", cls="metal")], "metal",
                              kind="door", pivot=(Lx / 2, 0, z0 + 5.0), axis=(0, 0, 1), joint="slide"))
    crane = [box((Lx - 1.0, 0.3, 0.5), (0, sy * (Wy / 2 - 0.9), z0 + 6.3), mat="Mat_Military_Grey", cls="metal") for sy in (-1, 1)]
    crane.append(box((0.6, Wy - 1.6, 0.6), (4.0, 0, z0 + 6.85), mat="Mat_Bus_Paint", cls="metal"))
    parts.append(Part("Overhead_Crane", crane, "metal"))
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=2.5, ruin_h=0.25, spread=0.4, rubble_cell=5.0,
                 chunk_scale=0.9, debris="metal", lod=(1.0, 0.6),
                 ref="Nave industrial 30 x 18 m, porticos cada 6 m, alero 8 m, cumbrera 10 m, puerta enrollable 5 x 5 m")


def build_chimney(name):
    """Chimenea industrial de ladrillo 35 m (base 4.4 m): se parte y cae como un tronco."""
    prof = [(0, 0), (2.2, 0), (2.2, 3.0), (1.6, 3.2), (0.95, 35.0), (0.7, 35.0), (1.3, 3.2), (1.3, 0.4), (0, 0.4)]
    trunk = lathe(prof, mat="Mat_Brick_Wall", segs=20, smooth=False, cls="brick", grain="z")
    bands = [lathe([(r + 0.06, 0), (r + 0.06, 0.25), (r - 0.05, 0.25), (r - 0.05, 0)], (0, 0, z), mat="Mat_Metal_Gunmetal", segs=20, closed=True,
                   smooth=False, cls="metal", frac=False) for r, z in ((1.42, 12.0), (1.2, 22.0), (0.98, 34.0))]
    return Asset(name, "Buildings", "tree", [Part("Shaft", [trunk], "brick", kind="trunk"), Part("Bands", bands, "metal", kind="branch")],
                 cut_h=6.0, lod=(1.0, 0.5), ref="Chimenea industrial de ladrillo 35 m, fuste conico 3.2 -> 1.9 m")


def build_gas_station(name):
    """Gasolinera: marquesina 14 x 9 m a 5 m, 2 islas de surtidores, tienda 8 x 6 m y mastil de precios."""
    parts = [Part("Forecourt", [box((18.0, 22.0, 0.15), (0, 2.0, 0.075), mat="Mat_Concrete_Base", cls="concrete")], "concrete")]
    for i, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        parts.append(Part(f"Column_{i}", [box((0.4, 0.4, 5.0), (sx * 4.5, sy * 2.5, 0.15 + 2.5), mat="Mat_Civil_White", cls="concrete")], "concrete"))
    can = [box((14.0, 9.0, 0.25), (0, 0, 5.3), mat="Mat_Steel_Galvanized", cls="metal")]
    can += [box((14.2, 0.1, 0.8), (0, sy * 4.55, 5.4), mat="Mat_Civil_White", cls="metal") for sy in (-1, 1)]
    can += [box((0.1, 9.2, 0.8), (sx * 7.05, 0, 5.4), mat="Mat_Civil_White", cls="metal") for sx in (-1, 1)]
    can.append(box((10.0, 0.04, 0.3), (0, -4.62, 5.4), mat="Mat_Bus_Paint", cls="metal", frac=False))
    parts.append(Part("Canopy", can, "metal"))
    for k, x in enumerate((-2.0, 2.0)):
        isl = [box((1.0, 5.0, 0.18), (x, 0, 0.24), mat="Mat_Concrete_Base", cls="concrete")]
        for y in (-1.3, 1.3):
            isl += [box((0.55, 0.9, 1.75), (x, y, 0.33 + 0.875), mat="Mat_Civil_White", cls="metal"),
                    box((0.57, 0.92, 0.18), (x, y, 0.33 + 1.6), mat="Mat_Bus_Paint", cls="metal", frac=False),
                    box((0.02, 0.4, 0.3), (x + 0.29, y, 1.3), mat="Mat_Glass_Window", cls="glass", frac=False)]
        parts.append(Part(f"PumpIsland_{k}", isl, "metal"))
    shop = build_house(name, 8.0, 6.0, 1, fh=3.2, wall_mat="Mat_Plaster_Wall", wcls="cinder", roof="flat", parapet=True, nwin=(3, 1))
    parts += _move(shop, (0, 10.0, 0.15))
    sign = [box((0.35, 0.35, 8.0), (8.0, -6.0, 4.0), mat="Mat_Steel_Galvanized", cls="metal"),
            box((2.2, 0.3, 2.6), (8.0, -6.0, 7.2), mat="Mat_Bus_Paint", cls="metal")]
    parts.append(Part("PriceSign", sign, "metal"))
    return Asset(name, "Buildings", "structure", parts, n_impacts=3, dmg_r=2.0, ruin_h=0.3, spread=0.4, rubble_cell=4.0,
                 debris="cinder", lod=(1.0, 0.6), ref="Estacion de servicio: marquesina 14 x 9 m a 5 m, 4 surtidores, tienda 8 x 6 m")


def build_ruin_wall(name):
    """Muro de ladrillo ya en ruinas (9 m, hasta 4.5 m) con hueco de ventana y escombro al pie."""
    rng = random.Random(77)
    parts, h = [], 3.0
    x = -4.5
    while x < 4.49:
        w = min(0.6, 4.5 - x)
        h = max(0.6, min(4.5, h + rng.uniform(-0.9, 0.8)))
        hh = h if not (-0.9 < x + w / 2 < 0.9) else min(h, 1.0)     # hueco de ventana sin dintel
        parts.append(Part(f"Strip_{len(parts)}", [mbox((w, 0.36, hh), (x + w / 2, 0, hh / 2), mat="Mat_Brick_Wall", cls="brick",
                                                       unit=(0.25, 0.125), u0=x)], "brick"))
        x += w
    pile = [mound(V(rng.uniform(-3, 3), -0.9, 0.0), rng.uniform(0.8, 1.4), rng.uniform(0.35, 0.6), "Mat_Brick_Interior", rng, cls="brick")
            for _ in range(3)]
    pile += [box((0.25, 0.12, 0.08), (rng.uniform(-4, 4), rng.uniform(-1.6, -0.4), 0.04), (0, 0, rng.uniform(0, 180)),
                 mat="Mat_Brick_Wall", cls="brick", frac=False) for _ in range(20)]
    parts.append(Part("Rubble", pile, "brick", kind="detail"))
    return Asset(name, "Buildings", "structure", parts, n_impacts=2, dmg_r=1.2, ruin_h=0.3, spread=0.4, rubble_cell=2.0,
                 debris="brick", lod=(1.0, 0.6), ref="Muro de ladrillo macizo de 1 pie (0.36 m) parcialmente derruido")


def _rubble_pile(name, mat, cls, beams):
    rng = random.Random(len(name) * 31)
    pcs = [mound(V(0, 0, 0), 3.2, 1.3, mat, rng, cls=cls), mound(V(1.6, 0.8, 0), 1.8, 0.8, mat, rng, cls=cls)]
    for _ in range(26):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(0.3, 3.4)
        z = max(0.1, 1.2 * (1 - r / 3.6))
        if cls == "concrete":
            pcs.append(box((rng.uniform(0.4, 1.4), rng.uniform(0.3, 1.0), rng.uniform(0.15, 0.3)), (math.cos(a) * r, math.sin(a) * r, z),
                           (rng.uniform(-35, 35), rng.uniform(-35, 35), rng.uniform(0, 180)), mat="Mat_Concrete_Base", cls="concrete", frac=False))
        else:
            pcs.append(ico(rng.uniform(0.15, 0.35), (math.cos(a) * r, math.sin(a) * r, z), mat="Mat_Brick_Wall", subdiv=1, rough=0.2,
                           seed=rng.randint(0, 999), cls="brick", frac=False))
    for _ in range(beams):
        a = rng.uniform(0, 2 * math.pi)
        p0 = V(math.cos(a) * 2.8, math.sin(a) * 2.8, 0.05)
        p1 = V(math.cos(a + 2.4) * 0.8, math.sin(a + 2.4) * 0.8, rng.uniform(0.8, 1.6))
        if cls == "concrete":
            pcs.append(strut(p0, p1, 0.012, "Mat_Rebar_Rust", 4, cls="metal", frac=False))
        else:
            pcs.append(beam(p0, p1, 0.18, 0.18, mat="Mat_Wood_Charred", cls="wood", frac=False))
    return pcs


def build_rubble_concrete(name):
    return Asset(name, "Terrain", "static", [Part("Rubble", _rubble_pile(name, "Mat_Concrete_Interior", "concrete", 10), "concrete")],
                 lod=(1.0, 0.5), ref="Monton de escombro de hormigon armado ~7 m con armaduras retorcidas")


def build_rubble_brick(name):
    return Asset(name, "Terrain", "static", [Part("Rubble", _rubble_pile(name, "Mat_Brick_Interior", "brick", 5), "brick")],
                 lod=(1.0, 0.5), ref="Monton de cascote de ladrillo ~7 m con vigas de madera quemadas")


# ------------------------------- militar: campamento ----------------------------------
def build_checkpoint(name):
    """Control de carretera: garita 2.2 x 2.2 m, barrera de 6 m (bisagra), chicane de barreras Jersey, sacos y senal STOP."""
    parts = []
    gx, gy, t = -1.5, -6.0, 0.2
    for side, ab in _box_runs(gx, gy, 2.2, 2.2, t).items():
        L = _run_len(ab)
        ops = [(L / 2, 0.9, 0.0, 2.0)] if side == "W" else [(L / 2, 1.2, 1.0, 1.0)]
        parts.append(Part(f"Booth_Wall_{side}", wall_run(ab[0], ab[1], 0.0, 2.5, t, ops, "Mat_Plaster_Wall", "cinder"), "cinder"))
        for k, (uc, w, sill, hh) in enumerate(ops):
            if sill > 0:
                parts.append(window_part(f"Booth_Win_{side}", ab[0], ab[1], 0.0, t, uc, w, sill, hh))
    parts.append(Part("Booth_Roof", [box((3.0, 3.0, 0.15), (gx, gy, 2.575), mat="Mat_Roof_Metal", cls="metal")], "metal"))
    post = [box((0.4, 0.4, 1.0), (0, -3.8, 0.5), mat="Mat_Civil_White", cls="metal"),
            box((0.3, 0.6, 0.35), (0, -4.3, 1.0), mat="Mat_Metal_Gunmetal", cls="metal")]
    parts.append(Part("Barrier_Post", post, "metal"))
    boom = []
    for k in range(6):                                     # franjas rojas y blancas
        boom.append(box((0.1, 1.0, 0.1), (0, -3.3 + k * 1.0, 1.05), mat="Mat_Sign_Red" if k % 2 else "Mat_Road_Paint", cls="metal"))
    parts.append(Part("Barrier_Boom", boom, "metal", kind="door", pivot=(0, -3.8, 1.05), axis=(1, 0, 0), joint="hinge"))
    prof = [(-0.305, 0), (0.305, 0), (0.305, 0.075), (0.19, 0.33), (0.075, 0.81), (-0.075, 0.81), (-0.19, 0.33), (-0.305, 0.075)]
    for k, (x, y) in enumerate(((10.0, -2.0), (16.0, 2.0), (-10.0, 2.0), (-16.0, -2.0))):
        j = prism(prof, 3.0, axis='x', mat="Mat_Concrete_Base", cls="concrete")
        j.transform(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z'))
        parts.append(Part(f"Jersey_{k}", [j], "concrete"))
    for row in range(3):
        for i in range(6):
            bag = box((0.58, 0.3, 0.14), (2.0 + i * 0.6 + (row % 2) * 0.3 - 1.5, -8.0, 0.07 + row * 0.14), mat="Mat_Fabric_Sandbag", bevel=0.03, cls="fabric")
            parts.append(Part(f"Bag_{row}_{i}", [bag], "fabric"))
    stop = [strut((3.0, -4.6, 0), (3.0, -4.6, 2.2), 0.03, "Mat_Steel_Galvanized", 6, cls="metal"),
            cyl(0.38, 0.03, (3.0, -4.62, 2.5), (90, 22.5, 0), mat="Mat_Sign_Red", segs=8, cls="metal", frac=False)]
    parts.append(Part("Stop_Sign", stop, "metal", kind="detail"))
    lamp = [strut((-3.5, -4.8, 0), (-3.5, -4.8, 5.0), 0.06, "Mat_Steel_Galvanized", 6, cls="metal"),
            box((0.5, 0.35, 0.3), (-3.5, -4.6, 5.0), mat="Mat_Military_Grey", cls="metal"),
            box((0.45, 0.02, 0.25), (-3.5, -4.42, 5.0), mat="Mat_Light_Lens", cls="glass", frac=False)]
    parts.append(Part("Floodlight", lamp, "metal", kind="detail"))
    return Asset(name, "Military", "structure", parts, n_impacts=2, dmg_r=1.2, ruin_h=0.35, spread=0.45, rubble_cell=2.0,
                 debris="concrete", lod=(1.0, 0.6), ref="Puesto de control vial: garita, barrera basculante 6 m, chicane de 4 Jersey")


def build_tent_gp(name):
    """Tienda GP Medium (US): 4.88 x 9.75 m, cumbrera 3.05 m, paredes laterales 1.68 m, vientos y estacas."""
    Wt, Lt, Hr, He, t = 4.88, 9.75, 3.05, 1.68, 0.02
    C = "Mat_Tent_Canvas"
    th = math.degrees(math.atan2(Hr - He, Wt / 2))
    run = math.hypot(Wt / 2, Hr - He) + 0.12
    parts = []
    for sy, sd in ((-1, "S"), (1, "N")):
        zc = He + (Hr - He) / 2 + 0.03
        parts.append(Part(f"Roof_{sd}", [box((Lt + 0.25, run, t), (0, sy * Wt / 4, zc), (sy * -th, 0, 0), mat=C, cls="fabric")], "fabric"))
        parts.append(Part(f"Side_{sd}", [box((Lt, t, He), (0, sy * Wt / 2, He / 2), mat=C, cls="fabric")], "fabric"))
    for sx, sd in ((-1, "W"), (1, "E")):
        e = prism([(-Wt / 2, 0), (Wt / 2, 0), (Wt / 2, He), (0, Hr), (-Wt / 2, He)], t, axis='x', offset=sx * Lt / 2, mat=C, cls="fabric")
        parts.append(Part(f"End_{sd}", [e], "fabric"))
    poles = [cyl(0.045, Hr, (x, 0, Hr / 2), mat="Mat_Pole_Wood", segs=8, cls="wood", grain="z") for x in (-Lt / 4, Lt / 4)]
    poles.append(box((Lt - 0.2, 0.08, 0.08), (0, 0, Hr - 0.06), mat="Mat_Wood_Beam", cls="wood", grain="x"))
    parts.append(Part("Poles", poles, "wood"))
    guys = []
    for sy in (-1, 1):
        for k in range(7):
            x = -Lt / 2 + 0.4 + k * (Lt - 0.8) / 6
            guys.append(strut((x, sy * Wt / 2, He), (x, sy * (Wt / 2 + 1.7), 0.05), 0.008, "Mat_Fabric_Canvas", 3, cls="fabric", frac=False))
            guys.append(box((0.05, 0.05, 0.3), (x, sy * (Wt / 2 + 1.75), 0.1), mat="Mat_Metal_Gunmetal", cls="metal", frac=False))
    parts.append(Part("GuyLines", guys, "fabric", kind="detail"))
    cots = [box((1.9, 0.7, 0.05), (-Lt / 2 + 1.3 + k * 2.2, sy * 1.5, 0.45), mat="Mat_Fabric_Canvas", cls="fabric", frac=False)
            for k in range(4) for sy in (-1, 1)]
    parts.append(Part("Cots", cots, "fabric", kind="detail"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=1.4, ruin_h=0.15, spread=0.5, rubble_cell=2.0,
                 debris="fabric", lod=(1.0, 0.5), ref="Tent, General Purpose, Medium: 16 x 32 ft, cumbrera 10 ft, pared 5.5 ft")


def build_camo_net(name):
    """Red de enmascaramiento 10 x 8 m sobre 5 postes (central 4 m), bordes estaquillados."""
    rng = random.Random(4242)
    nx, ny, Lx, Ly = 21, 17, 10.0, 8.0
    poles = [(0.0, 0.0, 4.0), (3.5, 2.6, 3.2), (-3.5, 2.6, 3.2), (3.5, -2.6, 3.2), (-3.5, -2.6, 3.2)]
    bm = bmesh.new()
    vs = []
    for j in range(ny):
        row = []
        for i in range(nx):
            x, y = -Lx / 2 + Lx * i / (nx - 1), -Ly / 2 + Ly * j / (ny - 1)
            tent = max(ph - 0.42 * math.hypot(x - px, y - py) ** 1.15 for px, py, ph in poles)
            edge = min(Lx / 2 - abs(x), Ly / 2 - abs(y))
            z = max(0.05, min(tent, 0.15 + 1.6 * edge)) + rng.uniform(-0.06, 0.06)
            row.append(bm.verts.new((x, y, z)))
        vs.append(row)
    for j in range(ny - 1):
        for i in range(nx - 1):
            bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
    solidify(bm, 0.03)
    for f in bm.faces:                                     # la red se ve igual por las dos caras
        f.material_index = 0
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    net = Piece(bm, "Mat_Camo_Net", "fabric")
    parts = [Part("Net", [net], "fabric")]
    parts.append(Part("Poles", [cyl(0.04, ph - 0.03, (px, py, (ph - 0.03) / 2), mat="Mat_Pole_Wood", segs=6, cls="wood", grain="z")
                                for px, py, ph in poles], "wood"))
    return Asset(name, "Military", "structure", parts, n_impacts=1, dmg_r=1.6, ruin_h=0.15, spread=0.4, rubble_cell=2.5,
                 debris="fabric", lod=(1.0, 0.5), ref="Red de enmascaramiento LCSS 10 x 8 m sobre postes (cubre un vehiculo)")


def build_mortar_pit(name):
    """Asentamiento de mortero de 81 mm: pozo de 2.4 m y 1 m de fondo, anillo de sacos y M252 con municion."""
    parts = trench_path_parts([(-0.8, 0.0), (0.8, 0.0)], depth=1.0, w=2.4, lining="planks", berm=False)
    R = 2.0
    for row in range(3):
        n = 22
        for i in range(n):
            a = 2 * math.pi * (i + 0.5 * (row % 2)) / n
            p = V(math.cos(a) * R, math.sin(a) * R, 1.0 + 0.07 + row * 0.13)
            parts.append(Part(f"Bag_{row}_{i}", [box((0.58, 0.3, 0.14), tuple(p), (0, 0, math.degrees(a) + 90), mat="Mat_Fabric_Sandbag",
                                                     bevel=0.03, cls="fabric")], "fabric"))
    m = [cyl(0.28, 0.06, (0, 0, 0.03), mat="Mat_Metal_Gunmetal", segs=12, cls="metal"),
         strut((0, 0, 0.08), (0, 0.82, 1.05), 0.045, "Mat_Military_Olive", 10, cls="metal")]
    m += [strut((0, 0.5, 0.68), (sx * 0.3, 0.72, 0.02), 0.015, "Mat_Metal_Gunmetal", 4, cls="metal") for sx in (-1, 1)]
    parts.append(Part("Mortar_M252", m, "metal", kind="detail"))
    parts.append(Part("Ammo", [box((0.55, 0.3, 0.25), (-0.6 + k * 0.6, -0.7, 0.125), mat="Mat_Crate_Base", cls="wood", grain="x") for k in range(3)],
                      "wood", kind="detail"))
    return Asset(name, "Fortifications", "structure", parts, n_impacts=1, dmg_r=0.9, ruin_h=0.35, spread=0.5, rubble_cell=1.5,
                 debris="fabric", ground_offset=-1.0, holes=list(TRENCH_HOLES), lod=(1.0,), ref="Asentamiento de mortero M252 81 mm (FM 3-22.90)")


def build_radar_trailer(name):
    """Radar de vigilancia aerea sobre remolque (tipo AN/MPQ-64 Sentinel): antena 2.4 x 1.4 m giratoria."""
    P, wr = "Mat_Military_Green", 0.45
    parts = []
    for i, x in enumerate((-0.55, -1.55)):
        for side, sy in (("L", 1), ("R", -1)):
            parts.append(tire_wheel(x, sy * 0.95, wr, wr, 0.32, f"Wheel_{i}{side}", P))
    body = [box((4.6, 2.1, 0.9), (-0.4, 0, 1.0), mat=P, cls="metal"),
            box((1.1, 1.8, 0.9), (1.5, 0, 1.9), mat=P, cls="metal")]
    parts.append(Part("Trailer", body, "metal", kind="hull"))
    bar = [strut((1.85, sy * 0.8, 0.75), (3.3, 0, 0.55), 0.05, "Mat_Metal_Gunmetal", 6, cls="metal") for sy in (-1, 1)]
    bar += [strut((xx, sy * 1.2, 0.8), (xx, sy * 1.45, 0.0), 0.04, "Mat_Metal_Gunmetal", 4, cls="metal") for xx in (1.6, -2.5) for sy in (-1, 1)]
    parts.append(Part("Drawbar_Jacks", bar, "metal", kind="detail"))
    tur = [cyl(0.55, 0.3, (-0.8, 0, 1.6), mat=P, segs=14, cls="metal"), box((0.6, 0.6, 1.0), (-0.8, 0, 2.2), mat=P, cls="metal")]
    parts.append(Part("Antenna_Mount", tur, "metal", kind="turret", pivot=(-0.8, 0, 1.45), axis=(0, 0, 1), joint="yaw"))
    ant = [box((0.28, 2.4, 1.4), (-0.55, 0, 3.15), (0, -12, 0), mat=P, cls="metal"),
           box((0.05, 2.3, 1.3), (-0.39, 0, 3.17), (0, -12, 0), mat="Mat_Military_Grey", cls="metal", frac=False)]
    parts.append(Part("Antenna_Array", ant, "metal", kind="gun", tags=("turret",), pivot=(-0.8, 0, 2.7), axis=(0, 1, 0), joint="pitch"))
    return Asset(name, "AirDefense", "vehicle", parts, forward_x=True, mass=3800, lod=(1.0, 0.5, 0.2),
                 ref="Radar 3D de vigilancia sobre remolque de 2 ejes (clase AN/MPQ-64 Sentinel), antena a ~3.2 m")


def build_market_stall(name):
    """Puesto de mercado 3 x 2 m: estructura de madera, toldo de lona, mostrador y cajas."""
    posts = [beam((sx * 1.45, sy * 0.95, 0), (sx * 1.45, sy * 0.95, 2.4 if sy < 0 else 2.0), 0.08, mat="Mat_Wood_Beam", cls="wood")
             for sx in (-1, 1) for sy in (-1, 1)]
    parts = [Part("Frame", posts, "wood")]
    aw = math.degrees(math.atan2(0.4, 1.9))
    parts.append(Part("Awning", [box((3.3, 2.3, 0.02), (0, -0.05, 2.22), (aw, 0, 0), mat="Mat_Fabric_Canvas", cls="fabric")], "fabric"))
    parts.append(Part("Counter", [box((2.9, 0.8, 0.06), (0, -0.55, 0.9), mat="Mat_Wood_Plank", cls="wood", grain="x"),
                                  box((2.9, 0.04, 0.85), (0, -0.93, 0.45), mat="Mat_Wood_Plank", cls="wood", grain="x")], "wood"))
    crates = [box((0.5, 0.35, 0.3), (-1.0 + k * 0.55, -0.55, 1.08), mat="Mat_Crate_Base", cls="wood", grain="x") for k in range(4)]
    crates += [box((0.5, 0.35, 0.3), (-0.8 + k * 0.6, 0.5, 0.15 + 0.3 * (k % 2)), mat="Mat_Crate_Base", cls="wood", grain="x") for k in range(3)]
    parts.append(Part("Crates", crates, "wood", kind="detail"))
    return Asset(name, "Props", "structure", parts, n_impacts=1, dmg_r=0.6, ruin_h=0.3, spread=0.5, rubble_cell=1.0,
                 debris="wood", lod=(1.0, 0.5), ref="Puesto de zoco/mercado 3 x 2 m")


# ==================================================================================
# CATALOGO + MAIN
# ==================================================================================
def catalog():
    c = [("Mil_Crate_Ammo", build_crate), ("Mil_Barrel_200L", build_barrel), ("Mil_Sandbag_Wall", build_sandbags),
         ("Mil_Barrier_Jersey", build_jersey), ("Mil_Hedgehog_AT", build_hedgehog), ("Mil_Hesco_MIL1", build_hesco),
         ("Mil_Watchtower", build_watchtower), ("Mil_Bunker", build_bunker), ("Mil_Container_20ft", build_container)]
    c += [(n, build_tracked) for n in TRACKED] + [(n, build_wheeled) for n in WHEELED] + [(n, build_heli) for n in HELIS]
    c += [("Air_Jet_F-35A", build_f35), ("Air_UAV_MQ-9", build_mq9), ("Nav_Patrol_MarkVI", build_markvi),
          ("Art_Howitzer_M777", build_m777)]
    c += [("Bld_House_Small", build_house_small), ("Bld_House_TwoStory", build_house_two),
          ("Bld_Apartment_4F", build_apartment), ("Bld_Hangar_HAS", build_has)]
    c += [("Ter_Terrain_Tile32", build_terrain), ("Ter_Rock_Boulder", build_rock), ("Ter_Crater_Set", build_craters)]
    c += [("Veg_Tree_Pine", build_pine), ("Veg_Tree_Oak", build_oak), ("Veg_Tree_Palm", build_palm),
          ("Veg_Tree_Dead", build_dead_tree), ("Veg_Bush", build_bush), ("Veg_Grass_Clump", build_grass)]
    # --- v3: elementos de las referencias (Defilade): desierto, mamposteria, trincheras, vehiculos
    c += [("Mil_CinderBlock_Wall", build_cinder_wall), ("Mil_TWall_Bremer", build_twall), ("Mil_Dragons_Teeth", build_dragons_teeth),
          ("Mil_Concertina_Wire", build_concertina), ("Prop_Utility_Pole", build_utility_pole), ("Prop_Fence_Wood", build_fence)]
    c += [("Bld_Compound_Desert", build_compound), ("Bld_Desert_House_2F", build_desert_house), ("Bld_Barn_Wood", build_barn)]
    c += [("Fort_Trench_Straight", build_trench_straight), ("Fort_Trench_ZigZag", build_trench_zigzag), ("Fort_Foxhole_2Man", build_foxhole),
          ("Fort_MG_Nest", build_mg_nest), ("Fort_Dugout_Log", build_dugout), ("Fort_Vehicle_Revetment", build_revetment)]
    c += [("Veh_Technical_Hilux_DShK", build_pickup), ("Civ_Car_Sedan", build_sedan), ("Veh_ENG_D9R_Armored", build_d9r),
          ("AD_CRAM_Centurion", build_cram), ("Air_Heli_AH-6_LittleBird", build_littlebird), ("Air_Drone_Shahed-136", build_shahed),
          ("Air_Drone_Quadcopter", build_quad)]
    # --- v4: infraestructura de mapa, mas vehiculos/aeronaves y edificios de zona de guerra
    c += [("Map_Road_Asphalt_12m", build_road_asphalt), ("Map_Road_Intersection_14m", build_road_intersection),
          ("Map_Road_Dirt_12m", build_road_dirt), ("Map_Pylon_HV_30m", build_pylon), ("Map_Radio_Mast_40m", build_radio_mast),
          ("Map_Water_Tower", build_water_tower), ("Map_Fuel_Tank_16m", build_fuel_tank), ("Map_Bridge_Concrete_36m", build_bridge),
          ("Map_Helipad_20m", build_helipad), ("Map_Runway_Section_60m", build_runway), ("Prop_Street_Lamp", build_street_lamp),
          ("Prop_Billboard", build_billboard)]
    c += [(n, build_truck_x) for n in TRUCKS] + [("Air_UAV_Bayraktar_TB2", build_tb2)]
    c += [("Bld_Church_BellTower", build_church), ("Bld_Mosque_Minaret", build_mosque), ("Bld_Factory_Hall", build_factory),
          ("Bld_Chimney_Brick_35m", build_chimney), ("Bld_Gas_Station", build_gas_station), ("Bld_Ruin_Wall_Brick", build_ruin_wall),
          ("Ter_Rubble_Concrete", build_rubble_concrete), ("Ter_Rubble_Brick", build_rubble_brick),
          ("Mil_Checkpoint", build_checkpoint), ("Mil_Tent_GP_Medium", build_tent_gp), ("Mil_Camo_Net_10x8", build_camo_net),
          ("Fort_Mortar_Pit_81mm", build_mortar_pit), ("AD_Radar_Trailer", build_radar_trailer), ("Prop_Market_Stall", build_market_stall)]
    return c


VARIANT_SKIP = {"Winter": {"Veg_Tree_Palm"}, "Desert": set(), "Temperate": set()}


def main():
    """blender -b --python generate_destructible_assets.py -- [--out DIR] [--only A,B] [--variants Temperate,Desert]"""
    global VARIANT, OUTPUT_DIR, ONLY, VARIANTS
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for i, a in enumerate(argv[:-1]):
        if a == "--out":
            OUTPUT_DIR = os.path.abspath(os.path.expanduser(argv[i + 1]))
        elif a == "--only":
            ONLY = [x for x in argv[i + 1].split(",") if x]
        elif a == "--variants":
            VARIANTS = [x for x in argv[i + 1].split(",") if x]
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)          # escena inicial limpia
    reset_scene()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    index, fails = [], []
    for var in VARIANTS:                                       # Temperate / Desert / Winter
        VARIANT = var
        for nm, fn in catalog():
            if (ONLY and nm not in ONLY) or nm in VARIANT_SKIP.get(var, ()):
                continue
            try:
                asset = fn(nm)
                if var != "Temperate":
                    asset.name = "%s_%s" % (nm, var)
                info = process_asset(asset)
                info["variant"] = var
                index.append(info)
            except Exception as exc:                            # un asset roto no detiene el lote
                import traceback
                traceback.print_exc()
                fails.append({"asset": nm, "variant": var, "error": str(exc)})
    VARIANT = "Temperate"
    with open(os.path.join(OUTPUT_DIR, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"generator": "Unity Destructible Military Asset Factory v4", "seed": SEED,
                   "unity_import": {"scale_factor": 1, "convert_units": True, "read_write": "ON para *_Chunks_* (MeshCollider runtime)",
                                    "materials": "Search and Remap por nombre (Mat_*) -> materiales compartidos"},
                   "states": {"0": "Intact", "1": "Damaged", "2": "Destroyed", "3": "Chunks_L1", "4": "Chunks_L2",
                              "8": "LODs", "9": "Debris"},
                   "assets": index, "failed": fails}, fh, indent=1)
    reset_scene()
    print("\n=== %d assets en %.1fs -> %s  (fallidos: %d) ===" % (len(index), time.time() - t0, OUTPUT_DIR, len(fails)))


if __name__ == "__main__":
    main()
