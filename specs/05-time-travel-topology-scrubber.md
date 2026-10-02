# SPEC-05: Time-Travel Cluster Topology Playback & Historical Scrubber Engine

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-02  
**Target:** `cluster-vis`  
**Extends:** `specs/03-horizontal-node-peers-and-diff-engine.md`, `specs/04-in-cluster-streaming-operator.md`  

---

## 1. Executive Summary & Design Goals

During incident forensics, continuous deployment canary rollouts, or capacity autoscaling events, operators need to see **how a cluster evolved across time**. 

SPEC-05 defines the **Time-Travel Cluster Topology Playback & Historical Scrubber Engine**:
1. **Chronological Snapshot Series & Delta Encoding:** Captures successive cluster states as an indexed timeline with delta-compressed state changes to conserve bandwidth and memory.
2. **Interactive HUD Timeline Scrubber:** A sleek bottom-docked timeline control panel featuring play/pause, scrub slider, speed multiplier ($0.5\times, 1\times, 2\times, 5\times, 10\times$), and jump-to-event markers (e.g. deployment rollouts, node drained, pod crashloops).
3. **Smooth 3D Spatial Tweening & State Transitions:** Components smoothly interpolate between states:
   - Newly scheduled pods animate down from the sky or materialize with emerald particles.
   - Evicted/deleted pods fade into hollow red wireframe ghosts before dissolving.
   - Version updates trigger a rotating flip animation with amber hazard pulse.

---

## 2. Timeline Data Contracts (`src/ingestion/timeline_models.py`)

### 2.1 Timeline Schema: `ClusterTimeline`
```python
class TimelineEvent(BaseModel):
    timestamp: str
    event_type: Literal["pod_scheduled", "pod_evicted", "image_updated", "node_scaled", "config_drift"]
    summary: str
    affected_node_ids: List[str]

class ClusterTimelineKeyframe(BaseModel):
    timestamp: str
    snapshot_index: int
    graph: ClusterGraph
    events: List[TimelineEvent] = Field(default_factory=list)

class ClusterTimeline(BaseModel):
    cluster_name: str
    start_time: str
    end_time: str
    duration_seconds: float
    keyframes: List[ClusterTimelineKeyframe]
```

### 2.2 Delta Compression Strategy
For multi-hour recordings, storing full keyframes becomes wasteful. Full keyframes are stored at 5-minute checkpoints, while intermediate states store JSON diff deltas:
$$\Delta_t = \text{State}_t - \text{State}_{t-1}$$

---

## 3. Timeline Recording CLI: `cluster-vis record`

A subcommand in `src/ingestion/recorder.py`:
```bash
python3 -m src.ingestion.recorder \
  --context kind-cluster-alpha \
  --interval 10s \
  --duration 30m \
  --output public/data/timelines/alpha-rollout.json
```
- Samples cluster state every $N$ seconds.
- Computes SHA-256 digest of topology to skip duplicate unchanged frames.
- Detects deployment rollout progressions (e.g. `postgres:18.6` $\rightarrow$ `postgres:18.7`).
- Emits bundled `ClusterTimeline` JSON artifact ready for instant browser playback.

---

## 4. Frontend Timeline Scrubber Component (`src/ui/timeline_scrubber.ts`)

### 4.1 UI Layout & HUD Docking
The scrubber is docked at the bottom of the viewport:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  ▶ PLAY   ⏸ PAUSE   [1x ▼]   ⏮ PREV   NEXT ⏭    04:15 / 30:00                          │
│                                                                                        │
│  ───────●──────────────────────◆───────────────────────▲─────────────────────────────  │
│       Node Scale Up        Postgres v18.7 Rollout   Cilium eBPF Skew                   │
│                                                                                        │
│  [2026-10-02 14:04:15 UTC] - Rolling update: postgres-primary pod scheduled on node-2 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Interactive Capabilities
1. **Scrub Bar Dragging:** Scrubbing the thumb immediately renders the cluster at that exact second without frame stuttering.
2. **Event Markers (`◆`):** Hovering over diamond markers displays a popover summary of the event (e.g. "Deployment `postgres` image updated").
3. **Playback Loop:** Automatically advances through frames with adjustable playback rate.
4. **Synchronous Dual-Cluster Playback:** When comparing two clusters over time (e.g. Production vs Staging during the same deployment window), both viewports advance synchronously.

---

## 5. 3D State Transition Engine (`src/scene/timeline_player.ts`)

When scrubbing between frame $A$ and frame $B$:
- **Component Persistence Tracking:** Uses deterministic component keys (`namespace/kind/name`) to identify identical entities across keyframes.
- **Position Interpolation:** Uses cubic hermite splines or spherical linear interpolation (`slerp`) for moving pods.
- **Material Morphing:**
  - If a component changes version between $A$ and $B$, animate the material from standard slate PBR $\rightarrow$ pulsing amber hazard stripe.
  - If a component is absent in $B$, fade opacity from $1.0 \rightarrow 0.2$ with wireframe red outlines.

---

## 6. Swarm Work Breakdown (Pantheon Tasks)

- **[TASK-CV-601]** [Data Models] Author `src/ingestion/timeline_models.py` defining `TimelineEvent`, `ClusterTimelineKeyframe`, and `ClusterTimeline`.
- **[TASK-CV-602]** [Timeline Recorder CLI] Author `src/ingestion/recorder.py` supporting periodic sampling, delta deduplication, and export.
- **[TASK-CV-603]** [Timeline Player Engine] Author `src/scene/timeline_player.ts` managing keyframe interpolation, component lifecycles, and delta transitions in Three.js.
- **[TASK-CV-604]** [HUD Timeline Scrubber UI] Author `src/ui/timeline_scrubber.ts` with playback controls, event pins, and scrub slider.
- **[TASK-CV-605]** [Synthetic Rollout Testbed Generator] Author script generating a multi-keyframe timeline simulating a realistic database upgrade and node failure.
- **[TASK-CV-606]** [Tests & Build Verification] Author unit tests in `tests/test_timeline.py`, verify `npm run build`, and visual verification.
