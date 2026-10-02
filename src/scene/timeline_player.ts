import { ClusterViewport } from './cluster_viewport.js';
import type { ClusterGraphData, ClusterNodeData } from './cluster_viewport.js';

export interface TimelineEventData {
  timestamp: string;
  event_type: 'pod_scheduled' | 'pod_evicted' | 'image_updated' | 'node_scaled' | 'config_drift' | 'custom';
  summary: string;
  affected_node_ids?: string[];
  metadata?: Record<string, any>;
}

export interface ClusterTimelineKeyframeData {
  timestamp: string;
  snapshot_index: number;
  time_offset_seconds?: number;
  graph?: ClusterGraphData;
  nodes?: ClusterNodeData[];
  edges?: any[];
  events?: TimelineEventData[];
  delta_summary?: Record<string, any>;
}

export interface ClusterTimelineData {
  $schema?: string;
  cluster_name: string;
  start_time: string;
  end_time: string;
  duration_seconds: number;
  keyframes: ClusterTimelineKeyframeData[];
  metadata?: Record<string, any>;
}

export interface TimelinePlayerCallbacks {
  onTimeUpdate?: (currentTime: number, duration: number, keyframeIndex: number) => void;
  onKeyframeChanged?: (keyframe: ClusterTimelineKeyframeData, index: number) => void;
  onEventTriggered?: (event: TimelineEventData) => void;
  onPlayStateChanged?: (isPlaying: boolean) => void;
  onSpeedChanged?: (speed: number) => void;
}

export class TimelinePlayer {
  private timeline: ClusterTimelineData | null = null;
  private viewports: ClusterViewport[] = [];
  private currentTime: number = 0;
  private currentKeyframeIndex: number = -1;
  private isPlaying: boolean = false;
  private playbackSpeed: number = 1.0;
  private isLooping: boolean = true;
  public callbacks: TimelinePlayerCallbacks = {};
  private keyframeOffsets: number[] = [];

  constructor(callbacks?: TimelinePlayerCallbacks) {
    if (callbacks) {
      this.callbacks = callbacks;
    }
  }

  setCallbacks(callbacks: TimelinePlayerCallbacks): void {
    this.callbacks = callbacks;
  }

  attachViewport(viewport: ClusterViewport): void {
    if (!this.viewports.includes(viewport)) {
      this.viewports.push(viewport);
    }
  }

  detachViewport(viewport: ClusterViewport): void {
    const index = this.viewports.indexOf(viewport);
    if (index !== -1) {
      this.viewports.splice(index, 1);
    }
  }

  loadTimeline(timeline: ClusterTimelineData): void {
    this.timeline = timeline;
    this.keyframeOffsets = [];

    const startTime = new Date(timeline.start_time).getTime();

    for (const kf of timeline.keyframes) {
      const offset = kf.time_offset_seconds ?? ((new Date(kf.timestamp).getTime() - startTime) / 1000);
      this.keyframeOffsets.push(offset);
    }

    this.currentTime = 0;
    this.currentKeyframeIndex = -1;
    this.isPlaying = false;

    if (timeline.keyframes.length > 0) {
      const firstKf = timeline.keyframes[0]!;
      this.applyKeyframe(firstKf);
      this.currentKeyframeIndex = 0;
      this.callbacks.onKeyframeChanged?.(firstKf, 0);
      this.callbacks.onTimeUpdate?.(0, this.getDuration(), 0);
    }
  }

  play(): void {
    if (!this.isPlaying) {
      this.isPlaying = true;
      this.callbacks.onPlayStateChanged?.(true);
    }
  }

  pause(): void {
    if (this.isPlaying) {
      this.isPlaying = false;
      this.callbacks.onPlayStateChanged?.(false);
    }
  }

  togglePlay(): void {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
  }

  seekToTime(seconds: number): void {
    const duration = this.timeline?.duration_seconds ?? 0;
    const clampedSeconds = Math.max(0, Math.min(seconds, duration));
    this.currentTime = clampedSeconds;
    this.updateKeyframeIndex();
    this.callbacks.onTimeUpdate?.(this.currentTime, this.getDuration(), this.currentKeyframeIndex);
  }

  seekToFrame(index: number): void {
    if (!this.timeline) {
      return;
    }
    const maxIndex = this.timeline.keyframes.length - 1;
    const clampedIndex = Math.max(0, Math.min(index, maxIndex));
    const offset = this.keyframeOffsets[clampedIndex];
    if (offset !== undefined) {
      this.currentTime = offset;
      this.updateKeyframeIndex();
      this.callbacks.onTimeUpdate?.(this.currentTime, this.getDuration(), this.currentKeyframeIndex);
    }
  }

  seekToPreviousKeyframe(): void {
    const newIndex = this.currentKeyframeIndex - 1;
    if (newIndex >= 0) {
      this.seekToFrame(newIndex);
    } else {
      this.seekToFrame(0);
    }
  }

  seekToNextKeyframe(): void {
    if (!this.timeline) {
      return;
    }
    const maxIndex = this.timeline.keyframes.length - 1;
    const newIndex = this.currentKeyframeIndex + 1;
    if (newIndex <= maxIndex) {
      this.seekToFrame(newIndex);
    }
  }

  setSpeed(speed: number): void {
    if (this.playbackSpeed !== speed) {
      this.playbackSpeed = speed;
      this.callbacks.onSpeedChanged?.(speed);
    }
  }

  setLoop(loop: boolean): void {
    this.isLooping = loop;
  }

  update(delta: number): void {
    if (!this.isPlaying || !this.timeline) {
      return;
    }

    const duration = this.timeline.duration_seconds;
    this.currentTime += delta * this.playbackSpeed;

    if (this.currentTime >= duration) {
      if (this.isLooping) {
        this.currentTime = this.currentTime % duration;
      } else {
        this.currentTime = duration;
        this.pause();
      }
    } else if (this.currentTime < 0) {
      if (this.isLooping) {
        this.currentTime = duration + (this.currentTime % duration);
      } else {
        this.currentTime = 0;
        this.pause();
      }
    }

    this.updateKeyframeIndex();
    this.callbacks.onTimeUpdate?.(this.currentTime, this.getDuration(), this.currentKeyframeIndex);
  }

  private updateKeyframeIndex(): void {
    if (!this.timeline || this.keyframeOffsets.length === 0) {
      return;
    }

    let newIndex = -1;
    for (let i = 0; i < this.keyframeOffsets.length; i++) {
      const offset = this.keyframeOffsets[i];
      if (offset !== undefined && this.currentTime >= offset) {
        newIndex = i;
      } else {
        break;
      }
    }

    if (newIndex !== this.currentKeyframeIndex && newIndex >= 0) {
      const nextKf = this.timeline.keyframes[newIndex];
      if (nextKf) {
        if (nextKf.events) {
          for (const ev of nextKf.events) {
            this.callbacks.onEventTriggered?.(ev);
          }
        }
        this.callbacks.onKeyframeChanged?.(nextKf, newIndex);
        this.applyKeyframe(nextKf);
        this.currentKeyframeIndex = newIndex;
      }
    }
  }

  applyKeyframe(kf: ClusterTimelineKeyframeData): void {
    if (kf.graph) {
      for (const viewport of this.viewports) {
        viewport.loadGraph(kf.graph);
      }
    } else if (kf.nodes) {
      const g: ClusterGraphData = {
        metadata: {
          cluster_name: this.timeline?.cluster_name ?? 'cluster-alpha',
          kubernetes_version: 'v1.36.4',
          distribution: 'kind',
          node_count: 2,
          pod_count: 2,
        },
        nodes: kf.nodes,
        edges: kf.edges ?? [],
      };
      for (const viewport of this.viewports) {
        viewport.loadGraph(g);
      }
    }
  }

  getCurrentTime(): number {
    return this.currentTime;
  }

  getDuration(): number {
    return this.timeline?.duration_seconds ?? 0;
  }

  getSpeed(): number {
    return this.playbackSpeed;
  }

  getIsPlaying(): boolean {
    return this.isPlaying;
  }

  getKeyframes(): ClusterTimelineKeyframeData[] {
    return this.timeline?.keyframes ?? [];
  }

  getCurrentKeyframe(): ClusterTimelineKeyframeData | null {
    return (this.timeline && this.currentKeyframeIndex >= 0)
      ? (this.timeline.keyframes[this.currentKeyframeIndex] ?? null)
      : null;
  }
}
