#!/home/jagosan/.hermes/toolchains/bpy_env/bin/python
"""
TASK-CV-103: Headless Blender 3D procedural asset generator for cluster-vis.

Builds the procedural "cluster kit" kit with clean PBR materials and exports
a single binary glTF package to public/assets/cluster-kit.glb.

Required named objects in the GLB hierarchy:
  - NodeTray           wide flat server tray / chassis
  - ControlPlane_Cube  dense beveled control plane block
  - Pod_Cylinder       capsule pod unit
  - Framework_Ray      hexagonal prism badge
  - Framework_Spark    gear / flanged star badge
  - Database_Postgres  cylinder drum with data stripes
  - Cache_Redis        segmented memory disk stack
  - Conduit_Link       data conduit connector

Headless execution standards (per headless-blender-pipeline skill):
  sys.stdout.flush(), sys.stderr.flush(), os._exit() at end to avoid
  C++ teardown thread segfaults / hangs.
"""

import bpy
import bmesh
import math
import os
import sys
import traceback

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
OUT_DIR = os.path.join(REPO_ROOT, "public", "assets")
OUT_GLB = os.path.join(OUT_DIR, "cluster-kit.glb")

# Palette (linear RGBA) — distinct isometric visual language per K8s layer.
COL_TRAIL = (0.16, 0.18, 0.21, 1.0)   # chassis charcoal
COL_TRAIL_LED = (0.10, 0.90, 0.45, 1.0)
COL_CP = (0.10, 0.35, 0.75, 1.0)      # control plane blue
COL_CP_CORE = (0.85, 0.88, 0.95, 1.0)
COL_POD = (0.93, 0.55, 0.13, 1.0)     # compute orange
COL_POD_CAP = (0.85, 0.86, 0.90, 1.0)
COL_RAY = (0.92, 0.20, 0.25, 1.0)     # Ray red
COL_RAY_EDGE = (0.98, 0.75, 0.30, 1.0)
COL_SPARK = (0.98, 0.80, 0.15, 1.0)   # Spark yellow
COL_SPARK_CORE = (0.35, 0.35, 0.40, 1.0)
COL_PG = (0.25, 0.50, 0.85, 1.0)      # Postgres blue
COL_PG_RING = (0.90, 0.92, 0.96, 1.0)
COL_REDIS = (0.80, 0.12, 0.12, 1.0)   # Redis red
COL_REDIS_CORE = (0.95, 0.55, 0.50, 1.0)
COL_CONDUIT = (0.10, 0.70, 0.75, 1.0) # network teal
COL_CONDUIT_FLANGE = (0.55, 0.60, 0.62, 1.0)

# Skyscraper & Conduit Architecture Colors
COL_SKYSCRAPER_TRAY = (0.12, 0.14, 0.17, 1.0)
COL_SKYSCRAPER_RIM = (0.05, 0.85, 0.95, 1.0) # cyan LED
COL_PENTHOUSE = (0.15, 0.25, 0.45, 0.8)     # glass canopy
COL_PENTHOUSE_CORE = (0.95, 0.80, 0.20, 1.0) # golden aggregation core
COL_VAULT = (0.20, 0.22, 0.25, 1.0)         # etcd heavy slate
COL_VAULT_ACCENT = (1.0, 0.60, 0.10, 1.0)   # etcd amber raft LED
COL_KUBELET = (0.15, 0.40, 0.35, 1.0)       # kubelet teal
COL_CONTAINERD = (0.30, 0.32, 0.35, 1.0)    # containerd steel
COL_POD_CAPSULE = (0.95, 0.55, 0.15, 1.0)   # pod orange
COL_CONDUIT_PIPE = (0.10, 0.75, 0.85, 1.0)  # conduit glass cyan
COL_CLIENT_PAD = (0.08, 0.10, 0.14, 1.0)    # dark client console
COL_CLIENT_GLOW = (0.30, 0.70, 1.0, 1.0)    # client holographic glow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pbr(name, base_color, metallic=0.0, roughness=0.5,
        emission_color=None, emission_strength=0.0):
    """Create a Blender 4.2 Principled BSDF material."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    # Blender 4.2 Principled inputs: Base Color, Metallic, Roughness,
    # Emission Color, Emission Strength.
    if len(base_color) == 3:
        base_color = tuple(base_color) + (1.0,)
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Emission Color" in bsdf.inputs:
        ec = emission_color if emission_color is not None else (0.0, 0.0, 0.0)
        bsdf.inputs["Emission Color"].default_value = (ec[0], ec[1], ec[2], 1.0)
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def new_mesh_obj(name, mat=None):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def link_into(obj, bm):
    bm.from_mesh(obj.data)
    return bm


def finalize(obj, bm, smooth=True):
    bm.to_mesh(obj.data)
    bm.free()
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    obj.data.update()


def join_to(target, others):
    """Join `others` geometry into `target` (single mesh, keeps mat slots)."""
    # Headless: matrix_world is lazily evaluated — force an update so the
    # bmesh transform below picks up the locations/rotations we just set.
    bpy.context.view_layer.update()
    for o in others:
        for slot_mat in o.data.materials:
            if slot_mat.name not in target.data.materials:
                target.data.materials.append(slot_mat)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        # Map material indices onto target slots.
        remap = {i: target.data.materials.find(m.name)
                 for i, m in enumerate(o.data.materials)}
        for f in bm.faces:
            f.material_index = remap.get(f.material_index, 0)
        bm.to_mesh(target.data)
        bm.free()
        bpy.data.objects.remove(o, do_unlink=True)
    target.data.update()


def primitive_cyl(name, mat, radius, depth, depth1=0.0, vertices=32,
                  loc=(0, 0, 0), smooth=True):
    obj = new_mesh_obj(name, mat)
    bm = bmesh.new()
    # Blender 4.2 bmesh has no create_cylinder; create_cone with
    # radius1 == radius2 is the canonical cylinder.
    r2 = radius if (not depth1) else depth1
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                          segments=vertices, radius1=radius,
                          radius2=r2, depth=depth)
    finalize(obj, bm, smooth=smooth)
    obj.location = loc
    return obj


def primitive_box(name, mat, size=(1, 1, 1), loc=(0, 0, 0)):
    obj = new_mesh_obj(name, mat)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    finalize(obj, bm, smooth=False)
    obj.location = loc
    return obj


# ---------------------------------------------------------------------------
# Asset builders — each returns a single named object centered on origin
# ---------------------------------------------------------------------------
def build_node_tray():
    """NodeTray: wide flat server tray/chassis with LED strip and rails."""
    chassis_mat = pbr("M_Trail_Chassis", COL_TRAIL, metallic=0.55, roughness=0.45)
    led_mat = pbr("M_Trail_LED", COL_TRAIL_LED, metallic=0.0, roughness=0.3,
                  emission_color=COL_TRAIL_LED, emission_strength=2.5)
    rail_mat = pbr("M_Trail_Rail", (0.35, 0.38, 0.40), metallic=0.9, roughness=0.3)

    tray = primitive_box("NodeTray", chassis_mat, size=(2.4, 1.6, 0.28))
    # Raised rear lip.
    lip = primitive_box("tray_lip", rail_mat, size=(2.4, 0.12, 0.18),
                        loc=(0, -0.74, 0.22))
    # Side rails.
    rail_l = primitive_box("tray_rail_l", rail_mat, size=(0.08, 1.6, 0.10),
                           loc=(-1.16, 0, 0.19))
    rail_r = primitive_box("tray_rail_r", rail_mat, size=(0.08, 1.6, 0.10),
                           loc=(1.16, 0, 0.19))
    # Emission LED strip across the front edge.
    led = primitive_box("tray_led", led_mat, size=(2.0, 0.05, 0.04),
                        loc=(0, 0.78, 0.06))
    # Vent grille ridges on the top face.
    vents = []
    for i in range(6):
        vents.append(primitive_box("tray_vent_%d" % i, rail_mat,
                                   size=(0.06, 1.1, 0.03),
                                   loc=(-0.75 + i * 0.30, 0, 0.155)))
    join_to(tray, [lip, rail_l, rail_r, led] + vents)
    return tray


def build_control_plane_cube():
    """ControlPlane_Cube: dense beveled control plane block."""
    shell_mat = pbr("M_CP_Shell", COL_CP, metallic=0.35, roughness=0.35)
    core_mat = pbr("M_CP_Core", COL_CP_CORE, metallic=0.1, roughness=0.25,
                   emission_color=COL_CP_CORE, emission_strength=0.35)

    cube = primitive_box("ControlPlane_Cube", shell_mat, size=(1.3, 1.3, 1.3))
    bev = cube.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.10
    bev.segments = 3
    bev.limit_method = "ANGLE"

    # Recessed core plate on top (dense density indicator).
    core = primitive_box("cp_core", core_mat, size=(0.75, 0.75, 0.10),
                         loc=(0, 0, 0.66))
    # Corner posts (etcd quorum pillars feel).
    posts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            posts.append(primitive_cyl("cp_post_%d_%d" % (sx, sy), shell_mat,
                                       radius=0.07, depth=1.42, vertices=12,
                                       loc=(sx * 0.55, sy * 0.55, 0),
                                       smooth=True))
    # Apply bevel BEFORE joining (join would drop transform-applied bevel
    # unless export_apply; applying now keeps the exported mesh exact).
    bpy.context.view_layer.objects.active = cube
    for o in [core] + posts:
        o.select_set(True)
    cube.select_set(True)
    bpy.ops.object.modifier_apply(modifier="Bevel")
    bpy.ops.object.select_all(action="DESELECT")

    join_to(cube, [core] + posts)
    return cube


def build_pod_cylinder():
    """Pod_Cylinder: capsule pod unit with cap cap and status band."""
    body_mat = pbr("M_Pod_Body", COL_POD, metallic=0.2, roughness=0.4)
    cap_mat = pbr("M_Pod_Cap", COL_POD_CAP, metallic=0.7, roughness=0.3)
    band_mat = pbr("M_Pod_Band", (1.0, 0.85, 0.30), metallic=0.0, roughness=0.3,
                   emission_color=(1.0, 0.85, 0.30), emission_strength=1.8)

    pod = primitive_cyl("Pod_Cylinder", body_mat, radius=0.42, depth=1.0,
                        vertices=32, loc=(0, 0, 0.0))
    # Hemispherical caps.
    top = new_mesh_obj("pod_cap_top", cap_mat)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.42)
    finalize(top, bm, smooth=True)
    top.location = (0, 0, 0.5)
    bot = new_mesh_obj("pod_cap_bot", cap_mat)
    bm2 = bmesh.new()
    bmesh.ops.create_uvsphere(bm2, u_segments=24, v_segments=12, radius=0.42)
    finalize(bot, bm2, smooth=True)
    bot.location = (0, 0, -0.5)
    # Status torus band around the waist (bmesh spin of a small circle).
    tor = new_mesh_obj("pod_band", band_mat)
    bm4 = bmesh.new()
    seg = 12
    ring = []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        ring.append(bm4.verts.new((0.44 + 0.045 * math.cos(a),
                                   0.0,
                                   0.045 * math.sin(a))))
    for i in range(seg):
        bm4.edges.new((ring[i], ring[(i + 1) % seg]))
    geom = bm4.verts[:] + bm4.edges[:]
    bmesh.ops.spin(bm4, geom=geom, cent=(0, 0, 0),
                   axis=(0, 0, 1), angle=2.0 * math.pi, steps=32, use_merge=True)
    bmesh.ops.remove_doubles(bm4, verts=bm4.verts, dist=1e-5)
    finalize(tor, bm4, smooth=True)

    join_to(pod, [top, bot, tor])
    return pod


def _star_prism(name, mat, points, r_out, r_in, depth, loc=(0, 0, 0)):
    """Flanged star / gear profile prism via bmesh."""
    obj = new_mesh_obj(name, mat)
    bm = bmesh.new()
    profile = []
    n2 = points * 2
    for i in range(n2):
        a = 2.0 * math.pi * i / n2
        r = r_out if i % 2 == 0 else r_in
        profile.append(bm.verts.new((r * math.cos(a), r * math.sin(a), 0.0)))
    face = bm.faces.new(profile)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    ext_verts = [v for v in ret["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, depth), verts=ext_verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    finalize(obj, bm, smooth=False)
    obj.location = loc
    return obj


def build_framework_ray():
    """Framework_Ray: hexagonal prism badge with gold edge core."""
    hex_mat = pbr("M_Ray_Hex", COL_RAY, metallic=0.45, roughness=0.3)
    edge_mat = pbr("M_Ray_Core", COL_RAY_EDGE, metallic=0.9, roughness=0.2,
                   emission_color=COL_RAY_EDGE, emission_strength=0.6)

    hexa = primitive_cyl("Framework_Ray", hex_mat, radius=0.72, depth=0.42,
                         vertices=6, loc=(0, 0, 0), smooth=False)
    # Rotated inner hex core (slightly thicker => proud badge center).
    core = primitive_cyl("ray_core", edge_mat, radius=0.40, depth=0.5,
                         vertices=6, loc=(0, 0, 0), smooth=False)
    core.rotation_euler[2] = math.radians(30)
    join_to(hexa, [core])
    return hexa


def build_framework_spark():
    """Framework_Spark: gear / flanged star badge."""
    star_mat = pbr("M_Spark_Gear", COL_SPARK, metallic=0.6, roughness=0.3)
    hub_mat = pbr("M_Spark_Hub", COL_SPARK_CORE, metallic=0.8, roughness=0.3)

    star = _star_prism("Framework_Spark", star_mat, points=8,
                       r_out=0.75, r_in=0.52, depth=0.32)
    hub = primitive_cyl("spark_hub", hub_mat, radius=0.24, depth=0.4,
                        vertices=20)
    # Axle pin through the hub.
    pin = primitive_cyl("spark_pin", star_mat, radius=0.09, depth=0.52,
                        vertices=12)
    join_to(star, [hub, pin])
    return star


def build_database_postgres():
    """Database_Postgres: cylinder drum with data stripes."""
    drum_mat = pbr("M_PG_Drum", COL_PG, metallic=0.3, roughness=0.4)
    ring_mat = pbr("M_PG_Ring", COL_PG_RING, metallic=0.75, roughness=0.25)
    stripe_mat = pbr("M_PG_Stripe", (0.55, 0.85, 1.0), metallic=0.0,
                     roughness=0.3,
                     emission_color=(0.55, 0.85, 1.0), emission_strength=2.0)

    drum = primitive_cyl("Database_Postgres", drum_mat, radius=0.62,
                         depth=1.3, vertices=32)
    parts = []
    # Two metal hoop rings.
    for i, z in enumerate((-0.45, 0.45)):
        parts.append(primitive_cyl("pg_ring_%d" % i, ring_mat,
                                   radius=0.655, depth=0.12, vertices=32,
                                   loc=(0, 0, z)))
    # Emission data stripes (thin proud rings).
    for i, z in enumerate((-0.18, 0.0, 0.18)):
        parts.append(primitive_cyl("pg_stripe_%d" % i, stripe_mat,
                                   radius=0.635, depth=0.05, vertices=32,
                                   loc=(0, 0, z)))
    # Lid.
    lid = primitive_cyl("pg_lid", ring_mat, radius=0.5, depth=0.12,
                        vertices=32, loc=(0, 0, 0.68))
    parts.append(lid)
    join_to(drum, parts)
    return drum


def build_cache_redis():
    """Cache_Redis: segmented memory disk stack."""
    disk_mat = pbr("M_Redis_Disk", COL_REDIS, metallic=0.5, roughness=0.35)
    core_mat = pbr("M_Redis_Core", COL_REDIS_CORE, metallic=0.3, roughness=0.3,
                   emission_color=COL_REDIS_CORE, emission_strength=0.8)

    # Segmented disks: alternating radii stack with gaps.
    stack = primitive_cyl("Cache_Redis", disk_mat, radius=0.55, depth=0.18,
                          vertices=28, loc=(0, 0, -0.42))
    parts = []
    radii = [0.5, 0.55, 0.46]
    zs = [-0.14, 0.14, 0.42]
    for i, (r, z) in enumerate(zip(radii, zs)):
        parts.append(primitive_cyl("redis_disk_%d" % i, disk_mat,
                                   radius=r, depth=0.18, vertices=28,
                                   loc=(0, 0, z)))
    # Central spine.
    spine = primitive_cyl("redis_spine", core_mat, radius=0.10, depth=1.25,
                          vertices=12)
    parts.append(spine)
    join_to(stack, parts)
    return stack


def build_conduit_link():
    """Conduit_Link: data conduit connector with end flanges."""
    pipe_mat = pbr("M_Conduit_Pipe", COL_CONDUIT, metallic=0.4, roughness=0.35,
                   emission_color=(0.10, 0.70, 0.75), emission_strength=0.25)
    flange_mat = pbr("M_Conduit_Flange", COL_CONDUIT_FLANGE, metallic=0.9,
                     roughness=0.25)

    # Main pipe lying along X.
    pipe = primitive_cyl("Conduit_Link", pipe_mat, radius=0.16, depth=1.6,
                         vertices=20)
    pipe.rotation_euler[2] = math.radians(90)
    parts = []
    for i, x in enumerate((-0.8, 0.8)):
        fl = primitive_cyl("conduit_flange_%d" % i, flange_mat,
                           radius=0.28, depth=0.10, vertices=20,
                           loc=(x, 0, 0))
        fl.rotation_euler[2] = math.radians(90)
        parts.append(fl)
        collar = primitive_cyl("conduit_collar_%d" % i, flange_mat,
                               radius=0.20, depth=0.06, vertices=20,
                               loc=(x * 0.82, 0, 0))
        collar.rotation_euler[2] = math.radians(90)
        parts.append(collar)
    join_to(pipe, parts)
    return pipe


# ---------------------------------------------------------------------------
# Skyscraper & Procedural Conduit Stack Builders (SPEC-01)
# ---------------------------------------------------------------------------
def build_skyscraper_floor_tray():
    """Skyscraper_FloorTray: Sleek beveled rectangular node platform with LED perimeter rim."""
    tray_mat = pbr("M_Skyscraper_Tray", COL_SKYSCRAPER_TRAY, metallic=0.75, roughness=0.35)
    rim_mat = pbr("M_Skyscraper_Rim", COL_SKYSCRAPER_RIM, metallic=0.0, roughness=0.2,
                  emission_color=COL_SKYSCRAPER_RIM, emission_strength=3.5)
    plating_mat = pbr("M_Skyscraper_Plating", (0.22, 0.25, 0.28, 1.0), metallic=0.9, roughness=0.25)

    tray = primitive_box("Skyscraper_FloorTray", tray_mat, size=(3.6, 2.4, 0.28))
    # LED Perimeter Rims
    rim_f = primitive_box("tray_rim_f", rim_mat, size=(3.6, 0.06, 0.05), loc=(0, -1.17, 0.14))
    rim_b = primitive_box("tray_rim_b", rim_mat, size=(3.6, 0.06, 0.05), loc=(0, 1.17, 0.14))
    rim_l = primitive_box("tray_rim_l", rim_mat, size=(0.06, 2.34, 0.05), loc=(-1.77, 0, 0.14))
    rim_r = primitive_box("tray_rim_r", rim_mat, size=(0.06, 2.34, 0.05), loc=(1.77, 0, 0.14))
    
    # Floor plating divisions
    plates = []
    for i in range(3):
        x = -1.0 + i * 1.0
        plates.append(primitive_box("tray_plate_%d" % i, plating_mat, size=(0.10, 2.2, 0.04), loc=(x, 0, 0.15)))
    
    join_to(tray, [rim_f, rim_b, rim_l, rim_r] + plates)
    return tray


def build_skyscraper_penthouse():
    """Skyscraper_Penthouse: Glass/canopy penthouse enclosure for API aggregation."""
    glass_mat = pbr("M_Penthouse_Glass", COL_PENTHOUSE, metallic=0.1, roughness=0.1)
    core_mat = pbr("M_Penthouse_Core", COL_PENTHOUSE_CORE, metallic=0.2, roughness=0.2,
                   emission_color=COL_PENTHOUSE_CORE, emission_strength=4.0)
    frame_mat = pbr("M_Penthouse_Frame", (0.35, 0.38, 0.42, 1.0), metallic=0.9, roughness=0.2)

    base = primitive_box("Skyscraper_Penthouse", glass_mat, size=(2.8, 1.8, 0.55))
    core = primitive_box("penthouse_core", core_mat, size=(0.8, 0.8, 0.7), loc=(0, 0, 0.1))
    
    # 4 Corner support pillars
    pillars = []
    for x in (-1.3, 1.3):
        for y in (-0.8, 0.8):
            pillars.append(primitive_cyl("penthouse_pillar", frame_mat, radius=0.08, depth=0.6, loc=(x, y, 0)))
    
    join_to(base, [core] + pillars)
    return base


def build_control_plane_vault():
    """ControlPlane_Vault: Heavy reinforced metallic vault box for etcd backing store."""
    vault_mat = pbr("M_Vault_Body", COL_VAULT, metallic=0.85, roughness=0.35)
    accent_mat = pbr("M_Vault_Accent", COL_VAULT_ACCENT, metallic=0.1, roughness=0.2,
                     emission_color=COL_VAULT_ACCENT, emission_strength=4.0)
    fin_mat = pbr("M_Vault_Fins", (0.12, 0.13, 0.15, 1.0), metallic=0.9, roughness=0.3)

    vault = primitive_box("ControlPlane_Vault", vault_mat, size=(2.2, 1.6, 1.2))
    
    # Cooling ribs / fins on left and right
    ribs = []
    for i in range(6):
        y = -0.6 + i * 0.24
        ribs.append(primitive_box("vault_rib_l_%d" % i, fin_mat, size=(0.10, 0.05, 1.0), loc=(-1.15, y, 0)))
        ribs.append(primitive_box("vault_rib_r_%d" % i, fin_mat, size=(0.10, 0.05, 1.0), loc=(1.15, y, 0)))
    
    # Amber consensus status bar on front face
    led = primitive_box("vault_led", accent_mat, size=(1.8, 0.06, 0.10), loc=(0, -0.83, 0.35))
    join_to(vault, ribs + [led])
    return vault


def build_module_kubelet():
    """Module_Kubelet: Compact control terminal box with vertical transmitter antenna."""
    kubelet_mat = pbr("M_Kubelet_Body", COL_KUBELET, metallic=0.6, roughness=0.4)
    ant_mat = pbr("M_Kubelet_Ant", (0.85, 0.85, 0.90, 1.0), metallic=0.9, roughness=0.2)
    screen_mat = pbr("M_Kubelet_Screen", COL_CLIENT_GLOW, metallic=0.0, roughness=0.2,
                     emission_color=COL_CLIENT_GLOW, emission_strength=2.5)

    box = primitive_box("Module_Kubelet", kubelet_mat, size=(0.65, 0.65, 0.45))
    antenna = primitive_cyl("kubelet_antenna", ant_mat, radius=0.03, depth=0.35, loc=(0.2, 0.2, 0.35))
    screen = primitive_box("kubelet_screen", screen_mat, size=(0.4, 0.04, 0.25), loc=(0, -0.33, 0.05))
    join_to(box, [antenna, screen])
    return box


def build_module_containerd():
    """Module_Containerd: Container runtime housing with socket intake ports and heatsinks."""
    containerd_mat = pbr("M_Containerd_Body", COL_CONTAINERD, metallic=0.8, roughness=0.3)
    fin_mat = pbr("M_Containerd_Fins", (0.15, 0.16, 0.18, 1.0), metallic=0.9, roughness=0.2)

    box = primitive_box("Module_Containerd", containerd_mat, size=(0.75, 0.75, 0.45))
    
    # Socket connector ports on sides
    ports = []
    for y in (-0.18, 0.18):
        ports.append(primitive_cyl("c_port_l", containerd_mat, radius=0.05, depth=0.10, loc=(-0.40, y, 0)))
        ports.append(primitive_cyl("c_port_r", containerd_mat, radius=0.05, depth=0.10, loc=(0.40, y, 0)))
    
    # Top heat sink fins
    fins = []
    for i in range(5):
        x = -0.24 + i * 0.12
        fins.append(primitive_box("c_fin_%d" % i, fin_mat, size=(0.03, 0.60, 0.08), loc=(x, 0, 0.26)))
        
    join_to(box, ports + fins)
    return box


def build_module_pod_capsule():
    """Module_PodCapsule: Capsule pod unit with workload status glow band."""
    pod_mat = pbr("M_PodCapsule_Body", COL_POD_CAPSULE, metallic=0.5, roughness=0.35)
    ring_mat = pbr("M_PodCapsule_Ring", COL_CLIENT_GLOW, metallic=0.0, roughness=0.2,
                   emission_color=COL_CLIENT_GLOW, emission_strength=3.0)
    cap_mat = pbr("M_PodCapsule_Cap", (0.25, 0.27, 0.30, 1.0), metallic=0.85, roughness=0.25)

    body = primitive_cyl("Module_PodCapsule", pod_mat, radius=0.25, depth=0.7)
    ring = primitive_cyl("pod_ring", ring_mat, radius=0.27, depth=0.12, loc=(0, 0, 0))
    cap_top = primitive_cyl("pod_cap_t", cap_mat, radius=0.23, depth=0.08, loc=(0, 0, 0.38))
    cap_bot = primitive_cyl("pod_cap_b", cap_mat, radius=0.23, depth=0.08, loc=(0, 0, -0.38))
    join_to(body, [ring, cap_top, cap_bot])
    return body


def build_conduit_vertical_shaft():
    """Conduit_VerticalShaft: Vertical cylindrical conduit pipe with connector flanges."""
    pipe_mat = pbr("M_Conduit_Pipe", COL_CONDUIT_PIPE, metallic=0.3, roughness=0.2,
                   emission_color=COL_CONDUIT_PIPE, emission_strength=0.8)
    flange_mat = pbr("M_Conduit_Flange", (0.50, 0.55, 0.60, 1.0), metallic=0.9, roughness=0.25)

    pipe = primitive_cyl("Conduit_VerticalShaft", pipe_mat, radius=0.12, depth=2.0)
    flange_t = primitive_cyl("c_flange_t", flange_mat, radius=0.18, depth=0.10, loc=(0, 0, 0.95))
    flange_b = primitive_cyl("c_flange_b", flange_mat, radius=0.18, depth=0.10, loc=(0, 0, -0.95))
    join_to(pipe, [flange_t, flange_b])
    return pipe


def build_conduit_elbow():
    """Conduit_Elbow: 90-degree curved conduit elbow connector."""
    pipe_mat = pbr("M_Conduit_Elbow", COL_CONDUIT_PIPE, metallic=0.3, roughness=0.2,
                   emission_color=COL_CONDUIT_PIPE, emission_strength=0.8)
    flange_mat = pbr("M_Conduit_Flange", (0.50, 0.55, 0.60, 1.0), metallic=0.9, roughness=0.25)

    vert = primitive_cyl("Conduit_Elbow", pipe_mat, radius=0.12, depth=0.5, loc=(0, 0, 0.25))
    corner = primitive_box("c_elbow_corner", pipe_mat, size=(0.28, 0.28, 0.28), loc=(0, 0, 0.5))
    horiz = primitive_box("c_elbow_h", pipe_mat, size=(0.50, 0.24, 0.24), loc=(0.25, 0, 0.5))
    flange = primitive_box("c_elbow_flange", flange_mat, size=(0.08, 0.32, 0.32), loc=(0.52, 0, 0.5))
    join_to(vert, [corner, horiz, flange])
    return vert


def build_client_slab():
    """Client_Slab: Floating minimalist terminal pad representing remote client tooling."""
    pad_mat = pbr("M_Client_Pad", COL_CLIENT_PAD, metallic=0.8, roughness=0.3)
    glow_mat = pbr("M_Client_Glow", COL_CLIENT_GLOW, metallic=0.0, roughness=0.2,
                   emission_color=COL_CLIENT_GLOW, emission_strength=3.0)
    pip_mat = pbr("M_Client_Pip", (0.80, 0.82, 0.85, 1.0), metallic=0.9, roughness=0.2)

    slab = primitive_box("Client_Slab", pad_mat, size=(1.2, 0.8, 0.08))
    screen = primitive_box("client_screen", glow_mat, size=(1.0, 0.6, 0.02), loc=(0, 0, 0.045))
    
    pips = []
    for sx in (-0.52, 0.52):
        for sy in (-0.32, 0.32):
            pips.append(primitive_cyl("client_pip", pip_mat, radius=0.02, depth=0.04, loc=(sx, sy, 0.05)))
            
    join_to(slab, [screen] + pips)
    return slab


# ---------------------------------------------------------------------------
# Scene setup / export
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SPEC-02: Rectangular Layer Trays & Chamfered Component Cuboids (Transformer Reference)
# ---------------------------------------------------------------------------

def build_layer_tray_control():
    """LayerTray_Control: Open rectangular glass tray for control plane with cyan rim."""
    tray_mat = pbr("M_Tray_Control_Glass", (0.15, 0.25, 0.35, 1.0), metallic=0.1, roughness=0.2)
    rim_mat = pbr("M_Tray_Control_Rim", (0.05, 0.85, 0.95, 1.0), metallic=0.2, roughness=0.1,
                  emission_color=(0.05, 0.85, 0.95, 1.0), emission_strength=4.0)

    # Floor base
    floor = primitive_box("LayerTray_Control", tray_mat, size=(6.5, 4.2, 0.08), loc=(0, 0, 0.04))
    # Low walls around perimeter
    w_front = primitive_box("tc_wf", tray_mat, size=(6.5, 0.08, 0.35), loc=(0, -2.06, 0.175))
    w_back  = primitive_box("tc_wb", tray_mat, size=(6.5, 0.08, 0.35), loc=(0, 2.06, 0.175))
    w_left  = primitive_box("tc_wl", tray_mat, size=(0.08, 4.04, 0.35), loc=(-3.21, 0, 0.175))
    w_right = primitive_box("tc_wr", tray_mat, size=(0.08, 4.04, 0.35), loc=(3.21, 0, 0.175))
    # Glowing top rim lines
    r_front = primitive_box("tc_rf", rim_mat, size=(6.54, 0.06, 0.06), loc=(0, -2.06, 0.35))
    r_back  = primitive_box("tc_rb", rim_mat, size=(6.54, 0.06, 0.06), loc=(0, 2.06, 0.35))
    r_left  = primitive_box("tc_rl", rim_mat, size=(0.06, 4.06, 0.06), loc=(-3.21, 0, 0.35))
    r_right = primitive_box("tc_rr", rim_mat, size=(0.06, 4.06, 0.06), loc=(3.21, 0, 0.35))

    join_to(floor, [w_front, w_back, w_left, w_right, r_front, r_back, r_left, r_right])
    return floor


def build_layer_tray_worker():
    """LayerTray_Worker: Open rectangular glass tray for worker node floor with emerald rim."""
    tray_mat = pbr("M_Tray_Worker_Glass", (0.12, 0.22, 0.18, 1.0), metallic=0.1, roughness=0.2)
    rim_mat = pbr("M_Tray_Worker_Rim", (0.10, 0.90, 0.45, 1.0), metallic=0.2, roughness=0.1,
                  emission_color=(0.10, 0.90, 0.45, 1.0), emission_strength=4.0)

    floor = primitive_box("LayerTray_Worker", tray_mat, size=(7.5, 4.5, 0.08), loc=(0, 0, 0.04))
    w_front = primitive_box("tw_wf", tray_mat, size=(7.5, 0.08, 0.35), loc=(0, -2.21, 0.175))
    w_back  = primitive_box("tw_wb", tray_mat, size=(7.5, 0.08, 0.35), loc=(0, 2.21, 0.175))
    w_left  = primitive_box("tw_wl", tray_mat, size=(0.08, 4.34, 0.35), loc=(-3.71, 0, 0.175))
    w_right = primitive_box("tw_wr", tray_mat, size=(0.08, 4.34, 0.35), loc=(3.71, 0, 0.175))
    r_front = primitive_box("tw_rf", rim_mat, size=(7.54, 0.06, 0.06), loc=(0, -2.21, 0.35))
    r_back  = primitive_box("tw_rb", rim_mat, size=(7.54, 0.06, 0.06), loc=(0, 2.21, 0.35))
    r_left  = primitive_box("tw_rl", rim_mat, size=(0.06, 4.36, 0.06), loc=(-3.71, 0, 0.35))
    r_right = primitive_box("tw_rr", rim_mat, size=(0.06, 4.36, 0.06), loc=(3.71, 0, 0.35))

    join_to(floor, [w_front, w_back, w_left, w_right, r_front, r_back, r_left, r_right])
    return floor


def build_layer_tray_vault():
    """LayerTray_Vault: Open rectangular glass tray for etcd cluster vault with amber rim."""
    tray_mat = pbr("M_Tray_Vault_Glass", (0.25, 0.18, 0.12, 1.0), metallic=0.1, roughness=0.2)
    rim_mat = pbr("M_Tray_Vault_Rim", (1.0, 0.65, 0.10, 1.0), metallic=0.2, roughness=0.1,
                  emission_color=(1.0, 0.65, 0.10, 1.0), emission_strength=4.0)

    floor = primitive_box("LayerTray_Vault", tray_mat, size=(4.5, 2.8, 0.08), loc=(0, 0, 0.04))
    w_front = primitive_box("tv_wf", tray_mat, size=(4.5, 0.08, 0.30), loc=(0, -1.36, 0.15))
    w_back  = primitive_box("tv_wb", tray_mat, size=(4.5, 0.08, 0.30), loc=(0, 1.36, 0.15))
    w_left  = primitive_box("tv_wl", tray_mat, size=(0.08, 2.64, 0.30), loc=(-2.21, 0, 0.15))
    w_right = primitive_box("tv_wr", tray_mat, size=(0.08, 2.64, 0.30), loc=(2.21, 0, 0.15))
    r_front = primitive_box("tv_rf", rim_mat, size=(4.54, 0.06, 0.06), loc=(0, -1.36, 0.30))
    r_back  = primitive_box("tv_rb", rim_mat, size=(4.54, 0.06, 0.06), loc=(0, 1.36, 0.30))
    r_left  = primitive_box("tv_rl", rim_mat, size=(0.06, 2.66, 0.06), loc=(-2.21, 0, 0.30))
    r_right = primitive_box("tv_rr", rim_mat, size=(0.06, 2.66, 0.06), loc=(2.21, 0, 0.30))

    join_to(floor, [w_front, w_back, w_left, w_right, r_front, r_back, r_left, r_right])
    return floor


def build_cuboid_apiserver():
    """Cuboid_APIServer: Chamfered cyan metallic cuboid with status bar and dual ports."""
    body_mat = pbr("M_Cuboid_APIServer_Body", (0.05, 0.45, 0.75, 1.0), metallic=0.8, roughness=0.25)
    bar_mat = pbr("M_Cuboid_APIServer_Bar", (0.05, 0.85, 0.95, 1.0), metallic=0.0, roughness=0.1,
                  emission_color=(0.05, 0.85, 0.95, 1.0), emission_strength=4.0)
    port_mat = pbr("M_Cuboid_APIServer_Port", (0.15, 0.18, 0.22, 1.0), metallic=0.9, roughness=0.2)

    box = primitive_box("Cuboid_APIServer", body_mat, size=(1.1, 0.7, 0.6))
    bar = primitive_box("apiserver_bar", bar_mat, size=(0.9, 0.04, 0.06), loc=(0, 0, 0.31))
    port_l = primitive_box("apiserver_pl", port_mat, size=(0.14, 0.04, 0.14), loc=(-0.25, -0.36, 0))
    port_r = primitive_box("apiserver_pr", port_mat, size=(0.14, 0.04, 0.14), loc=(0.25, -0.36, 0))

    join_to(box, [bar, port_l, port_r])
    return box


def build_cuboid_etcd():
    """Cuboid_etcd: Chamfered slate cuboid with glowing amber Raft consensus lens."""
    body_mat = pbr("M_Cuboid_etcd_Body", (0.22, 0.24, 0.28, 1.0), metallic=0.6, roughness=0.4)
    lens_mat = pbr("M_Cuboid_etcd_Lens", (1.0, 0.65, 0.10, 1.0), metallic=0.0, roughness=0.1,
                   emission_color=(1.0, 0.65, 0.10, 1.0), emission_strength=5.0)

    box = primitive_box("Cuboid_etcd", body_mat, size=(0.9, 0.7, 0.55))
    lens = primitive_box("etcd_lens", lens_mat, size=(0.7, 0.04, 0.12), loc=(0, -0.36, 0.05))
    join_to(box, [lens])
    return box


def build_cuboid_supervisor():
    """Cuboid_Supervisor: Chamfered violet cuboid with purple telemetry groove."""
    body_mat = pbr("M_Cuboid_Supervisor_Body", (0.45, 0.20, 0.75, 1.0), metallic=0.5, roughness=0.35)
    groove_mat = pbr("M_Cuboid_Supervisor_Groove", (0.75, 0.35, 0.95, 1.0), metallic=0.0, roughness=0.1,
                     emission_color=(0.75, 0.35, 0.95, 1.0), emission_strength=3.5)

    box = primitive_box("Cuboid_Supervisor", body_mat, size=(0.95, 0.65, 0.5))
    groove = primitive_box("sup_groove", groove_mat, size=(0.80, 0.50, 0.02), loc=(0, 0, 0.26))
    join_to(box, [groove])
    return box


def build_cuboid_kubelet():
    """Cuboid_Kubelet: Chamfered emerald cuboid with green heartbeat LED."""
    body_mat = pbr("M_Cuboid_Kubelet_Body", (0.10, 0.60, 0.40, 1.0), metallic=0.4, roughness=0.3)
    led_mat = pbr("M_Cuboid_Kubelet_LED", (0.10, 0.95, 0.45, 1.0), metallic=0.0, roughness=0.1,
                  emission_color=(0.10, 0.95, 0.45, 1.0), emission_strength=4.5)

    box = primitive_box("Cuboid_Kubelet", body_mat, size=(0.65, 0.45, 0.4))
    led = primitive_box("kubelet_led", led_mat, size=(0.10, 0.04, 0.10), loc=(0, -0.23, 0.05))
    join_to(box, [led])
    return box


def build_cuboid_containerd():
    """Cuboid_Containerd: Chamfered slate teal cuboid with container runtime slots."""
    body_mat = pbr("M_Cuboid_Containerd_Body", (0.18, 0.45, 0.45, 1.0), metallic=0.6, roughness=0.35)
    slot_mat = pbr("M_Cuboid_Containerd_Slot", (0.10, 0.25, 0.25, 1.0), metallic=0.9, roughness=0.2)

    box = primitive_box("Cuboid_Containerd", body_mat, size=(0.65, 0.45, 0.4))
    slots = []
    for i in range(3):
        x = -0.16 + i * 0.16
        slots.append(primitive_box("cnt_slot_%d" % i, slot_mat, size=(0.06, 0.04, 0.24), loc=(x, -0.23, 0)))
    join_to(box, slots)
    return box


def build_cuboid_pod():
    """Cuboid_Pod: Chamfered workload pod cuboid with workload status stripe."""
    body_mat = pbr("M_Cuboid_Pod_Body", (0.20, 0.50, 0.85, 1.0), metallic=0.4, roughness=0.35)
    stripe_mat = pbr("M_Cuboid_Pod_Stripe", (0.25, 0.90, 0.95, 1.0), metallic=0.0, roughness=0.1,
                    emission_color=(0.25, 0.90, 0.95, 1.0), emission_strength=3.0)

    box = primitive_box("Cuboid_Pod", body_mat, size=(0.85, 0.55, 0.45))
    stripe = primitive_box("pod_stripe", stripe_mat, size=(0.75, 0.04, 0.08), loc=(0, -0.28, 0))
    join_to(box, [stripe])
    return box


def build_cuboid_ray():
    """Cuboid_Ray: Chamfered electric magenta cuboid with high-throughput tensor bus channels."""
    body_mat = pbr("M_Cuboid_Ray_Body", (0.75, 0.15, 0.80, 1.0), metallic=0.5, roughness=0.3)
    channel_mat = pbr("M_Cuboid_Ray_Channel", (0.95, 0.35, 0.95, 1.0), metallic=0.2, roughness=0.1,
                      emission_color=(0.95, 0.35, 0.95, 1.0), emission_strength=4.0)

    box = primitive_box("Cuboid_Ray", body_mat, size=(0.95, 0.65, 0.5))
    ch1 = primitive_box("ray_ch1", channel_mat, size=(0.85, 0.06, 0.02), loc=(0, -0.15, 0.26))
    ch2 = primitive_box("ray_ch2", channel_mat, size=(0.85, 0.06, 0.02), loc=(0, 0.15, 0.26))
    join_to(box, [ch1, ch2])
    return box

def build_cuboid_daemonset():
    """
    Builds a low-profile sleek chamfered chassis representing a DaemonSet pod.
    Includes PBR metallic body and emissive cyan/teal status indicators.
    """
    # 1. Create Materials
    mat_chassis = pbr(
        "Mat_DaemonSet_Chassis",
        base_color=(0.14, 0.16, 0.18, 1.0),
        metallic=0.7,
        roughness=0.3
    )
    
    mat_led = pbr(
        "Mat_DaemonSet_LED",
        base_color=(0.10, 0.85, 0.80, 1.0),
        metallic=0.0,
        roughness=0.2,
        emission_color=(0.10, 0.85, 0.80, 1.0),
        emission_strength=4.0
    )

    # 2. Create Main Chassis
    # Size: (0.70, 0.45, 0.30)
    chassis = primitive_box(
        "Cuboid_DaemonSet_Body",
        mat_chassis,
        size=(0.70, 0.45, 0.30),
        loc=(0, 0, 0)
    )
    
    # Apply chamfer/bevel to chassis for sleek look
    # We use bmesh to bevel edges slightly
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(chassis.data)
    bmesh.ops.bevel(
        bm,
        geom=bm.edges[:],
        offset=0.02,
        segments=2,
        profile=0.5,
        affect='EDGES'
    )
    bm.to_mesh(chassis.data)
    bm.free()

    # 3. Create LED Bar (Front Face Indicator)
    # Positioned on the front face (Y negative or positive depending on orientation, let's say Y- is front)
    # Chassis Y half-size is 0.225. Place LED slightly in front.
    led_bar = primitive_box(
        "Cuboid_DaemonSet_LED_Bar",
        mat_led,
        size=(0.50, 0.02, 0.04),
        loc=(0, -0.235, 0.05) # Slightly above center, protruding from front
    )
    
    # 4. Create Dual Ring Ports (Representing Network/eBPF)
    # Using small cylinders or boxes as simplified ports on the side or back
    # Let's put two small emissive squares on the back face (Y positive)
    port1 = primitive_box(
        "Cuboid_DaemonSet_Port_1",
        mat_led,
        size=(0.06, 0.02, 0.06),
        loc=(-0.15, 0.235, -0.05)
    )
    
    port2 = primitive_box(
        "Cuboid_DaemonSet_Port_2",
        mat_led,
        size=(0.06, 0.02, 0.06),
        loc=(0.15, 0.235, -0.05)
    )

    # 5. Join all parts into the root object
    join_to(chassis, [led_bar, port1, port2])
    
    # Rename the final joined object to the required name
    chassis.name = "Cuboid_DaemonSet"
    
    return chassis


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block_list in (bpy.data.meshes, bpy.data.materials):
        for block in list(block_list):
            if block.users == 0:
                block_list.remove(block)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)
    for cam in list(bpy.data.cameras):
        bpy.data.cameras.remove(cam)


def main():
    reset_scene()

    builders = [
        build_node_tray,
        build_control_plane_cube,
        build_pod_cylinder,
        build_framework_ray,
        build_framework_spark,
        build_database_postgres,
        build_cache_redis,
        build_conduit_link,
        # New Skyscraper & Procedural Conduit Stack builders
        build_skyscraper_floor_tray,
        build_skyscraper_penthouse,
        build_control_plane_vault,
        build_module_kubelet,
        build_module_containerd,
        build_module_pod_capsule,
        build_conduit_vertical_shaft,
        build_conduit_elbow,
        build_client_slab,
        # SPEC-02 Layer Trays & Cuboids
        build_layer_tray_control,
        build_layer_tray_worker,
        build_layer_tray_vault,
        build_cuboid_apiserver,
        build_cuboid_etcd,
        build_cuboid_supervisor,
        build_cuboid_kubelet,
        build_cuboid_containerd,
        build_cuboid_pod,
        build_cuboid_ray,
        build_cuboid_daemonset,
    ]

    # Lay assets out in a row along +X with even pitch for kit browsing.
    pitch = 2.8
    for i, fn in enumerate(builders):
        obj = fn()
        obj.location = (i * pitch, 0.0, 0.0)
        print("[build] %-24s verts=%d mats=%d" %
              (obj.name, len(obj.data.vertices), len(obj.data.materials)))

    # Verify required names exist before export.
    required = [
        "NodeTray", "ControlPlane_Cube", "Pod_Cylinder",
        "Framework_Ray", "Framework_Spark", "Database_Postgres",
        "Cache_Redis", "Conduit_Link",
        "Skyscraper_FloorTray", "Skyscraper_Penthouse", "ControlPlane_Vault",
        "Module_Kubelet", "Module_Containerd", "Module_PodCapsule",
        "Conduit_VerticalShaft", "Conduit_Elbow", "Client_Slab",
        "LayerTray_Control", "LayerTray_Worker", "LayerTray_Vault",
        "Cuboid_APIServer", "Cuboid_etcd", "Cuboid_Supervisor",
        "Cuboid_Kubelet", "Cuboid_Containerd", "Cuboid_Pod", "Cuboid_Ray",
        "Cuboid_DaemonSet"
    ]
    present = {o.name for o in bpy.context.scene.objects}
    missing = [n for n in required if n not in present]
    if missing:
        raise RuntimeError("missing required objects: %s" % missing)

    os.makedirs(OUT_DIR, exist_ok=True)

    bpy.ops.object.select_all(action="DESELECT")
    for n in required:
        bpy.data.objects[n].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[required[0]]

    bpy.ops.export_scene.gltf(
        filepath=OUT_GLB,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_yup=True,
        export_extras=True,
    )

    size = os.path.getsize(OUT_GLB)
    if size <= 0:
        raise RuntimeError("exported GLB is empty: %s" % OUT_GLB)
    print("[export] wrote %s (%d bytes)" % (OUT_GLB, size))
    return 0


if __name__ == "__main__":
    rc = 1
    try:
        rc = main()
    except Exception:
        traceback.print_exc()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(rc)
