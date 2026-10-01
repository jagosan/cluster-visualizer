// SPEC-00 Phase 1 bootstrap. Dual-viewport ClusterViewport lands in Phase 4
// (src/scene/cluster_viewport.ts per docs/MAP.md).
import * as THREE from 'three';

const container = document.getElementById('app');
if (!container) throw new Error('#app container missing from index.html');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0e12);

const camera = new THREE.PerspectiveCamera(
  55,
  container.clientWidth / container.clientHeight,
  0.1,
  1000,
);
camera.position.set(6, 5, 8);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

scene.add(new THREE.AmbientLight(0x8899aa, 0.6));
const key = new THREE.DirectionalLight(0xffffff, 1.2);
key.position.set(5, 10, 5);
scene.add(key);

// Placeholder beacon until cluster-kit.glb (public/assets) is authored in Phase 2.
const beacon = new THREE.Mesh(
  new THREE.BoxGeometry(1, 2.5, 1),
  new THREE.MeshStandardMaterial({ color: 0x326ce5, metalness: 0.3, roughness: 0.4 }),
);
scene.add(beacon);

window.addEventListener('resize', () => {
  camera.aspect = container.clientWidth / container.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.clientWidth, container.clientHeight);
});

renderer.setAnimationLoop(() => {
  beacon.rotation.y += 0.005;
  renderer.render(scene, camera);
});
