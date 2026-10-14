"""Procedural materials for the golden-reference trees (Cycles). All patterns are UV-driven so they can
later be baked to game textures. Colours are linear-RGB values chosen against reference photos."""
from __future__ import annotations

import bpy


def _n(nt, kind, loc=(0, 0), **inputs):
    node = nt.nodes.new(kind)
    node.location = loc
    for k, v in inputs.items():
        node.inputs[k].default_value = v
    return node


def _ramp(nt, stops, loc=(0, 0)):
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.location = loc
    els = r.color_ramp.elements
    for _ in range(len(stops) - 2):
        els.new(0.5)
    for el, (pos, col) in zip(els, stops):
        el.position = pos
        el.color = (*col, 1.0)
    return r


def _new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    return m, nt, out


def bark(
    name="M_Bark",
    base=(0.1, 0.08, 0.06),
    dark=(0.045, 0.036, 0.028),
    lichen=(0.13, 0.125, 0.1),
    twig=(0.06, 0.05, 0.026),
    twig_radius=(0.009, 0.03),
):
    m, nt, out = _new(name)
    uv = nt.nodes.new("ShaderNodeTexCoord")
    mapping = _n(nt, "ShaderNodeMapping", (-900, 0))
    mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    nt.links.new(uv.outputs["UV"], mapping.inputs["Vector"])
    # large mottling
    mott = _n(nt, "ShaderNodeTexNoise", (-650, 250), Scale=3.2, Detail=6.0, Roughness=0.6)
    nt.links.new(mapping.outputs[0], mott.inputs["Vector"])
    mr = _ramp(nt, [(0.38, dark), (0.52, base), (0.66, lichen)], (-400, 250))
    nt.links.new(mott.outputs["Fac"], mr.inputs[0])
    # lenticels: small pale dots, slightly stretched around the circumference
    lmap = _n(nt, "ShaderNodeMapping", (-650, -50))
    lmap.inputs["Scale"].default_value = (1.0, 2.2, 1.0)
    nt.links.new(uv.outputs["UV"], lmap.inputs["Vector"])
    vor = _n(nt, "ShaderNodeTexVoronoi", (-450, -50), Scale=38.0)
    nt.links.new(lmap.outputs[0], vor.inputs["Vector"])
    dots = _ramp(nt, [(0.0, (0.8, 0.8, 0.8)), (0.09, (0, 0, 0))], (-250, -50))
    nt.links.new(vor.outputs["Distance"], dots.inputs[0])
    mix = _n(nt, "ShaderNodeMix", (-50, 150))
    mix.data_type = "RGBA"
    nt.links.new(dots.outputs[0], mix.inputs["Factor"])
    nt.links.new(mr.outputs[0], mix.inputs[6])
    mix.inputs[7].default_value = (0.14, 0.12, 0.095, 1)
    # fine roughness / bump
    fine = _n(nt, "ShaderNodeTexNoise", (-450, -300), Scale=22.0, Detail=10.0, Roughness=0.65)
    nt.links.new(mapping.outputs[0], fine.inputs["Vector"])
    hsum = _n(nt, "ShaderNodeMath", (-200, -300))
    hsum.operation = "ADD"
    nt.links.new(fine.outputs["Fac"], hsum.inputs[0])
    nt.links.new(dots.outputs[0], hsum.inputs[1])
    bump = _n(nt, "ShaderNodeBump", (100, -250), Strength=0.55, Distance=0.004)
    nt.links.new(hsum.outputs[0], bump.inputs["Height"])
    # young branchlets (thin wood) are green-brown, not grey: blend by the mesh 'radius' attribute
    a_r = nt.nodes.new("ShaderNodeAttribute")
    a_r.attribute_name = "radius"
    a_r.location = (-250, 400)
    young = _n(nt, "ShaderNodeMapRange", (-50, 400))
    young.inputs["From Min"].default_value = twig_radius[0]
    young.inputs["From Max"].default_value = twig_radius[1]
    young.inputs["To Min"].default_value = 1.0
    young.inputs["To Max"].default_value = 0.0
    nt.links.new(a_r.outputs["Fac"], young.inputs["Value"])
    tmix = _n(nt, "ShaderNodeMix", (150, 250))
    tmix.data_type = "RGBA"
    nt.links.new(young.outputs[0], tmix.inputs["Factor"])
    nt.links.new(mix.outputs[2], tmix.inputs[6])
    tmix.inputs[7].default_value = (*twig, 1)
    bsdf = _n(nt, "ShaderNodeBsdfPrincipled", (400, 0), Roughness=0.88)
    nt.links.new(tmix.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(bump.outputs[0], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return m


def simple(name, color, rough=0.6):
    m, nt, out = _new(name)
    b = _n(nt, "ShaderNodeBsdfPrincipled", (400, 0), Roughness=rough)
    b.inputs["Base Color"].default_value = (*color, 1)
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return m


def leaf(
    name="M_Leaf",
    upper=(0.016, 0.048, 0.007),
    upper_var=(0.06, 0.1, 0.012),
    under=(0.06, 0.085, 0.032),
    young=(0.3, 0.055, 0.025),
    trans=(0.2, 0.26, 0.02),
    gloss=0.5,
    coat=0.12,
):
    m, nt, out = _new(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = _n(nt, "ShaderNodeSeparateXYZ", (-1100, 300))
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    a_rand = nt.nodes.new("ShaderNodeAttribute")
    a_rand.attribute_name = "leaf_rand"
    a_rand.location = (-1100, 0)
    a_age = nt.nodes.new("ShaderNodeAttribute")
    a_age.attribute_name = "leaf_age"
    a_age.location = (-1100, -200)
    a_tint = nt.nodes.new("ShaderNodeAttribute")
    a_tint.attribute_type = "INSTANCER"
    a_tint.attribute_name = "tint"
    a_tint.location = (-1100, -400)

    # per-leaf + per-spray variation of the upper colour
    vsum = _n(nt, "ShaderNodeMath", (-850, 0))
    vsum.operation = "MULTIPLY_ADD"
    nt.links.new(a_rand.outputs["Fac"], vsum.inputs[0])
    vsum.inputs[1].default_value = 0.6
    nt.links.new(a_tint.outputs["Fac"], vsum.inputs[2])
    vclamp = _n(nt, "ShaderNodeClamp", (-650, 0))
    nt.links.new(vsum.outputs[0], vclamp.inputs["Value"])
    up_mix = _n(nt, "ShaderNodeMix", (-450, 100))
    up_mix.data_type = "RGBA"
    nt.links.new(vclamp.outputs[0], up_mix.inputs["Factor"])
    up_mix.inputs[6].default_value = (*upper, 1)
    up_mix.inputs[7].default_value = (*upper_var, 1)

    # midrib: pale yellow-green line at v = 0.5, fading toward the apex
    dv = _n(nt, "ShaderNodeMath", (-850, 400))
    dv.operation = "SUBTRACT"
    nt.links.new(sep.outputs["Y"], dv.inputs[0])
    dv.inputs[1].default_value = 0.5
    adv = _n(nt, "ShaderNodeMath", (-700, 400))
    adv.operation = "ABSOLUTE"
    nt.links.new(dv.outputs[0], adv.inputs[0])
    rib = _n(nt, "ShaderNodeMapRange", (-550, 400))
    rib.inputs["From Min"].default_value = 0.035
    rib.inputs["From Max"].default_value = 0.0
    nt.links.new(adv.outputs[0], rib.inputs["Value"])
    # lateral veins: faint chevrons
    vein_in = _n(nt, "ShaderNodeMath", (-700, 600))
    vein_in.operation = "MULTIPLY_ADD"
    nt.links.new(adv.outputs[0], vein_in.inputs[0])
    vein_in.inputs[1].default_value = -1.6
    nt.links.new(sep.outputs["X"], vein_in.inputs[2])
    vein_s = _n(nt, "ShaderNodeMath", (-550, 600))
    vein_s.operation = "MULTIPLY"
    nt.links.new(vein_in.outputs[0], vein_s.inputs[0])
    vein_s.inputs[1].default_value = 9.0
    vein_w = _n(nt, "ShaderNodeMath", (-400, 600))
    vein_w.operation = "PINGPONG"
    nt.links.new(vein_s.outputs[0], vein_w.inputs[0])
    vein_w.inputs[1].default_value = 0.5
    vein = _n(nt, "ShaderNodeMapRange", (-250, 600))
    vein.inputs["From Min"].default_value = 0.06
    vein.inputs["From Max"].default_value = 0.0
    vein.inputs["To Max"].default_value = 0.35
    nt.links.new(vein_w.outputs[0], vein.inputs["Value"])
    lines = _n(nt, "ShaderNodeMath", (-100, 500))
    lines.operation = "MAXIMUM"
    nt.links.new(rib.outputs[0], lines.inputs[0])
    nt.links.new(vein.outputs[0], lines.inputs[1])
    with_rib = _n(nt, "ShaderNodeMix", (-200, 200))
    with_rib.data_type = "RGBA"
    nt.links.new(lines.outputs[0], with_rib.inputs["Factor"])
    nt.links.new(up_mix.outputs[2], with_rib.inputs[6])
    with_rib.inputs[7].default_value = (0.11, 0.13, 0.035, 1)
    # young flush
    age_mix = _n(nt, "ShaderNodeMix", (0, 200))
    age_mix.data_type = "RGBA"
    nt.links.new(a_age.outputs["Fac"], age_mix.inputs["Factor"])
    nt.links.new(with_rib.outputs[2], age_mix.inputs[6])
    age_mix.inputs[7].default_value = (*young, 1)
    # underside
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    geo.location = (0, -100)
    side = _n(nt, "ShaderNodeMix", (200, 100))
    side.data_type = "RGBA"
    nt.links.new(geo.outputs["Backfacing"], side.inputs["Factor"])
    nt.links.new(age_mix.outputs[2], side.inputs[6])
    side.inputs[7].default_value = (*under, 1)
    rough = _n(nt, "ShaderNodeMapRange", (200, -150))
    nt.links.new(geo.outputs["Backfacing"], rough.inputs["Value"])
    rough.inputs["To Min"].default_value = gloss
    rough.inputs["To Max"].default_value = 0.62
    coat_w = _n(nt, "ShaderNodeMapRange", (200, -350))
    nt.links.new(geo.outputs["Backfacing"], coat_w.inputs["Value"])
    coat_w.inputs["To Min"].default_value = coat
    coat_w.inputs["To Max"].default_value = 0.0

    bsdf = _n(nt, "ShaderNodeBsdfPrincipled", (450, 100))
    nt.links.new(side.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(rough.outputs[0], bsdf.inputs["Roughness"])
    nt.links.new(coat_w.outputs[0], bsdf.inputs["Coat Weight"])
    bsdf.inputs["Coat Roughness"].default_value = 0.22
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    tr = _n(nt, "ShaderNodeBsdfTranslucent", (450, -250))
    tr.inputs["Color"].default_value = (*trans, 1)
    mixs = _n(nt, "ShaderNodeMixShader", (700, 0), Fac=0.34)
    nt.links.new(bsdf.outputs[0], mixs.inputs[1])
    nt.links.new(tr.outputs[0], mixs.inputs[2])
    nt.links.new(mixs.outputs[0], out.inputs["Surface"])
    return m






