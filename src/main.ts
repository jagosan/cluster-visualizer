import { ClusterViewport } from './scene/cluster_viewport.js';
import type { ClusterGraphData } from './scene/cluster_viewport.js';
import { DiffInspectorDrawer } from './ui/diff_inspector.js';
import { LiveStreamManager } from './scene/live_stream.js';
import { TimelinePlayer } from './scene/timeline_player.js';
import type { ClusterTimelineData } from './scene/timeline_player.js';
import { TimelineScrubber } from './ui/timeline_scrubber.js';
import { GridController, type ViewportSlot, type GridMode } from './scene/grid_controller.js';
import { DiffSequenceEngine } from './scene/diff_sequence.js';
import { DiffMediaDeck } from './ui/diff_media_deck.js';
// SPEC-10 / TASK-CV-1101 + TASK-CV-1102: interactive cluster onboarding modal
// and the instant simulated sample catalog registry.
import { ClusterOnboardingModal, type ViewportSlotId } from './ui/cluster_onboarding.js';
// SPEC-10 / TASK-CV-1105: ⚡ dockable autoscaling traffic simulation harness.
import { TrafficControlDeck } from './ui/traffic_deck.js';
import type { TrafficDeckViewportSlot } from './ui/traffic_deck.js';

interface DiffReportData {
  source_cluster: string;
  target_cluster: string;
  summary: {
    identical_nodes: number;
    version_skew_nodes: number;
    missing_in_target: number;
    added_in_target: number;
  };
  nodes: {
    node_id: string;
    status: 'identical' | 'version_skew' | 'missing' | 'added';
    source_version?: string;
    target_version?: string;
    source_image?: string;
    target_image?: string;
    source_digest?: string;
    target_digest?: string;
    diff_details: string[];
  }[];
}

async function bootstrap() {
  const containerA = document.getElementById('viewport-a');
  const containerB = document.getElementById('viewport-b');
  const containerC = document.getElementById('viewport-c');
  const containerD = document.getElementById('viewport-d');
  const viewportsWrapper = document.getElementById('viewports-wrapper');
  if (!containerA || !containerB || !viewportsWrapper) {
    throw new Error('Viewport container panes not found in DOM');
  }

  const trafficDeckRef: { current: TrafficControlDeck | null } = { current: null };
  const btnTrafficHarness = document.getElementById('btn-traffic-harness');

  // 1. Initialize Viewports
  const viewportA = new ClusterViewport(containerA, 'Cluster Alpha (v1.36.4)');
  const viewportB = new ClusterViewport(containerB, 'Cluster Beta (v1.35.8)');
  const viewportC = containerC ? new ClusterViewport(containerC, 'Cluster Gamma (Edge v1.37.0)') : null;
  const viewportD = containerD ? new ClusterViewport(containerD, 'Cluster Delta (Canary v1.36.4)') : null;

  // 2. Load 3D Asset Kit
  const assetKitUrl = './assets/cluster-kit.glb';
  const assetPromises = [
    viewportA.loadAssets(assetKitUrl),
    viewportB.loadAssets(assetKitUrl),
  ];
  if (viewportC) assetPromises.push(viewportC.loadAssets(assetKitUrl));
  if (viewportD) assetPromises.push(viewportD.loadAssets(assetKitUrl));
  await Promise.all(assetPromises);

  // 3. Load Cluster Data & Diff Report
  const [dataA, dataB, diffReport]: [ClusterGraphData, ClusterGraphData, DiffReportData] =
    await Promise.all([
      fetch('./data/cluster-alpha.json').then((r) => r.json()),
      fetch('./data/cluster-beta.json').then((r) => r.json()),
      fetch('./data/cluster-diff.json').then((r) => r.json()),
    ]);

  // Build diff lookups
  const diffMapA = new Map<string, { status: any; diffDetails: string[] }>();
  const diffMapB = new Map<string, { status: any; diffDetails: string[] }>();

  for (const match of diffReport.nodes) {
    diffMapA.set(match.node_id, {
      status: match.status,
      diffDetails: match.diff_details,
    });
    if (match.status === 'added') {
      diffMapB.set(match.node_id, {
        status: match.status,
        diffDetails: match.diff_details,
      });
    }
  }

  // Also map version skews and identical nodes to cluster B nodes
  for (const nodeB of dataB.nodes) {
    if (diffMapB.has(nodeB.id)) continue;
    const matchA = dataA.nodes.find((nA) => {
      if (nA.id === nodeB.id) return true;
      if (nA.name === nodeB.name && nA.namespace === nodeB.namespace) return true;
      const baseA = nA.name.split('-')[0];
      const baseB = nodeB.name.split('-')[0];
      return nA.kind === nodeB.kind && baseA === baseB && nA.namespace === nodeB.namespace;
    });
    if (matchA && diffMapA.has(matchA.id)) {
      diffMapB.set(nodeB.id, diffMapA.get(matchA.id)!);
    }
  }

  // Populate viewports
  viewportA.setClusterData(dataA, diffMapA);
  viewportB.setClusterData(dataB, diffMapB);
  if (viewportC) viewportC.setClusterData(dataA);
  if (viewportD) viewportD.setClusterData(dataB);

  // Wire Diff Media Deck
  const diffReportData: DiffReportData = {
    source_cluster: diffReport.source_cluster,
    target_cluster: diffReport.target_cluster,
    summary: diffReport.summary,
    nodes: diffReport.nodes.map((n) => ({
      node_id: n.node_id,
      status: n.status,
      source_version: n.source_version,
      target_version: n.target_version,
      source_image: n.source_image,
      target_image: n.target_image,
      source_digest: n.source_digest,
      target_digest: n.target_digest,
      diff_details: n.diff_details,
    })),
  };
  const diffEngine = new DiffSequenceEngine();
  diffEngine.setSequenceSource({ report: diffReportData, alphaGraph: dataA, betaGraph: dataB });
  const diffDeck = new DiffMediaDeck(diffEngine);

  diffDeck.onItemSelect((item) => {
    if (viewportA) {
      if (item.kind === 'deleted' || item.kind === 'modified' || item.alphaPosition) {
        viewportA.focusComponent(item.id, item.alphaPosition);
        viewportA.setDiffHighlight(item.id, item.kind);
      } else {
        viewportA.clearDiffHighlight();
      }
    }
    if (viewportB) {
      if (item.kind === 'added' || item.kind === 'modified' || item.betaPosition) {
        viewportB.focusComponent(item.id, item.betaPosition);
        viewportB.setDiffHighlight(item.id, item.kind);
      } else {
        viewportB.clearDiffHighlight();
      }
    }
  });

  // Wire topbar button #btn-diff-tour
  const btnDiffTour = document.getElementById('btn-diff-tour');
  if (btnDiffTour) {
    btnDiffTour.addEventListener('click', () => {
      diffDeck.toggle();
    });
  }

  // Wire keyboard shortcut KeyD
  window.addEventListener('keydown', (event) => {
    if (event.code === 'KeyD' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      if (!(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) {
        diffDeck.toggle();
      }
    }
  });

  // 4. Viewport Slots & Grid Controller (SPEC-06)
  const slots: ViewportSlot[] = [
    {
      id: 'a',
      viewport: viewportA,
      container: containerA,
      title: 'Cluster Alpha',
      clusterName: 'stage-regular',
      k8sVersion: '1.36.4',
      channel: 'Regular',
    },
    {
      id: 'b',
      viewport: viewportB,
      container: containerB,
      title: 'Cluster Beta',
      clusterName: 'prod-regular',
      k8sVersion: '1.36.4',
      channel: 'Regular',
    },
  ];

  if (viewportC && containerC) {
    slots.push({
      id: 'c',
      viewport: viewportC,
      container: containerC,
      title: 'Cluster Gamma',
      clusterName: 'edge-rapid',
      k8sVersion: '1.37.0',
      channel: 'Rapid',
    });
  }

  if (viewportD && containerD) {
    slots.push({
      id: 'd',
      viewport: viewportD,
      container: containerD,
      title: 'Cluster Delta',
      clusterName: 'canary-eval',
      k8sVersion: '1.36.4',
      channel: 'Regular',
    });
  }

  const btnGridSingle = document.getElementById('btn-grid-single');
  const btnGridDual = document.getElementById('btn-grid-dual');
  const btnGridQuad = document.getElementById('btn-grid-quad');

  const gridController = new GridController(
    {
      wrapperElement: viewportsWrapper,
      hudContainer: document.getElementById('version-skew-matrix'),
      onModeChange: (mode: GridMode) => {
        btnGridSingle?.classList.toggle('active', mode === 'single');
        btnGridDual?.classList.toggle('active', mode === 'dual');
        btnGridQuad?.classList.toggle('active', mode === 'quad');
      },
    },
    slots
  );

  btnGridSingle?.addEventListener('click', () => gridController.setMode('single'));
  btnGridDual?.addEventListener('click', () => gridController.setMode('dual'));
  btnGridQuad?.addEventListener('click', () => gridController.setMode('quad'));

  // 4. Populate Topbar Summary Pills
  const pillsContainer = document.getElementById('summary-pills');
  if (pillsContainer) {
    const s = diffReport.summary;
    pillsContainer.innerHTML = `
      <div class="pill pill-identical">✓ ${s.identical_nodes} Identical</div>
      <div class="pill pill-skew">⚠ ${s.version_skew_nodes} Version Skews</div>
      <div class="pill pill-missing">✕ ${s.missing_in_target} Missing in Beta</div>
      <div class="pill pill-added">+ ${s.added_in_target} Added in Beta</div>
    `;
  }

  // 6. Inspection Drawer & Hover Tooltip
  const inspector = new DiffInspectorDrawer();

  viewportA.onNodeHovered = (node, x, y) => inspector.showTooltip(node, x, y);
  viewportB.onNodeHovered = (node, x, y) => inspector.showTooltip(node, x, y);

  viewportA.onNodeSelected = (node) => {
    if (!node) {
      inspector.close();
      return;
    }
    const peer = dataB.nodes.find((n) => n.kind === node.kind && n.name === node.name) || null;
    inspector.inspectNode(node, peer);
  };

  viewportB.onNodeSelected = (node) => {
    if (!node) {
      inspector.close();
      return;
    }
    const peer = dataA.nodes.find((n) => n.kind === node.kind && n.name === node.name) || null;
    inspector.inspectNode(node, peer);
  };

  // 7. Wire UI Controls
  const allViewports = [viewportA, viewportB, viewportC, viewportD];
  const btnSyncCam = document.getElementById('btn-sync-cam');
  if (btnSyncCam) {
    btnSyncCam.addEventListener('click', () => {
      const active = gridController.toggleCameraSync();
      btnSyncCam.classList.toggle('active', active);
    });
  }

  let flowsEnabled = true;
  const btnToggleFlows = document.getElementById('btn-toggle-flows');
  if (btnToggleFlows) {
    btnToggleFlows.addEventListener('click', () => {
      flowsEnabled = !flowsEnabled;
      btnToggleFlows.classList.toggle('active', flowsEnabled);
      viewportA.flowSystem.group.visible = flowsEnabled;
      viewportB.flowSystem.group.visible = flowsEnabled;
    });
  }

  const btnResetCam = document.getElementById('btn-reset-cam');
  // SPEC-09 §7.1 / TASK-CV-1003: Staging Apron Focus HUD button (KeyY twin).
  const btnStaging = document.getElementById('btn-staging');
  if (btnStaging) {
    btnStaging.addEventListener('click', () => {
      let focused = false;
      for (const vp of allViewports) {
        if (vp) focused = vp.toggleStagingFocus() || focused;
      }
      btnStaging.classList.toggle('active', focused);
    });
  }
  // TASK-CV-1002: Autoscaling Radar HUD button (mirrors the KeyU hotkey).
  const btnRadar = document.getElementById('btn-autoscaling-radar');
  if (btnRadar) {
    btnRadar.addEventListener('click', () => {
      let active = false;
      for (const vp of allViewports) {
        if (vp) active = vp.toggleAutoscalingRadar() || active;
      }
      btnRadar.classList.toggle('active', active);
    });
  }
  // SPEC-09 §7.3 / TASK-CV-1004: Simulated Gang Admission trigger — fires
  // the reserved -> admitted -> gang-deployed animation chain on the Kueue
  // cargo pallets (KeyK twin).
  const btnAdmitGang = document.getElementById('btn-admit-gang');
  if (btnAdmitGang) {
    btnAdmitGang.addEventListener('click', () => {
      let fired = false;
      for (const vp of allViewports) {
        if (vp && vp.simulateGangAdmission()) fired = true;
      }
      if (fired) {
        btnAdmitGang.classList.add('active');
        window.setTimeout(() => btnAdmitGang.classList.remove('active'), 5200);
      }
    });
  }
  if (btnResetCam) {
    btnResetCam.addEventListener('click', () => {
      viewportA.camera.position.set(12, 10, 15);
      viewportA.controls.target.set(0, 1.0, 0);
      viewportA.controls.update();

      viewportB.camera.position.set(12, 10, 15);
      viewportB.controls.target.set(0, 1.0, 0);
      viewportB.controls.update();
    });
  }

  // 8. Ground Datum cutaway hotkey (TASK-CV-903): KeyG / 'g' toggles the
  // smoked-glass ground plane between solid (1.0) and ghosted (0.1).
  // TASK-CV-904: KeyB / 'b' toggles the Subterranean camera preset (SPEC-08
  // §7.2): smooth orbit tween re-anchoring on (0, -5.0, 0) with an upward
  // perspective framing the foundational root system.
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    // Ignore while typing in text inputs / prompts
    const target = e.target as HTMLElement | null;
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
      return;
    }
    if (e.code === 'KeyG' || e.key === 'g' || e.key === 'G') {
      e.preventDefault();
      for (const vp of allViewports) {
        vp?.toggleGroundCutaway();
      }
    }
    if (e.code === 'KeyB' || e.key === 'b' || e.key === 'B') {
      e.preventDefault();
      for (const vp of allViewports) {
        vp?.toggleSubterraneanView();
      }
    }
    // SPEC-09 §7.2 / TASK-CV-1002: KeyU toggles the Autoscaling Radar
    // Overlay — pulsating golden auras over VPA/HPA-managed pods.
    if (e.code === 'KeyU' || e.key === 'u' || e.key === 'U') {
      e.preventDefault();
      let active = false;
      for (const vp of allViewports) {
        if (vp) active = vp.toggleAutoscalingRadar() || active;
      }
      btnRadar?.classList.toggle('active', active);
    }
    // SPEC-09 §7.1 / TASK-CV-1003: KeyY Staging Apron Focus — smoothly
    // pans/orbits to the pre-admission staging yard at X = -18.0 showing
    // pending pods, ghost chassis, and tractor beams; toggles back to the
    // tower preset.
    if (e.code === 'KeyY' || e.key === 'y' || e.key === 'Y') {
      e.preventDefault();
      let focused = false;
      for (const vp of allViewports) {
        if (vp) focused = vp.toggleStagingFocus() || focused;
      }
      btnStaging?.classList.toggle('active', focused);
    }
    // SPEC-09 §7.3 / TASK-CV-1104: KeyK Simulated Gang Admission — drives
    // the Kueue cargo pallet through mag-rail transit + gang deployment.
    if (e.code === 'KeyK' || e.key === 'k' || e.key === 'K') {
      e.preventDefault();
      let fired = false;
      for (const vp of allViewports) {
        if (vp && vp.simulateGangAdmission()) fired = true;
      }
      if (fired) {
        btnAdmitGang?.classList.add('active');
        window.setTimeout(() => btnAdmitGang?.classList.remove('active'), 5200);
      }
    }
    // SPEC-10 §6 / TASK-CV-1105: KeyT toggles the ⚡ traffic simulation
    // control deck (null-guarded — keys may land before bootstrap finishes).
    if (e.code === 'KeyT' || e.key === 't' || e.key === 'T') {
      e.preventDefault();
      const deck = trafficDeckRef.current;
      if (deck) {
        deck.toggle();
        btnTrafficHarness?.classList.toggle('active', deck.isOpen());
      }
    }
  });

  // 9. In-Cluster Streaming Operator Client (SPEC-04)
  const streamStatusDot = document.getElementById('stream-status-dot');
  const btnLiveStream = document.getElementById('btn-live-stream');

  const liveStream = new LiveStreamManager({
    onStatusChange: (status) => {
      if (!streamStatusDot || !btnLiveStream) return;
      streamStatusDot.className = 'stream-dot';
      btnLiveStream.classList.remove('active');

      if (status === 'connected') {
        streamStatusDot.classList.add('connected');
        btnLiveStream.classList.add('active');
        btnLiveStream.title = 'Live Stream Connected (Click to disconnect)';
      } else if (status === 'reconnecting') {
        streamStatusDot.classList.add('reconnecting');
        btnLiveStream.title = 'Live Stream Reconnecting...';
      } else {
        btnLiveStream.title = 'Connect to in-cluster streaming operator';
      }
    },
    onInitialSnapshot: (snapshot) => {
      if (snapshot && snapshot.nodes) {
        viewportA.setClusterData(snapshot);
      }
    },
    onNodeAdded: (node) => {
      viewportA.addNode(node);
    },
    onNodeRemoved: (nodeId) => {
      viewportA.removeNode(nodeId);
    },
    onNodeModified: (nodeId, diffDetails, status) => {
      viewportA.modifyNode(nodeId, diffDetails, status);
    },
    // SPEC-09 / TASK-CV-1002: VPA morphing & HPA lateral spawning pipelines.
    onVpaRecommendation: (payload) => {
      viewportA.applyVpaRecommendation(payload.node_id, payload.dimensions ?? null);
    },
    onVpaResizeCommitted: (payload) => {
      const height = payload.geometry?.height;
      const radius = payload.geometry?.radius;
      if (typeof height === 'number' && typeof radius === 'number') {
        viewportA.applyVpaResize(
          payload.node_id,
          height,
          radius,
          payload.duration_ms ?? 1200,
        );
      }
    },
    onHpaScaleOut: (payload) => {
      viewportA.applyHpaScaleOut(payload);
    },
    // SPEC-09 / TASK-CV-1003: staging-yard Karpenter provisioning pipeline.
    onKarpenterClaimUpdated: (payload) => {
      viewportA.applyKarpenterClaim(payload);
    },
    onKarpenterTractorBeam: (payload) => {
      viewportA.applyKarpenterTractorBeam(payload);
    },
    // SPEC-09 / TASK-CV-1004: Kueue gang cargo pallet lifecycle pipeline.
    onKueueWorkloadUpdated: (payload) => {
      viewportA.applyKueueWorkloadUpdated(payload);
    },
    onKueueQuotaDeficit: (payload) => {
      viewportA.applyKueueQuotaDeficit(payload);
    },
    onKueueQuotaReserved: (payload) => {
      viewportA.applyKueueQuotaReserved(payload);
    },
    onKueueAdmissionAdmitted: (payload) => {
      viewportA.applyKueueAdmissionAdmitted(payload);
    },
    onKueueGangDeployed: (payload) => {
      viewportA.applyKueueGangDeployed(payload);
    },
  });

  if (btnLiveStream) {
    btnLiveStream.addEventListener('click', () => {
      if (liveStream.getStatus() === 'connected') {
        const confirmDisconnect = confirm('Live Stream is active. Disconnect and return to static offline mode?');
        if (confirmDisconnect) {
          liveStream.disconnect();
        }
      } else {
        const defaultUrl = 'http://localhost:8080/api/v1/topology/stream';
        const targetUrl = prompt('Enter Operator Topology Stream SSE URL:', defaultUrl);
        if (targetUrl) {
          liveStream.connect(targetUrl.trim());
        }
      }
    });
  }

  // Auto-connect if ?stream= URL parameter is provided
  const streamParam = new URLSearchParams(window.location.search).get('stream');
  if (streamParam) {
    liveStream.connect(streamParam);
  }

  // 9b. SPEC-10 / TASK-CV-1101 + 1102: Interactive Cluster Onboarding.
  // `➕ ADD CLUSTER` opens the two-tab modal: live Helm/client connect and
  // the instant simulated sample catalog with 1-click viewport slot binding.
  const viewportBySlot = new Map<ViewportSlotId, ClusterViewport | null>([
    ['a', viewportA],
    ['b', viewportB],
    ['c', viewportC],
    ['d', viewportD],
  ]);

  const onboardingModal = new ClusterOnboardingModal({
    onClusterLoaded: (slotId, clusterData) => {
      const target = viewportBySlot.get(slotId) ?? viewportA;
      if (!target) return;
      target.setClusterData(clusterData);
      const slot = slots.find((s) => s.id === slotId);
      if (slot) {
        slot.clusterName = clusterData.metadata.cluster_name;
        slot.k8sVersion = clusterData.metadata.kubernetes_version.replace(/^v/, '');
      }
      // TASK-CV-1105: traffic deck re-discovers target workloads from the
      // freshly loaded graph (closure fires after bootstrap completes).
      trafficDeckRef.current?.refreshWorkloads();
    },
    onLiveConnect: (url, _token, config) => {
      // Operator Mode streams SSE; derive the stream URL from the probed
      // API base unless the user pointed straight at a stream endpoint.
      // (kubeconfig-proxy / client-direct full extraction lands with
      // TASK-CV-1103's browser extractor; the SSE path works unchanged for
      // proxies that expose the operator endpoints.)
      const base = url.replace(/\/+$/, '');
      const streamUrl = base.endsWith('/api/v1/topology/stream')
        ? base
        : `${base}/api/v1/topology/stream`;
      void config; // config is handed to the caller-side store; stream needs URL only
      liveStream.connect(streamUrl);
    },
    onClientGraphExtracted: (graph) => {
      // TASK-CV-1103: Tab 1 Mode B parsed the raw Kubernetes API entirely
      // client-side — hydrate the active viewport with zero server install.
      const target = viewportA ?? viewportB;
      if (!target) return;
      target.setClusterData(graph);
      const slot = slots.find((s) => s.id === 'a') ?? slots[0];
      if (slot) {
        slot.clusterName = graph.metadata.cluster_name;
        slot.k8sVersion = graph.metadata.kubernetes_version.replace(/^v/, '');
      }
      trafficDeckRef.current?.refreshWorkloads(); // TASK-CV-1105
    },
    onError: (message) => {
      console.warn('Cluster onboarding:', message);
    },
  });

  const btnAddCluster = document.getElementById('btn-add-cluster');
  if (btnAddCluster) {
    btnAddCluster.addEventListener('click', () => {
      if (onboardingModal.isOpen) {
        onboardingModal.close();
      } else {
        onboardingModal.open();
      }
    });
  }

  // 9c. SPEC-10 / TASK-CV-1105: ⚡ Autoscaling Traffic Simulation Harness.
  // Bottom-docked glass control deck driving the client-side M/M/c/K engine
  // (Engine A) with comparative per-viewport telemetry and SPEC-10 §6.3 flow
  // particle modulation. Workloads are discovered live from each viewport's
  // loaded cluster graph (refreshed on every cluster swap below).
  const deckSlots: TrafficDeckViewportSlot[] = [
    { id: 'a', label: 'Viewport A', title: 'Cluster Alpha', viewport: viewportA },
    { id: 'b', label: 'Viewport B', title: 'Cluster Beta', viewport: viewportB },
  ];
  if (viewportC) deckSlots.push({ id: 'c', label: 'Viewport C', title: 'Cluster Gamma', viewport: viewportC });
  if (viewportD) deckSlots.push({ id: 'd', label: 'Viewport D', title: 'Cluster Delta', viewport: viewportD });

  const trafficDeck = new TrafficControlDeck({
    slots: deckSlots,
    dockContainer: document.getElementById('traffic-deck-dock'),
    hpaIntervalSeconds: 1,
  });
  trafficDeckRef.current = trafficDeck;

  if (btnTrafficHarness) {
    btnTrafficHarness.addEventListener('click', () => {
      trafficDeck.toggle();
      btnTrafficHarness.classList.toggle('active', trafficDeck.isOpen());
    });
  }

  // 9. Time-Travel Playback & Historical Scrubber Engine (SPEC-05)
  const timelinePlayer = new TimelinePlayer();
  timelinePlayer.attachViewport(viewportA);

  const timelineScrubber = new TimelineScrubber();
  timelineScrubber.attachPlayer(timelinePlayer);

  // Auto-load synthetic rollout timeline if available
  fetch('./data/timelines/synthetic_rollout.json')
    .then((r) => {
      if (r.ok) return r.json();
      throw new Error('Default synthetic rollout timeline not found');
    })
    .then((timeline: ClusterTimelineData) => {
      timelinePlayer.loadTimeline(timeline);
      timelineScrubber.renderKeyframePins(timeline);
    })
    .catch((err) => {
      console.log('Historical timeline auto-load skipped:', err);
    });

  const btnTimeline = document.getElementById('btn-timeline');
  if (btnTimeline) {
    btnTimeline.addEventListener('click', () => {
      timelineScrubber.toggle();
      btnTimeline.classList.toggle('active');
    });
  }

  // 10. Expose globals for debugging and testing
  (window as any).__viewportA = viewportA;
  (window as any).__viewportB = viewportB;
  (window as any).__viewportC = viewportC;
  (window as any).__viewportD = viewportD;
  (window as any).__gridController = gridController;
  (window as any).__inspector = inspector;
  (window as any).__dataA = dataA;
  (window as any).__dataB = dataB;
  (window as any).__liveStream = liveStream;
  (window as any).__timelinePlayer = timelinePlayer;
  (window as any).__timelineScrubber = timelineScrubber;
  (window as any).__trafficDeck = trafficDeck;
  (window as any).__trafficSimulator = trafficDeck.simulator;

  // 11. Animation Loop
  let lastTime = performance.now();
  function animate(now: number) {
    requestAnimationFrame(animate);
    const delta = (now - lastTime) / 1000;
    lastTime = now;

    timelinePlayer.update(delta);
    // SPEC-10 / TASK-CV-1105: pump Engine A (queuing + autoscaling physics),
    // flow-particle modulation, and comparative telemetry refresh.
    trafficDeck.update(delta);
    gridController.renderAll(delta);
  }
  requestAnimationFrame(animate);
}

window.addEventListener('DOMContentLoaded', () => {
  bootstrap().catch((err) => {
    console.error('Failed to bootstrap Cluster Visualizer:', err);
  });
});
