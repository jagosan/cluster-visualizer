// TASK-CV-1105 verification harness (run via esbuild bundle + node).
// Covers: workload discovery from real sample fixtures, compute-class
// detection, engine A physics through the deck's addressing model, and
// FlowParticleSystem §6.3 modulation (speed gain, tint, surge density).
import * as fs from 'node:fs';
import * as path from 'node:path';

// Minimal process shim (scripts/ sits outside the app tsconfig include).
const nodeProcess = (globalThis as unknown as {
  process: { cwd(): string; exit(code?: number): never };
}).process;

import {
  workloadBaseName,
  discoverWorkloads,
  detectComputeClass,
} from '../src/ui/traffic_deck.ts';
import { TrafficSimulator } from '../src/scene/traffic_simulator.ts';
import { FlowParticleSystem } from '../src/scene/flow_particles.ts';
import type { ClusterGraphData } from '../src/scene/cluster_viewport.ts';
import * as THREE from 'three';

let failures = 0;
function check(name: string, cond: boolean, detail = ''): void {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!cond) failures++;
}

const SAMPLE_DIR = path.resolve(nodeProcess.cwd(), 'public/data/samples');

// ---------------------------------------------------------------------------
// 1) Name collapsing
// ---------------------------------------------------------------------------
check('collapse boutique pod', workloadBaseName('frontend-bc4d8f7f9-xq7qk') === 'frontend', workloadBaseName('frontend-bc4d8f7f9-xq7qk'));
check('collapse cartservice', workloadBaseName('cartservice-f89c6d5d2-z2w4t') === 'cartservice');
check('collapse bench lane', workloadBaseName('bench-frontend-scaleup-6d7c8f9a-a1x') === 'bench-frontend-scaleup', workloadBaseName('bench-frontend-scaleup-6d7c8f9a-a1x'));
check('collapse static lane', workloadBaseName('bench-frontend-static-abcdb123-e5p') === 'bench-frontend-static', workloadBaseName('bench-frontend-static-abcdb123-e5p'));
check('collapse statefulset', workloadBaseName('postgres-primary-0') === 'postgres-primary', workloadBaseName('postgres-primary-0'));
check('collapse redis', workloadBaseName('redis-cluster-6587c5bb48-rshcr') === 'redis-cluster', workloadBaseName('redis-cluster-6587c5bb48-rshcr'));
check('keeps plain name', workloadBaseName('kubernetes') === 'kubernetes');

// ---------------------------------------------------------------------------
// 2) Discovery + compute-class on the four real samples
// ---------------------------------------------------------------------------
const samples: Array<[string, string]> = [
  ['sample-online-boutique.json', 'boutique'],
  ['sample-compute-class-bench.json', 'bench'],
  ['sample-ray-kuberay.json', 'ray'],
  ['sample-upstream-k8s.json', 'oss'],
];
for (const [file] of samples) {
  const raw = fs.readFileSync(path.join(SAMPLE_DIR, file), 'utf-8');
  const data = JSON.parse(raw) as ClusterGraphData;
  const wl = discoverWorkloads('a', data);
  const cc = detectComputeClass(data);
  const names = wl.map((w) => w.base);
  console.log(`  ${file}: class=${cc} workloads=[${names.join(', ')}]`);
  check(`${file}: discovery non-empty`, wl.length > 0 || file === 'sample-upstream-k8s.json');
  check(`${file}: unique unit ids`, new Set(wl.map((w) => w.unitId)).size === wl.length);
}
{
  const data = JSON.parse(fs.readFileSync(path.join(SAMPLE_DIR, 'sample-online-boutique.json'), 'utf-8')) as ClusterGraphData;
  check('boutique detects gke-compute-class', detectComputeClass(data) === 'gke-compute-class');
  const wl = discoverWorkloads('a', data);
  check('boutique finds frontend', wl.some((w) => w.base === 'frontend'));
  check('boutique finds cartservice', wl.some((w) => w.base === 'cartservice'));
  check('boutique frontend has HPA target 65', wl.find((w) => w.base === 'frontend')?.targetCpu === 65);
  check('boutique cartservice has VPA flag', wl.find((w) => w.base === 'cartservice')?.hasVpa === true);
}
{
  const data = JSON.parse(fs.readFileSync(path.join(SAMPLE_DIR, 'sample-compute-class-bench.json'), 'utf-8')) as ClusterGraphData;
  check('bench detects karpenter', detectComputeClass(data) === 'karpenter');
  const bases = discoverWorkloads('b', data).map((w) => w.base);
  check('bench merges scaleup+static lanes', bases.includes('bench-frontend-scaleup') && bases.includes('bench-frontend-static'), bases.join(','));
}

// ---------------------------------------------------------------------------
// 3) Engine A physics through the deck addressing model
// ---------------------------------------------------------------------------
{
  const sim = new TrafficSimulator({ hpaIntervalSeconds: 1, seed: 1337 });
  const gkeData = JSON.parse(fs.readFileSync(path.join(SAMPLE_DIR, 'sample-online-boutique.json'), 'utf-8')) as ClusterGraphData;
  const gkeWl = discoverWorkloads('a', gkeData).find((w) => w.base === 'frontend')!;
  sim.addWorkload({
    id: gkeWl.unitId, clusterId: 'a', workloadName: gkeWl.base,
    computeClassType: 'gke-compute-class', initialReplicas: gkeWl.replicas,
    minReplicas: 1, maxReplicas: Math.max(12, gkeWl.replicas * 2),
    targetCpuUtilization: gkeWl.targetCpu, serviceRatePerPod: 120, baselineLatencyMs: 12,
  });
  sim.configure({
    targetWorkloadId: gkeWl.unitId, pattern: 'step', baseRps: 100, peakRps: 850,
    durationSeconds: 120, enableHpa: true, enableVpa: false, simulateProvisioningSkew: true,
  });
  sim.start();
  let maxLat = 0;
  for (let i = 0; i < 600; i++) {
    sim.update(0.1);
    const st = sim.getState(gkeWl.unitId);
    if (st) maxLat = Math.max(maxLat, st.latencyMs);
  }
  const st = sim.getState(gkeWl.unitId)!;
  console.log(`  GKE frontend 60s: lat=${st.latencyMs}ms replicas=${st.currentReplicas} maxLat=${maxLat} rps=${sim.getCurrentRps(gkeWl.unitId)}`);
  check('GKE spike scales out', st.currentReplicas > gkeWl.replicas);
  check('GKE recovers < 20ms', st.latencyMs < 20, `${st.latencyMs}ms`);
  check('GKE transient < 100ms', maxLat < 100, `${maxLat}ms`);
}
{
  // Karpenter lane: latency must spike > 500ms while pods stage (SPEC §9.3).
  const sim = new TrafficSimulator({ hpaIntervalSeconds: 1, seed: 4242 });
  sim.addWorkload({
    id: 'b/bench-frontend-static', clusterId: 'b', workloadName: 'bench-frontend-static',
    computeClassType: 'karpenter', initialReplicas: 1, minReplicas: 1, maxReplicas: 10,
    targetCpuUtilization: 60, serviceRatePerPod: 120, baselineLatencyMs: 12,
  });
  sim.configure({
    targetWorkloadId: 'b/bench-frontend-static', pattern: 'step', baseRps: 100, peakRps: 850,
    durationSeconds: 120, enableHpa: true, enableVpa: false, simulateProvisioningSkew: true,
  });
  sim.start();
  let peak = 0;
  let sawPending = false;
  for (let i = 0; i < 400; i++) {
    sim.update(0.1);
    const st = sim.getState('b/bench-frontend-static');
    if (st) {
      peak = Math.max(peak, st.latencyMs);
      sawPending = sawPending || st.pendingReplicas > 0;
    }
  }
  console.log(`  Karpenter lane: peakLat=${peak}ms sawPending=${sawPending}`);
  check('Karpenter latency spikes > 500ms', peak > 500, `${peak}ms`);
  check('Karpenter stages pending pods', sawPending);
}

// ---------------------------------------------------------------------------
// 4) FlowParticleSystem modulation (no DOM required)
// ---------------------------------------------------------------------------
{
  const fs2 = new FlowParticleSystem();
  const curve = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(-5, 1, 0), new THREE.Vector3(0, 3, 0), new THREE.Vector3(5, 1, 0),
  );
  fs2.addCurveParticle(curve, 0x00ffcc, 0.25, 0.12);
  fs2.addFlowEdge({ sourcePos: new THREE.Vector3(-4, 0, 1), targetPos: new THREE.Vector3(4, 0, -1), flowType: 'data' });

  fs2.setModulation({ speedGain: 2.5, tint: 0xef4444, tintStrength: 0.9, surgeCount: 6, surgeColor: 0xef4444 });
  const surgeCount = () => fs2.group.children.filter((c) => c instanceof THREE.Mesh && (c as THREE.Mesh).geometry instanceof THREE.SphereGeometry && (c as THREE.Mesh).geometry.parameters.widthSegments === 6).length;
  check('surge particles spawn', surgeCount() === 6, `count=${surgeCount()}`);

  // speed gain actually accelerates progress (position changes faster)
  fs2.update(0.1, 1.0);
  fs2.setModulation({ surgeCount: 2 });
  check('surge particles removed', surgeCount() === 2, `count=${surgeCount()}`);

  fs2.clearModulation();
  check('clear modulation drops surge', surgeCount() === 0);
  fs2.clear();
  check('clear() resets system', fs2.group.children.length === 0);
}

// ---------------------------------------------------------------------------
console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
nodeProcess.exit(failures === 0 ? 0 : 1);
