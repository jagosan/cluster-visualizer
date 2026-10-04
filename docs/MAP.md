# Symbol & File Map: Cluster Visualizer (`cluster-vis`)

## Specifications & Architecture
- `specs/00-system-architecture.md`: Master specification, data contracts, and acceptance criteria.
- `docs/architecture/00-system-architecture.md`: Architecture blueprint, spatial layout, data flows, and hosting portability.
- `specs/01-architectural-skyscraper-topology.md`: Skyscraper topology, layered building levels, client horizon, and procedural conduits.
- `docs/architecture/01-architectural-skyscraper-topology.md`: Skyscraper architectural blueprint, spatial elevation matrix, and conduit ADRs.
- `specs/02-layered-rectangular-architecture.md`: Master specification for Transformer/DeepSeek-style 3D layered rectangular architecture.
- `docs/architecture/02-layered-rectangular-architecture.md`: Blueprint and design specifications for layer trays and component cuboids.
- `specs/03-horizontal-node-peers-and-diff-engine.md`: Master specification for horizontal node peers, 3D semantic git-diff engine, and universal cluster exporter.
- `docs/architecture/03-horizontal-node-peers-and-diff-engine.md`: Blueprint for single worker deck layout, volumetric diffing, and export CLI.
- `specs/04-in-cluster-streaming-operator.md`: In-cluster CRD (`clustervis.io/v1alpha1`) & real-time SSE topology streaming operator.
- `docs/architecture/04-in-cluster-streaming-operator.md`: Blueprint for SSE event streaming, dynamic mutations, and secret scrubbing.
- `specs/05-time-travel-topology-scrubber.md`: Time-travel cluster topology playback, delta recording, and HUD scrubber controls.
- `docs/architecture/05-time-travel-topology-scrubber.md`: Blueprint for chronological keyframes, spatial tweening, and timeline scrubber HUD.
- `specs/06-ephemeral-multi-cluster-testbed-and-live-streaming.md`: Master specification for ephemeral multi-cluster testbeds on Chunkito, K3d driver, and live streaming fleet matrix.
- `docs/architecture/06-ephemeral-multi-cluster-testbed-and-live-streaming.md`: Architectural blueprint for testbed orchestration, Tailscale streaming gateway, and multi-viewport layouts.
- `specs/07-portable-helm-packaging-and-latency-topology.md`: Master specification for in-cluster Helm packaging, latency-as-distance force field layout, and federated browser security.
- `docs/architecture/07-portable-helm-packaging-and-latency-topology.md`: Architectural blueprint for Helm topology, synthetic TCP probe daemonset, TokenReview auth, and dual-mode spatial lerping.
- specs/08-subterranean-dependencies-and-compute-classes.md: Master specification for subterranean foundation tiers (B1-B3), Karpenter machine shapes, GCP KCC & kro managed cloud vaults, and plunge latency conduits.
- docs/architecture/08-subterranean-dependencies-and-compute-classes.md: Blueprint for subterranean foundation tiers (B1-B3), Karpenter machine shapes, GCP KCC & kro managed cloud vaults, and plunge latency conduits.
- `specs/09-pod-autoscaling-morphing-and-kueue-staging.md`: Master specification for proportional pod capsule sizing, VPA in-place morphing, HPA lateral replication, and the external Kueue gang-scheduling staging yard.
- `docs/architecture/09-pod-autoscaling-morphing-and-kueue-staging.md`: Architectural blueprint for proportional capsules, VPA morphing, staging yard tarmac, and Kueue gang containers.
- `specs/10-interactive-ui-cluster-onboarding-sample-catalog-and-autoscaling-traffic-harness.md`: Master specification for interactive UI cluster onboarding, Helm install generator, instant simulated sample catalog, and autoscaling traffic simulation test harness.
- `docs/architecture/10-interactive-ui-cluster-onboarding-sample-catalog-and-autoscaling-traffic-harness.md`: Architectural blueprint for UI onboarding modals, sample catalog fixtures, discrete-event queuing simulation, and comparative scheduling latency dynamics.
- `docs/MAP.md`: This symbol and directory reference map.

## 3D Asset Pipeline (Blender `bpy`)
- `blender/build_cluster_assets.py`: Headless Blender script generating procedural models with PBR materials into `public/assets/cluster-kit.glb`.

## Ingestion, Graph Engine & Time-Travel (Python)
- `src/ingestion/models.py`: Pydantic models for `ClusterGraph`, `NodeComponent`, `DataFlowEdge`, `DiffReport`.
- `src/ingestion/timeline_models.py`: Pydantic models for `TimelineEvent`, `ClusterTimelineKeyframe`, `ClusterTimeline`.
- `src/ingestion/extractor.py`: Static Kubernetes manifest topology extractor.
- `src/ingestion/exporter.py`: Universal dynamic cluster exporter CLI (`cluster-vis dump`) querying live kubeconfigs.
- `src/ingestion/recorder.py`: Time-travel cluster topology recorder CLI (`cluster-vis record`) with delta deduplication.
- `src/ingestion/frameworks.py`: Specialized detectors for Ray, Spark, PostgreSQL, and Redis CRDs and workloads.
- `src/ingestion/differ.py`: Side-by-side graph diff classifier comparing two clusters.
- `src/ingestion/layout.py`: Spatial layout generator for horizontal worker deck ($Y = 0.5$) and control plane tiers.
- `scripts/generate_synthetic_timeline.py`: Synthetic rollout testbed generator for multi-keyframe timeline testing.

## In-Cluster Operator & Streaming Server (Python)
- `deploy/crd/clustervis.io_clustertopologysnapshots.yaml`: CRD manifest for `ClusterTopologySnapshot`.
- `deploy/operator/operator.yaml`: Kubernetes Deployment, ServiceAccount, and RBAC manifests.
- `src/operator/controller.py`: In-cluster Kubernetes watch informer loop reconciling pods, nodes, and CRDs.
- `src/operator/kcc_mapper.py`: Normalizes KCC/kro CRDs and node machine shapes into subterranean strata resources.
- `src/operator/server.py`: Lightweight HTTP & SSE streaming server (`/api/v1/topology/stream`, `/snapshot`, `/healthz`).
- `src/operator/auth.py`: TokenReview and SubjectAccessReview bearer token authenticator and RBAC validator.
- `src/operator/graph_engine.py`: In-memory topological graph, secret scrubbing, and latency edge aggregator.

## Helm Packaging & Synthetic Probe
- `charts/clustervis/Chart.yaml`: Helm chart metadata for unified in-cluster deployment.
- `charts/clustervis/values.yaml`: Default configuration values for operator, probe, auth, and ingress.
- `charts/clustervis/templates/`: Deployment, DaemonSet, Service, RBAC, and optional Ingress manifests.
- `src/probe/main.py`: Microscopic unprivileged TCP SYN round-robin ping probe daemon.
- `src/ingestion/latency_layout.py`: Force-directed spring-mass graph layout engine translating latency to spatial distance.

## Ephemeral Testbed & Chaos Injector (Python)
- `src/testbed/models.py`: Pydantic models for `FleetSpec`, `ClusterSpec`, `ClusterStatus`, `FleetStatusReport`, `ChaosScenario`.
- `src/testbed/drivers/base.py`: Abstract `ClusterDriver` base class for lifecycle, status, and manifest application.
- `src/testbed/drivers/k3d.py`: Concrete `K3dDriver` for rapid k3s-in-Docker provisioning on Chunkito with mock fallback.
- `src/testbed/manager.py`: `TestbedManager` coordinating fleet provisioning, kubeconfig merging, and operator deployment.
- `src/testbed/chaos.py`: `ChaosInjector` supporting rollout restart, node drain/cordon, pod kill, and canary weight shifts.
- `src/testbed/cli.py`: Unified CLI entrypoint (`cluster-vis testbed up/down/status/deploy-operator/inject`).
- `testbeds/fleet-spec.yaml`: Declarative multi-cluster matrix configuration across Kubernetes minor versions.
- `testbeds/workloads/`: Sample declarative workload manifests (Prometheus, Postgres HA, Ray cluster, microservices, canary service).

## Frontend WebGL Client (Vite + TypeScript + Three.js)
- `index.html`: Entry HTML with dual viewport split-screen canvas, HUD overlay, and timeline scrubber container `#timeline-scrubber-dock`.
- `src/main.ts`: Application bootstrap, event listeners, and viewport layout controller.
- `src/scene/grid_controller.ts`: `GridController` managing Single, Dual Split, and Quad Grid (2x2) layouts with synchronized orbit cameras and version skew matrix HUD.
- `src/scene/cluster_viewport.ts`: `ClusterViewport` Three.js scene manager, dynamic mutation animations, camera, and raycaster.
- `src/scene/timeline_player.ts`: `TimelinePlayer` engine handling keyframe playback, seek interpolation, and delta transitions.
- `src/ui/timeline_scrubber.ts`: `TimelineScrubber` bottom-docked HUD with scrub bar, event pins, play/pause, and speed multipliers.
- `src/scene/live_stream.ts`: `LiveStreamManager` SSE client handling reconnection, heartbeat, and real-time topology mutation events (incl. SPEC-09 `vpa_recommendation`, `vpa_resize_committed`, `hpa_scale_out`, and Kueue `kueue_workload_updated` / `kueue_quota_deficit` / `kueue_quota_reserved` / `kueue_admission_admitted` / `kueue_gang_deployed`).
- `src/scene/pod_capsules.ts`: `PodCapsuleManager` procedural proportional pod capsules (SPEC-09 §3.1), status material cache, emissive pulse, and VPA resize retargeting.
- `src/scene/autoscaling_fx.ts`: `AutoscalingFxManager` SPEC-09 §3.2/§3.3/§7.2 autoscaling pipelines — VPA recommendation ghost hulls, in-place 1200ms geometry morph tweens with energy ripples, HPA golden supervisor dispatch pulses down the central riser, lateral conveyor slides into node tray slots, and KeyU autoscaling radar aura rings.
- `src/scene/staging_yard.ts`: `StagingYardManager` SPEC-09 §4.1/§4.2 exterior pre-admission staging yard — reinforced freight tarmac ($X \in [-24, -12]$, $Y = 0.2$) with runway beacons, taxiway markers, and cargo rail intake rails; pending-pod anti-gravity hover bobbing at $Y = 1.0$; Karpenter NodeClaim ghost chassis wireframes on Sub-Level B1 ($Y = -2.5$) with luminous amber tractor beams; KeyY staging apron focus camera targets.
- `src/scene/kueue_pallet.ts`: `KueuePalletManager` SPEC-09 §5.2/§5.3 Kueue gang cargo containment pallets — modular industrial frames (corner posts, crossbeams, latch claws, floor plate) encasing constituent pods of a `Workload` on the staging rail ($X = -18.0$, dock domain $X \in [-21, -15]$, $Y \in [0.4, 1.8]$, $Z \in [-6, 6]$); holographic canvas HUD badges with workload name, LocalQueue/ClusterQueue, `X/Y Pods` count, and quota (vCPU / GiB / GPUs); lifecycle visuals: cold-blue standby + quota-deficit pulse (Inadmissible), amber spinning intake beacons + gantry crane lock (quota reserved), high-speed mag-rail transit tween ($X: -18 \to -8$, 2200 ms) with green admitted lighting, and 1400 ms gang deployment burst unlatching pods onto worker-deck targets; KeyK / `#btn-admit-gang` simulated admission trigger.
- `src/scene/layer_trays.ts`: `LayerTrayManager` procedural semi-transparent floor trays, machine shape chassis, and ground datum.
- `src/scene/subterranean_vaults.ts`: `SubterraneanVaultManager` procedural 3D vaults for CloudSQL, GCS, Pub/Sub, Redis, kro manifolds.
- `src/scene/plunge_conduits.ts`: `PlungeConduitManager` vertical Bezier conduits with latency spectrum shaders and degradation strobes.
- `src/scene/flank_labels.ts`: `FlankLabelManager` typographic billboard sprites floating on tower flanks.
- `src/scene/conduits.ts`: 3D procedural conduit pipe mesh generator and route splines.
- `src/scene/camera_sync.ts`: Synchronous dual-orbit camera controller.
- `src/scene/flow_particles.ts`: GPU / instanced particle system animating traffic and replication streams.
- `src/scene/diff_card.ts`: 3D floating billboarding HTML diff card anchored to drifted components.
- `src/ui/diff_inspector.ts`: Side-by-side comparison drawer, version mismatch highlights, and metric bars.
- `src/ui/cluster_selector.ts`: Dropdown / file loader for switching active clusters.
- `src/scene/layout_transition.ts`: Dual-mode coordinator lerping between Skyscraper and Latency Force coordinates.
- `src/ui/mode_toggle.ts`: HUD control for switching and tweening layout modes (`Skyscraper ⇄ Latency Field`).
- `src/ui/cluster_federation.ts`: Multi-cluster session store and client-side aggregator across SSE endpoints.
- `src/ui/auth_modal.ts`: Bearer token and OIDC authentication modal dialog.
- `src/ui/cluster_onboarding.ts`: SPEC-10 onboarding modal dialog for live Helm clusters and client-side connect.
- `src/ui/sample_catalog.ts`: SPEC-10 pre-packaged sample cluster registry for zero-delay instant loading.
- `src/scene/traffic_simulator.ts`: SPEC-10 discrete-event M/M/c/K queuing, autoscaling, and scheduling latency skew engine.
- `src/ui/traffic_deck.ts`: SPEC-10 bottom-docked translucent HUD traffic control deck.
- `src/ingestion/client_extractor.ts`: SPEC-10 in-browser Kubernetes API resource graph extractor.
