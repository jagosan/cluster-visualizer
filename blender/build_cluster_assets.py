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
# Scene setup / export
# ---------------------------------------------------------------------------
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
    ]

    # Lay assets out in a row along +X with even pitch for kit browsing.
    pitch = 2.8
    for i, fn in enumerate(builders):
        obj = fn()
        obj.location = (i * pitch, 0.0, 0.0)
        print("[build] %-20s verts=%d mats=%d" %
              (obj.name, len(obj.data.vertices), len(obj.data.materials)))

    # Verify required names exist before export.
    required = ["NodeTray", "ControlPlane_Cube", "Pod_Cylinder",
                "Framework_Ray", "Framework_Spark", "Database_Postgres",
                "Cache_Redis", "Conduit_Link"]
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
