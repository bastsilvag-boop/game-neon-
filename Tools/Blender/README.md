# Fábrica de assets y mapas destructibles de guerra moderna (Blender → Unity)

Todo lo que generan estos scripts sale en `~/Unity_Destructible_Military/`. Copia esa carpeta **con ese nombre** dentro de `Assets/` de tu proyecto de Unity y el importador la configura sola.

| Script | Qué hace | Cómo se ejecuta |
|---|---|---|
| `generate_destructible_assets.py` | 102 assets propios con medidas reales: vehículos, aeronaves, artillería, edificios, fortificaciones, infraestructura de mapa, terreno y vegetación. Sale en 3 variantes (templado, desierto, invierno) y todo es destructible | `blender -b --python generate_destructible_assets.py -- [--out DIR] [--only A,B] [--variants Temperate]` |
| `fetch_free_assets.py` | Descarga modelos, texturas, cielos HDRI y relieve real **gratuitos con licencia libre** (dominio público, CC0, CC-BY) | `python fetch_free_assets.py` |
| `adapt_free_assets.py` | Lleva los modelos descargados al mismo sistema destructible: escala real, frente, piezas, estados, fragmentos, LODs y créditos | `blender -b --python adapt_free_assets.py -- --in ThirdParty --out DIR` |
| `generate_maps.py` | Crea 6 mapas de guerra jugables: relieve con erosión o DEM real, carreteras, río con puente, capas de textura, agujeros para trincheras y cientos de assets colocados | `python generate_maps.py --assets DIR` |
| `../Unity/DestructibleMilitary/` | Scripts de Unity: importador, componente de destrucción, explosiones de prueba y constructor de mapas | Copia la carpeta a `Assets/` |

## Qué incluye (v4)

- **Vehículos**: M1A2 SEPv3, Leopard 2A7, T-90M, T-72B3, M2A4 Bradley, CV90, BMP-2, M109A7, Gepard, ZSU-23-4 Shilka, Stryker, Boxer, BTR-82A, JLTV, HMMWV, M-ATV, FMTV, **Ural-4320**, technical con DShK, D9R blindado, sedán, **autobús urbano** y **camión de reparto**.
- **Aire y antiaérea**: AH-64E, UH-60M, Ka-52, **Mi-24P**, **Mi-8MTV**, AH-6, F-35A, MQ-9, **Bayraktar TB2**, Shahed-136, cuadricóptero, C-RAM y **radar sobre remolque**.
- **Artillería**: M777, **M142 HIMARS** y **BM-21 Grad**.
- **Edificios**: casas, bloque de 4 plantas, refugio HAS, compound de adobe, casa desértica, granero, **iglesia con campanario**, **mezquita con alminar**, **nave industrial**, **chimenea de 35 m** (se parte y cae como un árbol), **gasolinera**, **muro en ruinas** y **montones de escombro**.
- **Infraestructura de mapa**: calzada de 12 m, cruce, camino de tierra, torre de alta tensión, mástil atirantado de 40 m, depósito elevado, tanque de combustible, **puente de 3 vanos** (si cae una pila, cae el vano), helipuerto, tramo de pista, farola y valla publicitaria.
- **Militar y fortificación**: HESCO, T-wall, Jersey, erizos, dientes de dragón, concertina, búnker, torre, contenedor, trincheras recta y en zigzag, pozo de tirador, nido de ametralladora, refugio de troncos, **pozo de mortero de 81 mm**, **control de carretera**, **tienda GP Medium** y **red de camuflaje**.
- **Descargado y adaptado** (licencias verificadas):
  - NASA 3D Resources, sin copyright: **RQ-4 Global Hawk** repintado sin logotipos, **radomo de radar** y **antena de seguimiento**.
  - Khronos glTF Sample Assets: cono vial y ventana rota (CC-BY), farola antigua y casco de vuelo A-11 (CC0), y nevera de tienda y camión Cesium (CC-BY).
  - **11 cielos HDRI** CC0 de Poly Haven.
  - **DEM real del USGS del Monte St. Helens** (dominio público).

## Destrucción

Cada FBX contiene los estados `_Intact`, `_Damaged`, `_Destroyed`, `_Chunks_L1`, `_Chunks_L2`, `_Debris` y `_LODs`. Las propiedades `dst_*` incluyen masa, vida, clase de material, anclaje, vecinos, pivotes y ejes.

- **Estructuras**:
  - Fractura Voronoi exacta.
  - Mampostería que se rompe por las juntas.
  - Grafo de contacto: lo que se queda sin apoyo cae.
- **Vehículos**: pecio calcinado, torreta despedida y piezas que se desprenden por su eje.
- **Trincheras y pozos**: el manifiesto trae `terrain_holes` para recortar el Terrain de Unity.

## Flujo completo

1. **Opcional: más modelos y texturas.**
   ```
   python fetch_free_assets.py --per-query 2 --max-faces 80000
   ```
   - **Fuentes**:
     - `direct`: NASA, Khronos, HDRI y DEM.
     - `ambientcg`: texturas CC0.
     - `polyhaven`: modelos, texturas y HDRI CC0. Su [API](https://github.com/Poly-Haven/Public-API/blob/master/ToS.md) permite uso comercial y pide un User-Agent propio, que el script ya envía.
     - `polypizza`: necesita `POLYPIZZA_KEY`.
     - `sketchfab`: necesita `SKETCHFAB_TOKEN`, el token gratuito de tu cuenta.
   - **Licencias**: solo acepta dominio público, CC0 y CC-BY. Rechaza NC, ND y editorial; CC-BY-SA solo con `--allow-sa`.
   - Cada modelo queda en `ThirdParty/<fuente>/<id>/` con su `LICENSE.txt`, más `CREDITS.md` y `third_party_catalog.json`.
2. **Assets propios.** Las texturas fotoescaneadas descargadas sustituyen a las procedurales.
   ```
   blender -b --python generate_destructible_assets.py
   ```
3. **Adaptar lo descargado.** Los ajustes de cada modelo van en la ficha (`adapt`) o en `adapt_overrides.json`:
   ```
   blender -b --python adapt_free_assets.py -- --variants Temperate
   ```
   - Opciones: `length`, `length_axis` (`y`/`z`), `rot_z`, `forward`, `skip`, `cls`, `cls_map`, `repaint` y `max_tris` (por defecto 60 000).
   - Para aviones de una sola malla: `split_islands` + `regions` (separa alas y cola).
4. **Mapas.**
   ```
   python generate_maps.py --assets ~/Unity_Destructible_Military
   ```

| Mapa | Tamaño | Contenido |
|---|---|---|
| `Desert_Town_Outpost` | 1 km | Pueblo con zoco y mezquita, uadi seco, puesto de control, gasolinera, pecios y FOB con HESCO, torres, tiendas, redes, C-RAM y helipuerto |
| `Temperate_River_Valley` | 1 km | Valle erosionado, río con puente, pueblo con iglesia, campos, bosques, alta tensión y línea de frente (trincheras, nidos, pozos, concertina, refugios, carros en asentamiento), con bajas enemigas y cráteres |
| `Winter_Trench_Front` | 512 m, celda de 0.5 m | Dos líneas de trincheras enfrentadas, tierra de nadie con cráteres, aldea en ruinas y bosque nevado |
| `Urban_District_Ruins` | 512 m | Cuadrícula de calles modulares, 300 edificios (30 % dañados y 20 % destruidos), fábricas, iglesia, gasolinera, parques y barricadas |
| `Volcano_StHelens_DEM` | 6 km, relieve real | Sitio de radar en el cráter y FOB con Mi-8/Mi-24, Grad y Shilka/Gepard |
| `Desert_Airbase` | 1 km | Pista de 900 m, 3 HAS, F-35, MQ-9, TB2, Global Hawk, helipuertos, combustible, radar, C-RAM y perímetro |

Cada mapa sale en `Maps/<Mapa>/` con estos archivos:

- alturas `_height.raw` (16 bit) y `.png`;
- capas `_splat.raw` y `.png`;
- agujeros `_holes.raw`;
- `<Mapa>.json` con objetos, agua, sol, cielo y puntos de despliegue;
- `_preview.png` (mapa táctico).

## Unity (2021.3 LTS o posterior; Built-in, URP o HDRP)

1. Copia `Tools/Unity/DestructibleMilitary/` en `Assets/`.
2. Copia la carpeta generada `Unity_Destructible_Military/` en `Assets/` con ese mismo nombre.
3. El importador (`DestructibleMilitaryPostprocessor`) configura:
   - escala 1 y Read/Write;
   - las propiedades `dst_*` en el componente `DestructibleMeta`;
   - el componente `DestructibleAsset` en la raíz;
   - solo `_Intact` activo;
   - MeshCollider en los estados;
   - un LODGroup;
   - las texturas `Mat_X_D` / `Mat_X_N`.

   Si los FBX se importaron antes que las texturas, ejecuta **Tools > Destructible Military > Reimport Models**.
4. **Mapas**:
   - **Tools > War Maps > Build Map From JSON...** construye el mapa en la escena abierta: Terrain con capas y agujeros, prefabs en su estado (pecios y edificios dañados), río, sol, cielo HDRI y spawns.
   - **Build All Maps** crea una escena por mapa a partir de `maps_index.json`.
   - Para el cielo, importa los `.hdr` de `ThirdParty/hdri` o de `direct/hdri_*`.
5. **Probar la destrucción**:
   - Añade `ExplosionDamage` a la cámara, entra en Play y haz clic.
   - Por código: `ExplosionDamage.Explode(punto, radio, danio)` o `DestructibleAsset.ApplyDamage(...)`.
   - El daño va en las unidades de `dst_hp` (≈ masa × factor del material). Valores orientativos: obús de 155 mm ≈ 30 000; RPG ≈ 4 000.

## Licencias (importante)

- **Dominio público y CC0**: libres para cualquier uso, sin atribución obligatoria.
- **CC-BY**: libre, incluso para uso comercial, pero **la atribución es obligatoria**. Copia `CREDITS_ThirdParty.md` en los créditos del juego. Cada FBX adaptado lleva además `dst_title`, `dst_author`, `dst_license` y `dst_source`.
- **NASA**: sus modelos no tienen copyright, pero la insignia de la NASA no puede usarse para insinuar respaldo. Por eso el Global Hawk se repinta con `repaint`.
- **Marcas**: los nombres reales de vehículos y armas son marcas o designaciones. Para uso comercial, revísalos.
- **DEM**: el del Monte St. Helens es del USGS (dominio público).
