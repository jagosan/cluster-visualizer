#!/usr/bin/env python3
import re

with open("blender/build_cluster_assets.py", "r") as f:
    content = f.read()

spec02_builders = '''

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
'''

# Insert builders before `def reset_scene():`
idx = content.find("def reset_scene():")
if idx == -1:
    raise RuntimeError("def reset_scene(): not found")

new_content = content[:idx] + spec02_builders + "\n" + content[idx:]

# Add to builders list in main()
old_builders = """        build_conduit_vertical_shaft,
        build_conduit_elbow,
        build_client_slab,"""

new_builders = """        build_conduit_vertical_shaft,
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
        build_cuboid_ray,"""

new_content = new_content.replace(old_builders, new_builders)

# Add to required list
old_required = """        "Conduit_VerticalShaft", "Conduit_Elbow", "Client_Slab"
    ]"""

new_required = """        "Conduit_VerticalShaft", "Conduit_Elbow", "Client_Slab",
        "LayerTray_Control", "LayerTray_Worker", "LayerTray_Vault",
        "Cuboid_APIServer", "Cuboid_etcd", "Cuboid_Supervisor",
        "Cuboid_Kubelet", "Cuboid_Containerd", "Cuboid_Pod", "Cuboid_Ray"
    ]"""

new_content = new_content.replace(old_required, new_required)

with open("blender/build_cluster_assets.py", "w") as f:
    f.write(new_content)

print("Updated blender/build_cluster_assets.py with SPEC-02 models.")
