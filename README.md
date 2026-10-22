# StrandForge

Blender 5.x-extension för stiliserat, semi-realistiskt mesh-hår: rita slingor som kurvor, forma tvärsnitt och bredd längs slingan, och låt Geometry Nodes generera sekundära detaljslingor som följer formen.

Status: **v0.1 – Clump Designer** (Core Hair Modeling + första versionen av Secondary Strands).

## Installera

**Zip:** bygg och installera via *Edit → Preferences → Get Extensions → Install from Disk*:

```
blender --command extension build --source-dir strandforge --output-dir dist
```

**Utveckling (live-redigering):** länka källmappen in i Blenders extension-katalog och starta om Blender:

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\5.2\extensions\user_default\strandforge" -Target "C:\Users\Johan\dev\strandforge\strandforge"
```

## Arbetsflöde

1. **N-panel → StrandForge** – välj huvudmesh, *Create Hair Project*.
2. **Add Region** (Bangs, Ponytail …) – varje region är ett hår-`Curves`-objekt med en delad GN-modifier.
3. **Create → Draw Strand** – `Surface` (längs huvudet), `Free` (rot på huvudet, resten på vyplan), `Extend` (fortsätt närmaste spets). Dra med LMB, Enter/Esc avslutar.
4. Forma i **Edit/Sculpt** (Blenders inbyggda Comb, Puff, Pinch, Smooth, Length …).
5. **Shape** – bredd, bredd längs slingan (Natural/Full/Sharp), tvärsnitt rot→spets, twist.
6. **Detail** – sekundära slingor, distributionsläge (Parallel/Flow/Organic), Draft/Preview/Final.
7. **Export → Bake to Mesh** – separat meshkopia i full detalj; kurvorna finns kvar.

`Alt+W` i 3D-vyn öppnar snabbmenyn (kan ändras under Preferences → Keymap).

## Arkitektur

| Del | Fil |
|---|---|
| Delat GN-träd `SF_HairStrand` (byggs från Python, versionerat) | `geometry/node_hair.py` |
| Hjälp-DSL för nodbygge | `geometry/builder.py` |
| Modifier-inputs via namn (5.2-API:t `mod.properties.inputs`) | `core/modifier.py` |
| Projekt, regioner, scenproperties | `core/project.py` |
| Läsa/skriva kurvor, markering, duplicering | `core/strands.py` |
| Inbyggda presets | `core/presets.py` |
| Operatorer | `operators/` |
| UI (en panel, fem flikar + snabbmeny) | `ui/panels.py` |

**Data per slinga** (curve-domän): `sf_preset` (0 = regionens inställningar, 1–6 = inbyggd preset), `sf_width_offset` (bredd = 1 + offset).
**Utdata:** mesh med `UVMap` (U runt slingan, V längs den) och `sf_v` (0 vid rot → 1 vid spets) för material.

Geometrin: kurvorna samplas om, får en minimum-twist-ram som roteras så att tjockleksaxeln pekar ut från hårbottens normal vid roten, och sveps med en egen superellips-profil (sharpness, teardrop, asymmetri, platt undersida) som interpoleras rot→spets. Sekundära slingor placeras i huvudslingans koordinater (längdposition, vinkel runt profilen) och följer därför med när huvudformen ändras.

När `TREE_VERSION` i `node_hair.py` höjs byggs trädet om automatiskt och befintliga modifier-värden flyttas över via namn.

## Tester

```
blender --background --factory-startup --python tests/test_nodes.py      # nodträdet
blender --background --factory-startup --python tests/test_addon.py      # operatorer end-to-end
blender --factory-startup --enable-event-simulate --python tests/ui_draw_test.py   # Draw Strand med simulerad mus
blender --factory-startup --python tests/ui_screenshots.py -- <mapp>     # skärmdumpar av alla flikar
blender --background --factory-startup --python tests/render_preview.py -- out.png SOFT_CLUMP
```

## Nästa steg (enligt specen)

- v0.2: Surface Strand/Micro Detail, Flyaway-generator, detaljmasker, auto-fallback vid redigering.
- v0.3: materialpresets, bakning av normal/AO, frisyrbibliotek med thumbnails.
- v1.0: benkedjor och vikter från kurvor, LOD via GN-parametrar, validering och Unreal-export.
