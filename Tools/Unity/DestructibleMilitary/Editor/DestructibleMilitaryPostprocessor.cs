using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace DestructibleMilitary.EditorTools
{
    /// <summary>
    /// Importador de los FBX de generate_destructible_assets.py / adapt_free_assets.py.
    /// Copia la carpeta de salida dentro de Assets conservando su nombre (por defecto
    /// "Unity_Destructible_Military"): todo lo que cuelga de ella se configura solo.
    ///  - Escala 1, Convert Units, Read/Write ON (MeshCollider de los chunks en runtime)
    ///  - dst_* (custom properties) -> componente DestructibleMeta en cada objeto
    ///  - raiz -> DestructibleAsset; solo el estado _Intact queda activo
    ///  - MeshCollider en los estados Intact/Damaged/Destroyed (estaticos)
    ///  - LODGroup: LOD0 = piezas intactas, LOD1/LOD2 = mallas *_LOD1/_LOD2 del grupo _LODs
    ///  - materiales Mat_*: albedo Textures/Mat_X_D.png + normal Textures/Mat_X_N.png
    /// Si importaste los FBX antes que las texturas: Tools > Destructible Military > Reimport Models.
    /// </summary>
    public class DestructibleMilitaryPostprocessor : AssetPostprocessor
    {
        public const string RootFolderName = "Unity_Destructible_Military";

        static bool IsOurs(string path)
        {
            return path.Replace('\\', '/').Contains("/" + RootFolderName + "/");
        }

        static string RootOf(string path)
        {
            path = path.Replace('\\', '/');
            int i = path.IndexOf("/" + RootFolderName + "/", StringComparison.Ordinal);
            return i < 0 ? null : path.Substring(0, i + RootFolderName.Length + 1);
        }

        void OnPreprocessModel()
        {
            if (!IsOurs(assetPath)) return;
            var mi = (ModelImporter)assetImporter;
            mi.globalScale = 1f;
            mi.useFileScale = true;
            mi.isReadable = true;
            mi.importBlendShapes = false;
            mi.importAnimation = false;
            mi.animationType = ModelImporterAnimationType.None;
            mi.importCameras = false;
            mi.importLights = false;
            mi.addCollider = false;
            mi.meshCompression = ModelImporterMeshCompression.Off;
        }

        void OnPreprocessTexture()
        {
            if (!IsOurs(assetPath)) return;
            var ti = (TextureImporter)assetImporter;
            string file = Path.GetFileNameWithoutExtension(assetPath);
            if (file.EndsWith("_N")) ti.textureType = TextureImporterType.NormalMap;
            if (assetPath.EndsWith(".hdr", StringComparison.OrdinalIgnoreCase)) ti.textureShape = TextureImporterShape.Texture2D;
            ti.mipmapEnabled = true;
            ti.anisoLevel = 4;
        }

        void OnPostprocessGameObjectWithUserProperties(GameObject go, string[] names, object[] values)
        {
            if (!IsOurs(assetPath)) return;
            DestructibleMeta meta = null;
            for (int i = 0; i < names.Length; i++)
            {
                if (!names[i].StartsWith("dst_")) continue;
                if (!meta)
                {
                    meta = go.GetComponent<DestructibleMeta>();          // sin '??': Unity usa nulos falsos
                    if (!meta) meta = go.AddComponent<DestructibleMeta>();
                }
                meta.Set(names[i], Convert.ToString(values[i], CultureInfo.InvariantCulture));
            }
        }

        void OnPostprocessMaterial(Material material)
        {
            if (!IsOurs(assetPath) || !material.name.StartsWith("Mat_")) return;
            string root = RootOf(assetPath);
            if (root == null) return;
            var d = AssetDatabase.LoadAssetAtPath<Texture2D>(root + "/Textures/" + material.name + "_D.png");
            var n = AssetDatabase.LoadAssetAtPath<Texture2D>(root + "/Textures/" + material.name + "_N.png");
            if (d)
            {
                if (material.HasProperty("_BaseMap")) material.SetTexture("_BaseMap", d);
                if (material.HasProperty("_MainTex")) material.SetTexture("_MainTex", d);
                if (material.HasProperty("_BaseColorMap")) material.SetTexture("_BaseColorMap", d);
                if (material.HasProperty("_BaseColor")) material.SetColor("_BaseColor", Color.white);
                if (material.HasProperty("_Color")) material.SetColor("_Color", Color.white);
            }
            if (n)
            {
                if (material.HasProperty("_BumpMap")) material.SetTexture("_BumpMap", n);
                if (material.HasProperty("_NormalMap")) material.SetTexture("_NormalMap", n);
                material.EnableKeyword("_NORMALMAP");
            }
        }

        void OnPostprocessModel(GameObject root)
        {
            if (!IsOurs(assetPath)) return;
            var meta = root.GetComponent<DestructibleMeta>();
            if (!meta || meta.Get("dst_role") != "asset") return;
            if (!root.GetComponent<DestructibleAsset>()) root.AddComponent<DestructibleAsset>();
            Transform intact = null, lods = null;
            foreach (Transform c in root.transform)
            {
                string n = c.name;
                bool state = n.EndsWith("_Intact") || n.EndsWith("_Damaged") || n.EndsWith("_Destroyed");
                if (state)
                    foreach (var mf in c.GetComponentsInChildren<MeshFilter>(true))
                        if (mf.sharedMesh && !mf.GetComponent<Collider>())
                            mf.gameObject.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
                if (n.EndsWith("_Intact")) intact = c;
                else if (n.EndsWith("_LODs")) lods = c;
                c.gameObject.SetActive(n.EndsWith("_Intact") || n.EndsWith("_LODs"));
            }
            BuildLods(root, intact, lods);
        }

        static void BuildLods(GameObject root, Transform intact, Transform lods)
        {
            if (!intact || !lods) return;
            var auto = lods.GetComponent<LODGroup>();
            if (auto) UnityEngine.Object.DestroyImmediate(auto);
            Renderer lod1 = null, lod2 = null;
            foreach (Transform c in lods)
            {
                var r = c.GetComponent<Renderer>();
                if (!r) continue;
                if (c.name.EndsWith("_LOD1")) lod1 = r;
                else if (c.name.EndsWith("_LOD2")) lod2 = r;
                else if (c.name.EndsWith("_LOD0")) c.gameObject.SetActive(false);   // LOD0 = las piezas intactas
            }
            var levels = new List<LOD> { new LOD(lod1 ? 0.35f : 0.02f, intact.GetComponentsInChildren<Renderer>(true)) };
            if (lod1) levels.Add(new LOD(lod2 ? 0.12f : 0.02f, new[] { lod1 }));
            if (lod2) levels.Add(new LOD(0.02f, new[] { lod2 }));
            var lg = root.GetComponent<LODGroup>();
            if (!lg) lg = root.AddComponent<LODGroup>();
            lg.SetLODs(levels.ToArray());
            lg.RecalculateBounds();
            if (!lod1 && !lod2) lods.gameObject.SetActive(false);
        }

        [MenuItem("Tools/Destructible Military/Reimport Models")]
        static void ReimportModels()
        {
            foreach (string guid in AssetDatabase.FindAssets("t:Model"))
            {
                string p = AssetDatabase.GUIDToAssetPath(guid);
                if (IsOurs(p)) AssetDatabase.ImportAsset(p, ImportAssetOptions.ForceUpdate);
            }
        }
    }
}
