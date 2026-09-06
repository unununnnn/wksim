# Prometheus P450 asset preparation

The preparation CLI is `tools/prepare_p450_asset.py`. By default it reads only
local Git objects at fixed commit `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce` of
amov-lab/Prometheus. Explicit `--fetch-missing` permits downloading only the three
known STL paths from `https://raw.githubusercontent.com/amov-lab/Prometheus/`
followed by that commit and the exact source path, only when Git reports the
blob missing. SDF, model.config and LICENSE remain local Git reads.
Downloads reject redirects, enforce a 128 MiB limit, use a 10-second socket
timeout and a 45-second elapsed budget checked between reads, and verify the
Git blob SHA1 before parsing. A pending socket operation may extend the elapsed
budget by its timeout. There are no automatic retries. Git automatic fetching
remains disabled; downloads are never inserted into the Git object database.
The CLI does not expand the sparse checkout, change Git configuration, import
into UE, or change simulation physics or placement.

## Verified source inventory

Paths below are relative to
`Simulator/gazebo_simulator/gazebo_models/uav_models/p450/`, except root LICENSE.
The exact entries were verified with `git ls-tree` at the pinned commit.

| Source | Git blob |
| --- | --- |
| meshes/p450.stl | d8deef5854cc0568ff64cd5892130a349aaec71f |
| meshes/p450_ccw.stl | bb5753c6e2d37acee9adf6a049377538fab1b594 |
| meshes/p450_cw.stl | 8c78676df1f48fc8f84bcd0c060ba3050b28e355 |
| p450.sdf | 95104093b5480618073f6bb151eaab75ca2aba37 |
| model.config | 1f13c5c4cd7a54c4c455b6ff4460411994d36dca |
| root LICENSE | 7a61a72408bdc8967b8289d630a309e47b816fa7 |

The actual SDF, model.config and root LICENSE were read from Git. model.config
identifies version 1.0, author BOSHEN97, and describes the AMOVLAB P450. Root
LICENSE contains Apache License 2.0 and Copyright 2022 AMOVLAB. The model tree
contains no separate license. An inventory of the gazebo_simulator tree found
no LICENSE/NOTICE/COPYING/COPYRIGHT filename; the root and Simulator immediate
trees contain no additional applicable notice file. No license exception was
found in these inspected materials. The downloaded, hash-verified binary STL
headers read `Exported from Blender-3.5.1` for the body and
`Exported from Blender-2.91.0` for both rotors, followed by zero padding. No
additional attribution or license exception occurs in those headers; their
exact 80 bytes are recorded in manifest hex and text fields. This is repository
license evidence, not an independent authorship audit.
The CLI retains LICENSE byte for byte and marks converted OBJ files as modified.

## Conversion and placement boundary

All five mesh visuals in the SDF have scale `1 1 1`, with zero visual poses.
STL itself is unitless: metres are inferred from its SDF usage. The intended
conversion is Gazebo X-forward/Y-left/Z-up metres to UE
X-forward/Y-right/Z-up centimetres: `(x,y,z) -> (100*x,-100*y,100*z)`.
The Y reflection reverses handedness; each triangle changes from `(a,b,c)` to
`(T(a),T(c),T(b))`. Facet normals are recomputed from those edges. The tool
retains the original body, CCW and CW mesh origins separately, without
recentering, repair, primitive replacement, extra scaling, or pose baking.

The following are SDF link translations, not measured STL bounds. All source
rotor roll/pitch/yaw values are zero. Direction strings retain upstream plugin
semantics. UE integration now applies negative yaw for CCW and positive yaw for
CW in the left-handed view frame; rendered frames alone cannot measure high-RPM
rotation direction because of temporal aliasing.

| Link | Source translation (m) | Unapplied UE translation (cm) | Mesh / source direction |
| --- | --- | --- | --- |
| rotor_0 | (0.1465, -0.147, 0.151) | (14.65, 14.7, 15.1) | CCW / ccw |
| rotor_1 | (-0.1465, 0.147, 0.151) | (-14.65, -14.7, 15.1) | CCW / ccw |
| rotor_2 | (0.1465, 0.147, 0.151) | (14.65, -14.7, 15.1) | CW / cw |
| rotor_3 | (-0.1465, -0.147, 0.151) | (-14.65, 14.7, 15.1) | CW / cw |

The SDF also includes GPS and D435i models; these are not among the three
extracted meshes. Collision primitives and inertial values are not converted.
The integration below applies visual placement only; physics parameters remain
the existing quad-X baseline.

## Execution and evidence, 2026-09-06

From the wksim directory, use the existing Python runtime:

```powershell
& D:/date/miniconda/python.exe -X utf8 -B -m unittest validation/test_wksim_console_p450_asset.py -v
& D:/date/miniconda/python.exe -X utf8 -B tools/prepare_p450_asset.py --fetch-missing --output validation/prometheus-p450-assets-20260906
```

The controlled tests cover binary files whose header begins with `solid`, ASCII
grammar, malformed lengths, empty data, non-finite coordinates, degenerate
triangles, frame conversion, winding and normals, preserved origins, repeatable
OBJ bytes, SDF metadata, existing-output refusal, incorrect Git entries, and
offline Git failures. Added controlled tests cover verified downloads, hash
mismatch, network timeout, declared/streamed size limits, deadline, truncation,
redirect rejection, allowlisted paths, and offline/non-mesh refusal.
All 19 tests passed. Tests use memory/mocks and create no artifact directory.

The initial offline preparation command failed before any output writes.
All three mesh blobs return `fatal: git cat-file: could not get object info`
with `GIT_NO_LAZY_FETCH=1`. The source tree references exist, but the mesh
contents are unavailable in this local partial clone (`remote.origin.promisor`
is true). SDF, model.config and LICENSE objects are locally readable (16806,
279 and 9704 bytes respectively). That initial attempt performed no download.

After explicit network authorization, the real `--fetch-missing` command
completed into the new `validation/prometheus-p450-assets-20260906` directory.
The three STL downloads matched the pinned Git blob IDs. A first conversion
attempt found 25 zero-area body triangles and stopped before creating output.
The converter now preserves and reports those faces without undefined normals;
it does not delete or repair them. The final body contains 53,125 triangles
(25 zero-area before and after conversion); CCW and CW each contain 74,532
triangles (zero zero-area). All three files are binary STL.

A separate read-back check recomputed all six raw SHA256 and Git blob hashes,
all three OBJ SHA256 values, OBJ face/vertex counts, and bounds successfully.
That preparation-only check made no UE import, appearance or physics claim.
The later native import and display evidence is recorded below separately.

### Actual bounds

Numbers below are rounded to nine decimal places; full precision is in
`manifest.json`. Each row is the independent mesh in its retained source
origin, before applying the rotor link translations above.

| Mesh | Source min (m) | Source max (m) |
| --- | --- | --- |
| Body | (-0.165089697, -0.161235452, -0.044560544) | (0.159039780, 0.164004505, 0.218195230) |
| CCW | (-0.050516888, -0.119030297, -0.004090588) | (0.050518278, 0.119032264, 0.006393076) |
| CW | (-0.050518006, -0.119030543, -0.004090350) | (0.050517175, 0.119032010, 0.006393314) |

| Mesh | Converted min (cm) | Converted max (cm) |
| --- | --- | --- |
| Body | (-16.508969665, -16.400450468, -4.456054419) | (15.903978050, 16.123545170, 21.819522977) |
| CCW | (-5.051688850, -11.903226376, -0.409058807) | (5.051827803, 11.903029680, 0.639307592) |
| CW | (-5.051800609, -11.903201044, -0.409035012) | (5.051717535, 11.903054267, 0.639331387) |

The body spans Z=-4.456 to +21.820 cm relative to its source origin. The rotor
meshes span approximately Z=-0.409 to +0.639 cm relative to their individual
origins; their SDF placement at Z=15.1 cm is recorded but not baked. These
offsets must not be mistaken for a centered bounding box or ground alignment.

### Actual SHA256

| Raw file | SHA256 |
| --- | --- |
| meshes/p450.stl | `1c2f3d619a1301e5042f03fdb031e701731a1eefb8b70696ad4c45525a20673d` |
| meshes/p450_ccw.stl | `b05c35cb494f102f200e3098b5df3f6e2f1245df7297df27b23a44909ca4b013` |
| meshes/p450_cw.stl | `6797ffebd8cda3b1925c95b380eb0e7f234e685e872fb59dc947377f69365ec1` |
| p450.sdf | `0dcaccca7d9aca2f13393f85f874d8bff2eb64fb505d2121b2a332587afd281d` |
| model.config | `c696a5ba152b1ac5d54bbad201fa906b2bd48f80da70619f326d300faf289fbd` |
| LICENSE | `b72b237a4df9f73995d1384e34deefc97d15328b56f4fb1feb9faf33e976ac45` |

| Output file | SHA256 |
| --- | --- |
| obj/p450.obj | `b3b5a66875096f37a3fff23d8db8c7b310728237ef74418540a3480c805f2622` |
| obj/p450_ccw.obj | `25ae53506c64342bb94688b51d87e34bff04c4255f9fb0310ca8c84eb476ecd1` |
| obj/p450_cw.obj | `01c1f8c3703076df1ca3fb2e6da5f29f2620e6a14fd7db769210be3ad7069727` |
| manifest.json | `c4a5dc46e1c5d29c70fcfe37c0047453e5249a34f2ca5adaf7d374e2b2be196b` |

On success the CLI verifies tree/blob identities, parses and converts all
inputs before creating the new output directory, saves six untouched raw files
under `raw/`, three OBJ files under `obj/`, and a deterministic `manifest.json`.
The manifest records commit, source paths, blob IDs, raw/output SHA256, byte
counts, triangle counts, encoding, before/after bounds, conversion convention,
author, license evidence, and SDF rotor metadata. No timestamp or absolute output
path enters the generated files. Existing output directories are refused;
partial output after an I/O failure is retained for inspection and never
silently overwritten or deleted.

## Native UE5.5 import and retention

The integration uses the existing UE5.5.4 PythonScript commandlet and an isolated
asset-only project at `E:/ue5.5/build/wksim-native-p450-import3-20260906/`.
No available Unreal MCP tool was found in the current session. No connection to
the user's running editor or modification to the vendor installation was made.
`tools/import_p450_ue55.py` imports the three meshes separately, creates two
solid non-emissive materials, refuses an existing destination, and records the
real engine version, input hashes and native mesh bounds. Source STL/OBJ bytes
are unchanged. UE reports missing UV/smoothing data and degenerate tangents;
the chosen materials require neither textures nor normal maps.

An actual import first revealed an extra Y reflection: body bounds differed by
0.276905775 cm. The installed UE source
`Engine/Source/Editor/UnrealEd/Private/Fbx/FbxUtilsImport.cpp` confirms that
`FFbxDataConverter::ConvertPos` negates Y even with scene conversion disabled.
The importer now writes its own private FBX-input OBJ adaptation which undoes
the frozen OBJ's Y reflection and winding, letting UE's mandatory reflection
produce the intended final coordinates. It does not change the frozen source
conversion or silently recenter/rescale the model.

`tools/check_p450_import.py` compares the original intended and actual imported
bounds. Its predeclared 0.002 cm asset-import diagnostic passed: body maximum
error 0.0000007153 cm; CCW 0.0004916191 cm; CW 0.0004910827 cm. This allowance is
not a dynamics or sensor-equivalence budget. Source zero-area faces remain in
OBJ; UE may discard degenerate geometry during import. Vertex counts are marked
unavailable because StaticMeshEditorSubsystem is absent in this commandlet,
not inferred from source triangle counts.

Evidence: `validation/p450-import-20260906-final/` retains the incorrect-axis
import; `validation/p450-import-20260906-axes/result.json` and `bounds-green.json`
record the corrected native import. Earlier quoting/API failures are retained
under the sibling `p450-import-20260906*` evidence directories.

The five `.uasset` files and byte-for-byte upstream license are retained in
`Simulator/ue55/Content/Wksim/P450/`. Their provenance is pinned by
`Simulator/ue55/p450-visual-manifest.json` and the actual build manifest. The
runtime requires them; it does not substitute primitives if a mesh is missing.
Body and all four source rotor origins share a geometry-only +4.4560544193 cm Z
offset, putting the source body's lowest point on the existing model ground.
The authoritative Actor pose, physical centre, model inputs, mass, inertia and
rotor arm remain unchanged. P450 geometry on quad-X test dynamics is labelled
in the HUD and manifest; it is not a calibrated P450 dynamics profile.

Native lighting diagnosis, display build and real dual-flight evidence are
indexed by [the P450 display report](2026-09-06_p450-view-report.md).
