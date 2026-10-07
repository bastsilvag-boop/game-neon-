"""
Render 3D de un mapa de generate_maps.py en Blender (terreno con sus 4 capas de textura,
rio, assets en su estado real y cielo HDRI). Sirve para revisar un mapa sin abrir Unity.

 blender -b --python render_map_preview.py -- --map Maps/Temperate_River_Valley/Temperate_River_Valley.json
         [--center 510,420] [--size 460] [--out preview3d.png] [--samples 48] [--res 1600x900]
         [--cam 150,28,330]  (azimut desde el sur en grados, elevacion, distancia en m)
         [--hdri ruta.hdr] [--no-assets]
"""
import argparse
import json
import math
import os
import sys

import bpy  # noqa: I001  (bpy antes que bmesh: necesario con el modulo bpy de pip)
import bmesh
import numpy as np
from mathutils import Matrix, Vector


def B(ux, uy, uz):
    """Unity (x este, y arriba, z norte) -> Blender (Z arriba): giro de 180 grados en planta."""
    return Vector((-ux, -uz, uy))


def load_template(fbx_path, asset_name, state):
    """Importa un FBX y devuelve una malla unica con el estado pedido (para instanciar)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx_path)
    new = [o for o in bpy.data.objects if o not in before]
    group = next((o for o in new if o.name.startswith("%s_%s" % (asset_name, state))), None)
    if group is None:
        group = next((o for o in new if o.name.startswith(asset_name + "_Intact")), None)
    parts = [o for o in (group.children_recursive if group else []) if o.type == 'MESH']
    bm = bmesh.new()
    mats, slot_of = [], {}
    for o in parts:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(o.matrix_world)
        remap = []
        for s in o.material_slots:
            m = s.material
            if m is not None and m.name not in slot_of:
                slot_of[m.name] = len(mats)
                mats.append(m)
            remap.append(slot_of.get(m.name, 0) if m is not None else 0)
        for f in tmp.faces:
            f.material_index = remap[f.material_index] if f.material_index < len(remap) else 0
        me = bpy.data.meshes.new("_t")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new("T_%s_%s" % (asset_name, state))
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    return me


def _sock(coll, name, kind='RGBA'):
    return next(sk for sk in coll if sk.name == name and sk.type == kind)


def _mix(nodes, blend):
    nd = nodes.new("ShaderNodeMix")
    nd.data_type = 'RGBA'
    nd.blend_type = blend
    _sock(nd.inputs, "Factor", 'VALUE').default_value = 1.0
    return nd, _sock(nd.inputs, "A"), _sock(nd.inputs, "B"), _sock(nd.outputs, "Result")


def terrain_material(info, root, map_dir):
    t = info["terrain"]
    mat = bpy.data.materials.new("Terrain")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs["Roughness"].default_value = 0.92
    uvw = nodes.new("ShaderNodeUVMap")
    uvw.uv_map = "World"
    uvs = nodes.new("ShaderNodeUVMap")
    uvs.uv_map = "Splat"
    sp_img = bpy.data.images.load(os.path.join(map_dir, info["map"] + "_splat.png"))
    sp_img.colorspace_settings.name = 'Non-Color'
    sp_img.alpha_mode = 'CHANNEL_PACKED'
    sp = nodes.new("ShaderNodeTexImage")
    sp.image = sp_img
    sp.interpolation = 'Linear'
    links.new(uvs.outputs["UV"], sp.inputs["Vector"])
    sep = nodes.new("ShaderNodeSeparateColor")
    links.new(sp.outputs["Color"], sep.inputs["Color"])
    weights = [sep.outputs[0], sep.outputs[1], sep.outputs[2], sp.outputs["Alpha"]]
    acc = None
    for i, layer in enumerate(info["layers"][:4]):
        mp = nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.0 / layer["tile_m"],) * 3
        links.new(uvw.outputs["UV"], mp.inputs["Vector"])
        tex = nodes.new("ShaderNodeTexImage")
        path = os.path.join(root, layer["diffuse"])
        if os.path.exists(path):
            tex.image = bpy.data.images.load(path, check_existing=True)
        links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        _n, a_in, b_in, out = _mix(nodes, 'MULTIPLY')
        links.new(tex.outputs["Color"], a_in)
        links.new(weights[i], b_in)
        if acc is None:
            acc = out
        else:
            _n2, a2, b2, out2 = _mix(nodes, 'ADD')
            links.new(acc, a2)
            links.new(out, b2)
            acc = out2
    links.new(acc, bsdf.inputs["Base Color"])
    return mat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--center", default="")
    ap.add_argument("--size", type=float, default=420.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--res", default="1600x900")
    ap.add_argument("--cam", default="150,28,0")
    ap.add_argument("--hdri", default="")
    ap.add_argument("--max-trees", type=int, default=900, dest="max_trees")
    ap.add_argument("--no-assets", action="store_true", dest="no_assets", help="solo terreno y agua (rapido)")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    info = json.load(open(a.map, encoding="utf-8"))
    map_dir = os.path.dirname(os.path.abspath(a.map))
    root = os.path.abspath(os.path.join(map_dir, "..", ".."))
    t = info["terrain"]
    n, S, H, y0 = t["heightmap_resolution"], t["size"][0], t["size"][1], t["position"][1]
    cell = S / (n - 1)
    h = np.fromfile(os.path.join(map_dir, t["heightmap_raw"]), dtype="<u2").reshape(n, n).astype(float) / 65535.0 * H + y0
    cx, cz = (map(float, a.center.split(","))) if a.center else (S / 2, S / 2)
    half = a.size / 2
    step = max(1, int(round(a.size / 700.0 / cell)))
    i0, i1 = max(0, int((cz - half) / cell)), min(n - 1, int((cz + half) / cell))
    j0, j1 = max(0, int((cx - half) / cell)), min(n - 1, int((cx + half) / cell))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    # ---------------- terreno
    rows = list(range(i0, i1 + 1, step))
    cols = list(range(j0, j1 + 1, step))
    bm = bmesh.new()
    vv = [[bm.verts.new(B(j * cell, h[i, j], i * cell)) for j in cols] for i in rows]
    uvw = bm.loops.layers.uv.new("World")
    uvs = bm.loops.layers.uv.new("Splat")
    for r in range(len(rows) - 1):
        for c in range(len(cols) - 1):
            f = bm.faces.new((vv[r][c], vv[r][c + 1], vv[r + 1][c + 1], vv[r + 1][c]))
            for lp in f.loops:
                ux, uz = -lp.vert.co.x, -lp.vert.co.y
                lp[uvw].uv = (ux, uz)
                lp[uvs].uv = (ux / S, uz / S)
    me = bpy.data.meshes.new("Terrain")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ter = bpy.data.objects.new("Terrain", me)
    sc.collection.objects.link(ter)
    me.materials.append(terrain_material(info, root, map_dir))
    # ---------------- agua
    for w in info.get("water", []):
        pts = np.array(w["points_xyz"], float).reshape(-1, 3)
        bmw = bmesh.new()
        ring = []
        for k, p in enumerate(pts):
            d = pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]
            side = np.array([-d[2], 0, d[0]]) / max(np.hypot(d[0], d[2]), 1e-6) * w["width"] / 2
            ring.append((bmw.verts.new(B(*(p - side))), bmw.verts.new(B(*(p + side)))))
        for (a0, b0), (a1, b1) in zip(ring[:-1], ring[1:]):
            bmw.faces.new((a0, a1, b1, b0))
        mw = bpy.data.meshes.new("River")
        bmw.to_mesh(mw)
        bmw.free()
        wm = bpy.data.materials.new("Water")
        if wm.node_tree is None:
            wm.use_nodes = True
        pb = next(nd for nd in wm.node_tree.nodes if nd.type == 'BSDF_PRINCIPLED')
        pb.inputs["Base Color"].default_value = (0.03, 0.09, 0.1, 1)
        pb.inputs["Roughness"].default_value = 0.04
        mw.materials.append(wm)
        ow = bpy.data.objects.new("River", mw)
        sc.collection.objects.link(ow)
    # ---------------- assets
    sel = [o for o in info["objects"] if abs(o["pos"][0] - cx) < half + 20 and abs(o["pos"][2] - cz) < half + 20 and not a.no_assets]
    trees = [o for o in sel if o["category"] == "Vegetation"]
    if len(trees) > a.max_trees:
        keep = set(id(o) for o in trees[::max(1, len(trees) // a.max_trees)])
        sel = [o for o in sel if o["category"] != "Vegetation" or id(o) in keep]
    templates = {}
    for o in sel:
        key = (o["fbx"], o["state"])
        if key not in templates:
            path = os.path.join(root, o["fbx"])
            templates[key] = load_template(path, o["name"], o["state"]) if os.path.exists(path) else None
        me_t = templates[key]
        if me_t is None:
            continue
        ob = bpy.data.objects.new(o["name"], me_t)
        ob.location = B(*o["pos"])
        ob.rotation_euler = (0, 0, -math.radians(o["yaw"]))
        sc.collection.objects.link(ob)
    print("objetos en el render: %d (%d mallas distintas)" % (len(sel), len(templates)))
    # ---------------- luz, cielo y camara
    world = bpy.data.worlds.new("World")
    sc.world = world
    if world.node_tree is None:
        world.use_nodes = True
    hdri = a.hdri
    if not hdri:
        for base in (os.path.join(root, "..", "ThirdParty"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "ThirdParty")):
            cand = os.path.join(base, "direct", "hdri_" + info.get("sky_hdri", ""), info.get("sky_hdri", "") + "_1k.hdr")
            if os.path.exists(cand):
                hdri = cand
                break
    bg = next(nd for nd in world.node_tree.nodes if nd.type == 'BACKGROUND')
    if hdri and os.path.exists(hdri):
        env = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(hdri)
        world.node_tree.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.9
    else:
        bg.inputs["Color"].default_value = (0.55, 0.65, 0.8, 1)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 3.2
    sun.data.angle = math.radians(1.5)
    pitch, yaw = info.get("sun", {}).get("pitch", 45), info.get("sun", {}).get("yaw", 130)
    sun.rotation_euler = (math.radians(90 - pitch), 0, math.radians(180 - yaw))
    sc.collection.objects.link(sun)
    az, el, dist = (float(v) for v in a.cam.split(","))
    dist = dist or a.size * 0.95
    tgt = B(cx, float(h[int(cz / cell), int(cx / cell)]), cz)
    d = Vector((math.sin(math.radians(az)), -math.cos(math.radians(az)), 0)) * math.cos(math.radians(el)) + Vector((0, 0, math.sin(math.radians(el))))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = tgt + d * dist
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = 32
    cam.data.clip_end = 20000
    sc.collection.objects.link(cam)
    sc.camera = cam
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = a.samples
    try:
        sc.cycles.use_denoising = True
    except Exception:
        pass
    rx, ry = (int(v) for v in a.res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.render.filepath = os.path.abspath(a.out or os.path.join(map_dir, info["map"] + "_render3d.png"))
    bpy.ops.render.render(write_still=True)
    print("render ->", sc.render.filepath)


if __name__ == "__main__":
    main()
