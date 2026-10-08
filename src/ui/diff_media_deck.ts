/**
 * SPEC-11 §2.3 / §5.2 — TASK-CV-1203: Diff Media Control Deck.
 *
 * Dockable, translucent floating HUD for the ⚡ DIFF INSPECTION TOUR. Per
 * blueprint ADR-02 this is the **view half** of the diff-sequence pair:
 * `DiffSequenceEngine` (src/scene/diff_sequence.ts, TASK-CV-1202) owns the
 * queue and playback state machine; the deck only projects engine state onto
 * the DOM and forwards user intent back through the engine API — it never
 * mutates diff state itself.
 *
 *   • Header row   — title, Added / Deleted / Modified / Latency counters and
 *                    a `[✕]` close button.
 *   • Controls row — `⏮ PREV` → prev(), `▶ PLAY / ⏸ PAUSE` → togglePlay(),
 *                    `⏭ NEXT` → next(), rate buttons `0.5x / 1x / 2x` →
 *                    setSpeed(s) (spec §3.2 media controls).
 *   • Scrubber row — `div.diff-track-wrap` with track bar, progress fill and
 *                    one numbered pin per queue item positioned at
 *                    `(index / (total - 1)) * 100%`, color-coded via
 *                    `DIFF_KIND_COLORS[item.kind]`; a track/thumb click or
 *                    drag seeks the engine (`seek(targetIndex)`).
 *   • Active-item banner — `Step ${index + 1}/${total}: ${item.componentName}
 *                    [${item.kind.toUpperCase()}]`, diff detail lines, version
 *                    skew (`${item.alphaVersion} ➔ ${item.betaVersion}`) and
 *                    latency skew (`[Δ ${item.latencyDeltaMs}ms]`).
 *   • Keyboard while visible — Space toggles playback, ← / → step prev /
 *                    next, Escape closes.
 *
 * Re-render is event-driven: `engine.onStep()` and `engine.onStateChange()`
 * repaint controls, the active banner, the progress fill and pin highlights.
 * Downstream consumers (viewport highlight layer, TASK-CV-1204) observe item
 * selections through `onItemSelect(cb)`.
 *
 * Wiring into `src/main.ts` happens in the integration step.
 */

import type {
  DiffSequenceItem,
  DiffSequenceState,
} from '../scene/diff_sequence.js';
import { DiffSequenceEngine, DIFF_KIND_COLORS } from '../scene/diff_sequence.js';

/* ========================================================================== *
 * Constants & helpers
 * ========================================================================== */

/** Playback-rate multipliers (spec §3.2: 0.5x / 1x / 2x). */
const SPEED_OPTIONS: readonly number[] = [0.5, 1, 2];

/** Fixed bottom floating dock styling (hidden until `open()`; spec §2.3). */
const CONTAINER_CSS = [
  'position: fixed',
  'bottom: 20px',
  'left: 50%',
  'transform: translateX(-50%)',
  'width: calc(100% - 48px)',
  'max-width: 960px',
  'background: rgba(17, 24, 39, 0.95)',
  'backdrop-filter: blur(16px)',
  '-webkit-backdrop-filter: blur(16px)',
  'border: 1px solid #374151',
  'border-radius: 12px',
  'box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7)',
  'padding: 12px 20px',
  'display: none',
  'flex-direction: column',
  'gap: 8px',
  'font-family: ui-sans-serif, system-ui, sans-serif',
  'color: #f3f4f6',
  'z-index: 550',
].join('; ') + ';';

/** Child-element stylesheet, injected once (house pattern: TrafficControlDeck). */
const DECK_CSS = `
#diff-media-deck .dmd-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
#diff-media-deck .dmd-title { font-size: 13px; font-weight: 700; letter-spacing: 0.06em; white-space: nowrap; }
#diff-media-deck .dmd-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; padding: 2px 8px; border-radius: 9999px; border: 1px solid currentColor; background: rgba(255, 255, 255, 0.04); white-space: nowrap; }
#diff-media-deck .dmd-close { margin-left: auto; background: transparent; border: none; color: #9ca3af; font-size: 16px; line-height: 1; cursor: pointer; padding: 4px 6px; transition: color 120ms ease; }
#diff-media-deck .dmd-close:hover { color: #f3f4f6; }
#diff-media-deck .dmd-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
#diff-media-deck .dmd-btn { background: #1f2937; border: 1px solid #374151; border-radius: 6px; color: #d1d5db; font-family: inherit; font-size: 11px; font-weight: 700; padding: 6px 12px; cursor: pointer; white-space: nowrap; transition: background 120ms ease, color 120ms ease, border-color 120ms ease, box-shadow 120ms ease; }
#diff-media-deck .dmd-btn:hover { background: #374151; color: #f9fafb; }
#diff-media-deck .dmd-btn.dmd-btn-active { border-color: #a855f7; color: #e9d5ff; box-shadow: 0 0 8px rgba(168, 85, 247, 0.35); }
#diff-media-deck .dmd-speed-sep { width: 1px; height: 18px; background: #374151; margin: 0 4px; flex: none; }
#diff-media-deck .diff-track-wrap { position: relative; height: 26px; cursor: pointer; user-select: none; touch-action: none; }
#diff-media-deck .dmd-track { position: absolute; left: 0; right: 0; top: 50%; transform: translateY(-50%); height: 6px; border-radius: 3px; background: #1f2937; border: 1px solid #374151; }
#diff-media-deck .dmd-progress { position: absolute; left: 0; top: 50%; transform: translateY(-50%); height: 6px; width: 0%; border-radius: 3px; background: #8b5cf6; pointer-events: none; transition: width 160ms ease; }
#diff-media-deck .dmd-pins { position: absolute; inset: 0; pointer-events: none; }
#diff-media-deck .dmd-pin { position: absolute; top: 50%; width: 10px; height: 10px; margin-left: -5px; transform: translateY(-50%); border-radius: 50%; border: 1px solid rgba(255, 255, 255, 0.6); box-sizing: border-box; pointer-events: auto; cursor: pointer; transition: box-shadow 120ms ease, border-color 120ms ease; }
#diff-media-deck .dmd-pin:hover { border-color: #ffffff; }
#diff-media-deck .dmd-pin.dmd-pin-active { border-color: #ffffff; box-shadow: 0 0 10px currentColor; }
#diff-media-deck .dmd-thumb { position: absolute; top: 50%; width: 14px; height: 14px; margin-left: -7px; transform: translateY(-50%); border-radius: 50%; background: #f3f4f6; border: 2px solid #a855f7; box-sizing: border-box; pointer-events: none; box-shadow: 0 0 8px rgba(168, 85, 247, 0.5); }
#diff-media-deck .dmd-banner { border: 1px solid #374151; border-radius: 8px; background: rgba(17, 24, 39, 0.85); padding: 8px 12px; font-size: 12px; line-height: 1.55; overflow: hidden; }
#diff-media-deck .dmd-banner-head { font-weight: 700; color: #f3f4f6; }
#diff-media-deck .dmd-kind { font-size: 10px; font-weight: 800; letter-spacing: 0.06em; }
#diff-media-deck .dmd-desc, #diff-media-deck .dmd-detail { color: #9ca3af; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#diff-media-deck .dmd-skew { color: #f59e0b; }
#diff-media-deck .dmd-latency { color: #c084fc; }
#diff-media-deck .dmd-empty { color: #6b7280; font-style: italic; }
`;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/** Percent along the 0–100% scrubber span for sequence index `index`. */
function positionPct(index: number, total: number): number {
  const span = total - 1;
  if (span <= 0) return 0;
  return (clamp(index, 0, span) / span) * 100;
}

/* ========================================================================== *
 * DiffMediaDeck
 * ========================================================================== */

export class DiffMediaDeck {
  private static cssInjected = false;

  private readonly engine: DiffSequenceEngine;
  private readonly container: HTMLElement;

  // Header row
  private readonly addedBadge: HTMLElement;
  private readonly deletedBadge: HTMLElement;
  private readonly modifiedBadge: HTMLElement;
  private readonly latencyBadge: HTMLElement;

  // Controls row
  private readonly playBtn: HTMLButtonElement;
  private readonly speedBtns: ReadonlyArray<{ btn: HTMLButtonElement; speed: number }>;

  // Scrubber row
  private readonly progressEl: HTMLElement;
  private readonly pinsEl: HTMLElement;
  private readonly thumbEl: HTMLElement;

  // Active-item banner
  private readonly bannerEl: HTMLElement;

  private visible = false;
  private dragging = false;
  /** Pin-count of the last render — pins rebuild only when the queue changes. */
  private renderedPinCount = -1;

  private readonly itemSelectCallbacks: Array<(item: DiffSequenceItem) => void> = [];
  private readonly unsubscribeStep: () => void;
  private readonly unsubscribeState: () => void;

  constructor(engine: DiffSequenceEngine) {
    this.engine = engine;
    DiffMediaDeck.injectCss();

    // --- Container ------------------------------------------------------------
    const container = document.createElement('div');
    container.id = 'diff-media-deck';
    container.style.cssText = CONTAINER_CSS;
    this.container = container;

    // --- Header row -------------------------------------------------------------
    const header = document.createElement('div');
    header.className = 'dmd-header';

    const title = document.createElement('span');
    title.className = 'dmd-title';
    title.textContent = '⚡ DIFF INSPECTION TOUR';
    header.appendChild(title);

    this.addedBadge = DiffMediaDeck.makeBadge('ADDED', DIFF_KIND_COLORS.added);
    this.deletedBadge = DiffMediaDeck.makeBadge('DELETED', DIFF_KIND_COLORS.deleted);
    this.modifiedBadge = DiffMediaDeck.makeBadge('MODIFIED', DIFF_KIND_COLORS.modified);
    this.latencyBadge = DiffMediaDeck.makeBadge('LATENCY', DIFF_KIND_COLORS.latency_delta);
    header.appendChild(this.addedBadge);
    header.appendChild(this.deletedBadge);
    header.appendChild(this.modifiedBadge);
    header.appendChild(this.latencyBadge);

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'dmd-close';
    closeBtn.textContent = '✕';
    closeBtn.title = 'Close diff inspection tour (Esc)';
    closeBtn.setAttribute('aria-label', 'Close diff inspection tour');
    closeBtn.addEventListener('click', () => this.close());
    header.appendChild(closeBtn);
    container.appendChild(header);

    // --- Controls row -----------------------------------------------------------
    const controls = document.createElement('div');
    controls.className = 'dmd-controls';

    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'dmd-btn';
    prevBtn.textContent = '⏮ PREV';
    prevBtn.title = 'Previous diff item (←)';
    prevBtn.addEventListener('click', () => engine.prev());
    controls.appendChild(prevBtn);

    const playBtn = document.createElement('button');
    playBtn.type = 'button';
    playBtn.className = 'dmd-btn';
    playBtn.textContent = '▶ PLAY';
    playBtn.title = 'Play / pause the tour (Space)';
    playBtn.addEventListener('click', () => engine.togglePlay());
    controls.appendChild(playBtn);
    this.playBtn = playBtn;

    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'dmd-btn';
    nextBtn.textContent = '⏭ NEXT';
    nextBtn.title = 'Next diff item (→)';
    nextBtn.addEventListener('click', () => engine.next());
    controls.appendChild(nextBtn);

    const sep = document.createElement('span');
    sep.className = 'dmd-speed-sep';
    controls.appendChild(sep);

    const speedBtns: Array<{ btn: HTMLButtonElement; speed: number }> = [];
    for (const speed of SPEED_OPTIONS) {
      const speedBtn = document.createElement('button');
      speedBtn.type = 'button';
      speedBtn.className = 'dmd-btn';
      speedBtn.textContent = `${speed}x`;
      speedBtn.title = `Playback speed ${speed}x`;
      speedBtn.addEventListener('click', () => engine.setSpeed(speed));
      controls.appendChild(speedBtn);
      speedBtns.push({ btn: speedBtn, speed });
    }
    this.speedBtns = speedBtns;
    container.appendChild(controls);

    // --- Scrubber row -------------------------------------------------------------
    const trackWrap = document.createElement('div');
    trackWrap.className = 'diff-track-wrap';
    trackWrap.setAttribute('role', 'group');
    trackWrap.setAttribute('aria-label', 'Diff sequence scrubber');

    const track = document.createElement('div');
    track.className = 'dmd-track';

    const progressEl = document.createElement('div');
    progressEl.className = 'dmd-progress';

    const pinsEl = document.createElement('div');
    pinsEl.className = 'dmd-pins';

    const thumbEl = document.createElement('div');
    thumbEl.className = 'dmd-thumb';

    trackWrap.appendChild(track);
    trackWrap.appendChild(progressEl);
    trackWrap.appendChild(pinsEl);
    trackWrap.appendChild(thumbEl);

    const seekFromClientX = (clientX: number): void => {
      const total = engine.getItemCount();
      if (total === 0) return;
      const rect = track.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
      const targetIndex = total === 1 ? 0 : Math.round(ratio * (total - 1));
      engine.seek(targetIndex);
    };

    trackWrap.addEventListener('mousedown', (e: MouseEvent) => {
      if (e.button !== 0) return; // left button only
      this.dragging = true;
      seekFromClientX(e.clientX);

      const handleMouseMove = (moveEvent: MouseEvent): void => {
        if (this.dragging) seekFromClientX(moveEvent.clientX);
      };
      const handleMouseUp = (): void => {
        this.dragging = false;
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    });

    this.progressEl = progressEl;
    this.pinsEl = pinsEl;
    this.thumbEl = thumbEl;
    container.appendChild(trackWrap);

    // --- Active-item banner --------------------------------------------------------
    const bannerEl = document.createElement('div');
    bannerEl.className = 'dmd-banner';
    this.bannerEl = bannerEl;
    container.appendChild(bannerEl);

    document.body.appendChild(container);

    // --- Engine subscriptions ---------------------------------------------------------
    // Engine event order: onStep fires first (banner + progress + pin paint),
    // onStateChange follows (counters / buttons / full scrubber refresh).
    this.unsubscribeStep = engine.onStep((item, state) => {
      this.render(state);
      for (const cb of [...this.itemSelectCallbacks]) cb(item);
    });
    this.unsubscribeState = engine.onStateChange((state) => this.render(state));

    window.addEventListener('keydown', this.handleKeyDown);

    // Initial paint from current engine state.
    this.render(engine.getState());
  }

  /* ------------------------------ construction ----------------------------- */

  private static injectCss(): void {
    if (DiffMediaDeck.cssInjected) return;
    DiffMediaDeck.cssInjected = true;
    const style = document.createElement('style');
    style.id = 'diff-media-deck-styles';
    style.textContent = DECK_CSS;
    document.head.appendChild(style);
  }

  private static makeBadge(label: string, color: string): HTMLElement {
    const badge = document.createElement('span');
    badge.className = 'dmd-badge';
    badge.style.color = color;
    badge.textContent = `${label} 0`;
    return badge;
  }

  /* --------------------------------- events ---------------------------------- */

  private readonly handleKeyDown = (e: KeyboardEvent): void => {
    if (!this.visible) return;

    // Ignore while typing in inputs / prompts (house convention, see main.ts).
    const target = e.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable)
    ) {
      return;
    }

    switch (e.code) {
      case 'Space':
        e.preventDefault();
        this.engine.togglePlay();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        this.engine.prev();
        break;
      case 'ArrowRight':
        e.preventDefault();
        this.engine.next();
        break;
      case 'Escape':
        this.close();
        break;
    }
  };

  /* -------------------------------- rendering --------------------------------- */

  private render(state: DiffSequenceState): void {
    const total = state.items.length;
    const currentIndex = state.currentIndex;

    // Counters ---------------------------------------------------------------
    let added = 0;
    let deleted = 0;
    let modified = 0;
    let latency = 0;
    for (const item of state.items) {
      switch (item.kind) {
        case 'added':
          added += 1;
          break;
        case 'deleted':
          deleted += 1;
          break;
        case 'modified':
          modified += 1;
          break;
        case 'latency_delta':
          latency += 1;
          break;
      }
    }
    this.addedBadge.textContent = `ADDED ${added}`;
    this.deletedBadge.textContent = `DELETED ${deleted}`;
    this.modifiedBadge.textContent = `MODIFIED ${modified}`;
    this.latencyBadge.textContent = `LATENCY ${latency}`;

    // Playback controls --------------------------------------------------------
    this.playBtn.textContent = state.isPlaying ? '⏸ PAUSE' : '▶ PLAY';
    for (const { btn, speed } of this.speedBtns) {
      btn.classList.toggle('dmd-btn-active', speed === state.speed);
    }

    // Progress fill + thumb ------------------------------------------------------
    const pct = positionPct(currentIndex, total);
    this.progressEl.style.width = `${pct.toFixed(2)}%`;
    this.thumbEl.style.left = `${pct.toFixed(2)}%`;
    this.thumbEl.style.visibility = currentIndex >= 0 && total > 0 ? 'visible' : 'hidden';

    // Pins (rebuild only when the queue size changes) -----------------------------
    if (this.renderedPinCount !== total) {
      this.buildPins(state.items);
    }
    const pins = this.pinsEl.children;
    for (let i = 0; i < pins.length; i++) {
      pins[i]?.classList.toggle('dmd-pin-active', i === currentIndex);
    }

    // Banner ------------------------------------------------------------------------
    this.renderBanner(state.items, currentIndex);
  }

  private buildPins(items: readonly DiffSequenceItem[]): void {
    this.pinsEl.innerHTML = '';
    this.renderedPinCount = items.length;

    items.forEach((item, index) => {
      const pin = document.createElement('div');
      pin.className = 'dmd-pin';
      pin.style.left = `${positionPct(index, items.length).toFixed(2)}%`;
      pin.style.backgroundColor = DIFF_KIND_COLORS[item.kind];
      pin.title = `#${index + 1} ${item.componentName} [${item.kind.toUpperCase()}]`;
      pin.addEventListener('click', (e: MouseEvent) => {
        e.stopPropagation();
        this.engine.seek(index);
      });
      this.pinsEl.appendChild(pin);
    });
  }

  private renderBanner(items: readonly DiffSequenceItem[], currentIndex: number): void {
    this.bannerEl.textContent = '';
    const total = items.length;
    const item = items[currentIndex];

    if (!item) {
      const empty = document.createElement('div');
      empty.className = 'dmd-empty';
      empty.textContent =
        total === 0
          ? 'No diff items in the current sequence.'
          : 'Press ▶ PLAY or click a scrubber pin to inspect a diff item.';
      this.bannerEl.appendChild(empty);
      return;
    }

    const head = document.createElement('div');
    head.className = 'dmd-banner-head';
    head.textContent = `Step ${currentIndex + 1}/${total}: ${item.componentName}`;
    const kindSpan = document.createElement('span');
    kindSpan.className = 'dmd-kind';
    kindSpan.style.color = DIFF_KIND_COLORS[item.kind];
    kindSpan.textContent = ` [${item.kind.toUpperCase()}]`;
    head.appendChild(kindSpan);
    this.bannerEl.appendChild(head);

    // Description + raw diff detail lines.
    if (item.description) {
      const desc = document.createElement('div');
      desc.className = 'dmd-desc';
      desc.textContent = item.description;
      this.bannerEl.appendChild(desc);
    }
    for (const detail of item.diffDetails) {
      const line = document.createElement('div');
      line.className = 'dmd-detail';
      line.textContent = detail;
      this.bannerEl.appendChild(line);
    }

    // Version skew: `alphaVersion ➔ betaVersion`.
    if (item.alphaVersion !== undefined || item.betaVersion !== undefined) {
      const skew = document.createElement('div');
      skew.className = 'dmd-skew';
      skew.textContent = `${item.alphaVersion ?? '?'} ➔ ${item.betaVersion ?? '?'}`;
      this.bannerEl.appendChild(skew);
    }

    // Latency skew: `[Δ ${latencyDeltaMs}ms]` (+ α/β readings when known).
    if (item.latencyDeltaMs !== undefined) {
      const sign = item.latencyDeltaMs >= 0 ? '+' : '';
      let text = `[Δ ${sign}${Math.round(item.latencyDeltaMs)}ms]`;
      if (item.alphaLatencyMs !== undefined && item.betaLatencyMs !== undefined) {
        text = `${Math.round(item.alphaLatencyMs)}ms ➔ ${Math.round(item.betaLatencyMs)}ms ${text}`;
      }
      const latencyLine = document.createElement('div');
      latencyLine.className = 'dmd-latency';
      latencyLine.textContent = text;
      this.bannerEl.appendChild(latencyLine);
    }
  }

  /* -------------------------------- public API --------------------------------- */

  /** Show the dock; auto-play when the queue has items, else arm at step 0. */
  open(): void {
    this.visible = true;
    this.container.style.display = 'flex';
    if (this.engine.getItemCount() > 0) {
      this.engine.play();
    } else {
      this.engine.start();
    }
    this.render(this.engine.getState());
  }

  /** Hide the dock and pause the tour. */
  close(): void {
    this.visible = false;
    this.container.style.display = 'none';
    this.engine.pause();
  }

  /** Show when hidden, hide when visible. */
  toggle(): void {
    if (this.isVisible()) {
      this.close();
    } else {
      this.open();
    }
  }

  /** True while the dock is on-screen. */
  isVisible(): boolean {
    return this.visible;
  }

  /**
   * Observe every item selection the deck sees through the engine step stream
   * (viewport highlight layer, camera tweening, …).
   */
  onItemSelect(cb: (item: DiffSequenceItem) => void): void {
    this.itemSelectCallbacks.push(cb);
  }

  /** Tear down listeners + DOM (page navigation / deck retirement). */
  dispose(): void {
    window.removeEventListener('keydown', this.handleKeyDown);
    this.unsubscribeStep();
    this.unsubscribeState();
    this.itemSelectCallbacks.length = 0;
    this.container.remove();
    document.getElementById('diff-media-deck-styles')?.remove();
    DiffMediaDeck.cssInjected = false;
  }
}
