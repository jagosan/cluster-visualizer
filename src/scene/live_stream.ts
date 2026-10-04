/**
 * Real-time Server-Sent Events (SSE) streaming client for live scene updates.
 * Handles connection lifecycle, automatic reconnection with exponential backoff,
 * and dispatches typed events to registered callbacks.
 */

export type StreamStatus = 'connected' | 'reconnecting' | 'disconnected';

/** SPEC-09 §3.2.1: VPA recommendation ghost-hull payload. */
export interface VpaRecommendationPayload {
  node_id: string;
  dimensions?: {
    current_height: number;
    current_radius: number;
    target_height: number;
    target_radius: number;
  } | null;
  target_cpu?: string | null;
  target_memory?: string | null;
  timestamp?: string;
}

/** SPEC-09 §3.2.2: VPA in-place resize commit payload. */
export interface VpaResizeCommittedPayload {
  node_id: string;
  geometry?: { height?: number; radius?: number } | null;
  duration_ms?: number;
  timestamp?: string;
}

/** SPEC-09 §3.3: HPA scale-out dispatch payload. */
export interface HpaScaleOutPayload {
  node_id: string;
  delta: number;
  current_replicas?: number;
  desired_replicas?: number;
  target_metric?: string | null;
  dispatch_from?: { x: number; y: number; z: number };
  riser_bottom?: { x: number; y: number; z: number };
  lateral_path?: { intake?: number[]; slot?: number[] };
  timestamp?: string;
}

/** SPEC-09 §4.2: Karpenter NodeClaim wire shape (mirror of models.py). */
export interface KarpenterNodeClaimWire {
  claim_name: string;
  namespace?: string;
  nodepool?: string;
  instance_type?: string | null;
  capacity_type?: 'spot' | 'on-demand';
  requested_cpu_cores?: number;
  requested_memory_gib?: number;
  requested_gpu_count?: number;
  pending_pod_uids?: string[];
  is_provisioned?: boolean;
  created_at?: string | null;
}

/** SPEC-09 §4.2: Karpenter NodeClaim snapshot payload (ghost chassis dock). */
export interface KarpenterClaimUpdatedPayload {
  claim: KarpenterNodeClaimWire;
  ghost_position?: { x: number; y: number; z: number } | null;
  staging_focus_x?: number;
  timestamp?: string;
}

/** SPEC-09 §4.2: amber provisioning tractor beam endpoints payload. */
export interface KarpenterTractorBeamPayload {
  node_id: string;
  claim_name: string;
  beam: { top?: number[] | null; bottom?: number[] | null; span_y?: number };
  timestamp?: string;
}

export interface LiveStreamCallbacks {
  onStatusChange?: (status: StreamStatus, url?: string) => void;
  onInitialSnapshot?: (snapshot: any) => void;
  onNodeAdded?: (node: any) => void;
  onNodeRemoved?: (nodeId: string) => void;
  onNodeModified?: (nodeId: string, diffDetails?: string[], status?: string) => void;
  onEdgeUpdated?: (edges: any[]) => void;
  // SPEC-09 / TASK-CV-1002 autoscaling mutation pipelines.
  onVpaRecommendation?: (payload: VpaRecommendationPayload) => void;
  onVpaResizeCommitted?: (payload: VpaResizeCommittedPayload) => void;
  onHpaScaleOut?: (payload: HpaScaleOutPayload) => void;
  // SPEC-09 / TASK-CV-1003 staging yard: Karpenter NodeClaim + tractor beams.
  onKarpenterClaimUpdated?: (payload: KarpenterClaimUpdatedPayload) => void;
  onKarpenterTractorBeam?: (payload: KarpenterTractorBeamPayload) => void;
  onHeartbeat?: (data: { timestamp: number; active_clients: number }) => void;
  onError?: (error: any) => void;
}

export class LiveStreamManager {
  private eventSource: EventSource | null = null;
  private currentUrl: string | null = null;
  private status: StreamStatus = 'disconnected';
  private reconnectAttempts = 0;
  private reconnectTimeout: number | null = null;
  private callbacks: LiveStreamCallbacks = {};

  constructor(callbacks?: LiveStreamCallbacks) {
    if (callbacks) {
      this.callbacks = { ...callbacks };
    }
  }

  /**
   * Connects to the SSE endpoint at the given URL.
   * If already connected or reconnecting, closes the existing connection first.
   */
  connect(url: string): void {
    // Clean up any existing connection
    this.cleanupConnection();

    this.currentUrl = url;
    this.setStatus('reconnecting');

    try {
      this.eventSource = new EventSource(url);

      this.eventSource.onopen = () => {
        this.reconnectAttempts = 0;
        this.setStatus('connected');
      };

      this.eventSource.onerror = (event: Event) => {
        // If the connection is closed, attempt to reconnect with backoff
        if (this.eventSource?.readyState === EventSource.CLOSED) {
          this.handleReconnect();
        }
        // Notify error callback if provided
        if (this.callbacks.onError) {
          this.callbacks.onError(event);
        }
      };

      // Listen for initial snapshot
      this.eventSource.addEventListener('initial_snapshot', (e: MessageEvent) => {
        try {
          const snapshot = JSON.parse(e.data);
          if (this.callbacks.onInitialSnapshot) {
            this.callbacks.onInitialSnapshot(snapshot);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // Listen for node added
      this.eventSource.addEventListener('node_added', (e: MessageEvent) => {
        try {
          const node = JSON.parse(e.data);
          if (this.callbacks.onNodeAdded) {
            this.callbacks.onNodeAdded(node);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // Listen for node removed
      this.eventSource.addEventListener('node_removed', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const nodeId = typeof data === 'string' ? data : data.nodeId;
          if (this.callbacks.onNodeRemoved) {
            this.callbacks.onNodeRemoved(nodeId);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // Listen for node modified
      this.eventSource.addEventListener('node_modified', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const nodeId = data.nodeId;
          const diffDetails = data.diffDetails;
          const status = data.status;
          if (this.callbacks.onNodeModified) {
            this.callbacks.onNodeModified(nodeId, diffDetails, status);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // Listen for edge updated
      this.eventSource.addEventListener('edge_updated', (e: MessageEvent) => {
        try {
          const edges = JSON.parse(e.data);
          if (this.callbacks.onEdgeUpdated) {
            this.callbacks.onEdgeUpdated(edges);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // SPEC-09 §3.2.1: VPA recommendation ghost hull
      this.eventSource.addEventListener('vpa_recommendation', (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data) as VpaRecommendationPayload;
          if (this.callbacks.onVpaRecommendation) {
            this.callbacks.onVpaRecommendation(payload);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // SPEC-09 §3.2.2: VPA in-place resize commit
      this.eventSource.addEventListener('vpa_resize_committed', (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data) as VpaResizeCommittedPayload;
          if (this.callbacks.onVpaResizeCommitted) {
            this.callbacks.onVpaResizeCommitted(payload);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // SPEC-09 §3.3: HPA scale-out lateral dispatch
      this.eventSource.addEventListener('hpa_scale_out', (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data) as HpaScaleOutPayload;
          if (this.callbacks.onHpaScaleOut) {
            this.callbacks.onHpaScaleOut(payload);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // SPEC-09 §4.2: Karpenter NodeClaim provisioning snapshot + ghost dock
      this.eventSource.addEventListener('karpenter_claim_updated', (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data) as KarpenterClaimUpdatedPayload;
          if (this.callbacks.onKarpenterClaimUpdated) {
            this.callbacks.onKarpenterClaimUpdated(payload);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // SPEC-09 §4.2: amber tractor beam from pending pods to ghost chassis
      this.eventSource.addEventListener('karpenter_tractor_beam', (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data) as KarpenterTractorBeamPayload;
          if (this.callbacks.onKarpenterTractorBeam) {
            this.callbacks.onKarpenterTractorBeam(payload);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });

      // Listen for heartbeat
      this.eventSource.addEventListener('heartbeat', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (this.callbacks.onHeartbeat) {
            this.callbacks.onHeartbeat(data);
          }
        } catch (err) {
          if (this.callbacks.onError) {
            this.callbacks.onError(err);
          }
        }
      });
    } catch (err) {
      if (this.callbacks.onError) {
        this.callbacks.onError(err);
      }
      this.setStatus('disconnected');
    }
  }

  /**
   * Disconnects from the SSE endpoint and clears any pending reconnection timers.
   */
  disconnect(): void {
    this.cleanupConnection();
    this.setStatus('disconnected');
  }

  /**
   * Returns the current connection status.
   */
  getStatus(): StreamStatus {
    return this.status;
  }

  /**
   * Returns the URL of the current or last connection attempt.
   */
  getUrl(): string | null {
    return this.currentUrl;
  }

  /**
   * Updates the callbacks used by the stream manager.
   */
  setCallbacks(callbacks: LiveStreamCallbacks): void {
    this.callbacks = { ...callbacks };
  }

  /**
   * Internal method to clean up the EventSource and any reconnect timers.
   */
  private cleanupConnection(): void {
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  /**
   * Sets the internal status and notifies the onStatusChange callback.
   */
  private setStatus(status: StreamStatus): void {
    if (this.status === status) {
      return;
    }
    this.status = status;
    if (this.callbacks.onStatusChange) {
      this.callbacks.onStatusChange(status, this.currentUrl ?? undefined);
    }
  }

  /**
   * Handles reconnection with exponential backoff.
   * Backoff sequence: 1s, 2s, 4s, 8s, capped at 15s.
   */
  private handleReconnect(): void {
    if (this.reconnectTimeout !== null) {
      return; // Already scheduled
    }

    this.setStatus('reconnecting');

    // Calculate delay: 2^attempts * 1000ms, capped at 15000ms
    const delay = Math.min(Math.pow(2, this.reconnectAttempts) * 1000, 15000);
    this.reconnectAttempts++;

    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      if (this.currentUrl) {
        this.connect(this.currentUrl);
      }
    }, delay);
  }
}
