import * as THREE from 'three';

/**
 * SPEC-13 §3.6 / ADR-1304 (TASK-CV-1405): 2D CAD SVG overlay.
 *
 * `CadOverlayManager` renders crisp, non-occluded architectural tags on top of the
 * WebGL canvas while CAD mode is active. Each cluster node is projected from world
 * space through the active camera into screen pixels and drawn as an SVG text label
 * (namespace / workload name) plus a planar coordinate marker.
 *
 * The overlay is a dedicated absolutely-positioned `<svg>` element layered above the
 * renderer canvas. It fades out when the user returns to 3D perspective mode so it
 * never occludes the elevation view.
 */

/** A single node descriptor handed to the overlay each frame. */
export interface CadOverlayNode {
  id: string;
  name: string;
  namespace: string;
  position: THREE.Vector3;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * Create an `SVGTextElement`-safe text node (avoids XSS via textContent).
 */
function svgText(parent: SVGElement, content: string): SVGTextElement {
  const el = document.createElementNS(SVG_NS, 'text');
  el.textContent = content;
  parent.appendChild(el);
  return el;
}

export class CadOverlayManager {
  private root: HTMLDivElement | null = null;
  private svg: SVGSVGElement | null = null;

  /** Cached per-node SVG groups keyed by node id (reused across frames). */
  private readonly nodeGroups = new Map<string, SVGGElement>();

  private initialized = false;

  /**
   * Create and mount the overlay DOM inside `container`. The overlay is appended as a
   * sibling above the renderer canvas and hidden until CAD mode activates.
   */
  initialize(container: HTMLElement): void {
    this.root = document.createElement('div');
    this.root.className = 'cad-overlay-root';
    Object.assign(this.root.style, {
      position: 'absolute',
      inset: '0',
      overflow: 'hidden',
      pointerEvents: 'none',
      zIndex: '10',
      opacity: '0',
      transition: 'opacity 300ms ease',
    });

    this.svg = document.createElementNS(SVG_NS, 'svg');
    Object.assign(this.svg.style, {
      width: '100%',
      height: '100%',
      display: 'block',
    });
    this.svg.setAttribute('viewBox', `0 0 ${container.clientWidth} ${container.clientHeight}`);
    this.root.appendChild(this.svg);
    container.appendChild(this.root);

    this.initialized = true;
  }

  /**
   * Project each node's world position through the active camera into screen pixels and
   * refresh its CAD tag. Called every frame from the render loop.
   */
  update(
    camera: THREE.Camera,
    nodes: CadOverlayNode[],
    isCadActive: boolean,
  ): void {
    if (!this.initialized || !this.svg) return;

    const width = this.svg.clientWidth || 1;
    const height = this.svg.clientHeight || 1;
    this.svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    // Track which node ids are still live so stale tags can be removed.
    const liveIds = new Set<string>();

    for (const node of nodes) {
      liveIds.add(node.id);
      let group = this.nodeGroups.get(node.id);
      if (!group) {
        group = document.createElementNS(SVG_NS, 'g');
        group.setAttribute('data-node-id', node.id);

        // Crisp coordinate marker: small cross at the anchor point.
        const marker = document.createElementNS(SVG_NS, 'path');
        marker.setAttribute('d', 'M -4 0 L 4 0 M 0 -4 L 0 4');
        marker.setAttribute('stroke', '#22d3ee');
        marker.setAttribute('stroke-width', '1.2');
        marker.setAttribute('shape-rendering', 'crispEdges');
        marker.setAttribute('fill', 'none');
        group.appendChild(marker);

        // Namespace tag (dim, small).
        const nsText = svgText(group, node.namespace);
        nsText.setAttribute('font-family', "'Courier New', monospace");
        nsText.setAttribute('font-size', '9');
        nsText.setAttribute('fill', '#94a3b8');

        // Workload name tag (bright, larger).
        const nameText = svgText(group, node.name);
        nameText.setAttribute('font-family', "'Courier New', monospace");
        nameText.setAttribute('font-size', '11');
        nameText.setAttribute('fill', '#e2e8f0');
        nameText.setAttribute('font-weight', '600');

        // Planar coordinate marker (X, Z).
        const coordText = svgText(group, '');
        coordText.setAttribute('font-family', "'Courier New', monospace");
        coordText.setAttribute('font-size', '9');
        coordText.setAttribute('fill', '#f59e0b');

        this.svg.appendChild(group);
        this.nodeGroups.set(node.id, group);
      }

      // Project the world position to normalized device coordinates.
      const projected = node.position.clone().project(camera);

      // Skip nodes behind the camera (NDC z > 1 means beyond far plane).
      if (projected.z > 1) {
        group.setAttribute('display', 'none');
        continue;
      }
      group.removeAttribute('display');

      const x = (projected.x * 0.5 + 0.5) * width;
      const y = (-projected.y * 0.5 + 0.5) * height;

      // Anchor the marker at the projected point.
      const marker = group.firstElementChild as SVGPathElement | null;
      if (marker) {
        marker.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
      }

      // Namespace above, workload name below, coordinates beneath both.
      const children = Array.from(group.children).filter(
        (el): el is SVGTextElement => el.tagName === 'text',
      );
      if (children[0]) {
        children[0].setAttribute('x', x.toFixed(1));
        children[0].setAttribute('y', (y - 6).toFixed(1));
        children[0].setAttribute('text-anchor', 'middle');
        children[0].textContent = node.namespace;
      }
      if (children[1]) {
        children[1].setAttribute('x', x.toFixed(1));
        children[1].setAttribute('y', (y + 16).toFixed(1));
        children[1].setAttribute('text-anchor', 'middle');
        children[1].textContent = node.name;
      }
      if (children[2]) {
        children[2].setAttribute('x', x.toFixed(1));
        children[2].setAttribute('y', (y + 28).toFixed(1));
        children[2].setAttribute('text-anchor', 'middle');
        children[2].textContent = `(${node.position.x.toFixed(1)}, ${node.position.z.toFixed(1)})`;
      }
    }

    // Remove stale node groups that are no longer in the scene.
    for (const [id, group] of this.nodeGroups.entries()) {
      if (!liveIds.has(id)) {
        group.remove();
        this.nodeGroups.delete(id);
      }
    }

    // Fade the overlay in/out with CAD mode; keep it interactive-free either way.
    this.setVisible(isCadActive);
  }

  /** Show or hide the entire overlay (fade via CSS transition). */
  setVisible(visible: boolean): void {
    if (this.root) {
      this.root.style.opacity = visible ? '1' : '0';
    }
  }

  /** Remove the overlay DOM from its container and clear cached nodes. */
  dispose(): void {
    for (const group of this.nodeGroups.values()) {
      group.remove();
    }
    this.nodeGroups.clear();

    if (this.root && this.root.parentNode) {
      this.root.parentNode.removeChild(this.root);
    }
    this.root = null;
    this.svg = null;
    this.initialized = false;
  }
}
