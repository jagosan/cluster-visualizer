/**
 * ClusterOnboardingModal — SPEC-10 §2 / TASK-CV-1101
 *
 * Persistent topbar `➕ ADD CLUSTER` modal supporting two operational models:
 *
 *   TAB 1 — LIVE CLUSTER
 *     [A] Helm Operator Mode: dynamically generated, copyable Helm CLI install
 *         commands (SPEC-07 chart) + TokenReview bearer-token connect against
 *         the in-cluster operator (SSE stream).
 *     [B] Client-Side Connect: direct read-only connection via Kubernetes API
 *         URL + token with zero in-cluster footprint (SPEC-10 §2.1.2).
 *
 *   TAB 2 — SIMULATED SAMPLE CATALOG
 *     One-click cards for the 4 SPEC-10 §3 presets, each loading instantly
 *     (< 100 ms) into a selected viewport slot (Slot A/B/C/D).
 *
 * Security (SPEC-07 §5.1 / SPEC-10 §2.1, §5 matrix): bearer tokens live ONLY
 * in sessionStorage under `clustervis_token_<id>` — never localStorage,
 * cookies, disk, URL query strings, or external servers. Connectivity is
 * probed against `/api/v1/healthz` with `/snapshot` fallback before any
 * connect callback fires; failures surface as inline inline errors without
 * crashing the visualizer (SPEC-10 §9.1).
 */

import type { ClusterGraphData } from '../scene/cluster_viewport.js';
import { fetchAndExtractClusterGraph } from '../ingestion/client_extractor.js';
import { SampleCatalogRegistry, defaultSampleCatalog } from './sample_catalog.js';

/** SPEC-10 §7.1 onboarding mode discriminator. */
export type OnboardingMode = 'helm' | 'client' | 'sample';

/** SPEC-10 §7.1 live cluster connection configuration. */
export interface LiveClusterConfig {
  name: string;
  apiUrl: string;
  authType: 'token' | 'kubeconfig-proxy' | 'none';
  token?: string;
  namespace?: string;
  enableLatencyProbe: boolean;
}

/** Viewport slots offered for one-click sample hydration. */
export type ViewportSlotId = 'a' | 'b' | 'c' | 'd';

export interface ClusterOnboardingCallbacks {
  /** Fired when a sample preset has been fetched and is ready to hydrate. */
  onClusterLoaded?: (slotId: ViewportSlotId, clusterData: ClusterGraphData) => void;
  /** Fired when a live target passed the connectivity probe. */
  onLiveConnect?: (url: string, token: string, config?: LiveClusterConfig) => void;
  /**
   * TASK-CV-1103: fired when Tab 1 Mode B (Client Direct Connect) finished
   * fetching + parsing the raw Kubernetes API responses into a normalized
   * ClusterGraphData graph entirely in browser memory.
   */
  onClientGraphExtracted?: (graph: ClusterGraphData, config: LiveClusterConfig) => void;
  /** Fired on any user-visible failure (inline error text). */
  onError?: (message: string) => void;
}

interface HealthProbeResult {
  ok: boolean;
  latencyMs: number;
  detail: string;
}

const TOKEN_STORAGE_PREFIX = 'clustervis_token_';
const PROBE_TIMEOUT_MS = 6000;

const HUD_PANEL_STYLE: Partial<CSSStyleDeclaration> = {
  position: 'fixed',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: 'min(760px, calc(100vw - 48px))',
  maxHeight: 'calc(100vh - 96px)',
  overflowY: 'auto',
  background: 'rgba(17, 24, 39, 0.95)',
  backdropFilter: 'blur(12px)',
  border: '1px solid #1f2937',
  borderRadius: '12px',
  boxShadow: '0 16px 40px rgba(0, 0, 0, 0.7)',
  color: '#f3f4f6',
  fontFamily: 'inherit',
  fontSize: '13px',
  zIndex: '9500',
  padding: '0',
};

export class ClusterOnboardingModal {
  private overlay: HTMLElement | null = null;
  private readonly callbacks: ClusterOnboardingCallbacks;
  private readonly catalog: SampleCatalogRegistry;
  private activeTab: 'live' | 'samples' = 'live';
  private activeSubmode: 'helm' | 'client' = 'helm';
  private selectedSlot: ViewportSlotId = 'a';
  private boundKeyHandler: ((e: KeyboardEvent) => void) | null = null;

  constructor(
    callbacks: ClusterOnboardingCallbacks = {},
    catalog: SampleCatalogRegistry = defaultSampleCatalog,
  ) {
    this.callbacks = callbacks;
    this.catalog = catalog;
  }

  // -------------------------------------------------------------------------
  // Pure helpers (exported surface for tests)
  // -------------------------------------------------------------------------

  /**
   * Deterministic Helm CLI command generator (SPEC-10 §2.1.1) tailored to
   * the entered cluster name / namespace. Option A: OCI registry install;
   * Option B: local repository checkout with NodePort service exposure.
   */
  static buildHelmCommands(clusterName: string, namespace = 'clustervis-system'): string {
    const safeName = clusterName.trim().toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '') || 'clustervis-target';
    const safeNs = namespace.trim() || 'clustervis-system';
    return [
      `# Option A: Direct Helm OCI install → ${safeName}`,
      'helm upgrade --install clustervis oci://ghcr.io/jagosan/charts/clustervis \\',
      `  --namespace ${safeNs} \\`,
      '  --create-namespace \\',
      '  --set auth.type=token \\',
      '  --set service.type=LoadBalancer',
      '',
      '# Option B: Local Repository Checkout',
      'helm upgrade --install clustervis ./charts/clustervis \\',
      `  --namespace ${safeNs} \\`,
      '  --create-namespace \\',
      '  --set auth.type=token \\',
      '  --set service.type=NodePort \\',
      '  --set service.nodePort=30080',
    ].join('\n');
  }

  /** sessionStorage token persistence per SPEC-07 §5.1 (`clustervis_token_<id>`). */
  static storeToken(endpointId: string, token: string): void {
    try {
      sessionStorage.setItem(TOKEN_STORAGE_PREFIX + endpointId, token);
    } catch {
      // sessionStorage unavailable (private browsing quota) — token stays in-memory only.
    }
  }

  static readToken(endpointId: string): string | undefined {
    try {
      return sessionStorage.getItem(TOKEN_STORAGE_PREFIX + endpointId) ?? undefined;
    } catch {
      return undefined;
    }
  }

  static clearToken(endpointId: string): void {
    try {
      sessionStorage.removeItem(TOKEN_STORAGE_PREFIX + endpointId);
    } catch {
      // ignore
    }
  }

  /**
   * Connectivity test probe (SPEC-10 §8 TASK-CV-1101): tries
   * `${api}/api/v1/healthz` first, then falls back to `${api}/snapshot`.
   * A 200 on either endpoint qualifies the target as a reachable ClusterVis
   * operator; any network error, timeout, or non-2xx yields ok:false.
   */
  static async probeConnectivity(
    apiUrl: string,
    token?: string,
    timeoutMs = PROBE_TIMEOUT_MS,
  ): Promise<HealthProbeResult> {
    const base = apiUrl.trim().replace(/\/+$/, '');
    if (!/^https?:\/\//i.test(base)) {
      return { ok: false, latencyMs: 0, detail: 'URL must start with http:// or https://' };
    }
    const candidates = ['/api/v1/healthz', '/snapshot'];
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let lastDetail = 'No endpoint responded';
    for (const path of candidates) {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), timeoutMs);
      const start = performance.now();
      try {
        const res = await fetch(base + path, {
          method: 'GET',
          headers,
          signal: controller.signal,
          credentials: 'omit',
        });
        const latencyMs = Math.round(performance.now() - start);
        if (res.ok) {
          return { ok: true, latencyMs, detail: `${path} → ${res.status} in ${latencyMs} ms` };
        }
        lastDetail =
          res.status === 401 || res.status === 403
            ? `${path} → ${res.status} (token rejected by TokenReview)`
            : `${path} → HTTP ${res.status}`;
      } catch (err) {
        const aborted = err instanceof DOMException && err.name === 'AbortError';
        lastDetail = aborted
          ? `${path} timed out after ${timeoutMs} ms`
          : `${path} unreachable (${err instanceof Error ? err.message : String(err)}) — check CORS/network`;
      } finally {
        window.clearTimeout(timer);
      }
    }
    return { ok: false, latencyMs: 0, detail: lastDetail };
  }

  /**
   * TASK-CV-1103: raw Kubernetes API connectivity probe for Tab 1 Mode B
   * (Client Direct Connect). Tries `${api}/version` (unauthenticated on
   * kube-apiserver, proxied by `kubectl proxy`) then falls back to
   * `${api}/api/v1/nodes?limit=1` which additionally proves the read-only
   * token carries `list nodes` RBAC. Distinct from `probeConnectivity`
   * which targets ClusterVis *operator* endpoints.
   */
  static async probeKubernetesApi(
    apiUrl: string,
    token?: string,
    timeoutMs = PROBE_TIMEOUT_MS,
  ): Promise<HealthProbeResult> {
    const base = apiUrl.trim().replace(/\/+$/, '').replace(/\/api\/v1$/, '').replace(/\/api$/, '');
    if (!/^https?:\/\//i.test(base)) {
      return { ok: false, latencyMs: 0, detail: 'URL must start with http:// or https://' };
    }
    const candidates = ['/version', '/api/v1/nodes?limit=1'];
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let lastDetail = 'No endpoint responded';
    for (const path of candidates) {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), timeoutMs);
      const start = performance.now();
      try {
        const res = await fetch(base + path, {
          method: 'GET',
          headers,
          signal: controller.signal,
          credentials: 'omit',
        });
        const latencyMs = Math.round(performance.now() - start);
        if (res.ok) {
          return { ok: true, latencyMs, detail: `${path.split('?')[0]} → ${res.status} in ${latencyMs} ms` };
        }
        lastDetail =
          res.status === 401 || res.status === 403
            ? `${path.split('?')[0]} → ${res.status} (token rejected / missing RBAC)`
            : `${path.split('?')[0]} → HTTP ${res.status}`;
      } catch (err) {
        const aborted = err instanceof DOMException && err.name === 'AbortError';
        lastDetail = aborted
          ? `${path.split('?')[0]} timed out after ${timeoutMs} ms`
          : `${path.split('?')[0]} unreachable (${err instanceof Error ? err.message : String(err)}) — check CORS/network`;
      } finally {
        window.clearTimeout(timer);
      }
    }
    return { ok: false, latencyMs: 0, detail: lastDetail };
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  get isOpen(): boolean {
    return this.overlay !== null;
  }

  open(initialTab: 'live' | 'samples' = 'live'): void {
    this.close();
    this.activeTab = initialTab;

    const overlay = document.createElement('div');
    overlay.className = 'clustervis-onboarding-overlay';
    overlay.style.cssText =
      'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9400;display:flex;';
    overlay.addEventListener('click', (e: MouseEvent) => {
      if (e.target === overlay) this.close();
    });

    const panel = document.createElement('div');
    panel.className = 'clustervis-onboarding-modal';
    Object.assign(panel.style, HUD_PANEL_STYLE);
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'Add Cluster — live connect or simulated sample');

    panel.appendChild(this.renderHeader());
    panel.appendChild(this.renderTabBar());

    const body = document.createElement('div');
    body.className = 'cob-body';
    body.style.cssText = 'padding:18px 20px 20px;display:flex;flex-direction:column;gap:14px;';
    if (this.activeTab === 'live') {
      body.appendChild(this.renderLiveTab());
    } else {
      body.appendChild(this.renderSampleTab());
    }
    panel.appendChild(body);

    overlay.appendChild(panel);
    document.body.appendChild(overlay);
    this.overlay = overlay;

    this.boundKeyHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') this.close();
    };
    document.addEventListener('keydown', this.boundKeyHandler);

    const firstInput = panel.querySelector('input:not([disabled])') as HTMLInputElement | null;
    firstInput?.focus();
  }

  close(): void {
    if (this.overlay) {
      this.overlay.remove();
      this.overlay = null;
    }
    if (this.boundKeyHandler) {
      document.removeEventListener('keydown', this.boundKeyHandler);
      this.boundKeyHandler = null;
    }
  }

  // -------------------------------------------------------------------------
  // Header / tabs
  // -------------------------------------------------------------------------

  private renderHeader(): HTMLElement {
    const header = document.createElement('div');
    header.style.cssText =
      'display:flex;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid #1f2937;position:sticky;top:0;background:rgba(17,24,39,0.98);border-radius:12px 12px 0 0;z-index:2;';
    const title = document.createElement('div');
    title.innerHTML =
      '<span style="font-weight:700;letter-spacing:0.08em;font-size:13px;">➕ ADD CLUSTER</span>' +
      '<span style="color:#9ca3af;font-size:11px;margin-left:10px;">Live connect or instant simulated sample</span>';
    const closeBtn = this.btn('✕', 'Close (Esc)');
    closeBtn.style.cssText += ';background:transparent;border:none;font-size:16px;color:#9ca3af;';
    closeBtn.addEventListener('click', () => this.close());
    header.appendChild(title);
    header.appendChild(closeBtn);
    return header;
  }

  private renderTabBar(): HTMLElement {
    const bar = document.createElement('div');
    bar.className = 'cob-tabs';
    bar.style.cssText =
      'display:flex;gap:0;padding:0 20px;border-bottom:1px solid #1f2937;position:sticky;top:47px;background:rgba(17,24,39,0.97);z-index:1;';
    const mkTab = (id: 'live' | 'samples', label: string): HTMLButtonElement => {
      const b = document.createElement('button');
      b.textContent = label;
      const active = this.activeTab === id;
      b.style.cssText =
        'background:transparent;border:none;border-bottom:2px solid ' +
        (active ? '#38bdf8' : 'transparent') + ';color:' +
        (active ? '#38bdf8' : '#9ca3af') +
        ';padding:10px 14px;font-size:12px;font-weight:700;letter-spacing:0.05em;cursor:pointer;font-family:inherit;';
      return b;
    };
    // Rebuild-on-switch: simpler and always consistent with internal state.
    const liveTab = mkTab('live', '📡 LIVE CLUSTER');
    const sampleTab = mkTab('samples', '🧪 SIMULATED SAMPLE CATALOG');
    liveTab.onclick = () => this.open('live');
    sampleTab.onclick = () => this.open('samples');
    bar.appendChild(liveTab);
    bar.appendChild(sampleTab);
    return bar;
  }

  // -------------------------------------------------------------------------
  // TAB 1 — Live cluster (Helm operator + client-side connect)
  // -------------------------------------------------------------------------

  private renderLiveTab(): HTMLElement {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;flex-direction:column;gap:14px;';

    // Submode pills [A] Helm / [B] Client
    const pillRow = document.createElement('div');
    pillRow.style.cssText = 'display:flex;gap:8px;';
    const mk = (id: 'helm' | 'client', label: string): HTMLButtonElement => {
      const b = this.btn(label, '');
      const on = this.activeSubmode === id;
      if (on) b.classList.add('active');
      b.style.background = on ? 'rgba(56,189,248,0.2)' : '#1f2937';
      b.style.color = on ? '#38bdf8' : '#e5e7eb';
      b.style.borderColor = on ? '#38bdf8' : '#374151';
      b.onclick = () => {
        this.activeSubmode = id;
        this.open('live');
      };
      return b;
    };
    pillRow.appendChild(mk('helm', '[A] Helm Operator Mode'));
    pillRow.appendChild(mk('client', '[B] Client-Side Connect'));
    wrap.appendChild(pillRow);

    if (this.activeSubmode === 'helm') wrap.appendChild(this.renderHelmPane());
    else wrap.appendChild(this.renderClientPane());

    wrap.appendChild(this.renderSecurityFootnote());
    return wrap;
  }

  private renderHelmPane(): HTMLElement {
    const pane = document.createElement('div');
    pane.style.cssText = 'display:flex;flex-direction:column;gap:12px;';

    const note = document.createElement('p');
    note.style.cssText = 'margin:0;color:#9ca3af;font-size:12px;line-height:1.5;';
    note.textContent =
      'For cluster administrators: deploy the clustervis Helm chart (SPEC-07) into the target cluster, then paste its bearer token below. Auth is verified via the Kubernetes TokenReview API; the operator role is strictly read-only (get/list/watch; secrets & configmaps denied).';
    pane.appendChild(note);

    const nameInput = this.input('text', 'Cluster name (e.g. prod-gke-us-central1)');
    const urlInput = this.input('text', 'Operator URL (e.g. https://clustervis.tailnet.ts:30080)');
    const nsInput = this.input('text', 'Namespace (default: clustervis-system)');
    const tokenInput = this.tokenTextarea();

    const cmdBox = document.createElement('pre');
    cmdBox.className = 'cob-helm-cmd';
    cmdBox.style.cssText =
      'margin:0;background:#0f172a;border:1px solid #1f2937;border-radius:6px;padding:10px 12px;font-size:11px;font-family:ui-monospace,monospace;color:#94a3b8;overflow-x:auto;white-space:pre;';
    cmdBox.textContent = ClusterOnboardingModal.buildHelmCommands(nameInput.value);
    nameInput.addEventListener('input', () => {
      cmdBox.textContent = ClusterOnboardingModal.buildHelmCommands(
        nameInput.value, nsInput.value || 'clustervis-system',
      );
    });

    const cmdRow = document.createElement('div');
    cmdRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;';
    const cmdLabel = document.createElement('span');
    cmdLabel.style.cssText = 'font-size:11px;font-weight:700;color:#9ca3af;letter-spacing:0.05em;';
    cmdLabel.textContent = 'HELM CLI INSTALL';
    const copyBtn = this.btn('📋 Copy', 'Copy Helm install commands');
    copyBtn.addEventListener('click', async () => {
      const text = cmdBox.textContent ?? '';
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      }
      copyBtn.textContent = '✓ Copied';
      window.setTimeout(() => { copyBtn.textContent = '📋 Copy'; }, 1600);
    });
    cmdRow.appendChild(cmdLabel);
    cmdRow.appendChild(copyBtn);

    const probe = this.probeStatusLine();

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;';
    const testBtn = this.btn('🔌 Test Connection', 'Probe /api/v1/healthz or /snapshot');
    const connectBtn = this.btn('⚡ Connect Stream', 'Connect SSE topology stream');
    connectBtn.style.background = 'rgba(16,185,129,0.15)';
    connectBtn.style.borderColor = 'rgba(16,185,129,0.4)';
    connectBtn.style.color = '#10b981';
    actions.appendChild(testBtn);
    actions.appendChild(connectBtn);

    const runProbe = async (): Promise<HealthProbeResult> => {
      probe.set('testing', 'Probing /api/v1/healthz → /snapshot fallback …');
      const result = await ClusterOnboardingModal.probeConnectivity(
        urlInput.value, tokenInput.value.trim() || undefined,
      );
      probe.set(result.ok ? 'ok' : 'err', result.detail);
      return result;
    };

    testBtn.addEventListener('click', () => { void runProbe(); });
    connectBtn.addEventListener('click', () => {
      void (async () => {
        const config: LiveClusterConfig = {
          name: nameInput.value.trim() || 'live-cluster',
          apiUrl: urlInput.value.trim(),
          authType: tokenInput.value.trim() ? 'token' : 'none',
          namespace: nsInput.value.trim() || 'clustervis-system',
          enableLatencyProbe: true,
        };
        if (!config.apiUrl) {
          probe.set('err', 'Operator URL is required.');
          this.callbacks.onError?.('Operator URL is required.');
          return;
        }
        const result = await runProbe();
        if (!result.ok) return; // inline error shown; visualizer keeps running
        const token = tokenInput.value.trim();
        ClusterOnboardingModal.storeToken(this.endpointId(config), token || '');
        this.callbacks.onLiveConnect?.(config.apiUrl, token, config);
        this.close();
      })();
    });

    pane.appendChild(cmdRow);
    pane.appendChild(cmdBox);
    pane.appendChild(nameInput);
    const urlNsRow = document.createElement('div');
    urlNsRow.style.cssText = 'display:flex;gap:10px;';
    urlNsRow.appendChild(this.field('Target API URL', urlInput));
    urlNsRow.appendChild(this.field('Namespace', nsInput));
    pane.appendChild(urlNsRow);
    pane.appendChild(this.field('Bearer Token (TokenReview-verified, sessionStorage only)', tokenInput));
    pane.appendChild(probe.el);
    pane.appendChild(actions);
    return pane;
  }

  private renderClientPane(): HTMLElement {
    const pane = document.createElement('div');
    pane.style.cssText = 'display:flex;flex-direction:column;gap:12px;';

    const note = document.createElement('p');
    note.style.cssText = 'margin:0;color:#9ca3af;font-size:12px;line-height:1.5;';
    note.textContent =
      'Zero in-cluster footprint: point the browser at the Kubernetes API (or a local `kubectl proxy --port=8001`) with a read-only token. Resources are fetched directly (/api/v1/nodes, /api/v1/pods, /api/v1/services, /apis/autoscaling/v2/horizontalpodautoscalers) and parsed client-side by the TASK-CV-1103 browser extractor — no Helm, CRDs, or namespaces required.';
    pane.appendChild(note);

    const nameInput = this.input('text', 'Connection name (e.g. dev-kubectl-proxy)');
    const urlInput = this.input('text', 'Kubernetes API URL (e.g. https://10.0.0.5:6443 or http://127.0.0.1:8001)');
    const tokenInput = this.tokenTextarea();
    const proxyHint = document.createElement('div');
    proxyHint.style.cssText = 'font-size:11px;color:#6b7280;';
    proxyHint.innerHTML =
      'Tip: without cluster-admin, run <code style="background:#1f2937;color:#38bdf8;padding:1px 5px;border-radius:4px;">kubectl proxy --port=8001</code> and use <code style="background:#1f2937;color:#38bdf8;padding:1px 5px;border-radius:4px;">http://127.0.0.1:8001</code> with auth type <em>none</em>.';

    const probe = this.probeStatusLine();
    probe.set('idle', 'Client probe: GET /version → GET /api/v1/nodes?limit=1');
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:8px;';
    const testBtn = this.btn('🔌 Test Connection', 'Probe the raw Kubernetes API /version endpoint');
    const connectBtn = this.btn('🔗 Connect Read-Only', 'Fetch + parse cluster topology client-side');
    actions.appendChild(testBtn);
    actions.appendChild(connectBtn);

    testBtn.addEventListener('click', () => {
      void (async () => {
        probe.set('testing', 'Probing /version → /api/v1/nodes?limit=1 …');
        const r = await ClusterOnboardingModal.probeKubernetesApi(
          urlInput.value, tokenInput.value.trim() || undefined,
        );
        probe.set(r.ok ? 'ok' : 'err', r.detail);
      })();
    });
    connectBtn.addEventListener('click', () => {
      const apiUrl = urlInput.value.trim();
      if (!apiUrl) {
        probe.set('err', 'Kubernetes API URL is required.');
        return;
      }
      const localProxy = /^https?:\/\/(127\.0\.0\.1|localhost|0\.0\.0\.0)(:\d+)?/i.test(apiUrl);
      const config: LiveClusterConfig = {
        name: nameInput.value.trim() || 'client-side-cluster',
        apiUrl,
        authType: localProxy ? 'kubeconfig-proxy' : (tokenInput.value.trim() ? 'token' : 'none'),
        namespace: undefined,
        enableLatencyProbe: false,
      };
      void (async () => {
        // TASK-CV-1103: Mode B extracts the whole topology client-side —
        // /version first as the connectivity probe, then nodes/pods/services/
        // HPAs/VPAs in parallel — and hydrates without any SSE stream.
        probe.set('testing', 'Probing /version …');
        const health = await ClusterOnboardingModal.probeKubernetesApi(
          apiUrl, tokenInput.value.trim() || undefined,
        );
        if (!health.ok) {
          probe.set('err', health.detail);
          return;
        }
        probe.set('ok', `API reachable (${health.detail}) — extracting topology client-side …`);
        connectBtn.disabled = true;
        try {
          const graph = await fetchAndExtractClusterGraph(apiUrl, tokenInput.value.trim() || undefined);
          probe.set('ok', `✓ ${graph.metadata.node_count} nodes · ${graph.metadata.pod_count} pods · ${graph.edges.length} edges parsed in browser memory`);
          const token = tokenInput.value.trim();
          ClusterOnboardingModal.storeToken(this.endpointId(config), token || '');
          this.callbacks.onClientGraphExtracted?.(graph, config);
          window.setTimeout(() => this.close(), 450);
        } catch (err) {
          const msg = `Client extraction failed: ${err instanceof Error ? err.message : String(err)}`;
          probe.set('err', msg);
          this.callbacks.onError?.(msg);
          connectBtn.disabled = false;
        }
      })();
    });

    pane.appendChild(nameInput);
    pane.appendChild(this.field('Kubernetes API URL', urlInput));
    pane.appendChild(this.field('Read-Only Bearer Token (optional for kube-proxy; sessionStorage only)', tokenInput));
    pane.appendChild(proxyHint);
    pane.appendChild(probe.el);
    pane.appendChild(actions);
    return pane;
  }

  // -------------------------------------------------------------------------
  // TAB 2 — Simulated sample catalog
  // -------------------------------------------------------------------------

  private renderSampleTab(): HTMLElement {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;flex-direction:column;gap:14px;';

    const note = document.createElement('p');
    note.style.cssText = 'margin:0;color:#9ca3af;font-size:12px;line-height:1.5;';
    note.textContent =
      'Pre-packaged production-grade topologies bundled with the client — zero cloud credentials, zero daemons, full 3D Skyscraper hydration in < 100 ms. Pick a preset, pick a slot, load.';
    wrap.appendChild(note);

    // Slot selector
    const slotRow = document.createElement('div');
    slotRow.style.cssText = 'display:flex;align-items:center;gap:8px;';
    const slotLabel = document.createElement('span');
    slotLabel.style.cssText = 'font-size:11px;font-weight:700;color:#9ca3af;letter-spacing:0.05em;';
    slotLabel.textContent = 'TARGET SLOT';
    slotRow.appendChild(slotLabel);
    const slots: Array<[ViewportSlotId, string]> = [
      ['a', 'Slot A'], ['b', 'Slot B'], ['c', 'Slot C'], ['d', 'Slot D'],
    ];
    for (const [id, label] of slots) {
      const b = this.btn(label, `Load selected sample into ${label}`);
      const on = this.selectedSlot === id;
      b.style.background = on ? 'rgba(56,189,248,0.2)' : '#1f2937';
      b.style.color = on ? '#38bdf8' : '#e5e7eb';
      b.style.borderColor = on ? '#38bdf8' : '#374151';
      b.onclick = () => {
        this.selectedSlot = id;
        this.open('samples');
      };
      slotRow.appendChild(b);
    }
    wrap.appendChild(slotRow);

    // Catalog cards
    const grid = document.createElement('div');
    grid.className = 'cob-sample-grid';
    grid.style.cssText =
      'display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;';
    for (const item of this.catalog.listItems()) {
      grid.appendChild(this.renderSampleCard(item));
    }
    wrap.appendChild(grid);
    wrap.appendChild(this.renderSecurityFootnote());
    return wrap;
  }

  private renderSampleCard(item: {
    id: string; title: string; description: string; category: string;
    k8sVersion: string; nodeCount: number; podCount: number; highlightFeatures: string[];
  }): HTMLElement {
    const catColor: Record<string, string> = {
      oss: '#38bdf8', microservices: '#10b981', 'ai-ml': '#d946ef', benchmark: '#f59e0b',
    };
    const accent = catColor[item.category] ?? '#38bdf8';

    const card = document.createElement('div');
    card.className = 'cob-sample-card';
    card.style.cssText =
      `display:flex;flex-direction:column;gap:8px;background:rgba(15,23,42,0.8);border:1px solid #1f2937;` +
      `border-top:2px solid ${accent};border-radius:8px;padding:12px 14px;`;

    const head = document.createElement('div');
    head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;';
    const title = document.createElement('div');
    title.style.cssText = 'font-weight:700;font-size:13px;color:#f3f4f6;';
    title.textContent = item.title;
    const cat = document.createElement('span');
    cat.style.cssText =
      `font-size:10px;font-weight:700;letter-spacing:0.06em;padding:2px 8px;border-radius:9999px;` +
      `color:${accent};background:${accent}22;border:1px solid ${accent}55;`;
    cat.textContent = item.category.toUpperCase();
    head.appendChild(title);
    head.appendChild(cat);

    const meta = document.createElement('div');
    meta.style.cssText = 'font-size:11px;color:#9ca3af;font-family:ui-monospace,monospace;';
    meta.textContent = `k8s ${item.k8sVersion} · ${item.nodeCount} nodes · ${item.podCount} pods`;

    const desc = document.createElement('p');
    desc.style.cssText = 'margin:0;font-size:11px;color:#d1d5db;line-height:1.5;';
    desc.textContent = item.description;

    const feats = document.createElement('ul');
    feats.style.cssText = 'margin:0;padding-left:16px;font-size:11px;color:#9ca3af;line-height:1.6;';
    for (const f of item.highlightFeatures.slice(0, 4)) {
      const li = document.createElement('li');
      li.textContent = f;
      feats.appendChild(li);
    }

    const loadBtn = this.btn(`⚡ LOAD → ${this.selectedSlot.toUpperCase()}`, `Load ${item.title} into Slot ${this.selectedSlot.toUpperCase()}`);
    loadBtn.style.cssText +=
      `;background:${accent}1f;border-color:${accent}55;color:${accent};font-weight:700;justify-content:center;`;
    loadBtn.addEventListener('click', () => {
      void this.loadSample(item.id, this.selectedSlot, loadBtn);
    });

    card.appendChild(head);
    card.appendChild(meta);
    card.appendChild(desc);
    card.appendChild(feats);
    card.appendChild(loadBtn);
    return card;
  }

  /** Fetch + hand the hydrated graph to the grid controller callback. */
  private async loadSample(id: string, slot: ViewportSlotId, btn?: HTMLButtonElement): Promise<void> {
    if (btn) {
      btn.textContent = '⏳ LOADING…';
      btn.disabled = true;
    }
    try {
      const data = await this.catalog.fetchSampleData(id);
      this.callbacks.onClusterLoaded?.(slot, data);
      if (btn) btn.textContent = '✓ LOADED';
      window.setTimeout(() => this.close(), 350);
    } catch (err) {
      const msg = `Sample load failed: ${err instanceof Error ? err.message : String(err)}`;
      if (btn) {
        btn.textContent = '✕ FAILED — RETRY';
        btn.disabled = false;
      }
      this.callbacks.onError?.(msg);
    }
  }

  // -------------------------------------------------------------------------
  // Small DOM factories
  // -------------------------------------------------------------------------

  private endpointId(config: LiveClusterConfig): string {
    return `${config.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${config.apiUrl.replace(/^https?:\/\//, '').replace(/[^a-z0-9]+/g, '-')}`;
  }

  private btn(label: string, title: string): HTMLButtonElement {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    if (title) b.title = title;
    b.style.cssText =
      'background:#1f2937;color:#e5e7eb;border:1px solid #374151;padding:6px 12px;border-radius:6px;' +
      'font-size:12px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;gap:6px;' +
      'transition:all 0.15s ease;font-family:inherit;';
    return b;
  }

  private input(type: string, placeholder: string): HTMLInputElement {
    const i = document.createElement('input');
    i.type = type;
    i.placeholder = placeholder;
    i.style.cssText =
      'width:100%;background:#0f172a;border:1px solid #374151;border-radius:6px;padding:8px 10px;' +
      'color:#f3f4f6;font-size:12px;font-family:ui-monospace,monospace;box-sizing:border-box;outline:none;';
    return i;
  }

  private tokenTextarea(): HTMLTextAreaElement {
    const t = document.createElement('textarea');
    t.rows = 3;
    t.placeholder = 'eyJhbGciOiJSUzI1NiIsImtpZCI6…  (ServiceAccount bearer token)';
    t.spellcheck = false;
    t.style.cssText =
      'width:100%;background:#0f172a;border:1px solid #374151;border-radius:6px;padding:8px 10px;' +
      'color:#f3f4f6;font-size:11px;font-family:ui-monospace,monospace;resize:vertical;box-sizing:border-box;outline:none;';
    return t;
  }

  private field(label: string, control: HTMLElement): HTMLElement {
    const f = document.createElement('div');
    f.style.cssText = 'display:flex;flex-direction:column;gap:4px;flex:1;min-width:0;';
    const l = document.createElement('label');
    l.style.cssText = 'font-size:11px;font-weight:600;color:#9ca3af;';
    l.textContent = label;
    f.appendChild(l);
    f.appendChild(control);
    return f;
  }

  private probeStatusLine(): {
    el: HTMLElement;
    set: (kind: 'idle' | 'testing' | 'ok' | 'err', text: string) => void;
  } {
    const el = document.createElement('div');
    el.className = 'cob-probe';
    el.style.cssText =
      'min-height:18px;font-size:11px;font-family:ui-monospace,monospace;color:#6b7280;display:flex;align-items:center;gap:8px;';
    const set = (kind: 'idle' | 'testing' | 'ok' | 'err', text: string): void => {
      el.style.color =
        kind === 'ok' ? '#10b981' : kind === 'err' ? '#ef4444' : kind === 'testing' ? '#f59e0b' : '#6b7280';
      el.textContent = text;
    };
    set('idle', 'Connectivity probe: GET /api/v1/healthz → GET /snapshot');
    return { el, set };
  }

  private renderSecurityFootnote(): HTMLElement {
    const f = document.createElement('div');
    f.style.cssText =
      'font-size:10px;color:#6b7280;border-top:1px dashed #1f2937;padding-top:10px;line-height:1.6;';
    f.innerHTML =
      '🔒 Tokens are kept strictly in <code style="color:#38bdf8;">sessionStorage</code> (<code style="color:#38bdf8;">clustervis_token_&lt;id&gt;</code>) — cleared when the tab closes, never written to disk, localStorage, cookies, or URL query strings (SPEC-07 §5.1). RBAC is least-privilege read-only; the operator scrubs all *KEY*/*TOKEN*/*PASS*/*AUTH*/*SECRET* values before serialization.';
    return f;
  }
}
