"""Build only /Game/XinyiMaterialAB test assets, after the UE baseline passes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

repo = Path(os.environ['ACW_REPO_ROOT']).resolve()
if repo.name != 'xinyi-material-ue58-round1':
    raise RuntimeError('Candidate build requires the isolated worktree')
sys.path.insert(0, str(repo / 'adapters/unreal/lookdev'))
sys.path.insert(0, str(repo / 'tools/lookdev'))
import unreal
import xinyi_look_build_assets as builder
from ue_custom_code import custom_code, MATERIALS
from material_round1_shader import make_candidate

lib, mel, tools = builder.lib, builder.mel, builder.tools
root = '/Game/XinyiMaterialAB'
out = repo / 'unreal/Saved/XinyiLook/unreal'
report = {'status': 'FAIL_MATERIAL_AB_BUILD', 'asset_scope': root,
          'level_saved': False, 'baseline_assets_written': False, 'textures': []}


def statistics(mat):
    stats = mel.get_statistics(mat)
    result = {}
    for name in ('num_pixel_shader_instructions', 'num_vertex_shader_instructions', 'num_samplers',
                 'num_pixel_texture_samples', 'num_vertex_texture_samples'):
        try:
            result[name] = stats.get_editor_property(name)
        except Exception:
            result[name] = None
    return result


def texture(record):
    name = record['name']
    source = repo / 'assets/materials/xinyi/ue58_round1' / (name + '.png')
    if hashlib.sha256(source.read_bytes()).hexdigest() != record['sha256']:
        raise RuntimeError('Source texture hash mismatch: ' + name)
    dest = root + '/Textures'
    task = unreal.AssetImportTask()
    for key, value in (('filename', str(source)), ('destination_path', dest), ('destination_name', name),
                       ('automated', True), ('replace_existing', True), ('save', False)):
        task.set_editor_property(key, value)
    tools.import_asset_tasks([task])
    tex = lib.load_asset(dest + '/' + name)
    if tex is None:
        raise RuntimeError('Texture import failed: ' + name)
    props = {'srgb': False, 'compression_settings': unreal.TextureCompressionSettings.TC_MASKS,
             'compression_no_alpha': False, 'mip_gen_settings': unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
             'address_x': unreal.TextureAddress.TA_WRAP, 'address_y': unreal.TextureAddress.TA_WRAP,
             'lod_bias': 0}
    for key, value in props.items():
        tex.set_editor_property(key, value)
        if tex.get_editor_property(key) != value:
            raise RuntimeError('Texture setting did not persist: ' + key)
    if not lib.save_loaded_asset(tex):
        raise RuntimeError('Cannot save test texture: ' + name)
    report['textures'].append({'asset': tex.get_path_name(), 'source_sha256': record['sha256'],
        'size': record['size'], 'source_mode': record['mode'],
        'settings': {key: str(tex.get_editor_property(key)) for key in props},
        'channel_min': record['channel_min'], 'channel_max': record['channel_max'],
        'alpha_is_data': True})
    return tex


try:
    baseline = json.loads((out / 'look_capture.report.json').read_text())
    if baseline.get('status') != 'PASS_LOOK_CAPTURE' or not baseline.get('captures') or not baseline.get('reopen_ok'):
        raise RuntimeError('A real UE baseline must pass before candidate build')
    source = json.loads((repo / 'assets/materials/xinyi/ue58_round1/source.json').read_text())
    facade, roof = [texture(r) for r in source['textures']]
    baseline_mat = lib.load_asset('/Game/XinyiLook/Materials/M_XinyiCity')
    mpc = lib.load_asset('/Game/XinyiLook/Materials/MPC_XinyiLook')
    shop = lib.load_asset('/Game/XinyiLook/Textures/T_XinyiShopAtlas')
    plan = lib.load_asset('/Game/XinyiLook/Textures/T_XinyiStorefrontPlan')
    if any(x is None for x in (baseline_mat, mpc, shop, plan)):
        raise RuntimeError('Baseline material dependencies are missing')
    path = root + '/Materials/M_XinyiCity_Masks'
    if lib.does_asset_exist(path):
        mat = lib.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset('M_XinyiCity_Masks', root + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        raise RuntimeError('Could not create test material')
    mat.set_editor_property('float_precision_mode', unreal.MaterialFloatPrecisionMode.MFPM_FULL)
    mat.set_editor_property('tangent_space_normal', False)
    wp = builder.world_pos_m(mat, -1200, -300)
    normal = builder.expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -150)
    uvs = [builder.texcoord(mat, i, -1200, i * 120) for i in range(3)]
    night = builder.mpc_param(mat, mpc, 'Night', -1200, 360)
    lit = builder.mpc_param(mat, mpc, 'LitFrac', -1200, 480)
    emissive = builder.mpc_param(mat, mpc, 'EmissiveScale', -600, 500)
    stx = builder.texture_object(mat, shop, -1200, 600, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    ptx = builder.texture_object(mat, plan, -1200, 720, unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    ftx = builder.texture_object(mat, facade, -1200, 840, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    rtx = builder.texture_object(mat, roof, -1200, 960, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    code = make_candidate(custom_code('M_XinyiCity'))
    inputs = [name for name, _ in MATERIALS['M_XinyiCity'][0]] + ['FacadeTX', 'RoofTX']
    node = builder.custom(mat, -700, 0, code, inputs, builder.SURFACE_OUTPUTS, 'XinyiMaterialAB_Masks')
    builder.wire(((wp, 'WP'), (normal, 'N'), (uvs[0], 'UV0'), (uvs[1], 'UV1'), (uvs[2], 'UV2'),
                  (night, 'Night'), (lit, 'LitFrac'), (stx, 'ShopTX'), (ptx, 'PlanTX'),
                  (ftx, 'FacadeTX'), (rtx, 'RoofTX')), node)
    builder.finish_surface(mat, node, emissive, -300, 300)
    mel.recompile_material(mat)
    if not lib.save_asset(path):
        raise RuntimeError('Cannot save candidate material')
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    report['statistics'] = {'baseline': statistics(baseline_mat), 'candidate': statistics(mat)}
    if (report['statistics']['candidate']['num_pixel_shader_instructions'] or 0) <= 0:
        raise RuntimeError('Candidate did not compile')
    report.update(status='PASS_MATERIAL_AB_BUILD', material=path,
                  generated_custom_source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                  baseline_hlsl_sha256=hashlib.sha256((repo / 'tools/lookdev/shaders/xinyi_city.hlsl').read_bytes()).hexdigest(),
                  period_metres=32, facade_v='negative height; U mirrors only',
                  sample_policy='one full RGBA SampleGrad for each eligible facade/roof surface; no decal')
except Exception:
    report['error'] = traceback.format_exc()
finally:
    (out / 'material_ab_build.report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    unreal.log('XINYI_MATERIAL_AB_BUILD ' + report['status'])
    # Match xinyi_look_build_assets.py: ExecutePythonScript exits after returning.
    # The first attempt's explicit QUIT_EDITOR was followed by an
    # InteractiveToolsContext shutdown assertion; the automatic-exit retry passed.
