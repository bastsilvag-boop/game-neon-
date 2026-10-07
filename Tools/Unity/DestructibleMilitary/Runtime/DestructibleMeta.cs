using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace DestructibleMilitary
{
    /// <summary>
    /// Propiedades dst_* que generate_destructible_assets.py escribe en cada objeto del FBX
    /// (custom properties). El importador (DestructibleMilitaryPostprocessor) las copia aqui.
    /// Vectores en coordenadas locales de Unity "x,y,z"; listas separadas por comas.
    /// </summary>
    [DisallowMultipleComponent]
    public class DestructibleMeta : MonoBehaviour
    {
        public List<string> keys = new List<string>();
        public List<string> values = new List<string>();

        public bool Has(string key)
        {
            return keys.IndexOf(key) >= 0;
        }

        public string Get(string key, string fallback = "")
        {
            int i = keys.IndexOf(key);
            return i >= 0 ? values[i] : fallback;
        }

        public float GetFloat(string key, float fallback = 0f)
        {
            float v;
            return float.TryParse(Get(key), NumberStyles.Float, CultureInfo.InvariantCulture, out v) ? v : fallback;
        }

        public int GetInt(string key, int fallback = 0)
        {
            string s = Get(key);
            int v;
            if (int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out v)) return v;
            float f;
            return float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out f) ? Mathf.RoundToInt(f) : fallback;
        }

        public bool GetBool(string key)
        {
            string s = Get(key).Trim().ToLowerInvariant();
            return s == "1" || s == "true";
        }

        public Vector3 GetVector(string key, Vector3 fallback)
        {
            string[] p = Get(key).Split(',');
            if (p.Length != 3) return fallback;
            float x, y, z;
            if (!float.TryParse(p[0], NumberStyles.Float, CultureInfo.InvariantCulture, out x)) return fallback;
            if (!float.TryParse(p[1], NumberStyles.Float, CultureInfo.InvariantCulture, out y)) return fallback;
            if (!float.TryParse(p[2], NumberStyles.Float, CultureInfo.InvariantCulture, out z)) return fallback;
            return new Vector3(x, y, z);
        }

        public int[] GetInts(string key)
        {
            var list = new List<int>();
            foreach (string part in Get(key).Split(','))
            {
                int v;
                if (int.TryParse(part.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out v)) list.Add(v);
            }
            return list.ToArray();
        }

        public void Set(string key, string value)
        {
            int i = keys.IndexOf(key);
            if (i >= 0) values[i] = value;
            else
            {
                keys.Add(key);
                values.Add(value);
            }
        }
    }
}
