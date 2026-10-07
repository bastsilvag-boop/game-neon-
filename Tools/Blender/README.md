# Fábrica de assets destructibles de guerra moderna (Blender → Unity)

Tres scripts que trabajan juntos. Todo lo que generan sale en `~/Unity_Destructible_Military/`, listo para arrastrarlo a Unity.

| Script | Qué hace | Cómo se ejecuta |
|---|---|---|
| `generate_destructible_assets.py` | Genera 68 assets propios (vehículos con medidas reales, edificios, fortificaciones, terreno, vegetación) en 3 variantes: templado, desierto e invierno | `blender --background --python generate_destructible_assets.py` |
| `fetch_free_assets.py` | Busca y descarga modelos **gratuitos con licencia libre (CC0 / CC-BY)** de guerra moderna y texturas fotoescaneadas CC0 | `python fetch_free_assets.py` |
| `adapt_free_assets.py` | Convierte los modelos descargados al mismo pipeline destructible: escala real, orientación, piezas, estados, fragmentos, LODs y créditos | `blender --background --python adapt_free_assets.py` |

## Flujo recomendado

1. **Claves gratuitas** (solo para las fuentes que las piden):
   - Sketchfab: crea una cuenta y copia tu *API token* de <https://sketchfab.com/settings/password>.
     Ponlo en la variable de entorno `SKETCHFAB_TOKEN`.
   - Poly Pizza: pide una key en <https://poly.pizza/settings/api> y ponla en `POLYPIZZA_KEY`.
   - ambientCG (texturas) no necesita clave.
2. **Descarga**:
   ```
   python fetch_free_assets.py --per-query 2 --max-faces 80000
   ```
   - Busca unas 100 categorías: carros, IFV/APC, artillería, antiaérea, helicópteros, cazas, drones, armas de infantería, fortificaciones, props, ruinas y soldados.
   - Solo acepta CC0 y CC-BY. Rechaza NC, ND y editorial; CC-BY-SA únicamente si pasas `--allow-sa`.
   - Guarda cada modelo en `ThirdParty/<fuente>/<id>/` junto con su `LICENSE.txt`. También crea `ThirdParty/CREDITS.md` y `third_party_catalog.json`.
3. **Adaptación**:
   ```
   blender --background --python adapt_free_assets.py -- --variants Temperate,Winter
   ```
   Para corregir un modelo concreto (escala, giro, frente, piezas que hay que ignorar), añade una entrada en `adapt_overrides.json`, por ejemplo:
   ```json
   {"sketchfab_0123abcd...": {"length": 9.53, "rot_z": 90, "forward": "+Y", "skip": ["display_base"]}}
   ```
4. **Regenera los assets propios**. Si descargaste texturas de ambientCG, el generador las usa automáticamente en lugar de las procedurales.

## Licencias (importante)

- **CC0**: libre para cualquier uso, sin atribución.
- **CC-BY**: libre, incluso para uso comercial, pero **la atribución es obligatoria**. Incluye `CREDITS_ThirdParty.md` en los créditos del juego. Cada FBX adaptado lleva también `dst_title`, `dst_author`, `dst_license` y `dst_source`.
- Los nombres reales de vehículos y armas son marcas o designaciones. Para uso comercial, revisa las marcas y los logotipos (por ejemplo, el logo del camión de ejemplo de Khronos).
- La API de Poly Haven exige una licencia para proyectos comerciales, así que no se usa por defecto. Sus assets (CC0) pueden descargarse a mano desde la web.

## Unity

- **Importación**: Scale Factor 1 y Convert Units activado. Activa Read/Write en los FBX que tengan fragmentos.
- **Texturas**: las de los assets propios se buscan en `Textures/`. Los modelos adaptados llevan las suyas embebidas en el FBX.
- **Al instanciar**: deja activo solo `<Asset>_Intact`. Cuando llegue el daño, cambia a `_Damaged`, `_Destroyed` o `_Chunks_L1`.
- **Física de los fragmentos**: usa Rigidbody + MeshCollider convex, con la masa `dst_mass`.
- **Colapso estructural**: el grafo `dst_neighbors` permite calcularlo con un BFS que parte de los fragmentos `dst_anchored`; lo que no quede conectado cae.
