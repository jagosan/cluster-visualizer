import { TimelinePlayer } from '../scene/timeline_player.js';
import type {
  ClusterTimelineData,
  ClusterTimelineKeyframeData,
  TimelineEventData,
} from '../scene/timeline_player.js';

export class TimelineScrubber {
  private container: HTMLElement;
  private player: TimelinePlayer | null = null;
  private isVisible: boolean = false;
  private isDragging: boolean = false;
  private speedSteps: number[] = [0.5, 1, 2, 5, 10];
  private speedIndex: number = 1;
  private duration: number = 0;

  private playBtn!: HTMLButtonElement;
  private prevBtn!: HTMLButtonElement;
  private nextBtn!: HTMLButtonElement;
  private speedBtn!: HTMLButtonElement;
  private timeReadout!: HTMLElement;
  private track!: HTMLElement;
  private progressBar!: HTMLElement;
  private thumb!: HTMLElement;
  private pinsContainer!: HTMLElement;
  private eventBanner!: HTMLElement;
  private closeBtn!: HTMLButtonElement;

  constructor() {
    this.container = document.createElement('div');
    this.container.id = 'timeline-scrubber-dock';
    this.container.className = 'timeline-scrubber-dock';
    this.container.innerHTML = `
      <div class="ts-row">
        <button class="btn" id="ts-prev" title="Previous Keyframe">⏮</button>
        <button class="btn" id="ts-play" title="Play/Pause">▶ PLAY</button>
        <button class="btn" id="ts-next" title="Next Keyframe">⏭</button>
        <button class="btn" id="ts-speed" title="Speed">1x</button>
        <span class="ts-time" id="ts-time">00:00 / 00:00</span>
        <div style="flex:1"></div>
        <button class="btn" id="ts-close" title="Close">✕</button>
      </div>
      <div class="ts-track-wrap" id="ts-track-wrap">
        <div class="ts-track" id="ts-track">
          <div class="ts-progress" id="ts-progress"></div>
          <div class="ts-thumb" id="ts-thumb"></div>
          <div class="ts-pins" id="ts-pins"></div>
        </div>
      </div>
      <div class="ts-banner" id="ts-banner" style="display:none"></div>
    `;
    document.body.appendChild(this.container);

    this.initElements();
    this.bindEvents();
  }

  private initElements(): void {
    const prevBtn = document.getElementById('ts-prev');
    const playBtn = document.getElementById('ts-play');
    const nextBtn = document.getElementById('ts-next');
    const speedBtn = document.getElementById('ts-speed');
    const timeReadout = document.getElementById('ts-time');
    const track = document.getElementById('ts-track');
    const progressBar = document.getElementById('ts-progress');
    const thumb = document.getElementById('ts-thumb');
    const pinsContainer = document.getElementById('ts-pins');
    const eventBanner = document.getElementById('ts-banner');
    const closeBtn = document.getElementById('ts-close');

    if (
      !prevBtn ||
      !playBtn ||
      !nextBtn ||
      !speedBtn ||
      !timeReadout ||
      !track ||
      !progressBar ||
      !thumb ||
      !pinsContainer ||
      !eventBanner ||
      !closeBtn
    ) {
      throw new Error('TimelineScrubber: Failed to find required DOM elements.');
    }

    this.prevBtn = prevBtn as HTMLButtonElement;
    this.playBtn = playBtn as HTMLButtonElement;
    this.nextBtn = nextBtn as HTMLButtonElement;
    this.speedBtn = speedBtn as HTMLButtonElement;
    this.timeReadout = timeReadout;
    this.track = track;
    this.progressBar = progressBar;
    this.thumb = thumb;
    this.pinsContainer = pinsContainer;
    this.eventBanner = eventBanner;
    this.closeBtn = closeBtn as HTMLButtonElement;
  }

  private bindEvents(): void {
    this.playBtn.addEventListener('click', () => {
      this.player?.togglePlay();
    });

    this.prevBtn.addEventListener('click', () => {
      this.player?.seekToPreviousKeyframe();
    });

    this.nextBtn.addEventListener('click', () => {
      this.player?.seekToNextKeyframe();
    });

    this.speedBtn.addEventListener('click', () => {
      this.speedIndex = (this.speedIndex + 1) % this.speedSteps.length;
      const s = this.speedSteps[this.speedIndex] ?? 1.0;
      this.player?.setSpeed(s);
      this.speedBtn.textContent = `${s}x`;
    });

    this.closeBtn.addEventListener('click', () => {
      this.hide();
    });

    const handleMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return; // Only left click
      this.isDragging = true;
      this.seekFromEvent(e);
      
      const handleMouseMove = (moveEvent: MouseEvent) => {
        if (this.isDragging) {
          this.seekFromEvent(moveEvent);
        }
      };

      const handleMouseUp = () => {
        this.isDragging = false;
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    };

    this.track.addEventListener('mousedown', handleMouseDown);
    this.thumb.addEventListener('mousedown', handleMouseDown);

    window.addEventListener('keydown', (e: KeyboardEvent) => {
      if (!this.isVisible) return;

      // Prevent default scrolling behavior for space and arrows if focused on body/body-like
      // Note: In a real app, you might want to check if an input is focused.
      if (e.code === 'Space') {
        e.preventDefault();
        this.player?.togglePlay();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        this.player?.seekToTime(Math.max(0, (this.player.getCurrentTime?.() ?? 0) - 2));
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        this.player?.seekToTime(Math.min(this.duration, (this.player.getCurrentTime?.() ?? 0) + 2));
      }
    });
  }

  private seekFromEvent(e: MouseEvent): void {
    const rect = this.track.getBoundingClientRect();
    if (rect.width === 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    this.player?.seekToTime(ratio * this.duration);
  }

  private formatTime(sec: number): string {
    const totalSeconds = Math.floor(sec);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  }

  public attachPlayer(player: TimelinePlayer): void {
    this.player = player;
    this.duration = player.getDuration();

    player.callbacks.onTimeUpdate = (curr: number, dur: number, _idx: number) => {
      this.duration = dur;
      const pct = dur > 0 ? (curr / dur) * 100 : 0;
      this.progressBar.style.width = `${pct}%`;
      this.thumb.style.left = `${pct}%`;
      this.timeReadout.textContent = `${this.formatTime(curr)} / ${this.formatTime(dur)}`;
    };

    player.callbacks.onPlayStateChanged = (isPlaying: boolean) => {
      this.playBtn.textContent = isPlaying ? '⏸ PAUSE' : '▶ PLAY';
    };

    player.callbacks.onSpeedChanged = (s: number) => {
      this.speedBtn.textContent = `${s}x`;
    };

    player.callbacks.onEventTriggered = (ev: TimelineEventData) => {
      this.flashBanner(ev.summary);
    };

    player.callbacks.onKeyframeChanged = (_kf: ClusterTimelineKeyframeData, idx: number) => {
      this.highlightPin(idx);
    };
  }

  public renderKeyframePins(timeline: ClusterTimelineData): void {
    this.pinsContainer.innerHTML = '';
    const dur = timeline.duration_seconds || 1;

    timeline.keyframes.forEach((kf: ClusterTimelineKeyframeData, i: number) => {
      const offset = kf.time_offset_seconds ?? 0;
      const pct = (offset / dur) * 100;
      
      const pin = document.createElement('div');
      pin.className = 'ts-pin';
      pin.style.left = `${pct}%`;
      
      // Safely access first event summary if available
      const firstEvent = kf.events?.[0];
      pin.title = firstEvent?.summary || `Frame ${i}`;
      
      pin.addEventListener('click', (e: MouseEvent) => {
        e.stopPropagation();
        this.player?.seekToFrame(i);
      });
      
      this.pinsContainer.appendChild(pin);
    });
  }

  private flashBanner(msg: string): void {
    this.eventBanner.textContent = msg;
    this.eventBanner.style.display = 'block';
    
    setTimeout(() => {
      // Only hide if the message hasn't changed in the meantime
      if (this.eventBanner.textContent === msg) {
        this.eventBanner.style.display = 'none';
      }
    }, 3000);
  }

  private highlightPin(activeIdx: number): void {
    const pins = this.pinsContainer.children;
    for (let i = 0; i < pins.length; i++) {
      const pin = pins[i];
      if (pin) {
        if (i === activeIdx) {
          pin.classList.add('ts-pin-active');
        } else {
          pin.classList.remove('ts-pin-active');
        }
      }
    }
  }

  public show(): void {
    this.isVisible = true;
    this.container.style.display = 'block';
  }

  public hide(): void {
    this.isVisible = false;
    this.container.style.display = 'none';
  }

  public toggle(): void {
    if (this.isVisible) {
      this.hide();
    } else {
      this.show();
    }
  }
}
