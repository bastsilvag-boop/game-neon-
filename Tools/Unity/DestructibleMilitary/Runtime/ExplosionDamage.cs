using System.Collections.Generic;
using UnityEngine;

namespace DestructibleMilitary
{
    /// <summary>
    /// Explosiones de prueba: Explode() reparte danio con caida lineal a los DestructibleAsset
    /// del radio. Anade este componente a la camara y haz clic para disparar (solo en Play).
    /// Danio orientativo (unidades dst_hp): granada 400, RPG 4000, obus 155 mm 30000, bomba 250 kg 120000.
    /// </summary>
    public class ExplosionDamage : MonoBehaviour
    {
        public float damage = 30000f;
        public float radius = 8f;
        public float chunkBreakRadius = 4f;
        public float maxDistance = 2000f;
        public LayerMask mask = ~0;

        void Update()
        {
            Vector3 mouse;
            if (!ClickThisFrame(out mouse)) return;
            var cam = GetComponent<Camera>() ? GetComponent<Camera>() : Camera.main;
            if (!cam) return;
            RaycastHit hit;
            if (Physics.Raycast(cam.ScreenPointToRay(mouse), out hit, maxDistance, mask))
                Explode(hit.point, radius, damage, chunkBreakRadius);
        }

        static bool ClickThisFrame(out Vector3 pos)
        {
#if ENABLE_INPUT_SYSTEM
            var m = UnityEngine.InputSystem.Mouse.current;
            pos = m != null ? (Vector3)m.position.ReadValue() : Vector3.zero;
            return m != null && m.leftButton.wasPressedThisFrame;
#elif ENABLE_LEGACY_INPUT_MANAGER
            pos = Input.mousePosition;
            return Input.GetMouseButtonDown(0);
#else
            pos = Vector3.zero;
            return false;
#endif
        }

        public static void Explode(Vector3 point, float radius, float damage, float chunkBreakRadius = 4f)
        {
            var done = new HashSet<DestructibleAsset>();
            foreach (var col in Physics.OverlapSphere(point, radius))
            {
                var da = col.GetComponentInParent<DestructibleAsset>();
                if (!da || !done.Add(da)) continue;
                float d = Vector3.Distance(point, col.bounds.ClosestPoint(point));   // valido tambien con MeshCollider no convexo
                float k = Mathf.Clamp01(1f - d / Mathf.Max(radius, 0.01f));
                da.ApplyDamage(damage * k, point, chunkBreakRadius);
            }
            foreach (var col in Physics.OverlapSphere(point, radius))
            {
                var rb = col.attachedRigidbody;
                if (rb && !rb.isKinematic) rb.AddExplosionForce(6f, point, radius, 0.5f, ForceMode.VelocityChange);
            }
        }
    }
}
