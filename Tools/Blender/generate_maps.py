"""
=====================================================================================
 GENERADOR DE MAPAS DE GUERRA REALISTAS PARA UNITY (relieve + capas + distribucion)
=====================================================================================
Crea mapas jugables a escala real con los assets destructibles del catalogo
(generate_destructible_assets.py y adapt_free_assets.py):

  relieve      ruido fractal + erosion hidraulica (red de drenaje: valles y crestas) +
               erosion termica, o un DEM REAL (USGS, Monte St. Helens a 30 m)
  red vial     carreteras asfaltadas y caminos de tierra explanados en el terreno,
               rio con puente, uadi seco, crateres de artilleria
  capas        splatmap de 4 capas (hierba/arena/nieve, tierra/barro, roca, asfalto)
               segun pendiente, altura, humedad y mascaras de carretera/campo/crater
  objetos      pueblos y barrios a lo largo de las calles, iglesia/mezquita, zoco,
               gasolinera, bosques, tendidos electricos, lineas de trincheras con
               pozos y nidos, campamentos con HESCO, puestos de control, base aerea,
               pecios (estado Destroyed) y edificios danados. Las huellas salen de los
               manifiestos .json (bounds reales) y el terreno se explana bajo cada una.
  agujeros     trincheras/pozos/refugios recortan el Terrain (terrain_holes del .json)

 Salida (Maps/<Mapa>/):
   <Mapa>_height.raw   16 bit little-endian, res x res, fila 0 = sur (z = 0)
   <Mapa>_height.png   el mismo relieve en PNG 16 bit (norte arriba)
   <Mapa>_splat.raw    RGBA 8 bit, (res-1)^2, fila 0 = sur  (+ _splat.png, norte arriba)
   <Mapa>_holes.raw    1 byte por celda (1 = suelo, 0 = agujero), (res-1)^2, fila 0 = sur
   <Mapa>.json         terreno, capas, objetos {asset, fbx, variante, pos, yaw, estado},
                       agua, sol, cielo HDRI y puntos de despliegue
   <Mapa>_preview.png  mapa tactico (sombreado + capas + objetos)
 En Unity: Tools > War Maps > Build Map From JSON (WarMapBuilder.cs).

 Uso:  python generate_maps.py [--assets ~/Unity_Destructible_Military] [--out <assets>/Maps]
                               [--only desert,urban] [--dem ThirdParty/direct/dem_mount_st_helens/SainteHelens.dem]
 Python 3.8+ con numpy (tambien el Python de Blender).
=====================================================================================
"""
import argparse
import heapq
import json
import math
import os
import random
import struct
import sys
import time
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LAYER_TILE = {"Mat_Terrain_Grass": 4.0, "Mat_Terrain_Soil": 4.0, "Mat_Terrain_Sand": 5.0, "Mat_Terrain_Snow": 5.0,
              "Mat_Rock_Base": 6.0, "Mat_Asphalt": 3.0}
LAYER_RGB = {"Mat_Terrain_Grass": (0.33, 0.42, 0.19), "Mat_Terrain_Soil": (0.43, 0.34, 0.24), "Mat_Terrain_Sand": (0.78, 0.68, 0.48),
             "Mat_Terrain_Snow": (0.93, 0.95, 0.98), "Mat_Rock_Base": (0.47, 0.45, 0.42), "Mat_Asphalt": (0.17, 0.17, 0.17)}
CAT_RGB = {"Buildings": (0.72, 0.24, 0.16), "Military": (0.86, 0.76, 0.18), "Fortifications": (0.98, 0.52, 0.08),
           "Vehicles": (0.12, 0.32, 0.88), "Artillery": (0.10, 0.25, 0.70), "AirDefense": (0.62, 0.18, 0.82),
           "Aircraft": (0.15, 0.72, 0.92), "Civilian": (0.35, 0.60, 0.98), "Vegetation": (0.05, 0.24, 0.06),
           "Map": (0.62, 0.62, 0.66), "Props": (0.85, 0.55, 0.55), "Terrain": (0.52, 0.46, 0.40), "Naval": (0.1, 0.2, 0.5)}
FLAT_CATS = {"Buildings", "Military", "Fortifications", "Map", "Props", "AirDefense"}
TILT_CATS = {"Vehicles", "Artillery", "Civilian", "Aircraft"}
OFFS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
ODST = [math.sqrt(2), 1.0, math.sqrt(2), 1.0, 1.0, math.sqrt(2), 1.0, math.sqrt(2)]


# ---------------------------------------------------------------------------------- IO
def write_png(path, a):
    """PNG sin dependencias: gris 8/16 bit (HxW) o RGB/RGBA 8 bit (HxWx3/4). Fila 0 = arriba."""
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    if a.ndim == 2:
        ct, bd = 0, (16 if a.dtype == np.uint16 else 8)
        if bd == 16:
            a = a.astype(">u2")
    else:
        ct, bd = (2 if a.shape[2] == 3 else 6), 8
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, bd, ct, 0, 0, 0)) +
                 chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def moving_average(v, w):
    if w <= 1 or len(v) < 3:
        return np.asarray(v, float)
    k = np.ones(w)
    num = np.convolve(np.pad(v, w, mode="edge"), k, mode="same")[w:-w]
    return num / w


def resize(a, n):
    """Remuestreo bicubico (Catmull-Rom) de una malla a n x n."""
    def axis(m):
        x = np.linspace(0, m - 1, n)
        i = np.floor(x).astype(int)
        t = x - i
        idx = np.stack([i - 1, i, i + 1, i + 2], 1).clip(0, m - 1)
        w = np.stack([(-t ** 3 + 2 * t ** 2 - t) / 2, (3 * t ** 3 - 5 * t ** 2 + 2) / 2,
                      (-3 * t ** 3 + 4 * t ** 2 + t) / 2, (t ** 3 - t ** 2) / 2], 1)
        return idx, w
    ri, rw = axis(a.shape[0])
    ci, cw = axis(a.shape[1])
    tmp = (a[ri] * rw[:, :, None]).sum(1)
    return (tmp[:, ci] * cw[None, :, :]).sum(2)


# ------------------------------------------------------------------------------- ruido
def value_noise(n, cells, rng):
    cells = max(1, int(cells))
    g = rng.random((cells + 1, cells + 1))
    g[-1, :] = g[0, :]
    g[:, -1] = g[:, 0]
    t = np.linspace(0, cells, n, endpoint=False)
    i = np.floor(t).astype(int)
    f = t - i
    f = f * f * f * (f * (f * 6 - 15) + 10)
    fx, fy = f[None, :], f[:, None]
    a, b = g[np.ix_(i, i)], g[np.ix_(i, i + 1)]
    c, d = g[np.ix_(i + 1, i)], g[np.ix_(i + 1, i + 1)]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(n, rng, base=4, octaves=8, gain=0.5, lac=2.0):
    """Ruido fractal en [-1, 1]."""
    h, amp, cells, tot = np.zeros((n, n)), 1.0, float(base), 0.0
    for _ in range(octaves):
        if cells > n / 2:
            break
        h += amp * (value_noise(n, cells, rng) * 2 - 1)
        tot += amp
        amp *= gain
        cells *= lac
    return h / max(tot, 1e-9)


def ridged(n, rng, base=3, octaves=7, gain=0.5):
    """Ruido de crestas en [0, 1] (cordilleras)."""
    h, amp, cells, tot, wgt = np.zeros((n, n)), 1.0, float(base), 0.0, np.ones((n, n))
    for _ in range(octaves):
        if cells > n / 2:
            break
        r = (1 - np.abs(value_noise(n, cells, rng) * 2 - 1)) ** 2
        r *= wgt
        wgt = np.clip(r * 1.5, 0, 1)
        h += amp * r
        tot += amp
        amp *= gain
        cells *= 2
    return h / max(tot, 1e-9)


def warp(F, rng, amp, base=4):
    """Deformacion de dominio: muestrea F en coordenadas desplazadas por ruido (relieve menos 'geometrico')."""
    n = F.shape[0]
    I, J = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float), indexing="ij")
    y = np.clip(I + amp * fbm(n, rng, base=base), 0, n - 1.001)
    x = np.clip(J + amp * fbm(n, rng, base=base), 0, n - 1.001)
    i0, j0 = y.astype(int), x.astype(int)
    ty, tx = y - i0, x - j0
    return (F[i0, j0] * (1 - tx) + F[i0, j0 + 1] * tx) * (1 - ty) + (F[i0 + 1, j0] * (1 - tx) + F[i0 + 1, j0 + 1] * tx) * ty


def hills(n, rng, base=4):
    """Colinas en [0, 1] con crestas suaves (fbm deformado y elevado al cuadrado)."""
    f = warp(0.5 + 0.5 * fbm(n, rng, base=base), rng, n / 10.0, base=3)
    return np.clip(f, 0, 1) ** 2


# ----------------------------------------------------------------------------- erosion
def d8(h):
    n0, n1 = h.shape
    pad = np.pad(h, 1, mode="edge")
    best = np.zeros_like(h)
    idx = np.full(h.shape, -1, dtype=np.int64)
    for k, (dy, dx) in enumerate(OFFS):
        s = (h - pad[1 + dy:1 + dy + n0, 1 + dx:1 + dx + n1]) / ODST[k]
        m = s > best
        best[m] = s[m]
        idx[m] = k
    return idx, best


def flow_acc(h, idx):
    """Acumulacion de flujo D8 (celdas drenadas)."""
    n0, n1 = h.shape
    N = n0 * n1
    r, c = np.divmod(np.arange(N), n1)
    off = np.array(OFFS)
    k = idx.ravel()
    tr = r + off[np.maximum(k, 0), 0]
    tc = c + off[np.maximum(k, 0), 1]
    ok = (k >= 0) & (tr >= 0) & (tr < n0) & (tc >= 0) & (tc < n1)
    tgt = np.where(ok, tr * n1 + tc, -1).tolist()
    acc = [1.0] * N
    for i in np.argsort(-h.ravel(), kind="stable").tolist():
        t = tgt[i]
        if t >= 0:
            acc[t] += acc[i]
    return np.array(acc).reshape(n0, n1)


def thermal(h, cell, talus_deg=34.0, iters=3, rate=0.5):
    """Desprendimientos: el material por encima del angulo de reposo cae a los vecinos."""
    t = math.tan(math.radians(talus_deg)) * cell
    n0, n1 = h.shape
    for _ in range(iters):
        pad = np.pad(h, 1, mode="edge")
        out, inn = np.zeros_like(h), np.zeros_like(h)
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            d = h - pad[1 + dy:1 + dy + n0, 1 + dx:1 + dx + n1] - t
            f = np.where(d > 0, d * rate * 0.25, 0.0)
            out += f
            fp = np.pad(f, 1)
            inn += fp[1 - dy:1 - dy + n0, 1 - dx:1 - dx + n1]
        h = h - out + inn
    return h


def erode(h, cell, iters=10, k=0.03, m=0.45, talus=33.0):
    """Erosion fluvial (ley de potencia de corriente) + termica: valles, barrancos y conos."""
    for _ in range(iters):
        idx, s = d8(h)
        A = flow_acc(h, idx)
        h = h - np.minimum(k * (A ** m) * s, 0.45 * s)
        h = thermal(h, cell, talus, iters=2)
    return h


# ------------------------------------------------------------------------- polilineas
def densify(pts, step):
    P = np.asarray(pts, float)
    out = [P[0]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(1, int(np.linalg.norm(b - a) / step))
        out += [a + (b - a) * (k / n) for k in range(1, n + 1)]
    return np.array(out)


def catmull(pts, step):
    """Polilinea suavizada (Catmull-Rom) muestreada cada ~step m."""
    P = [np.asarray(p, float) for p in pts]
    if len(P) < 3:
        return densify(pts, step)
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(1, int(np.linalg.norm(p2 - p1) / step))
        for k in range(n):
            t = k / n
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return np.array(out)


def path_dirs(P):
    d = np.gradient(P, axis=0)
    return d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)


def yaw_facing(dx, dz):
    """Yaw de Unity (grados) para que el +Z local mire hacia (dx, dz)."""
    return math.degrees(math.atan2(dx, dz))


def yaw_along_x(dx, dz):
    """Yaw para que el +X local (largo de trincheras, puentes, pistas) siga (dx, dz)."""
    return math.degrees(math.atan2(-dz, dx))


def rot(lx, lz, yaw):
    th = math.radians(yaw)
    c, s = math.cos(th), math.sin(th)
    return lx * c + lz * s, -lx * s + lz * c


# ----------------------------------------------------------------------------- catalogo
class Catalog:
    """catalog.json + third_party_adapted.json -> huellas reales de cada asset/variante."""

    def __init__(self, root):
        self.root, self.rows, self.cache = root, {}, {}
        cp = os.path.join(root, "catalog.json")
        if not os.path.exists(cp):
            raise SystemExit("No existe %s: ejecuta antes generate_destructible_assets.py" % cp)
        rows = json.load(open(cp, encoding="utf-8"))["assets"]
        tp = os.path.join(root, "third_party_adapted.json")
        if os.path.exists(tp):
            rows += json.load(open(tp, encoding="utf-8")).get("assets", [])
        for a in rows:
            var = a.get("variant", "Temperate")
            base = a["asset"]
            if var != "Temperate" and base.endswith("_" + var):
                base = base[:-len(var) - 1]
            if a.get("fbx") and a.get("manifest"):
                self.rows[(base, var)] = a
        self.bases = sorted({b for b, _v in self.rows})

    def resolve(self, name):
        if name in self.bases:
            return name
        return next((b for b in self.bases if b.startswith(name)), None)

    def get(self, base, var):
        base = self.resolve(base)
        if base is None:
            return None
        a = self.rows.get((base, var)) or self.rows.get((base, "Temperate"))
        if a is None:
            return None
        key = a["manifest"]
        if key not in self.cache:
            man = json.load(open(os.path.join(self.root, a["manifest"]), encoding="utf-8"))
            (x0, y0, z0), (x1, y1, z1) = man["bounds_unity"]
            self.cache[key] = dict(base=base, name=a["asset"], fbx=a["fbx"], variant=a.get("variant", "Temperate"),
                                   size=(abs(x1 - x0), abs(z1 - z0)), center=((x0 + x1) / 2, (z0 + z1) / 2), height=abs(y1 - y0),
                                   ground_offset=man.get("ground_offset", 0.0), holes=man.get("terrain_holes", []),
                                   category=man.get("category", "Misc"), mode=man.get("mode", "static"))
        return self.cache[key]


# ---------------------------------------------------------------------------------- DEM
def read_usgs_dem(path):
    """DEM ASCII del USGS (registro A + perfiles B) -> (alturas [sur->norte, oeste->este], paso_m, origen UTM)."""
    import re
    txt = open(path, "rb").read().decode("ascii", "replace")
    A = txt[:1024]
    m = re.search(r"(\d\.\d{6}E[+-]\d\d)(\d\.\d{6}E[+-]\d\d)(\d\.\d{6}E[+-]\d\d)\s+1\s+(\d+)", A)
    if not m:
        raise ValueError("cabecera DEM no reconocida")
    dx, dy, dz, ncols = float(m.group(1)), float(m.group(2)), float(m.group(3)), int(m.group(4))
    tok = txt[1024:].replace("D", "E").split()
    i, prof = 0, []
    for _ in range(ncols):
        mr = int(tok[i + 2])
        x0, y0, zdat = float(tok[i + 4]), float(tok[i + 5]), float(tok[i + 6])
        z = np.array(tok[i + 9:i + 9 + mr], dtype=float) * dz + zdat
        prof.append((x0, y0, z))
        i += 9 + mr
    ymin = min(p[1] for p in prof)
    ymax = max(p[1] + (len(p[2]) - 1) * dy for p in prof)
    rows = int(round((ymax - ymin) / dy)) + 1
    grid = np.full((rows, len(prof)), np.nan)
    for j, (x0, y0, z) in enumerate(prof):
        r0 = int(round((y0 - ymin) / dy))
        grid[r0:r0 + len(z), j] = z
    grid[grid < -1000] = np.nan
    return grid, dx, (prof[0][0], ymin)


# -------------------------------------------------------------------------------- mapa
class WarMap:
    def __init__(self, cat, name, size, res, variant, layers, seed, desc, sky="lebombo", sun=(50.0, 130.0)):
        self.cat, self.name, self.size, self.res, self.variant = cat, name, float(size), res, variant
        self.layers, self.desc, self.sky, self.sun = layers, desc, sky, sun
        self.cell = self.size / (res - 1)
        self.xs = np.arange(res) * self.cell
        self.h = np.zeros((res, res))
        self.rng = np.random.default_rng(seed)
        self.rr = random.Random(seed)
        z = np.zeros((res, res))
        self.m_dirt, self.m_asphalt, self.m_rock, self.m_wet = z.copy(), z.copy(), z.copy(), z.copy()
        self.road_edge = np.full((res, res), np.inf)            # distancia al borde de calzada (m)
        self.water_d = np.full((res, res), np.inf)
        self.objects, self.rects, self.grid = [], [], {}
        self.roads, self.water, self.spawns, self.missing = [], [], [], set()

    # ------------------------------------------------------------ muestreo
    def height(self, x, z):
        fx, fz = np.clip(x / self.cell, 0, self.res - 1.001), np.clip(z / self.cell, 0, self.res - 1.001)
        j, i = int(fx), int(fz)
        tx, tz = fx - j, fz - i
        h = self.h
        return float((h[i, j] * (1 - tx) + h[i, j + 1] * tx) * (1 - tz) + (h[i + 1, j] * (1 - tx) + h[i + 1, j + 1] * tx) * tz)

    def at(self, arr, x, z):
        i = int(np.clip(round(z / self.cell), 0, self.res - 1))
        j = int(np.clip(round(x / self.cell), 0, self.res - 1))
        return float(arr[i, j])

    def slope_deg(self):
        gz, gx = np.gradient(self.h, self.cell)
        return np.degrees(np.arctan(np.hypot(gx, gz)))

    def normal(self, x, z):
        e = self.cell
        gx = (self.height(x + e, z) - self.height(x - e, z)) / (2 * e)
        gz = (self.height(x, z + e) - self.height(x, z - e)) / (2 * e)
        n = np.array([-gx, 1.0, -gz])
        return (n / np.linalg.norm(n)).round(4).tolist()

    def window(self, x0, x1, z0, z1):
        j0, j1 = int(max(0, math.floor(x0 / self.cell))), int(min(self.res, math.ceil(x1 / self.cell) + 1))
        i0, i1 = int(max(0, math.floor(z0 / self.cell))), int(min(self.res, math.ceil(z1 / self.cell) + 1))
        return i0, i1, j0, j1

    def polyline_field(self, P, vals, maxd):
        """Distancia a la polilinea (inf mas alla de maxd) y valor interpolado en el punto mas cercano."""
        dist = np.full((self.res, self.res), np.inf)
        val = np.zeros((self.res, self.res))
        for a, b, va, vb in zip(P[:-1], P[1:], vals[:-1], vals[1:]):
            i0, i1, j0, j1 = self.window(min(a[0], b[0]) - maxd, max(a[0], b[0]) + maxd,
                                         min(a[1], b[1]) - maxd, max(a[1], b[1]) + maxd)
            if i0 >= i1 or j0 >= j1:
                continue
            X, Z = self.xs[j0:j1][None, :], self.xs[i0:i1][:, None]
            d = b - a
            t = np.clip(((X - a[0]) * d[0] + (Z - a[1]) * d[1]) / max(float(d @ d), 1e-9), 0, 1)
            dd = np.hypot(X - (a[0] + t * d[0]), Z - (a[1] + t * d[1]))
            sub, sv = dist[i0:i1, j0:j1], val[i0:i1, j0:j1]
            m = (dd < sub) & (dd <= maxd)
            sub[m] = dd[m]
            sv[m] = (va + t * (vb - va))[m]
        return dist, val

    # ------------------------------------------------------------ terreno
    def road(self, pts, width, kind="asphalt", curve=True, blend=8.0, smooth_m=70.0, grade=True, profile=None):
        P = catmull(pts, 3.0) if curve else densify(pts, 3.0)
        hs = np.array([self.height(x, z) for x, z in P]) if profile is None else np.asarray(profile, float)
        hs = moving_average(hs, max(1, int(smooth_m / 3.0)))
        half = width / 2
        dist, rh = self.polyline_field(P, hs, half + 1.0 + blend)
        dry = smooth(0.0, 4.0, self.water_d)                              # el rio no se rellena: lo salva un puente
        if grade:
            w = (1 - smooth(half + 0.8, half + 0.8 + blend, dist)) * dry
            self.h = self.h * (1 - w) + np.where(np.isfinite(dist), rh, 0) * w
        core = (1 - smooth(half - 0.5, half + 0.5, dist)) * dry
        if kind == "asphalt":
            self.m_asphalt = np.maximum(self.m_asphalt, core)
            self.m_dirt = np.maximum(self.m_dirt, (1 - smooth(half + 0.3, half + 2.2, dist)) * 0.8)
        else:
            self.m_dirt = np.maximum(self.m_dirt, core)
        self.road_edge = np.minimum(self.road_edge, dist - half)
        self.roads.append({"kind": kind, "width": width, "points": P})
        return P

    def river(self, pts, width, depth, water=True, bank=0.3, band=70.0, follow_valley=True):
        """Cauce: sigue el fondo del valle entre los puntos guia (camino de menor coste por
        altura), fluye hacia el extremo mas bajo y funde las orillas con el terreno."""
        if follow_valley:
            path = []
            for a, b in zip(pts[:-1], pts[1:]):
                seg = self.least_cost_path(a, b, n=128, slope_w=5.0, low_w=40.0)
                path += seg if not path else seg[1:]
            pts = path
        if self.height(*pts[0]) < self.height(*pts[-1]):
            pts = pts[::-1]                                                # aguas abajo = extremo mas bajo
        P = catmull(pts, 4.0)
        hs = moving_average(np.array([self.height(x, z) for x, z in P]), 15)
        bed = moving_average(np.minimum.accumulate(hs) - depth, 9)
        half = width / 2
        dist, bz = self.polyline_field(P, bed, half + band)
        carve = np.where(dist <= half, bz + depth * 1.05 * np.clip(dist / half, 0, 1) ** 2, bz + depth * 1.05 + (dist - half) * bank)
        w = 1 - smooth(half + band * 0.55, half + band, dist)               # sin paredes: transicion suave
        self.h = np.where(np.isfinite(dist), self.h * (1 - w) + np.minimum(self.h, carve) * w, self.h)
        self.m_wet = np.maximum(self.m_wet, 1 - smooth(half, half + 6, dist))
        self.m_dirt = np.maximum(self.m_dirt, (1 - smooth(half * 0.6, half + 3, dist)) * (0.9 if water else 1.0))
        if water:
            self.water_d = np.minimum(self.water_d, dist - half * 0.85)
            lvl = bed + depth * 0.72
            self.water.append({"type": "river", "width": round(width * 0.97, 2),               # plano (JsonUtility)
                               "points_xyz": [round(float(v), 2) for (x, z), y in zip(P, lvl) for v in (x, y, z)]})
        return P

    def crater(self, x, z, r, depth):
        i0, i1, j0, j1 = self.window(x - r * 2, x + r * 2, z - r * 2, z + r * 2)
        if i0 >= i1 or j0 >= j1:
            return
        X, Z = self.xs[j0:j1][None, :], self.xs[i0:i1][:, None]
        d = np.hypot(X - x, Z - z) / r
        self.h[i0:i1, j0:j1] += np.where(d < 1, -depth * (1 - d * d), 0) + 0.3 * depth * np.exp(-((d - 1.0) / 0.25) ** 2)
        self.m_dirt[i0:i1, j0:j1] = np.maximum(self.m_dirt[i0:i1, j0:j1], 1 - smooth(0.9, 1.7, d))

    def craters(self, n, region, rmin=1.5, rmax=5.0):
        for _ in range(n):
            x, z = self.rr.uniform(region[0], region[2]), self.rr.uniform(region[1], region[3])
            r = self.rr.uniform(rmin, rmax) * (2.2 if self.rr.random() < 0.08 else 1.0)
            self.crater(x, z, r, r * self.rr.uniform(0.25, 0.4))

    def field(self, cx, cz, w, l, yaw, strength=0.7):
        R = math.hypot(w, l)
        i0, i1, j0, j1 = self.window(cx - R, cx + R, cz - R, cz + R)
        X, Z = self.xs[j0:j1][None, :] - cx, self.xs[i0:i1][:, None] - cz
        th = math.radians(yaw)
        u = X * math.cos(th) - Z * math.sin(th)
        v = X * math.sin(th) + Z * math.cos(th)
        inside = (1 - smooth(w / 2 - 2, w / 2, np.abs(u))) * (1 - smooth(l / 2 - 2, l / 2, np.abs(v)))
        stripes = 0.5 + 0.5 * np.sin(2 * math.pi * v / 2.8)
        self.m_dirt[i0:i1, j0:j1] = np.maximum(self.m_dirt[i0:i1, j0:j1], inside * (0.35 + 0.45 * stripes) * strength)

    def flatten_rect(self, cx, cz, hx, hz, yaw, margin=0.8, blend=5.0, target=None):
        R = math.hypot(hx, hz) + margin + blend + self.cell
        i0, i1, j0, j1 = self.window(cx - R, cx + R, cz - R, cz + R)
        if i0 >= i1 or j0 >= j1:
            return
        X, Z = self.xs[j0:j1][None, :] - cx, self.xs[i0:i1][:, None] - cz
        th = math.radians(yaw)
        u = X * math.cos(th) - Z * math.sin(th)
        v = X * math.sin(th) + Z * math.cos(th)
        dout = np.hypot(np.maximum(np.abs(u) - hx - margin, 0), np.maximum(np.abs(v) - hz - margin, 0))
        sub = self.h[i0:i1, j0:j1]
        inside = dout <= 0
        if target is None:
            target = float(np.median(sub[inside])) if inside.any() else self.height(cx, cz)
        w = 1 - smooth(0.0, blend, dout)
        self.h[i0:i1, j0:j1] = sub * (1 - w) + target * w

    # ------------------------------------------------------------ objetos
    def _rect(self, info, x, z, yaw, pad):
        lx, lz = info["center"]
        ox, oz = rot(lx, lz, yaw)
        return (x + ox, z + oz, info["size"][0] / 2 + pad, info["size"][1] / 2 + pad, yaw)

    @staticmethod
    def _corners(r):
        cx, cz, hx, hz, yaw = r
        return [(cx + a, cz + b) for a, b in (rot(sx * hx, sz * hz, yaw) for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)))]

    @staticmethod
    def _overlap(A, B):
        ca, cb = WarMap._corners(A), WarMap._corners(B)
        for r in (A, B):
            for ax in (rot(1, 0, r[4]), rot(0, 1, r[4])):
                pa = [p[0] * ax[0] + p[1] * ax[1] for p in ca]
                pb = [p[0] * ax[0] + p[1] * ax[1] for p in cb]
                if max(pa) < min(pb) or max(pb) < min(pa):
                    return False
        return True

    def collides(self, r):
        R = math.hypot(r[2], r[3])
        k0, k1 = int((r[0] - R) // 32), int((r[0] + R) // 32)
        l0, l1 = int((r[1] - R) // 32), int((r[1] + R) // 32)
        seen = set()
        for k in range(k0, k1 + 1):
            for l in range(l0, l1 + 1):
                for idx in self.grid.get((k, l), ()):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    o = self.rects[idx]
                    if math.hypot(o[0] - r[0], o[1] - r[1]) < R + math.hypot(o[2], o[3]) and self._overlap(o, r):
                        return True
        return False

    def _add_rect(self, r):
        idx = len(self.rects)
        self.rects.append(r)
        R = math.hypot(r[2], r[3])
        for k in range(int((r[0] - R) // 32), int((r[0] + R) // 32) + 1):
            for l in range(int((r[1] - R) // 32), int((r[1] + R) // 32) + 1):
                self.grid.setdefault((k, l), []).append(idx)

    def place(self, base, x, z, yaw=0.0, state="Intact", variant=None, flatten=None, check=True, pad=0.6,
              on_road=False, y=None, tilt=None, max_slope=None, blend=5.0, solid=True):
        info = self.cat.get(base, variant or self.variant)
        if info is None:
            self.missing.add(base)
            return False
        m = 2.0
        if not (m <= x <= self.size - m and m <= z <= self.size - m):
            return False
        r = self._rect(info, x, z, yaw, pad)
        if check:
            if self.collides(r):
                return False
            if not on_road and min(self.at(self.road_edge, px, pz) for px, pz in self._corners(r) + [(x, z)]) < 0.3:
                return False
            if min(self.at(self.water_d, px, pz) for px, pz in self._corners(r) + [(x, z)]) < 0.5:
                return False
        if max_slope is not None:
            sl = math.degrees(math.atan(math.hypot(*(np.array(self.normal(x, z))[[0, 2]] / max(self.normal(x, z)[1], 1e-6)))))
            if sl > max_slope:
                return False
        cat = info["category"]
        if flatten is None:
            flatten = cat in FLAT_CATS
        if flatten:
            self.flatten_rect(r[0], r[1], r[2] - pad, r[3] - pad, yaw, blend=blend)
        if solid:                                                            # las calzadas modulares no bloquean
            self._add_rect(r)
        self.objects.append(dict(asset=info["base"], name=info["name"], fbx=info["fbx"], variant=info["variant"], category=cat,
                                 x=float(x), z=float(z), yaw=float(yaw) % 360.0, state=state, y=y, holes=info["holes"],
                                 go=info["ground_offset"], tilt=(cat in TILT_CATS) if tilt is None else tilt, size=info["size"]))
        return True

    def place_near(self, base, x, z, yaw, tries=25, spread=6.0, **kw):
        for k in range(tries):
            dx, dz = (0, 0) if k == 0 else (self.rr.uniform(-spread, spread), self.rr.uniform(-spread, spread))
            if self.place(base, x + dx, z + dz, yaw + (0 if k == 0 else self.rr.uniform(-15, 15)), **kw):
                return True
        return False

    def line(self, base, pts, spacing, yaw_mode="along_x", offset=0.0, jitter=0.0, state="Intact", **kw):
        P = densify(pts, max(0.5, spacing / 4))
        L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        n = 0
        for s in np.arange(spacing / 2, L[-1], spacing):
            k = int(np.searchsorted(L, s))
            k = min(max(k, 1), len(P) - 1)
            a, b = P[k - 1], P[k]
            t = (s - L[k - 1]) / max(L[k] - L[k - 1], 1e-9)
            p = a + (b - a) * t
            d = (b - a) / max(np.linalg.norm(b - a), 1e-9)
            nrm = np.array([-d[1], d[0]])
            q = p + nrm * offset + (self.rr.uniform(-jitter, jitter) if jitter else 0)
            yaw = yaw_along_x(*d) if yaw_mode == "along_x" else yaw_facing(*d) if yaw_mode == "along_z" else yaw_facing(nrm[0], nrm[1])
            if self.place(base, float(q[0]), float(q[1]), yaw, state=state, **kw):
                n += 1
        return n

    def street_buildings(self, P, choices, setback=3.0, gap=3.0, sides=(1, -1), states=None, road_half=4.0, skip=None):
        """Edificios a ambos lados de una calle, mirando a la calle (puerta +Z local)."""
        P = np.asarray(P, float)
        L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        names, wts = zip(*choices)
        for side in sides:
            s = self.rr.uniform(4, 12)
            while s < L[-1] - 5:
                base = self.rr.choices(names, wts)[0]
                info = self.cat.get(base, self.variant)
                if info is None:
                    self.missing.add(base)
                    s += 10
                    continue
                wdt, dep = info["size"]
                k = min(max(int(np.searchsorted(L, s)), 1), len(P) - 1)
                d = P[k] - P[k - 1]
                d = d / max(np.linalg.norm(d), 1e-9)
                nrm = np.array([-d[1], d[0]]) * side
                q = P[k - 1] + d * (s - L[k - 1] + wdt / 2) + nrm * (road_half + setback + dep / 2)
                if skip is None or not skip(q):
                    st = "Intact"
                    if states:
                        st = self.rr.choices(list(states.keys()), list(states.values()))[0]
                    self.place(base, float(q[0]), float(q[1]), yaw_facing(-nrm[0], -nrm[1]), state=st)
                s += wdt + gap + self.rr.uniform(0, 4)

    def scatter(self, choices, n, region=None, mask=None, min_dist=4.0, max_slope=32.0, road_clear=2.5, state="Intact", tries=8, **kw):
        names, wts = zip(*choices)
        x0, z0, x1, z1 = region or (0, 0, self.size, self.size)
        sl = self.slope_deg()
        placed, pts = 0, {}
        cs = max(min_dist, 1.0)
        for _ in range(n * tries):
            if placed >= n:
                break
            x, z = self.rr.uniform(x0, x1), self.rr.uniform(z0, z1)
            if mask is not None and self.rr.random() > mask(x, z):
                continue
            if self.at(sl, x, z) > max_slope or self.at(self.road_edge, x, z) < road_clear or self.at(self.water_d, x, z) < 1.0:
                continue
            key = (int(x // cs), int(z // cs))
            if any(math.hypot(px - x, pz - z) < min_dist for kx in (-1, 0, 1) for kz in (-1, 0, 1) for px, pz in pts.get((key[0] + kx, key[1] + kz), ())):
                continue
            if self.place(self.rr.choices(names, wts)[0], x, z, self.rr.uniform(0, 360), state=state, pad=0.0, **kw):
                pts.setdefault(key, []).append((x, z))
                placed += 1
        return placed

    def ring(self, base, cx, cz, hx, hz, gate_side="S", gate_w=8.0, **kw):
        """Perimetro rectangular de un elemento lineal (HESCO, T-wall, concertina) con puerta."""
        corners = [(cx - hx, cz - hz), (cx + hx, cz - hz), (cx + hx, cz + hz), (cx - hx, cz + hz)]
        sides = {"S": (0, 1), "E": (1, 2), "N": (2, 3), "W": (3, 0)}
        info = self.cat.get(base, self.variant)
        if info is None:
            self.missing.add(base)
            return
        step = info["size"][0] + 0.05
        for sd, (a, b) in sides.items():
            A, Bp = np.array(corners[a], float), np.array(corners[b], float)
            L = np.linalg.norm(Bp - A)
            d = (Bp - A) / L
            n = int(L // step)
            for k in range(n):
                s = (k + 0.5) * L / n
                if sd == gate_side and abs(s - L / 2) < gate_w / 2:
                    continue
                q = A + d * s
                self.place(base, float(q[0]), float(q[1]), yaw_along_x(*d), check=False, **kw)

    def least_cost_path(self, start, goal, n=160, slope_w=80.0, low_w=0.0):
        """Dijkstra en una malla gruesa: slope_w castiga la pendiente (carreteras) y low_w la
        altura relativa (rios: buscan el fondo del valle)."""
        step = self.size / (n - 1)
        idx = np.linspace(0, self.res - 1, n).round().astype(int)
        hc = self.h[np.ix_(idx, idx)]
        hn = (hc - hc.min()) / max(float(np.ptp(hc)), 1e-6)
        s = (int(round(start[1] / step)), int(round(start[0] / step)))
        g = (int(round(goal[1] / step)), int(round(goal[0] / step)))
        dist = {s: 0.0}
        prev, heap = {}, [(0.0, s)]
        while heap:
            d, (i, j) = heapq.heappop(heap)
            if (i, j) == g:
                break
            if d > dist.get((i, j), 1e30):
                continue
            for (di, dj), L0 in zip(OFFS, ODST):
                a, b = i + di, j + dj
                if 0 <= a < n and 0 <= b < n:
                    L = step * L0
                    sl = abs(hc[a, b] - hc[i, j]) / L
                    nd = d + L * (1 + slope_w * sl * sl + low_w * hn[a, b] ** 2) + (5000 if sl > 0.3 and not low_w else 0)
                    if nd < dist.get((a, b), 1e30):
                        dist[(a, b)] = nd
                        prev[(a, b)] = (i, j)
                        heapq.heappush(heap, (nd, (a, b)))
        path, cur = [], g
        while cur in prev:
            path.append((cur[1] * step, cur[0] * step))
            cur = prev[cur]
        path.append((s[1] * step, s[0] * step))
        path = path[::-1]
        return path[::3] + ([path[-1]] if (len(path) - 1) % 3 else [])

    # ------------------------------------------------------------ salida
    def splat(self):
        sl = self.slope_deg()
        rock = np.clip(smooth(30, 42, sl) + self.m_rock, 0, 1)
        asph = self.m_asphalt * (1 - rock * 0.5)
        dirt = np.clip(self.m_dirt + self.m_wet * 0.5, 0, 1) * (1 - asph)
        base = np.clip(1 - rock - dirt - asph, 0, 1)
        W = np.stack([base, dirt, rock, asph], -1)
        if getattr(self, "layer_fn", None):
            W = self.layer_fn(self, sl)
        W = W / np.maximum(W.sum(-1, keepdims=True), 1e-6)
        W = (W[:-1, :-1] + W[1:, :-1] + W[:-1, 1:] + W[1:, 1:]) / 4
        return (np.clip(W, 0, 1) * 255).round().astype(np.uint8)

    def holes(self):
        n = self.res - 1
        solid = np.ones((n, n), dtype=bool)
        cc = (np.arange(n) + 0.5) * self.cell
        for o in self.objects:
            for hle in o["holes"]:
                lx, lz = hle["center_xz"]
                ox, oz = rot(lx, lz, o["yaw"])
                ax, az = rot(hle["axis_xz"][0], hle["axis_xz"][1], o["yaw"])
                cx, cz, hl, hw = o["x"] + ox, o["z"] + oz, hle["length"] / 2, hle["width"] / 2
                R = math.hypot(hl, hw) + self.cell
                j0, j1 = max(0, int((cx - R) / self.cell)), min(n, int((cx + R) / self.cell) + 2)
                i0, i1 = max(0, int((cz - R) / self.cell)), min(n, int((cz + R) / self.cell) + 2)
                if i0 >= i1 or j0 >= j1:
                    continue
                X, Z = cc[j0:j1][None, :] - cx, cc[i0:i1][:, None] - cz
                u, v = X * ax + Z * az, -X * az + Z * ax
                solid[i0:i1, j0:j1] &= ~((np.abs(u) <= hl) & (np.abs(v) <= hw))
        return solid

    def preview(self, path, W):
        cols = np.array([LAYER_RGB.get(l, (0.5, 0.5, 0.5)) for l in self.layers])
        img = np.tensordot(W.astype(float) / 255.0, cols, axes=(2, 0))
        gz, gx = np.gradient(self.h, self.cell)
        nrm = np.stack([-gx, -gz, np.ones_like(gx)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        L = np.array([-0.5, 0.5, 0.707])
        L /= np.linalg.norm(L)
        sh = np.clip(nrm @ L, 0, 1)
        sh = (sh[:-1, :-1] + sh[1:, 1:]) / 2
        img *= (0.35 + 0.85 * sh)[..., None]
        wd = (self.water_d[:-1, :-1] < 0)
        img[wd] = img[wd] * 0.3 + np.array([0.12, 0.28, 0.45]) * 0.7
        n = self.res - 1
        cc = (np.arange(n) + 0.5) * self.cell
        for o in self.objects:
            col = np.array(CAT_RGB.get(o["category"], (1, 0, 1)))
            if o["state"] == "Destroyed":
                col = col * 0.45
            hx, hz = max(o["size"][0] / 2, self.cell * 0.7), max(o["size"][1] / 2, self.cell * 0.7)
            if o["category"] == "Vegetation":
                hx = hz = max(1.6, self.cell)
            R = math.hypot(hx, hz) + self.cell
            j0, j1 = max(0, int((o["x"] - R) / self.cell)), min(n, int((o["x"] + R) / self.cell) + 2)
            i0, i1 = max(0, int((o["z"] - R) / self.cell)), min(n, int((o["z"] + R) / self.cell) + 2)
            if i0 >= i1 or j0 >= j1:
                continue
            X, Z = cc[j0:j1][None, :] - o["x"], cc[i0:i1][:, None] - o["z"]
            th = math.radians(o["yaw"])
            u = X * math.cos(th) - Z * math.sin(th)
            v = X * math.sin(th) + Z * math.cos(th)
            m = (np.abs(u) <= hx) & (np.abs(v) <= hz)
            sub = img[i0:i1, j0:j1]
            sub[m] = sub[m] * 0.15 + col * 0.85
        out = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        if out.shape[0] < 900:
            k = int(math.ceil(1024 / out.shape[0]))
            out = np.kron(out, np.ones((k, k, 1), dtype=np.uint8))
        write_png(path, np.flipud(out))

    def export(self, out_root):
        t0 = time.time()
        d = os.path.join(out_root, self.name)
        os.makedirs(d, exist_ok=True)
        hmin, hmax = float(self.h.min()), float(self.h.max())
        rng_h = max(hmax - hmin, 1.0) + 2.0
        h01 = (self.h - hmin) / rng_h
        (np.clip(h01, 0, 1) * 65535).round().astype("<u2").tofile(os.path.join(d, self.name + "_height.raw"))
        write_png(os.path.join(d, self.name + "_height.png"), np.flipud((np.clip(h01, 0, 1) * 65535).round().astype(np.uint16)))
        W = self.splat()
        W.tofile(os.path.join(d, self.name + "_splat.raw"))
        write_png(os.path.join(d, self.name + "_splat.png"), np.flipud(W))
        holes = self.holes()
        holes.astype(np.uint8).tofile(os.path.join(d, self.name + "_holes.raw"))
        objs = []
        for o in self.objects:
            y = o["y"] if o["y"] is not None else self.height(o["x"], o["z"]) + o["go"]
            rec = {"asset": o["asset"], "name": o["name"], "fbx": o["fbx"], "variant": o["variant"], "category": o["category"],
                   "pos": [round(o["x"], 3), round(y, 3), round(o["z"], 3)], "yaw": round(o["yaw"], 2), "state": o["state"]}
            if o["tilt"]:
                rec["up"] = self.normal(o["x"], o["z"])
            objs.append(rec)
        sx, sz = self.sun
        man = {
            "map": self.name, "description": self.desc, "variant": self.variant, "generator": "generate_maps.py v1",
            "units": "m; Unity: x este, y arriba, z norte; origen = esquina SO del terreno",
            "terrain": {"size": [self.size, round(rng_h, 3), self.size], "position": [0.0, round(hmin, 3), 0.0],
                        "heightmap_resolution": self.res, "heightmap_raw": self.name + "_height.raw", "raw_format": "uint16 LE, fila 0 = sur",
                        "alphamap_resolution": self.res - 1, "splat_raw": self.name + "_splat.raw", "splat_format": "RGBA8 = capas 0..3, fila 0 = sur",
                        "holes_raw": self.name + "_holes.raw", "holes_count": int((~holes).sum()), "cell_m": round(self.cell, 4)},
            "layers": [{"material": l, "diffuse": "Textures/%s_D.png" % l, "normal": "Textures/%s_N.png" % l,
                        "tile_m": LAYER_TILE.get(l, 4.0)} for l in self.layers],
            "sun": {"pitch": sx, "yaw": sz, "intensity": 1.1}, "sky_hdri": self.sky,
            "water": self.water, "spawns": self.spawns,
            "roads": [{"kind": r["kind"], "width": r["width"], "points_xz": [round(float(v), 1) for x, z in r["points"][::4] for v in (x, z)]}
                      for r in self.roads],
            "objects": objs,
            "missing_assets": sorted(self.missing),
        }
        with open(os.path.join(d, self.name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(man, fh, indent=1, ensure_ascii=False)
        self.preview(os.path.join(d, self.name + "_preview.png"), W)
        cats = {}
        for o in objs:
            cats[o["category"]] = cats.get(o["category"], 0) + 1
        print("  %-28s %4d m  res %d  relieve %.0f m  objetos %d %s  agujeros %d  (%.1fs)" % (
            self.name, self.size, self.res, rng_h, len(objs), cats, int((~holes).sum()), time.time() - t0))
        if self.missing:
            print("    (no encontrados en el catalogo: %s)" % ", ".join(sorted(self.missing)))
        return man


# ------------------------------------------------------------------------------ mapas
def map_desert_town(cat):
    m = WarMap(cat, "Desert_Town_Outpost", 1024, 1025, "Desert", ["Mat_Terrain_Sand", "Mat_Terrain_Soil", "Mat_Rock_Base", "Mat_Asphalt"],
               101, "Pueblo desertico con zoco y mezquita, uadi seco, carretera principal, puesto de control y FOB con HESCO en la colina NE",
               sky="lebombo", sun=(48.0, 120.0))
    n, rng = m.res, m.rng
    X, Z = np.meshgrid(m.xs, m.xs)
    rocky = 60 * resize(hills(513, rng, base=5), n) * smooth(0.3, 0.8, (X + Z) / 2048) ** 1.3
    lo = erode(resize(18 * fbm(513, rng, base=3) + 8 * fbm(513, rng, base=8), 513) + resize(rocky, 513), m.cell * 2, iters=8)
    h = resize(lo, n)
    a = math.radians(28)
    wv = 6 * fbm(n, rng, base=6)
    dunes = 2.4 * (1 - np.abs(np.sin(2 * math.pi * (X * math.cos(a) + Z * math.sin(a)) / 48 + wv))) ** 1.6
    m.h = h + dunes * (1 - smooth(4, 20, rocky))
    m.h -= m.h.min()
    m.m_rock = np.clip(smooth(0.55, 0.85, ridged(n, rng, base=10)) * smooth(12, 35, rocky), 0, 1)
    m.river([(0, 300), (300, 380), (600, 330), (1024, 420)], 30, 3.2, water=False, bank=0.22, band=40, follow_valley=False)
    main = m.road([(520, 0), (510, 300), (512, 512), (530, 760), (560, 1024)], 8.0, "asphalt")
    m.road([(250, 520), (512, 512), (800, 540)], 6.0, "dirt")
    m.road([(530, 760), (700, 820), (790, 850)], 5.0, "dirt")
    m.road([(330, 470), (420, 600), (512, 650)], 5.0, "dirt")
    town = lambda q: math.hypot(q[0] - 512, q[1] - 512) < 32                  # noqa: E731  (plaza central libre)
    houses = [("Bld_Compound_Desert", 3), ("Bld_Desert_House_2F", 5), ("Bld_House_Small", 2), ("Mil_CinderBlock_Wall", 1)]
    st = {"Intact": 0.7, "Damaged": 0.2, "Destroyed": 0.1}
    m.street_buildings(main[(main[:, 1] > 380) & (main[:, 1] < 700)], houses, setback=4, states=st, skip=town)
    m.street_buildings(catmull([(250, 520), (512, 512), (800, 540)], 3)[1:], houses, setback=4, states=st, road_half=3.0, skip=town)
    m.street_buildings(catmull([(330, 470), (420, 600), (512, 650)], 3), houses, setback=3, states=st, road_half=2.5, skip=town)
    m.place_near("Bld_Mosque_Minaret", 556, 548, -90, spread=4)
    for k in range(10):
        m.place_near("Prop_Market_Stall", 492 + (k % 5) * 8, 497 + (k // 5) * 9, 0 if k < 5 else 180, spread=2)
    m.place_near("Bld_Gas_Station", 545, 395, 90)
    m.place("Mil_Checkpoint", 512, 318, -90, on_road=True, check=False)
    for k, (x, z) in enumerate(((500, 330), (526, 340))):
        m.place("Mil_TWall_Bremer", x, z, 90, check=False)
    m.place_near("Veh_APC_BTR-82A", 540, 300, 30, state="Destroyed")
    m.place_near("Veh_Technical_Hilux_DShK", 505, 260, 200, state="Destroyed")
    m.place_near("Veh_Technical_Hilux_DShK", 515, 690, 10, state="Destroyed", on_road=True)
    for k in range(5):
        m.place_near("Civ_Car_Sedan", 500 + m.rr.uniform(-30, 30), 450 + k * 50, m.rr.uniform(0, 360),
                     state=m.rr.choice(["Intact", "Destroyed", "Damaged"]), spread=10)
    m.place_near("Civ_Bus_City", 540, 610, 95, state="Destroyed")
    m.place_near("Civ_Truck_Box", 470, 512, 10, state="Damaged")
    m.line("Prop_Utility_Pole", main[(main[:, 1] > 200) & (main[:, 1] < 900)], 40, yaw_mode="along_z", offset=7.5)
    # FOB en la colina NE: HESCO, torres, tiendas, redes, helipuerto, C-RAM
    fx, fz = 830.0, 880.0
    m.flatten_rect(fx, fz, 42, 42, 0, blend=18)
    m.ring("Mil_Hesco_MIL1", fx, fz, 38, 38, gate_side="W")
    for sx in (-1, 1):
        for sz in (-1, 1):
            m.place("Mil_Watchtower", fx + sx * 34, fz + sz * 34, 45, check=False)
    for k in range(4):
        m.place("Mil_Tent_GP_Medium", fx - 18 + k * 9, fz + 18, 90)
    m.place("Mil_Camo_Net_10x8", fx - 12, fz - 15, 0)
    m.place("Veh_MRAP_M-ATV", fx - 12, fz - 15, 0, check=False)
    m.place("Mil_Camo_Net_10x8", fx + 4, fz - 15, 0)
    m.place("Veh_LTV_JLTV", fx + 4, fz - 15, 0, check=False)
    for k in range(3):
        m.place("Mil_Container_20ft", fx + 20, fz - 20 + k * 4, 90)
    m.place("AD_CRAM_Centurion", fx + 18, fz + 10, 0)
    m.place("Fort_Mortar_Pit_81mm", fx - 22, fz, 0)
    m.place("Map_Helipad_20m", fx - 75, fz + 10, 0)
    m.place("Air_Heli_UH-60M_BlackHawk", fx - 75, fz + 10, 90, check=False)
    m.place("Map_Radio_Mast_40m", fx + 70, fz + 60, 0)
    m.scatter([("Veg_Tree_Palm", 5), ("Veg_Bush", 2)], 140, mask=lambda x, z: 1.0 if m.at(m.m_wet, x, z) > 0.3 or abs(z - 330 - (x / 1024) * 60) < 50 else 0.03)
    m.scatter([("Veg_Bush", 3), ("Veg_Grass_Clump", 2)], 260, min_dist=6)
    m.scatter([("Ter_Rock_Boulder", 1)], 120, mask=lambda x, z: m.at(m.m_rock, x, z) + 0.05, max_slope=45, min_dist=8)
    m.place_near("Ter_Rubble_Concrete", 470, 620, 0)
    m.place_near("Ter_Rubble_Brick", 560, 470, 40)
    for k in range(14):
        m.crater(m.rr.uniform(480, 580), m.rr.uniform(700, 1000), m.rr.uniform(2, 4.5), m.rr.uniform(0.8, 1.5))
    m.spawns = [{"team": "A", "pos": [fx, m.height(fx, fz), fz]}, {"team": "B", "pos": [512.0, m.height(512, 60), 60.0]}]
    return m


def map_temperate_valley(cat):
    m = WarMap(cat, "Temperate_River_Valley", 1024, 1025, "Temperate", ["Mat_Terrain_Grass", "Mat_Terrain_Soil", "Mat_Rock_Base", "Mat_Asphalt"],
               202, "Valle con rio y puente de hormigon, pueblo con iglesia, campos, bosques, tendido de alta tension y linea de frente",
               sky="forest_slope", sun=(42.0, 150.0))
    n, rng = m.res, m.rng
    base = 45 * fbm(513, rng, base=3) + 55 * hills(513, rng, base=4) + 6 * fbm(513, rng, base=12)
    lo = erode(base, m.cell * 2, iters=12)
    m.h = resize(lo, n) + 1.2 * fbm(n, rng, base=40)
    m.h -= m.h.min()
    riv = m.river([(0, 260), (250, 230), (480, 280), (700, 240), (1024, 300)], 24, 4.0)
    rd = [(600, 0), (560, 160), (520, 268), (500, 400), (480, 560), (470, 760), (500, 1024)]
    P = catmull(rd, 3.0)
    prof = moving_average(np.array([m.height(x, z) for x, z in P]), 23)
    k = int(np.argmin([min(np.hypot(*(p - q)) for q in riv[::3]) for p in P]))          # cruce con el rio
    near = np.hypot(*(P - P[k]).T) < 40
    deck = max(m.height(*P[max(k - 15, 0)]), m.height(*P[min(k + 15, len(P) - 1)])) + 0.6
    prof = np.where(near, deck, prof)
    main = m.road(rd, 7.0, "asphalt", profile=prof, smooth_m=40)
    d = path_dirs(P)[k]
    m.place("Map_Bridge_Concrete_36m", float(P[k][0]), float(P[k][1]), yaw_along_x(*d), y=deck - 6.53, check=False, flatten=False)
    m.road([(300, 560), (480, 560), (720, 600)], 5.0, "dirt")
    m.road([(470, 760), (650, 830), (900, 840)], 4.5, "dirt")
    houses = [("Bld_House_Small", 5), ("Bld_House_TwoStory", 4), ("Bld_Barn_Wood", 1)]
    church = lambda q: math.hypot(q[0] - 515, q[1] - 610) < 30                # noqa: E731
    m.place("Bld_Church_BellTower", 515, 610, 270)
    m.street_buildings(main[(main[:, 1] > 450) & (main[:, 1] < 720)], houses, setback=6, gap=5, skip=church,
                       states={"Intact": 0.75, "Damaged": 0.17, "Destroyed": 0.08})
    m.street_buildings(catmull([(300, 560), (480, 560), (720, 600)], 3), houses, setback=6, gap=6, road_half=2.5, skip=church,
                       states={"Intact": 0.75, "Damaged": 0.17, "Destroyed": 0.08})
    m.place_near("Bld_Gas_Station", 520, 440, 270)
    for k in range(6):
        m.place_near("Bld_Barn_Wood", m.rr.uniform(250, 800), m.rr.uniform(650, 900), m.rr.uniform(0, 360), spread=20)
    for (cx, cz, w, l, yaw) in ((330, 650, 140, 90, 10), (650, 690, 120, 100, -15), (720, 470, 150, 110, 30),
                                (300, 420, 120, 80, -10), (820, 900, 160, 90, 5), (180, 820, 120, 120, 20)):
        m.field(cx, cz, w, l, yaw)
    m.line("Prop_Street_Lamp", main[(main[:, 1] > 520) & (main[:, 1] < 680)], 24, yaw_mode="along_z", offset=5.0)
    m.line("Prop_Utility_Pole", main[(main[:, 1] > 300) & (main[:, 1] < 1000)], 45, yaw_mode="along_z", offset=-6.0)
    m.line("Map_Pylon_HV_30m", [(10, 940), (520, 860), (1014, 700)], 220, yaw_mode="along_z")
    # linea de frente al norte del rio, mirando al sur
    front = catmull([(250, 330), (400, 345), (600, 350), (780, 330)], 3)
    m.line("Fort_Trench_ZigZag", front, 26, yaw_mode="along_x", offset=0)
    m.line("Fort_MG_Nest", front, 90, yaw_mode="perp", offset=-14)
    m.line("Fort_Foxhole_2Man", front, 55, yaw_mode="perp", offset=-22, jitter=3)
    m.line("Mil_Concertina_Wire", front, 10.5, yaw_mode="along_x", offset=-34)
    m.line("Fort_Dugout_Log", front, 120, yaw_mode="perp", offset=14)
    for k, x in enumerate((420, 470, 560, 610)):
        m.place_near("Fort_Vehicle_Revetment", x, 372, 180, spread=8)
    m.place_near("Veh_MBT_Leopard2A7", 420, 372, 180, check=False)
    m.place_near("Veh_IFV_M2A4_Bradley", 610, 372, 180, check=False)
    m.place_near("Fort_Mortar_Pit_81mm", 520, 395, 180)
    # obstaculos y bajas enemigas al sur del puente
    m.line("Mil_Dragons_Teeth", [(470, 205), (500, 200)], 6, yaw_mode="along_x")
    m.line("Mil_Dragons_Teeth", [(560, 205), (600, 210)], 6, yaw_mode="along_x")
    for x, z, a in ((540, 150, 20), (590, 120, 160), (470, 170, 300)):
        m.place_near("Veh_MBT_T-72B3", x, z, a, state="Destroyed", spread=10)
    m.place_near("Veh_IFV_BMP-2", 620, 190, 330, state="Destroyed", spread=10)
    m.place_near("Mil_Hedgehog_AT", 548, 225, 0, on_road=True)
    m.craters(40, (380, 60, 720, 230), 1.5, 4.5)
    forest = 0.5 + 0.5 * fbm(n, np.random.default_rng(7), base=5)
    m.scatter([("Veg_Tree_Pine", 5), ("Veg_Tree_Oak", 3)], 1100, mask=lambda x, z: smooth(0.55, 0.7, m.at(forest, x, z)) * (1 if z > 330 or z < 200 else 0.2), min_dist=5)
    m.scatter([("Veg_Tree_Oak", 3), ("Veg_Bush", 4)], 260, min_dist=6, mask=lambda x, z: 0.25 + 0.75 * m.at(m.m_wet, x, z))
    m.scatter([("Veg_Bush", 2), ("Veg_Grass_Clump", 3)], 300, min_dist=5)
    slp = m.slope_deg()
    m.scatter([("Ter_Rock_Boulder", 1)], 60, mask=lambda x, z: m.at(slp, x, z) / 40.0, max_slope=50, min_dist=10)
    m.spawns = [{"team": "A", "pos": [480.0, m.height(480, 700), 700.0]}, {"team": "B", "pos": [600.0, m.height(600, 40), 40.0]}]
    return m


def map_winter_front(cat):
    m = WarMap(cat, "Winter_Trench_Front", 512, 1025, "Winter", ["Mat_Terrain_Snow", "Mat_Terrain_Soil", "Mat_Rock_Base", "Mat_Asphalt"],
               303, "Frente de trincheras invernal: dos lineas enfrentadas, tierra de nadie con crateres, aldea en ruinas y bosque",
               sky="kiara_1_dawn", sun=(18.0, 110.0))
    n, rng = m.res, m.rng
    lo = erode(16 * fbm(513, rng, base=3) + 18 * hills(513, rng, base=3) + 5 * fbm(513, rng, base=9), m.cell * 2, iters=6)
    m.h = resize(lo, n) + 0.35 * fbm(n, rng, base=60)
    m.h -= m.h.min()
    m.road([(0, 140), (200, 150), (512, 130)], 4.5, "dirt")
    m.road([(256, 0), (250, 150), (240, 512)], 4.0, "dirt")
    for zl, rev in ((185, True), (375, False)):                            # A (sur) mira al norte, B al sur
        P = catmull([(30, zl), (150, zl + 12), (300, zl - 6), (480, zl + 8)], 2)
        P = P[::-1] if rev else P                                          # adelante = -normal izquierda
        m.line("Fort_Trench_ZigZag", P, 21, yaw_mode="along_x")
        m.line("Fort_MG_Nest", P, 70, yaw_mode="perp", offset=-12)
        m.line("Fort_Foxhole_2Man", P, 38, yaw_mode="perp", offset=-22, jitter=2)
        m.line("Mil_Concertina_Wire", P, 9.5, yaw_mode="along_x", offset=-32)
        m.line("Mil_Dragons_Teeth", P, 30, yaw_mode="along_x", offset=-40)
        m.line("Fort_Dugout_Log", P, 85, yaw_mode="perp", offset=12)
        m.line("Fort_Mortar_Pit_81mm", P, 110, yaw_mode="perp", offset=34)
    m.craters(90, (20, 215, 492, 345), 1.2, 4.0)
    for b, st in (("Bld_House_Small", "Destroyed"), ("Bld_House_TwoStory", "Destroyed"), ("Bld_Barn_Wood", "Damaged"),
                  ("Bld_Church_BellTower", "Damaged"), ("Bld_House_Small", "Damaged"), ("Bld_Ruin_Wall_Brick", "Intact"),
                  ("Bld_Ruin_Wall_Brick", "Intact"), ("Ter_Rubble_Brick", "Intact"), ("Ter_Rubble_Concrete", "Intact")):
        m.place_near(b, m.rr.uniform(60, 190), m.rr.uniform(250, 320), m.rr.uniform(0, 360), state=st, spread=25)
    for b, a in (("Veh_MBT_T90M", 10), ("Veh_IFV_BMP-2", 200), ("Veh_IFV_M2A4_Bradley", 150), ("Veh_MBT_Leopard2A7", 340)):
        m.place_near(b, m.rr.uniform(150, 450), m.rr.uniform(240, 330), a, state="Destroyed", spread=30)
    m.place_near("Map_Radio_Mast_40m", 420, 470, 0)
    m.place_near("Map_Water_Tower", 90, 60, 0, state="Damaged")
    forest = 0.5 + 0.5 * fbm(n, np.random.default_rng(11), base=5)
    m.scatter([("Veg_Tree_Pine", 6), ("Veg_Tree_Dead", 1)], 700, mask=lambda x, z: smooth(0.5, 0.62, m.at(forest, x, z)) * (0 if 160 < z < 400 else 1),
              min_dist=4.5)
    m.scatter([("Veg_Tree_Dead", 1)], 50, region=(20, 215, 492, 345), min_dist=8)
    m.scatter([("Veg_Bush", 1)], 160, min_dist=5)
    m.spawns = [{"team": "A", "pos": [256.0, m.height(256, 60), 60.0]}, {"team": "B", "pos": [250.0, m.height(250, 480), 480.0]}]
    return m


def map_urban(cat):
    m = WarMap(cat, "Urban_District_Ruins", 512, 513, "Temperate", ["Mat_Terrain_Grass", "Mat_Terrain_Soil", "Mat_Rock_Base", "Mat_Asphalt"],
               404, "Barrio urbano en cuadricula (calles modulares de 12 m y cruces), bloques de viviendas, nave industrial, "
                    "iglesia, gasolinera, parque y danos de guerra", sky="potsdamer_platz", sun=(38.0, 140.0))
    rng = m.rng
    m.h = 3.0 * fbm(m.res, rng, base=2) + 0.25 * fbm(m.res, rng, base=30)
    m.h -= m.h.min()
    m.m_dirt[:] = 0.45
    G = [40 + 74 * k for k in range(7)]
    for g in G:                                                             # explanacion y mascara de calles
        m.road([(g, 0), (g, 512)], 12.6, "asphalt", curve=False, smooth_m=150)
        m.road([(0, g), (512, g)], 12.6, "asphalt", curve=False, smooth_m=150)
    for gx in G:
        for gz in G:
            m.place("Map_Road_Intersection_14m", gx, gz, 0, on_road=True, check=False, solid=False)
    for g in G:
        for a, b in zip(G[:-1], G[1:]):
            for k in range(5):
                c = a + 7 + 6 + 12 * k
                m.place("Map_Road_Asphalt_12m", c, g, 0, on_road=True, check=False, solid=False)
                m.place("Map_Road_Asphalt_12m", g, c, 90, on_road=True, check=False, solid=False)
    blocks = [(a + 7.3, b + 7.3, a + 74 - 7.3, b + 74 - 7.3) for a in G[:-1] for b in G[:-1]]
    special = {0: "Bld_Factory_Hall", 7: "Bld_Church_BellTower", 14: "Bld_Gas_Station", 24: "park", 30: "Bld_Factory_Hall", 12: "park"}
    st = {"Intact": 0.5, "Damaged": 0.3, "Destroyed": 0.2}
    for bi, (x0, z0, x1, z1) in enumerate(blocks):
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        sp = special.get(bi)
        if sp == "park":
            m.scatter([("Veg_Tree_Oak", 3), ("Veg_Bush", 2)], 25, region=(x0 + 3, z0 + 3, x1 - 3, z1 - 3), min_dist=6)
            continue
        if sp:
            m.place_near(sp, cx, cz, 0, state=m.rr.choices(list(st), list(st.values()))[0], spread=4)
            if sp == "Bld_Factory_Hall":
                m.place_near("Bld_Chimney_Brick_35m", x1 - 6, z1 - 6, 0, state="Intact")
        for side, (ax, az, bx, bz, fx, fz) in enumerate(((x0, z0, x1, z0, 0, -1), (x1, z0, x1, z1, 1, 0), (x1, z1, x0, z1, 0, 1), (x0, z1, x0, z0, -1, 0))):
            P = np.array([(ax, az), (bx, bz)], float)
            m.street_buildings(P, [("Bld_Apartment_4F", 3), ("Bld_House_TwoStory", 3), ("Bld_House_Small", 1), ("Bld_Ruin_Wall_Brick", 1),
                                   ("Ter_Rubble_Concrete", 1)], setback=0.5, gap=2.5, sides=(1,), road_half=0.0, states=st)
    for k in range(18):
        g = m.rr.choice(G)
        c = m.rr.uniform(20, 490)
        x, z = (g + m.rr.choice((-2.5, 2.5)), c) if k % 2 else (c, g + m.rr.choice((-2.5, 2.5)))
        m.place(m.rr.choice(["Civ_Car_Sedan", "Civ_Car_Sedan", "Civ_Truck_Box", "Veh_Truck_Ural-4320"]), x, z,
                90 if k % 2 == 0 else 0, state=m.rr.choice(["Intact", "Damaged", "Destroyed"]), on_road=True)
    m.place("Civ_Bus_City", G[3] + 2.5, G[2] + 30, 0, state="Destroyed", on_road=True)
    m.place("Veh_MBT_T-72B3", G[4], G[4] + 25, 180, state="Destroyed", on_road=True)
    m.place("Veh_APC_BTR-82A", G[2] + 30, G[5] - 2.5, 90, state="Damaged", on_road=True)
    m.place("Mil_Checkpoint", G[3], 15, -90, on_road=True, check=False)
    for k in range(6):
        m.place("Mil_Barrier_Jersey", G[1] + m.rr.uniform(-4, 4), G[3] + 12 + k * 3.2, 90, on_road=True)
        m.place("Mil_Hedgehog_AT", G[5] + m.rr.uniform(-4, 4), G[2] + 15 + k * 4, m.rr.uniform(0, 90), on_road=True)
    for g in G:
        m.line("Prop_Street_Lamp", [(g + 5.4, 5), (g + 5.4, 507)], 26, yaw_mode="along_z", on_road=True)
    m.place_near("Prop_Billboard", G[2] + 20, G[1] + 12, 0)
    m.place_near("Prop_Billboard", G[4] + 20, G[5] - 12, 180)
    m.spawns = [{"team": "A", "pos": [256.0, m.height(256, 20), 20.0]}, {"team": "B", "pos": [256.0, m.height(256, 492), 492.0]}]
    return m


def map_volcano(cat, dem_path):
    if not dem_path or not os.path.exists(dem_path):
        print("  (sin DEM real: %s) -> se omite Volcano_StHelens_DEM" % dem_path)
        return None
    grid, step, (e0, n0) = read_usgs_dem(dem_path)
    ce, cn, half = 562200.0, 5116900.0, 3000.0                       # crater del Monte St. Helens (UTM 10N)
    j0, j1 = int((ce - half - e0) / step), int((ce + half - e0) / step) + 1
    i0, i1 = int((cn - half - n0) / step), int((cn + half - n0) / step) + 1
    crop = grid[i0:i1, j0:j1]
    if np.isnan(crop).any():
        crop = np.where(np.isnan(crop), np.nanmin(crop), crop)
    m = WarMap(cat, "Volcano_StHelens_DEM", 6000, 1025, "Temperate", ["Mat_Terrain_Grass", "Mat_Terrain_Soil", "Mat_Rock_Base", "Mat_Terrain_Snow"],
               505, "Relieve REAL: Monte St. Helens tras la erupcion (DEM USGS 30 m, dominio publico), 6 x 6 km: "
                    "sitio de radar en la cresta, FOB con helipuerto en el valle y bosques",
               sky="immenstadter_horn", sun=(40.0, 140.0))
    for _ in range(3):                                                # quita el bandeado E-O del DEM de 1980 (perfiles digitalizados)
        p = np.pad(crop, ((2, 2), (0, 0)), mode="edge")
        crop = (p[:-4] + 4 * p[1:-3] + 6 * p[2:-2] + 4 * p[3:-1] + p[4:]) / 16.0
    m.h = resize(crop, m.res) + 1.6 * fbm(m.res, m.rng, base=200)
    hmin = m.h.min()
    m.h -= hmin
    elev = m.h + hmin

    def layers(mm, sl):
        snow = smooth(2150, 2350, elev) * (1 - smooth(38, 50, sl))
        rock = np.clip(smooth(28, 40, sl) + smooth(2000, 2400, elev) * 0.3, 0, 1) * (1 - snow)
        grass = (1 - smooth(1150, 1450, elev)) * (1 - smooth(18, 30, sl))
        ash = np.clip(1 - snow - rock - grass, 0, 1) + mm.m_dirt
        return np.stack([grass, ash, rock, snow], -1)
    m.layer_fn = layers
    sl = m.slope_deg()
    sc_f = sl + (elev - elev.min()) / 40.0                                # llano y bajo -> FOB
    i, j = np.unravel_index(np.argmin(sc_f[120:-120, 120:-120]), sc_f[120:-120, 120:-120].shape)
    fx, fz = float((j + 120) * m.cell), float((i + 120) * m.cell)
    score = elev - 40 * sl
    i, j = np.unravel_index(np.argmax(score[150:-150, 150:-150]), score[150:-150, 150:-150].shape)
    rx, rz = float((j + 150) * m.cell), float((i + 150) * m.cell)
    path = m.least_cost_path((fx, fz), (rx, rz - 60))                     # hasta la puerta sur del recinto
    m.road(path, 5.0, "dirt", smooth_m=40, blend=6)
    m.flatten_rect(rx, rz, 45, 45, 0, blend=25)
    m.flatten_rect(fx, fz, 60, 60, 0, blend=25)
    radome = cat.resolve("TP_Radar_Radome")
    dish = cat.resolve("TP_Tracking_Antenna")
    if radome:
        m.place_near(radome, rx - 15, rz + 12, 0)
    if dish:
        m.place_near(dish, rx + 18, rz + 12, 30)
    m.place_near("AD_Radar_Trailer", rx, rz - 18, 0)
    m.place_near("Veh_SPAAG_ZSU-23-4_Shilka", rx - 25, rz - 25, 200)
    m.place_near("Veh_SPAAG_Gepard_1A2", rx + 25, rz - 25, 160)
    m.ring("Mil_Hesco_MIL1", rx, rz, 42, 42, gate_side="S")
    m.place("Map_Helipad_20m", fx - 20, fz, 0)
    m.place("Air_Heli_Mi-8MTV", fx - 20, fz, 90, check=False)
    m.place("Map_Helipad_20m", fx + 20, fz, 0)
    m.place("Air_Heli_Mi-24P_Hind", fx + 20, fz, 90, check=False)
    for k in range(4):
        m.place("Mil_Tent_GP_Medium", fx - 30 + k * 12, fz + 30, 90)
    m.place("Veh_Truck_Ural-4320", fx + 35, fz - 30, 0)
    m.place("Art_MLRS_BM-21_Grad", fx + 20, fz - 35, 0)
    m.scatter([("Veg_Tree_Pine", 1)], 1400, mask=lambda x, z: (1 - smooth(1150, 1400, m.height(x, z) + hmin)) * (0.15 if z > 4200 else 1.0),
              min_dist=8, max_slope=30)
    m.scatter([("Veg_Tree_Dead", 1)], 500, region=(0, 4200, 6000, 6000), min_dist=10, max_slope=35)
    m.spawns = [{"team": "A", "pos": [fx, m.height(fx, fz), fz]}, {"team": "B", "pos": [rx, m.height(rx, rz), rz]}]
    return m


def map_airbase(cat):
    m = WarMap(cat, "Desert_Airbase", 1024, 1025, "Desert", ["Mat_Terrain_Sand", "Mat_Terrain_Soil", "Mat_Rock_Base", "Mat_Asphalt"],
               606, "Base aerea en el desierto: pista de 960 m, calle de rodaje, plataforma, 3 refugios HAS, helipuertos, "
                    "deposito de combustible, radar, C-RAM, campamento y perimetro de concertina", sky="rooitou_park", sun=(55.0, 100.0))
    n, rng = m.res, m.rng
    X, Z = np.meshgrid(m.xs, m.xs)
    m.h = 6 * fbm(n, rng, base=3) + 1.8 * (1 - np.abs(np.sin(2 * math.pi * (X * 0.8 + Z * 0.6) / 40 + 4 * fbm(n, rng, base=6))))
    m.h -= m.h.min()
    m.flatten_rect(520, 600, 480, 260, 0, blend=60)
    for k in range(15):
        m.place("Map_Runway_Section_60m", 82 + k * 60, 420, 0, check=False)
    m.road([(100, 520), (940, 520)], 23, "asphalt", curve=False, smooth_m=200)
    for x in (200, 520, 840):
        m.road([(x, 442), (x, 520)], 23, "asphalt", curve=False, smooth_m=60)
    m.road([(300, 590), (740, 590)], 100, "asphalt", curve=False, smooth_m=200)
    m.road([(520, 640), (520, 1024)], 8, "asphalt")
    for k, x in enumerate((360, 440, 680)):
        m.place("Bld_Hangar_HAS", x, 700, 180)
    m.place("Air_Jet_F-35A", 360, 650, 180, check=False)
    m.place("Air_Jet_F-35A", 680, 650, 180, check=False, state="Damaged")
    m.place("Air_UAV_MQ-9", 420, 590, 180, on_road=True)
    m.place("Air_UAV_MQ-9", 470, 590, 180, on_road=True)
    m.place("Air_UAV_Bayraktar_TB2", 560, 590, 180, on_road=True)
    m.place("Air_UAV_Bayraktar_TB2", 590, 590, 180, on_road=True)
    gh = cat.resolve("TP_RQ_4_Global_Hawk")
    if gh:
        m.place(gh, 660, 585, 180, on_road=True)
    for k, x in enumerate((820, 870)):
        m.place("Map_Helipad_20m", x, 610, 0)
    m.place("Air_Heli_AH-64E_Apache", 820, 610, 90, check=False)
    m.place("Air_Heli_UH-60M_BlackHawk", 870, 610, 90, check=False)
    for k in range(3):
        m.place("Map_Fuel_Tank_16m", 860 + (k % 2) * 45, 780 + (k // 2) * 45, 0)
    m.place("Map_Water_Tower", 200, 760, 0)
    m.place("Map_Radio_Mast_40m", 120, 880, 0)
    radome = cat.resolve("TP_Radar_Radome")
    if radome:
        m.place(radome, 260, 880, 0)
    dish = cat.resolve("TP_Tracking_Antenna")
    if dish:
        m.place(dish, 300, 900, 0)
    m.place("AD_Radar_Trailer", 340, 860, 0)
    m.place("AD_CRAM_Centurion", 600, 760, 0)
    m.place("AD_CRAM_Centurion", 230, 640, 0)
    for k in range(8):
        m.place("Mil_Tent_GP_Medium", 420 + (k % 4) * 14, 820 + (k // 4) * 16, 90)
    for k in range(9):
        m.place("Mil_Container_20ft", 640 + (k % 3) * 9, 820 + (k // 3) * 4.5, 0)
    m.place("Mil_Checkpoint", 520, 985, -90, on_road=True, check=False)
    m.ring("Mil_Concertina_Wire", 520, 650, 470, 300, gate_side="N", gate_w=14)
    for sx in (-1, 1):
        for sz in (-1, 1):
            m.place("Mil_Watchtower", 520 + sx * 462, 650 + sz * 292, 45, check=False)
    m.ring("Mil_TWall_Bremer", 882, 802, 60, 60, gate_side="W", gate_w=10)
    m.place_near("Air_Drone_Shahed-136", 760, 760, 30, state="Destroyed")
    m.craters(6, (600, 700, 760, 800), 1.0, 2.5)
    m.scatter([("Veg_Bush", 3), ("Veg_Grass_Clump", 1)], 180, region=(0, 0, 1024, 340), min_dist=8)
    m.scatter([("Ter_Rock_Boulder", 1)], 40, region=(0, 0, 1024, 300), min_dist=12)
    m.spawns = [{"team": "A", "pos": [520.0, m.height(520, 760), 760.0]}, {"team": "B", "pos": [520.0, m.height(520, 60), 60.0]}]
    return m


MAPS = [("desert", map_desert_town), ("valley", map_temperate_valley), ("winter", map_winter_front), ("urban", map_urban),
        ("volcano", map_volcano), ("airbase", map_airbase)]


def main():
    ap = argparse.ArgumentParser(description="Mapas de guerra realistas para Unity")
    ap.add_argument("--assets", default=os.path.join(os.path.expanduser("~"), "Unity_Destructible_Military"))
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--dem", default=os.path.join(HERE, "ThirdParty", "direct", "dem_mount_st_helens", "SainteHelens.dem"))
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ([] if "bpy" in sys.modules else sys.argv[1:])
    a = ap.parse_args(argv)
    root = os.path.abspath(os.path.expanduser(a.assets))
    out = os.path.abspath(os.path.expanduser(a.out)) if a.out else os.path.join(root, "Maps")
    only = [o.strip().lower() for o in a.only.split(",") if o.strip()]
    cat = Catalog(root)
    os.makedirs(out, exist_ok=True)
    index = []
    for key, fn in MAPS:
        if only and key not in only:
            continue
        t0 = time.time()
        m = fn(cat, a.dem) if key == "volcano" else fn(cat)
        if m is None:
            continue
        man = m.export(out)
        index.append({"map": man["map"], "json": "%s/%s.json" % (man["map"], man["map"]), "description": man["description"],
                      "size_m": man["terrain"]["size"][0], "objects": len(man["objects"]), "seconds": round(time.time() - t0, 1)})
    with open(os.path.join(out, "maps_index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1, ensure_ascii=False)
    print("\n=== %d mapas -> %s ===" % (len(index), out))


if __name__ == "__main__":
    main()
