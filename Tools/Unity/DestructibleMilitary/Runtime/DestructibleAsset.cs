using System.Collections.Generic;
using UnityEngine;

namespace DestructibleMilitary
{
    public enum DestructionState { Intact = 0, Damaged = 1, Destroyed = 2, Chunks = 3 }

    /// <summary>
    /// Controla los estados de un asset generado (Intact / Damaged / Destroyed / Chunks_L1 / Debris).
    /// - ApplyDamage(): resta vida (mismas unidades que dst_hp: ~kg x factor del material).
    /// - Estructuras: al llegar a 0 activa los chunks; los que estan en el radio salen despedidos y
    ///   el resto se sostiene por el grafo dst_neighbors desde los chunks anclados (BFS); lo que
    ///   queda sin apoyo cae. Los siguientes impactos siguen rompiendo (destruccion progresiva).
    /// - Vehiculos: pasa al pecio calcinado (Destroyed) y lanza los escombros (Debris).
    /// SetState() tambien funciona en el editor (lo usa WarMapBuilder para edificios danados/pecios).
    /// </summary>
    [DisallowMultipleComponent]
    public class DestructibleAsset : MonoBehaviour
    {
        [Tooltip("Estado al iniciar la escena (los mapas pueden empezar con edificios danados o pecios).")]
        public DestructionState initialState = DestructionState.Intact;
        [Tooltip("Vida total. <= 0: suma de dst_hp de las piezas intactas.")]
        public float maxHitPoints = 0f;
        [Range(0f, 1f)] public float damagedAt = 0.55f;
        [Tooltip("Estructuras: true = colapso fisico con chunks; false = ruina estatica (estado Destroyed).")]
        public bool physicalCollapse = true;
        [Tooltip("Velocidad (m/s) que reciben los chunks/escombros en el centro de la explosion.")]
        public float blastSpeed = 9f;
        public float chunkLifetime = 60f;
        public float debrisLifetime = 25f;

        public float HitPoints { get; private set; }
        public DestructionState State { get; private set; }
        public string Category { get; private set; }
        public string Mode { get; private set; }

        Transform intact, damaged, destroyed, chunksL1, debris, lods;
        LODGroup lodGroup;
        bool found;

        class Chunk
        {
            public Transform t;
            public int id;
            public bool anchored, free;
            public int[] nb;
            public float mass;
            public Vector3 center;
        }

        readonly List<Chunk> chunks = new List<Chunk>();
        readonly Dictionary<int, Chunk> byId = new Dictionary<int, Chunk>();

        void FindGroups()
        {
            if (found) return;
            found = true;
            foreach (Transform c in transform)
            {
                string n = c.name;
                if (n.EndsWith("_Intact")) intact = c;
                else if (n.EndsWith("_Damaged")) damaged = c;
                else if (n.EndsWith("_Destroyed")) destroyed = c;
                else if (n.EndsWith("_Chunks_L1")) chunksL1 = c;
                else if (n.EndsWith("_Debris")) debris = c;
                else if (n.EndsWith("_LODs")) lods = c;
            }
            var meta = GetComponent<DestructibleMeta>();
            Category = meta ? meta.Get("dst_category") : "";
            Mode = meta ? meta.Get("dst_mode") : "";
            lodGroup = GetComponent<LODGroup>();
        }

        void Awake()
        {
            FindGroups();
            if (maxHitPoints <= 0f) maxHitPoints = ComputeHitPoints();
            HitPoints = initialState == DestructionState.Intact ? maxHitPoints : initialState == DestructionState.Damaged ? maxHitPoints * damagedAt : 0f;
            SetState(initialState);
        }

        float ComputeHitPoints()
        {
            float hp = 0f;
            if (intact)
                foreach (var m in intact.GetComponentsInChildren<DestructibleMeta>(true))
                    hp += m.GetFloat("dst_hp", 0f);
            if (hp <= 0f)
            {
                var meta = GetComponent<DestructibleMeta>();
                float mass = meta ? meta.GetFloat("dst_mass", 1000f) : 1000f;
                hp = Mathf.Max(50f, mass * 0.4f);
            }
            return hp;
        }

        static void Show(Transform t, bool on)
        {
            if (t && t.gameObject.activeSelf != on) t.gameObject.SetActive(on);
        }

        /// <summary>Cambia el estado visible. Valido en editor y en juego.</summary>
        public void SetState(DestructionState s)
        {
            FindGroups();
            if (s == DestructionState.Damaged && !damaged) s = DestructionState.Intact;
            if (s == DestructionState.Chunks && !chunksL1) s = DestructionState.Destroyed;
            if (s == DestructionState.Destroyed && !destroyed) s = chunksL1 ? DestructionState.Chunks : DestructionState.Intact;
            State = s;
            Show(intact, s == DestructionState.Intact);
            Show(damaged, s == DestructionState.Damaged);
            Show(destroyed, s == DestructionState.Destroyed);
            Show(chunksL1, s == DestructionState.Chunks);
            if (debris && s == DestructionState.Intact) Show(debris, false);
            if (lodGroup) lodGroup.enabled = s == DestructionState.Intact;
            Show(lods, s == DestructionState.Intact && lodGroup != null);
        }

        /// <summary>Danio puntual o de area. point en mundo; radius = radio de rotura de chunks.</summary>
        public void ApplyDamage(float amount, Vector3 point, float radius = 3f)
        {
            FindGroups();
            if (State == DestructionState.Chunks)
            {
                BreakChunks(point, radius, blastSpeed);
                return;
            }
            if (State == DestructionState.Destroyed) return;
            HitPoints -= amount;
            if (HitPoints <= 0f) Kill(point, radius);
            else if (HitPoints <= maxHitPoints * damagedAt && State == DestructionState.Intact) SetState(DestructionState.Damaged);
        }

        public void Kill(Vector3 point, float radius = 3f)
        {
            HitPoints = 0f;
            bool vehicle = Mode == "vehicle";
            if (!vehicle && physicalCollapse && chunksL1)
            {
                SetState(DestructionState.Chunks);
                BreakChunks(point, radius, blastSpeed);
            }
            else SetState(DestructionState.Destroyed);
            LaunchDebris(point);
        }

        void BuildChunks()
        {
            chunks.Clear();
            byId.Clear();
            if (!chunksL1) return;
            foreach (Transform c in chunksL1)
            {
                var m = c.GetComponent<DestructibleMeta>();
                if (!m) continue;
                var ch = new Chunk
                {
                    t = c, id = m.GetInt("dst_id", chunks.Count), anchored = m.GetBool("dst_anchored"),
                    nb = m.GetInts("dst_neighbors"), mass = Mathf.Max(1f, m.GetFloat("dst_mass", 25f))
                };
                var b = new Bounds(c.position, Vector3.zero);
                bool any = false;
                foreach (var r in c.GetComponentsInChildren<Renderer>(true))
                {
                    if (!any) { b = r.bounds; any = true; }
                    else b.Encapsulate(r.bounds);
                }
                ch.center = b.center;
                foreach (var mf in c.GetComponentsInChildren<MeshFilter>(true))
                {
                    if (mf.GetComponent<Collider>() || !mf.sharedMesh) continue;
                    var mc = mf.gameObject.AddComponent<MeshCollider>();
                    mc.sharedMesh = mf.sharedMesh;
                    mc.convex = true;
                }
                chunks.Add(ch);
                byId[ch.id] = ch;
            }
        }

        void BreakChunks(Vector3 point, float radius, float speed)
        {
            if (chunks.Count == 0) BuildChunks();
            foreach (var ch in chunks)
                if (!ch.free && Vector3.Distance(ch.center, point) <= radius) Free(ch, point, radius, speed);
            // soporte: BFS desde los anclados por el grafo de contacto; lo no alcanzado cae
            var reached = new HashSet<int>();
            var q = new Queue<Chunk>();
            foreach (var ch in chunks)
                if (!ch.free && ch.anchored && reached.Add(ch.id)) q.Enqueue(ch);
            while (q.Count > 0)
            {
                var c = q.Dequeue();
                foreach (int n in c.nb)
                {
                    Chunk o;
                    if (byId.TryGetValue(n, out o) && !o.free && reached.Add(o.id)) q.Enqueue(o);
                }
            }
            foreach (var ch in chunks)
                if (!ch.free && !reached.Contains(ch.id)) Free(ch, point, radius * 3f, speed * 0.15f);
        }

        void Free(Chunk ch, Vector3 point, float radius, float speed)
        {
            ch.free = true;
            var rb = ch.t.GetComponent<Rigidbody>();
            if (!rb) rb = ch.t.gameObject.AddComponent<Rigidbody>();
            rb.mass = ch.mass;
            rb.isKinematic = false;
            rb.interpolation = RigidbodyInterpolation.Interpolate;
            rb.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            if (speed > 0f) rb.AddExplosionForce(speed, point, Mathf.Max(radius, 0.5f) * 2f, 0.4f, ForceMode.VelocityChange);
            if (chunkLifetime > 0f && Application.isPlaying) Destroy(ch.t.gameObject, chunkLifetime + Random.Range(0f, 8f));
        }

        void LaunchDebris(Vector3 point)
        {
            if (!debris || !Application.isPlaying) return;
            Show(debris, true);
            foreach (Transform d in debris)
            {
                foreach (var mf in d.GetComponentsInChildren<MeshFilter>(true))
                {
                    if (mf.GetComponent<Collider>() || !mf.sharedMesh) continue;
                    var mc = mf.gameObject.AddComponent<MeshCollider>();
                    mc.sharedMesh = mf.sharedMesh;
                    mc.convex = true;
                }
                var meta = d.GetComponent<DestructibleMeta>();
                var rb = d.GetComponent<Rigidbody>();
                if (!rb) rb = d.gameObject.AddComponent<Rigidbody>();
                rb.mass = meta ? Mathf.Max(0.5f, meta.GetFloat("dst_mass", 5f)) : 5f;
                rb.AddExplosionForce(blastSpeed, point, 12f, 0.8f, ForceMode.VelocityChange);
                if (debrisLifetime > 0f) Destroy(d.gameObject, debrisLifetime + Random.Range(0f, 5f));
            }
        }
    }
}
