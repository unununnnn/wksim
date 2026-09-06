"""Run inside UE5.5's PythonScript commandlet; imports into an isolated project.

This is asset conversion, not flight or sensor-physics acceptance. It never
modifies the upstream STL or any map, and refuses existing destination assets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import unreal


def fbx_source_obj(source, destination):
    """Undo the explicit UE Y reflection for FBX's obligatory handedness step.

    UE5.5 FbxDataConverter::ConvertPos negates Y even with ConvertScene=false.
    This is importer-specific adaptation, not a change to the frozen OBJ/STL.
    """
    lines=[]
    for line in source.read_text(encoding='ascii').splitlines():
        words=line.split()
        if words and words[0] in ('v','vn'):
            if len(words)!=4:
                raise ValueError('Unexpected generated OBJ vector')
            words[2]=format(-float(words[2]),'.17g')
            line=' '.join(words)
        elif words and words[0]=='f':
            if len(words)!=4:
                raise ValueError('Expected triangle-only generated OBJ')
            line=' '.join((words[0],words[1],words[3],words[2]))
        lines.append(line)
    with destination.open('x',encoding='ascii') as output:
        output.write('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=os.getenv('WKSIM_P450_SOURCE'))
    parser.add_argument('--report',type=Path,default=os.getenv('WKSIM_P450_REPORT'))
    args=parser.parse_args()
    if args.source is None or args.report is None:
        parser.error('Provide source/report through arguments or WKSIM_P450_SOURCE/REPORT')
    if args.report.exists():
        raise ValueError('Import report already exists')
    source=args.source.resolve()
    destination='/Game/Wksim/P450'
    asset_editor=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    mesh_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if asset_editor.does_directory_exist(destination):
        raise ValueError('Refusing to replace existing P450 assets')
    tools=unreal.AssetToolsHelpers.get_asset_tools()
    fbx_directory=args.report.parent/'fbx-input'
    fbx_directory.mkdir(parents=True,exist_ok=False)
    report=dict(status='failed',engine=unreal.SystemLibrary.get_engine_version(),
                project=unreal.Paths.get_project_file_path(),assets=[])
    try:
        for name in ('p450','p450_ccw','p450_cw'):
            obj=source/(name+'.obj')
            if not obj.is_file():
                raise FileNotFoundError(obj)
            fbx_obj=fbx_directory/obj.name
            fbx_source_obj(obj,fbx_obj)
            task=unreal.AssetImportTask()
            task.filename=str(fbx_obj)
            task.destination_path=destination
            task.destination_name='SM_'+name
            task.automated=True
            task.replace_existing=False
            task.save=True
            task.factory=unreal.FbxFactory()
            options=unreal.FbxImportUI()
            options.import_mesh=True
            options.import_as_skeletal=False
            options.import_materials=False
            options.import_textures=False
            options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
            data=options.static_mesh_import_data
            # The importer adapter supplies right-handed centimetres; FBX's
            # mandatory Y conversion restores the frozen intended UE bounds.
            data.convert_scene=False
            data.convert_scene_unit=False
            data.force_front_x_axis=False
            data.combine_meshes=True
            data.auto_generate_collision=False
            data.generate_lightmap_u_vs=False
            data.import_uniform_scale=1.0
            data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
            data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
            task.options=options
            tools.import_asset_tasks([task])
            meshes=[value for value in task.get_objects() if isinstance(value,unreal.StaticMesh)]
            if len(meshes)!=1:
                raise RuntimeError('Expected one imported static mesh for '+name)
            mesh=meshes[0]
            box=mesh.get_bounding_box()
            report['assets'].append(dict(name=name,path=mesh.get_path_name(),
                source=str(obj),source_sha256=hashlib.sha256(obj.read_bytes()).hexdigest(),
                fbx_input=str(fbx_obj),fbx_input_sha256=hashlib.sha256(fbx_obj.read_bytes()).hexdigest(),
                bounds_cm=dict(min=[box.min.x,box.min.y,box.min.z],max=[box.max.x,box.max.y,box.max.z]),
                lod0_vertices=(mesh_editor.get_number_verts(mesh,0) if mesh_editor else None),
                vertex_count_scope='Unavailable when StaticMeshEditorSubsystem is not initialized in commandlet'))
        # Solid surface parameters only: no emission that could hide lighting bugs.
        for name,color,roughness in (
                ('M_P450_Body',(.35,.48,.52),.6),('M_P450_Rotor',(.035,.045,.055),.5)):
            material=tools.create_asset(name,destination,unreal.Material,unreal.MaterialFactoryNew())
            node=unreal.MaterialEditingLibrary.create_material_expression(material,unreal.MaterialExpressionConstant3Vector)
            node.constant=unreal.LinearColor(*color,1.0)
            unreal.MaterialEditingLibrary.connect_material_property(node,'',unreal.MaterialProperty.MP_BASE_COLOR)
            rough=unreal.MaterialEditingLibrary.create_material_expression(material,unreal.MaterialExpressionConstant)
            rough.r=roughness
            unreal.MaterialEditingLibrary.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
            unreal.MaterialEditingLibrary.recompile_material(material)
            asset_editor.save_loaded_asset(material)
            report['assets'].append(dict(name=name,path=material.get_path_name(),base_color=list(color),roughness=roughness))
        report['status']='imported_not_flight_validated'
    finally:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x',encoding='utf-8') as output:
            json.dump(report,output,ensure_ascii=False,allow_nan=False,indent=2)
        unreal.log('WKSIM_P450_IMPORT '+str(args.report))


main()
