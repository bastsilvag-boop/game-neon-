using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace DestructibleMilitary.EditorTools
{
    /// <summary>
    /// Construye en la escena abierta un mapa de generate_maps.py: Terrain (alturas RAW 16 bit,
    /// 4 capas, agujeros para trincheras), objetos destructibles en su estado (Intact/Damaged/
    /// Destroyed), agua de rios, sol, cielo HDRI y puntos de despliegue.
    /// La carpeta de salida debe estar dentro de Assets con su nombre original
    /// (Assets/.../Unity_Destructible_Military/Maps/&lt;Mapa&gt;/&lt;Mapa&gt;.json).
    /// </summary>
    public static class WarMapBuilder
    {
#pragma warning disable 0649    // campos rellenados por JsonUtility
        [Serializable] class TerrainInfo
        {
            public float[] size; public float[] position; public int heightmap_resolution; public string heightmap_raw;
            public int alphamap_resolution; public string splat_raw; public string holes_raw;
        }
        [Serializable] class LayerInfo { public string material; public string diffuse; public string normal; public float tile_m; }
        [Serializable] class SunInfo { public float pitch; public float yaw; public float intensity; }
        [Serializable] class ObjInfo
        {
            public string asset; public string name; public string fbx; public string variant; public string category;
            public float[] pos; public float yaw; public string state; public float[] up;
        }
        [Serializable] class WaterInfo { public string type; public float width; public float[] points_xyz; }
        [Serializable] class SpawnInfo { public string team; public float[] pos; }
        [Serializable] class MapInfo
        {
            public string map; public string description; public string variant; public TerrainInfo terrain; public LayerInfo[] layers;
            public SunInfo sun; public string sky_hdri; public WaterInfo[] water; public SpawnInfo[] spawns; public ObjInfo[] objects;
        }
        [Serializable] class IndexRow { public string map; public string json; }
        [Serializable] class IndexInfo { public IndexRow[] rows; }
#pragma warning restore 0649

        [MenuItem("Tools/War Maps/Build Map From JSON...")]
        static void BuildMenu()
        {
            string path = EditorUtility.OpenFilePanel("Mapa de guerra (.json)", Application.dataPath, "json");
            if (!string.IsNullOrEmpty(path)) Build(path, true);
        }

        [MenuItem("Tools/War Maps/Build All Maps (one scene each)")]
        static void BuildAll()
        {
            string idx = EditorUtility.OpenFilePanel("maps_index.json", Application.dataPath, "json");
            if (string.IsNullOrEmpty(idx)) return;
            var rows = JsonUtility.FromJson<IndexInfo>("{\"rows\":" + File.ReadAllText(idx) + "}").rows;
            string dir = Path.GetDirectoryName(idx);
            foreach (var r in rows)
            {
                var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                Build(Path.Combine(dir, r.json), false);
                string scenePath = ToAssetPath(Path.Combine(dir, r.map, r.map + ".unity"));
                if (scenePath != null) EditorSceneManager.SaveScene(scene, scenePath);
            }
        }

        static string ToAssetPath(string full)
        {
            full = Path.GetFullPath(full).Replace('\\', '/');
            string data = Path.GetFullPath(Application.dataPath).Replace('\\', '/');
            return full.StartsWith(data) ? "Assets" + full.Substring(data.Length) : null;
        }

        public static GameObject Build(string jsonPath, bool undo)
        {
            var info = JsonUtility.FromJson<MapInfo>(File.ReadAllText(jsonPath));
            string mapDir = Path.GetDirectoryName(Path.GetFullPath(jsonPath));
            string rootDir = Path.GetFullPath(Path.Combine(mapDir, "..", ".."));
            string mapAsset = ToAssetPath(mapDir), rootAsset = ToAssetPath(rootDir);
            if (mapAsset == null || rootAsset == null)
            {
                EditorUtility.DisplayDialog("War Maps", "Copia la carpeta Unity_Destructible_Military dentro de Assets antes de construir.", "OK");
                return null;
            }
            var t = info.terrain;
            int res = t.heightmap_resolution, ares = t.alphamap_resolution;
            try
            {
                EditorUtility.DisplayProgressBar("War Maps", "Terreno " + info.map, 0.05f);
                var td = new TerrainData();
                td.heightmapResolution = res;
                td.size = new Vector3(t.size[0], t.size[1], t.size[2]);
                byte[] raw = File.ReadAllBytes(Path.Combine(mapDir, t.heightmap_raw));
                var h = new float[res, res];
                for (int i = 0; i < res; i++)
                    for (int j = 0; j < res; j++)
                    {
                        int k = (i * res + j) * 2;
                        h[i, j] = (raw[k] | (raw[k + 1] << 8)) / 65535f;
                    }
                td.SetHeights(0, 0, h);
                // capas
                var layers = new List<TerrainLayer>();
                for (int l = 0; l < info.layers.Length; l++)
                {
                    var li = info.layers[l];
                    var tl = new TerrainLayer
                    {
                        diffuseTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(rootAsset + "/" + li.diffuse),
                        normalMapTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(rootAsset + "/" + li.normal),
                        tileSize = new Vector2(li.tile_m, li.tile_m)
                    };
                    string lp = mapAsset + "/" + info.map + "_Layer" + l + "_" + li.material + ".terrainlayer";
                    AssetDatabase.CreateAsset(tl, AssetDatabase.GenerateUniqueAssetPath(lp));
                    layers.Add(tl);
                }
                td.terrainLayers = layers.ToArray();
                td.alphamapResolution = ares;
                byte[] sp = File.ReadAllBytes(Path.Combine(mapDir, t.splat_raw));
                int nl = Mathf.Min(4, layers.Count);
                var am = new float[ares, ares, nl];
                for (int i = 0; i < ares; i++)
                    for (int j = 0; j < ares; j++)
                    {
                        int k = (i * ares + j) * 4;
                        float sum = 0f;
                        for (int l = 0; l < nl; l++) sum += sp[k + l];
                        for (int l = 0; l < nl; l++) am[i, j, l] = sum > 0 ? sp[k + l] / sum : (l == 0 ? 1f : 0f);
                    }
                td.SetAlphamaps(0, 0, am);
                if (!string.IsNullOrEmpty(t.holes_raw) && File.Exists(Path.Combine(mapDir, t.holes_raw)))
                {
                    byte[] ho = File.ReadAllBytes(Path.Combine(mapDir, t.holes_raw));
                    int hr = td.holesResolution;
                    var holes = new bool[hr, hr];
                    for (int i = 0; i < hr; i++)
                        for (int j = 0; j < hr; j++)
                            holes[i, j] = i >= ares || j >= ares || ho[i * ares + j] != 0;
                    td.SetHoles(0, 0, holes);
                }
                AssetDatabase.CreateAsset(td, AssetDatabase.GenerateUniqueAssetPath(mapAsset + "/" + info.map + "_TerrainData.asset"));
                var root = new GameObject(info.map);
                if (undo) Undo.RegisterCreatedObjectUndo(root, "Build war map");
                var terrainGo = Terrain.CreateTerrainGameObject(td);
                terrainGo.name = info.map + "_Terrain";
                terrainGo.transform.SetParent(root.transform, false);
                terrainGo.transform.position = new Vector3(t.position[0], t.position[1], t.position[2]);
                var terrain = terrainGo.GetComponent<Terrain>();
                Shader ts = FindShader("Universal Render Pipeline/Terrain/Lit", "HDRP/TerrainLit");
                if (ts) terrain.materialTemplate = new Material(ts);
                terrain.heightmapPixelError = 4f;
                terrain.basemapDistance = 600f;
                // objetos
                var groups = new Dictionary<string, Transform>();
                var cache = new Dictionary<string, GameObject>();
                var missing = new HashSet<string>();
                int n = info.objects != null ? info.objects.Length : 0;
                for (int o = 0; o < n; o++)
                {
                    var ob = info.objects[o];
                    if (o % 50 == 0) EditorUtility.DisplayProgressBar("War Maps", "Objetos " + o + "/" + n, 0.2f + 0.75f * o / Mathf.Max(1, n));
                    GameObject prefab;
                    if (!cache.TryGetValue(ob.fbx, out prefab))
                    {
                        prefab = AssetDatabase.LoadAssetAtPath<GameObject>(rootAsset + "/" + ob.fbx);
                        cache[ob.fbx] = prefab;
                    }
                    if (!prefab) { missing.Add(ob.fbx); continue; }
                    Transform parent;
                    if (!groups.TryGetValue(ob.category, out parent))
                    {
                        parent = new GameObject(ob.category).transform;
                        parent.SetParent(root.transform, false);
                        groups[ob.category] = parent;
                    }
                    var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab, parent);
                    go.transform.position = new Vector3(ob.pos[0], ob.pos[1], ob.pos[2]);
                    var rotq = Quaternion.Euler(0f, ob.yaw, 0f);
                    if (ob.up != null && ob.up.Length == 3) rotq = Quaternion.FromToRotation(Vector3.up, new Vector3(ob.up[0], ob.up[1], ob.up[2])) * rotq;
                    go.transform.rotation = rotq;
                    var da = go.GetComponent<DestructibleAsset>();
                    if (da)
                    {
                        DestructionState st;
                        if (Enum.TryParse(ob.state, out st) && st != DestructionState.Intact)
                        {
                            da.initialState = st;
                            da.SetState(st);
                        }
                    }
                }
                // agua
                if (info.water != null)
                    foreach (var w in info.water) BuildWater(root.transform, w, mapAsset + "/" + info.map);
                // sol y cielo
                Light sun = null;
#if UNITY_2023_1_OR_NEWER
                var lights = UnityEngine.Object.FindObjectsByType<Light>(FindObjectsSortMode.None);
#else
                var lights = UnityEngine.Object.FindObjectsOfType<Light>();
#endif
                foreach (var l in lights)
                    if (l.type == LightType.Directional) { sun = l; break; }
                if (!sun)
                {
                    sun = new GameObject("Sun").AddComponent<Light>();
                    sun.type = LightType.Directional;
                }
                if (info.sun != null)
                {
                    sun.transform.rotation = Quaternion.Euler(info.sun.pitch, info.sun.yaw, 0f);
                    sun.intensity = info.sun.intensity;
                }
                sun.shadows = LightShadows.Soft;
                if (!string.IsNullOrEmpty(info.sky_hdri))
                {
                    foreach (string guid in AssetDatabase.FindAssets(info.sky_hdri + " t:Texture"))
                    {
                        var tex = AssetDatabase.LoadAssetAtPath<Texture>(AssetDatabase.GUIDToAssetPath(guid));
                        Shader sky = Shader.Find("Skybox/Panoramic");
                        if (!tex || !sky) continue;
                        var m = new Material(sky);
                        m.SetTexture("_MainTex", tex);
                        AssetDatabase.CreateAsset(m, AssetDatabase.GenerateUniqueAssetPath(mapAsset + "/" + info.map + "_Sky.mat"));
                        RenderSettings.skybox = m;
                        DynamicGI.UpdateEnvironment();
                        break;
                    }
                }
                if (info.spawns != null)
                    foreach (var s in info.spawns)
                    {
                        var g = new GameObject("Spawn_" + s.team);
                        g.transform.SetParent(root.transform, false);
                        g.transform.position = new Vector3(s.pos[0], s.pos[1] + 1f, s.pos[2]);
                    }
                AssetDatabase.SaveAssets();
                EditorSceneManager.MarkSceneDirty(root.scene);
                if (missing.Count > 0)
                    Debug.LogWarning("War Maps: no se encontraron " + missing.Count + " FBX (genera esos assets o variantes): " + string.Join(", ", missing));
                Debug.Log("War Maps: " + info.map + " construido con " + n + " objetos. " + info.description);
                return root;
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }
        }

        static Shader FindShader(params string[] names)
        {
            foreach (string n in names)
            {
                Shader s = Shader.Find(n);
                if (s) return s;
            }
            return null;
        }

        static void BuildWater(Transform parent, WaterInfo w, string assetBase)
        {
            if (w.points_xyz == null || w.points_xyz.Length < 6) return;
            int n = w.points_xyz.Length / 3;
            var pts = new Vector3[n];
            for (int i = 0; i < n; i++) pts[i] = new Vector3(w.points_xyz[i * 3], w.points_xyz[i * 3 + 1], w.points_xyz[i * 3 + 2]);
            var verts = new Vector3[n * 2];
            var uvs = new Vector2[n * 2];
            var tris = new int[(n - 1) * 6];
            float along = 0f;
            for (int i = 0; i < n; i++)
            {
                Vector3 d = pts[Mathf.Min(i + 1, n - 1)] - pts[Mathf.Max(i - 1, 0)];
                d.y = 0f;
                Vector3 side = Vector3.Cross(Vector3.up, d.normalized) * (w.width * 0.5f);
                verts[i * 2] = pts[i] - side;
                verts[i * 2 + 1] = pts[i] + side;
                if (i > 0) along += Vector3.Distance(pts[i], pts[i - 1]);
                uvs[i * 2] = new Vector2(0f, along / w.width);
                uvs[i * 2 + 1] = new Vector2(1f, along / w.width);
                if (i < n - 1)
                {
                    int k = i * 6, a = i * 2;
                    tris[k] = a; tris[k + 1] = a + 2; tris[k + 2] = a + 1;
                    tris[k + 3] = a + 1; tris[k + 4] = a + 2; tris[k + 5] = a + 3;
                }
            }
            var mesh = new Mesh { name = "River", indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
            mesh.vertices = verts;
            mesh.uv = uvs;
            mesh.triangles = tris;
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            AssetDatabase.CreateAsset(mesh, AssetDatabase.GenerateUniqueAssetPath(assetBase + "_River.asset"));
            var go = new GameObject("Water_" + w.type);
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            Shader sh = FindShader("Universal Render Pipeline/Lit", "HDRP/Lit", "Standard");
            var mat = new Material(sh) { name = "Mat_Water_River" };
            Color c = new Color(0.08f, 0.2f, 0.24f, 1f);
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", c);
            if (mat.HasProperty("_Color")) mat.SetColor("_Color", c);
            if (mat.HasProperty("_Smoothness")) mat.SetFloat("_Smoothness", 0.95f);
            if (mat.HasProperty("_Glossiness")) mat.SetFloat("_Glossiness", 0.95f);
            AssetDatabase.CreateAsset(mat, AssetDatabase.GenerateUniqueAssetPath(assetBase + "_Water.mat"));
            go.AddComponent<MeshRenderer>().sharedMaterial = mat;
        }
    }
}
