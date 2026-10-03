// src/ui/cluster_federation.ts
// TASK-CV-806 / SPEC-07 §7.1 & §7.2

export interface ClusterEndpoint {
  id: string;
  name: string;
  url: string;
  token?: string;
  status: 'connected' | 'connecting' | 'error' | 'offline';
  latencyMs: number;
  kubernetesVersion: string;
}

export interface WorkloadComparison {
  clusterId: string;
  clusterName: string;
  workloadName: string;
  version: string;
  latencyMs: number;
  rps: number;
}

const TOKEN_STORAGE_PREFIX = 'clustervis_token_';

export class ClusterFederationManager {
  private readonly endpoints: Map<string, ClusterEndpoint>;

  constructor() {
    this.endpoints = new Map<string, ClusterEndpoint>();
  }

  /**
   * Adds a new cluster endpoint.
   * Status defaults to 'offline', latencyMs to 0, and kubernetesVersion to 'unknown'.
   */
  addEndpoint(
    endpoint: Omit<ClusterEndpoint, 'status' | 'latencyMs' | 'kubernetesVersion'>
  ): ClusterEndpoint {
    const newEndpoint: ClusterEndpoint = {
      ...endpoint,
      status: 'offline',
      latencyMs: 0,
      kubernetesVersion: 'unknown',
    };
    this.endpoints.set(newEndpoint.id, newEndpoint);
    return newEndpoint;
  }

  /**
   * Removes a cluster endpoint by ID.
   */
  removeEndpoint(id: string): void {
    this.endpoints.delete(id);
  }

  /**
   * Returns all registered endpoints.
   */
  getEndpoints(): ClusterEndpoint[] {
    return Array.from(this.endpoints.values());
  }

  /**
   * Returns a specific endpoint by ID, or undefined if not found.
   */
  getEndpoint(id: string): ClusterEndpoint | undefined {
    return this.endpoints.get(id);
  }

  /**
   * Persists a token for a given endpoint ID in sessionStorage.
   * Never uses localStorage per SPEC-07 §5.1.
   */
  setToken(id: string, token: string): void {
    try {
      sessionStorage.setItem(TOKEN_STORAGE_PREFIX + id, token);
    } catch {
      // Silently fail if sessionStorage is unavailable (e.g., private browsing restrictions)
    }
  }

  /**
   * Retrieves a token for a given endpoint ID from sessionStorage.
   */
  getToken(id: string): string | undefined {
    try {
      return sessionStorage.getItem(TOKEN_STORAGE_PREFIX + id) ?? undefined;
    } catch {
      return undefined;
    }
  }

  /**
   * Attempts to connect to a cluster endpoint by performing a health check.
   * Tries /api/v1/healthz first, then /api/v1/topology as fallback.
   * Updates endpoint status and latency based on response.
   */
  async connectEndpoint(id: string): Promise<boolean> {
    const endpoint = this.endpoints.get(id);
    if (!endpoint) {
      return false;
    }

    // Mark as connecting
    endpoint.status = 'connecting';
    this.endpoints.set(id, endpoint);

    const token = this.getToken(id);
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const healthzUrl = `${endpoint.url.replace(/\/$/, '')}/api/v1/healthz`;
    const topologyUrl = `${endpoint.url.replace(/\/$/, '')}/api/v1/topology`;

    const startTime = performance.now();

    try {
      // Try healthz first
      let response = await fetch(healthzUrl, {
        method: 'GET',
        headers,
        signal: AbortSignal.timeout(5000),
      });

      if (!response.ok) {
        // Fallback to topology
        response = await fetch(topologyUrl, {
          method: 'GET',
          headers,
          signal: AbortSignal.timeout(5000),
        });
      }

      const endTime = performance.now();
      const latencyMs = Math.round(endTime - startTime);

      if (response.ok) {
        endpoint.status = 'connected';
        endpoint.latencyMs = latencyMs;

        // Attempt to extract Kubernetes version from response if available
        try {
          const data: unknown = await response.json();
          if (
            data &&
            typeof data === 'object' &&
            'kubernetesVersion' in data &&
            typeof (data as Record<string, unknown>).kubernetesVersion === 'string'
          ) {
            endpoint.kubernetesVersion = (data as Record<string, unknown>)
              .kubernetesVersion as string;
          }
        } catch {
          // Keep existing version if parsing fails
        }

        this.endpoints.set(id, endpoint);
        return true;
      } else {
        endpoint.status = 'error';
        endpoint.latencyMs = latencyMs;
        this.endpoints.set(id, endpoint);
        return false;
      }
    } catch {
      const endTime = performance.now();
      const latencyMs = Math.round(endTime - startTime);
      endpoint.status = 'error';
      endpoint.latencyMs = latencyMs;
      this.endpoints.set(id, endpoint);
      return false;
    }
  }

  /**
   * Compares a workload across all connected clusters.
   * Returns comparison data for each connected endpoint.
   */
  compareWorkload(workloadName: string): WorkloadComparison[] {
    const comparisons: WorkloadComparison[] = [];
    const endpoints = this.getEndpoints();

    for (const endpoint of endpoints) {
      if (endpoint.status !== 'connected') {
        continue;
      }

      // In a real implementation, this would fetch actual workload data.
      // Here we return a placeholder comparison based on available endpoint data.
      const comparison: WorkloadComparison = {
        clusterId: endpoint.id,
        clusterName: endpoint.name,
        workloadName,
        version: endpoint.kubernetesVersion,
        latencyMs: endpoint.latencyMs,
        rps: 0, // Placeholder: actual RPS would come from metrics API
      };
      comparisons.push(comparison);
    }

    return comparisons;
  }
}

/**
 * Factory function to create a new ClusterFederationManager instance.
 */
export function createFederationManager(): ClusterFederationManager {
  return new ClusterFederationManager();
}
