"""Import only the new toggleable single-building kit; never save a level."""
import json
import os
from pathlib import Path
import sys
import traceback

repo=Path(os.environ['ACW_REPO_ROOT']).resolve()
revision=os.environ.get('ACW_EXEMPLAR_REVISION','r1')
assert revision in ('r1','r2') and repo.name=='xinyi-material-ue58-round1'
out=repo/'unreal/Saved/XinyiExemplar/Walkup269873'
kit=json.loads((out/('kit_'+revision+'.json')).read_text())
sys.path.insert(0,str(repo/'adapters/unreal/lookdev'))
import unreal
import xinyi_look_build_assets as b

root='/Game/XinyiExemplar/Walkup269873'
receipt={'status':'FAIL_EXEMPLAR_IMPORT','revision':revision,'level_saved':False,'scope':root}
try:
    path=root+'/M_WalkupKit'
    if b.lib.does_asset_exist(path):
        material=b.lib.load_asset(path)
    else:
        material=b.tools.create_asset('M_WalkupKit',root,unreal.Material,unreal.MaterialFactoryNew())
        a=b.texcoord(material,0,-700,0); c=b.texcoord(material,1,-700,160)
        node=b.custom(material,-400,0,'return float3(UV0.x, UV0.y, UV1.x);',
                      ['UV0','UV1'],[],'WalkupKit_StoredLinearRGB')
        b.wire(((a,'UV0'),(c,'UV1')),node)
        b.mel.connect_material_property(node,'',unreal.MaterialProperty.MP_BASE_COLOR)
        rough=b.expr(material,unreal.MaterialExpressionConstant,-300,200,r=.74)
        metal=b.expr(material,unreal.MaterialExpressionConstant,-300,300,r=.12)
        b.mel.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
        b.mel.connect_material_property(metal,'',unreal.MaterialProperty.MP_METALLIC)
        b.mel.recompile_material(material)
        assert b.lib.save_asset(path)
    dest=root+'/'+revision+'/Mesh'
    assert dest.startswith(root+'/')
    mesh_path,mesh=b.import_mesh(out/kit['glb'],dest,material,3)
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    triangles=mesh.get_num_triangles(0)
    sections=mesh.get_num_sections(0)
    assert triangles==kit['triangles'] and sections==1
    actual=b.mesh_bounds(mesh)
    stats=b.mel.get_statistics(material)
    receipt.update(status='PASS_EXEMPLAR_IMPORT',mesh=mesh_path,material=path,
                   triangles=triangles,sections=sections,actual_bounds_origin_cm=actual[0],
                   actual_bounds_extent_cm=actual[1],nanite=False,
                   material_statistics={k:stats.get_editor_property(k) for k in
                       ('num_pixel_shader_instructions','num_vertex_shader_instructions','num_samplers','num_pixel_texture_samples')},
                   asset_paths=sorted(b.lib.list_assets(root,recursive=True)))
except Exception:
    receipt['error']=traceback.format_exc()
    raise
finally:
    (out/('import_'+revision+'.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    unreal.log('EXEMPLAR_IMPORT '+receipt['status'])
