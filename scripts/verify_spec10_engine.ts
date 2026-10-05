// TASK-CV-1103 / TASK-CV-1104 verification harness (run via esbuild bundle).
import { extractClusterGraph } from '../src/ingestion/client_extractor.ts';
import type { K8sApiRawBundle } from '../src/ingestion/client_extractor.ts';
import {
  TrafficSimulator,
  patternRps,
  stagingHoverPosition,
  SCHED_PROFILES,
} from '../src/scene/traffic_simulator.ts';
import type { WorkloadScalingState } from '../src/scene/traffic_simulator.ts';

let failures = 0;
function check(name: string, cond: boolean, detail = ''): void {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!cond) failures++;
}

// ---------------------------------------------------------------------------
// 1) Client extractor: synthetic raw K8s bundle
// ---------------------------------------------------------------------------
const bundle: K8sApiRawBundle = {
  version: { gitVersion: 'v1.36.4' },
  nodes: [
    {
      metadata: { name: 'cp-1', labels: { 'node-role.kubernetes.io/control-plane': '' } },
      spec: { taints: [{ key: 'node-role.kubernetes.io/control-plane', effect: 'NoSchedule' }] },
      status: {
        nodeInfo: { kubeletVersion: 'v1.36.4', osImage: 'Container-Optimized OS' },
        capacity: { cpu: '8', memory: '32768Mi' },
        allocatable: { cpu: '8', memory: '32768Mi' },
        addresses: [{ type: 'InternalIP', address: '10.0.0.5' }],
        conditions: [{ type: 'Ready', status: 'True' }],
      },
    },
    {
      metadata: { name: 'worker-1', labels: { 'cloud.google.com/gke-nodepool': 'pool-a', 'topology.kubernetes.io/zone': 'us-central1-a' } },
      status: {
        nodeInfo: { kubeletVersion: 'v1.36.4' },
        capacity: { cpu: '4', memory: '16384Mi' },
        conditions: [{ type: 'Ready', status: 'True' }],
      },
    },
    {
      metadata: { name: 'worker-2', labels: { 'karpenter.sh/nodepool': 'general' } },
      status: {
        nodeInfo: { kubeletVersion: 'v1.36.4' },
        capacity: { cpu: '16', memory: '65536Mi' },
        conditions: [{ type: 'Ready', status: 'False' }],
      },
    },
  ],
  pods: [
    { metadata: { name: 'kube-apiserver-cp-1', namespace: 'kube-system' }, spec: { nodeName: 'cp-1', containers: [{ name: 'kube-apiserver', image: 'k8s.gcr.io/kube-apiserver:v1.36.4', resources: { requests: { cpu: '250m', memory: '512Mi' } } }] }, status: { phase: 'Running', containerStatuses: [{ ready: true, restartCount: 0 }] } },
    { metadata: { name: 'etcd-cp-1', namespace: 'kube-system' }, spec: { nodeName: 'cp-1', containers: [{ name: 'etcd' }] }, status: { phase: 'Running' } },
    { metadata: { name: 'kube-scheduler-cp-1', namespace: 'kube-system' }, spec: { nodeName: 'cp-1', containers: [{ name: 'scheduler' }] }, status: { phase: 'Running' } },
    { metadata: { name: 'kube-controller-manager-cp-1', namespace: 'kube-system' }, spec: { nodeName: 'cp-1', containers: [{ name: 'cm' }] }, status: { phase: 'Running' } },
    { metadata: { name: 'coredns-589f-abcde', namespace: 'kube-system', labels: { k8s_app: 'kube-dns' } }, spec: { nodeName: 'worker-1', containers: [{ name: 'coredns', resources: { requests: { cpu: '100m', memory: '70Mi' } } }] }, status: { phase: 'Running' } },
    { metadata: { name: 'kube-proxy-xyz12', namespace: 'kube-system' }, spec: { nodeName: 'worker-1', containers: [{ name: 'kube-proxy' }] }, status: { phase: 'Running' } },
    { metadata: { name: 'frontend-7d9d-f2k2l', namespace: 'boutique', labels: { app: 'frontend' } }, spec: { nodeName: 'worker-1', containers: [{ name: 'frontend', resources: { requests: { cpu: '500m', memory: '256Mi' } } }] }, status: { phase: 'Running' } },
    { metadata: { name: 'cartservice-6b8c-9m4nn', namespace: 'boutique', labels: { app: 'cartservice' } }, spec: { nodeName: 'worker-2', containers: [{ name: 'cart', resources: { requests: { cpu: '200m', memory: '64Mi' } } }] }, status: { phase: 'Running' } },
    // Pending pod → must stage at X < -12
    { metadata: { name: 'checkout-5f7c-qw3rt', namespace: 'boutique' }, spec: { containers: [{ name: 'checkout' }] }, status: { phase: 'Pending', conditions: [{ type: 'PodScheduled', status: 'False' }] } },
    { metadata: { name: 'ray-cluster-head-xc12', namespace: 'ai' }, spec: { nodeName: 'worker-1', containers: [{ name: 'ray-head', resources: { requests: { cpu: '2', memory: '4Gi' } } }] }, status: { phase: 'Running' } },
  ],
  services: [
    { metadata: { name: 'frontend', namespace: 'boutique' }, spec: { type: 'LoadBalancer', selector: { app: 'frontend' }, ports: [{ port: 80 }] } },
    { metadata: { name: 'redis-cart', namespace: 'boutique' }, spec: { type: 'ClusterIP', selector: { app: 'cartservice' }, ports: [{ port: 6379 }] } },
  ],
  hpas: [
    {
      metadata: { name: 'frontend' },
      spec: { scaleTargetRef: { kind: 'Deployment', name: 'frontend' }, minReplicas: 2, maxReplicas: 10, metrics: [{ type: 'Resource', resource: { name: 'cpu', target: { type: 'Utilization', averageUtilization: 65 } } }] },
      status: { currentReplicas: 2, desiredReplicas: 3 },
    },
  ],
  vpas: [
    {
      metadata: { name: 'cartservice-vpa' },
      spec: { targetRef: { kind: 'Deployment', name: 'cartservice' }, updatePolicy: { updateMode: 'Auto' } },
      status: { recommendation: { containerRecommendations: [{ containerName: 'cart', target: { cpu: '400m', memory: '800Mi' } }] } },
    },
  ],
};

const graph = extractClusterGraph(bundle);
console.log('--- extractor ---');
check('metadata version', graph.metadata.kubernetes_version === 'v1.36.4');
check('node_count = 3', graph.metadata.node_count === 3);
check('pod_count = 10', graph.metadata.pod_count === 10);
check('distribution gke (mixed labels)', graph.metadata.distribution === 'gke', graph.metadata.distribution);

const byName = new Map(graph.nodes.map((n) => [n.name, n]));
const apiserver = byName.get('kube-apiserver-cp-1');
check('apiserver Y=7.0', apiserver?.spatial.y === 7.0);
const etcd = byName.get('etcd-cp-1');
check('etcd Y=5.5 Z=-3.5', etcd?.spatial.y === 5.5 && etcd?.spatial.z === -3.5);
const sched = byName.get('kube-scheduler-cp-1');
check('scheduler Y=4.5 Z=0.8', sched?.spatial.y === 4.5 && sched?.spatial.z === 0.8);

const w1 = byName.get('worker-1');
const w2 = byName.get('worker-2');
const w0 = byName.get('cp-1');
check('3 chassis centered: -6, 0, +6', w0?.spatial.x === -6 && w1?.spatial.x === 0 && w2?.spatial.x === 6, `${w0?.spatial.x},${w1?.spatial.x},${w2?.spatial.x}`);
const kubeletW1 = graph.nodes.find((n) => n.id === 'node/worker-1/kubelet');
check('synth kubelet at chassis-1.8', kubeletW1?.spatial.x === -1.8 && kubeletW1?.spatial.y === 0.7);
const frontend = byName.get('frontend-7d9d-f2k2l');
check('frontend on worker-1 chassis, Y=0.75', frontend?.spatial.y === 0.75 && Math.abs(frontend!.spatial.x - -0.6) < 1e-9 && frontend?.spatial.z === 0.2, `${frontend?.spatial.x}`);
check('frontend capsule dims (3-dp mirror of layout.py)', frontend?.pod_geometry?.height === 0.647 && frontend?.pod_geometry?.radius === 0.2, JSON.stringify(frontend?.pod_geometry));

const pending = byName.get('checkout-5f7c-qw3rt');
check('pending pod staged X < -12', (pending?.spatial.x ?? 0) < -12 && pending?.spatial.y === 1.0, `x=${pending?.spatial.x}`);
check('pending geometry flag', pending?.pod_geometry?.is_pending === true);

const ds = byName.get('kube-proxy-xyz12');
check('daemonset bay asset + Y=0.65', ds?.spatial.asset_type === 'Cuboid_DaemonSet' && ds?.spatial.y === 0.65);

const ray = byName.get('ray-cluster-head-xc12');
check('ray head → framework floor Y=2.5 asset Cuboid_Ray', ray?.spatial.y === 2.5 && ray?.spatial.asset_type === 'Cuboid_Ray');

check('HPA metadata attached to frontend pod', frontend?.autoscaling?.has_hpa === true && frontend?.autoscaling?.target_metric === 'cpu:65' && frontend?.autoscaling?.current_replicas === 2 && frontend?.autoscaling?.desired_replicas === 3);
const cart = byName.get('cartservice-6b8c-9m4nn');
check('VPA recommendation attached (400m/800Mi → resize in place)', cart?.autoscaling?.has_vpa === true && cart?.autoscaling?.vpa_target_cpu === '0.4' && cart?.autoscaling?.is_resizing_in_place === true, JSON.stringify(cart?.autoscaling));

const svcFrontend = graph.nodes.find((n) => n.id === 'svc/boutique/frontend');
check('service node at aggregation tier', svcFrontend?.spatial.y === 9.5 && svcFrontend?.spatial.asset_type === 'LayerTray_Control');
const svcEdges = graph.edges.filter((e) => e.source === 'svc/boutique/frontend');
check('selector edge frontend→frontend pod', svcEdges.some((e) => e.target === frontend?.id), JSON.stringify(svcEdges.map((e) => e.target)));

const hb = graph.edges.filter((e) => e.volume_label === 'lease heartbeat');
check('3 kubelet heartbeat edges', hb.length === 3);
const raft = graph.edges.filter((e) => e.volume_label === 'raft KV');
check('apiserver↔etcd raft edges', raft.length === 1);
const clientEdge = graph.edges.find((e) => e.volume_label === 'client-direct extraction');
check('client horizon edge present', clientEdge !== undefined && clientEdge.target === apiserver?.id);
check('machine shapes for 3 nodes', (graph.machine_shapes?.length ?? 0) === 3 && graph.machine_shapes?.[1]?.vcpus === 4 && graph.machine_shapes?.[1]?.compute_class === 'pool-a');

// determinism: same bundle → identical coordinates
const graph2 = extractClusterGraph(bundle);
check('deterministic layout', JSON.stringify(graph.nodes) === JSON.stringify(graph2.nodes));

// ---------------------------------------------------------------------------
// 2) Traffic simulator physics
// ---------------------------------------------------------------------------
console.log('--- patterns ---');
const rngConst = () => 0.5;
const st = { chaosValue: 100, chaosNextFlipAt: 0, chaosUp: true };
check('step: base before 2s', patternRps('step', 1, 0.016, 100, 850, 120, rngConst, st) === 100);
check('step: peak at/after 2s', patternRps('step', 2.5, 0.016, 100, 850, 120, rngConst, st) === 850);
const sine0 = patternRps('sine', 0, 0.016, 100, 850, 120, rngConst, st);
check('sine starts at base', Math.abs(sine0 - 100) < 1e-6, `${sine0}`);
const sineHalf = patternRps('sine', 30, 0.016, 100, 850, 120, rngConst, st); // period = 60 s
check('sine hits peak at period/2', Math.abs(sineHalf - 850) < 1e-6, `${sineHalf}`);
check('ramp mid = midpoint', Math.abs(patternRps('ramp', 48, 0.016, 100, 850, 120, rngConst, st) - 475) < 1e-6);
check('ramp caps at peak', patternRps('ramp', 500, 0.016, 100, 850, 120, rngConst, st) === 850);
const chaosA = { chaosValue: 100, chaosNextFlipAt: 0, chaosUp: true };
const chaosB = { chaosValue: 100, chaosNextFlipAt: 0, chaosUp: true };
const vA = patternRps('chaos', 0.5, 0.5, 100, 850, 120, () => 0.42, chaosA);
const vB = patternRps('chaos', 0.5, 0.5, 100, 850, 120, () => 0.42, chaosB);
check('chaos deterministic for fixed seed', vA === vB && Number.isFinite(vA));

console.log('--- staging geometry ---');
const p0 = stagingHoverPosition(0);
const p5 = stagingHoverPosition(5);
check('hover grid X < -12 always', p0.x === -22 && p5.x === -20 && p0.y === 1.0 && p5.z === -4, `${p0.x} ${p5.x} ${p5.z}`);

console.log('--- simulator: GKE vs Karpenter spike ---');
function runScenario(computeClass: 'gke-compute-class' | 'karpenter'): {
  maxLatency: number;
  maxError: number;
  finalState: WorkloadScalingState | null;
  scheduled: number;
  staged: number;
  hpaEvents: number;
  tAt500: number | null;
} {
  let scheduled = 0;
  let staged = 0;
  let hpaEvents = 0;
  const sim = new TrafficSimulator({ hpaIntervalSeconds: 1, seed: 42, callbacks: {
    onPodScheduled: () => scheduled++,
    onPendingStaged: () => staged++,
    onHpaScaleOut: () => hpaEvents++,
  } });
  sim.addWorkload(
    { id: 'frontend', clusterId: `cluster-${computeClass}`, workloadName: 'frontend', computeClassType: computeClass, initialReplicas: 2, minReplicas: 2, maxReplicas: 12, targetCpuUtilization: 60, serviceRatePerPod: 120 },
    { pattern: 'step', baseRps: 100, peakRps: 1200, durationSeconds: 180 },
  );
  sim.start();
  let maxLatency = 0;
  let maxError = 0;
  let tAt500: number | null = null;
  const dt = 1 / 30;
  for (let t = 0; t < 180; t += dt) {
    sim.update(dt);
    const s = sim.getState('frontend');
    if (!s) break;
    maxLatency = Math.max(maxLatency, s.latencyMs);
    maxError = Math.max(maxError, s.errorRate);
    if (tAt500 === null && s.latencyMs >= 500) tAt500 = Math.round(t * 10) / 10;
  }
  return { maxLatency, maxError, finalState: sim.getState('frontend'), scheduled, staged, hpaEvents, tAt500 };
}

const gke = runScenario('gke-compute-class');
const kar = runScenario('karpenter');
console.log(`GKE      : maxLat=${gke.maxLatency}ms final=${JSON.stringify(gke.finalState)} sched=${gke.scheduled} staged=${gke.staged} hpaEv=${gke.hpaEvents}`);
console.log(`Karpenter: maxLat=${kar.maxLatency}ms final=${JSON.stringify(kar.finalState)} sched=${kar.scheduled} staged=${kar.staged} hpaEv=${kar.hpaEvents} tAt500=${kar.tAt500}`);

check('GKE spike absorbed: peak latency ≤ 60ms', gke.maxLatency <= 60, `${gke.maxLatency}ms`);
check('GKE error rate ~0% (whole run)', gke.maxError < 0.01, `${gke.maxError}`);
check('GKE pods scheduled within seconds (fast path, no staging)', gke.staged === 0 && gke.scheduled >= 8, `${gke.scheduled}/${gke.staged}`);
check('GKE recovers to baseline latency', (gke.finalState?.latencyMs ?? 9999) < 30, `${gke.finalState?.latencyMs}ms`);
check('GKE scaled out to ≥8 replicas', (gke.finalState?.currentReplicas ?? 0) >= 8, `${gke.finalState?.currentReplicas}`);

check('Karpenter latency spikes > 500ms', kar.maxLatency > 500, `${kar.maxLatency}ms`);
check('Karpenter spike onset within ~30s', kar.tAt500 !== null && kar.tAt500 <= 30, `${kar.tAt500}`);
check('Karpenter peak error rate ≈ 18.4% §5.3 band', kar.maxError > 0.15 && kar.maxError <= 0.21, `${kar.maxError}`);
check('Karpenter recovers after cold-VM pods land', (kar.finalState?.errorRate ?? 1) < 0.02 && (kar.finalState?.latencyMs ?? 9999) < 100, `err=${kar.finalState?.errorRate} lat=${kar.finalState?.latencyMs}`);
check('Karpenter pods staged in exterior yard', kar.staged >= 4, `${kar.staged}`);
check('Karpenter pods arrive after cold-VM τ (~95-150s)', kar.scheduled >= 4 && (kar.finalState?.currentReplicas ?? 0) >= 6, `sched=${kar.scheduled} replicas=${kar.finalState?.currentReplicas}`);
check('karpenter τ profile in 60-150 band', SCHED_PROFILES.karpenter.nodeProvisionS >= 60 && SCHED_PROFILES.karpenter.nodeProvisionS <= 150);

console.log('--- lifecycle: pause/reset/burst ---');
const sim2 = new TrafficSimulator({ hpaIntervalSeconds: 1, seed: 7 });
sim2.addWorkload(
  { id: 'wl', clusterId: 'c1', workloadName: 'wl', computeClassType: 'static-nodepool', initialReplicas: 2, serviceRatePerPod: 120 },
  { pattern: 'ramp', baseRps: 50, peakRps: 2000, durationSeconds: 60 },
);
sim2.start();
for (let i = 0; i < 300; i++) sim2.update(1 / 30);
const beforePause = sim2.getState('wl')!;
sim2.pause();
const simTimeAtPause = sim2.getSimTime();
for (let i = 0; i < 300; i++) sim2.update(1 / 30);
check('pause freezes physics', Math.abs(sim2.getSimTime() - simTimeAtPause) < 1e-9);
check('paused state stable', sim2.getState('wl')!.latencyMs === beforePause.latencyMs);
sim2.reset();
check('reset restores initial replicas', sim2.getState('wl')!.currentReplicas === 2 && sim2.getState('wl')!.errorRate === 0);
check('reset zeroes sim time', sim2.getSimTime() === 0);

const beforeBurst = sim2.getCurrentRps('wl');
sim2.burst(2000, 5);
sim2.update(0.05);
check('burst overrides λ up to 2000', sim2.getCurrentRps('wl') >= 2000, `${beforeBurst} → ${sim2.getCurrentRps('wl')}`);
for (let i = 0; i < 200; i++) sim2.update(0.05);
check('burst decays after window', sim2.getCurrentRps('wl') < 2000);
sim2.stop();
const tAfterStop = sim2.getSimTime();
sim2.update(1);
check('stop halts the clock', sim2.getSimTime() === tAfterStop);

console.log('--- VPA morph trigger ---');
let reco = 0;
let morph = 0;
const sim3 = new TrafficSimulator({
  hpaIntervalSeconds: 1,
  seed: 3,
  callbacks: {
    onVpaRecommendation: () => reco++,
    onVpaResize: () => morph++,
  },
});
sim3.addWorkload(
  { id: 'cart', clusterId: 'c1', workloadName: 'cartservice', computeClassType: 'gke-compute-class', initialReplicas: 1, maxReplicas: 2, targetCpuUtilization: 60, serviceRatePerPod: 100, hasVpa: true, podCpuCores: 0.4, podMemoryGib: 1 },
  { pattern: 'step', baseRps: 50, peakRps: 500, durationSeconds: 30, enableHpa: false, enableVpa: true },
);
sim3.start();
for (let i = 0; i < 30 * 30; i++) sim3.update(1 / 30);
check('VPA recommendation fired under sustained >80% CPU', reco >= 1, `reco=${reco}`);
check('VPA resize committed after τ_vpa', morph >= 1, `morph=${morph}`);
const muScaled = sim3.getState('cart');
check('VPA grew effective μ (latency back down)', (muScaled?.latencyMs ?? 9999) < 100, `${muScaled?.latencyMs}`);

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
if (failures > 0) throw new Error(`${failures} SPEC-10 engine check(s) failed`);
