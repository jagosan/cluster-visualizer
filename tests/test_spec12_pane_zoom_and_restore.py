"""Unit tests for SPEC-12 Viewport Pane Zoom-In Focus and Previous View
Restoration (TASK-CV-1301 + TASK-CV-1302 + TASK-CV-1303 + TASK-CV-1304).

Covers:
1. §3.1 GridController Zoom & Focus State Machine (grid_controller.ts):
   - Dynamic slot targeting in single mode: the pane matching
     `slot.id === this.focusedSlotId` (via `find` with `?? this.slots[0]`
     fallback) gets `display: block` / `width: 100%` / `height: 100%` and the
     hardcoded `i === 0` targeting bug must be gone.
   - zoomSlot(): toggle guard, previousMode recording, isZoomed, setMode('single').
   - restorePreviousMode(): `previousMode ?? 'dual'` target, isZoomed reset,
     updateZoomButtons() refresh.
   - isZoomActive(): mode === 'single' && isZoomed.
   - setMode(): updateZoomButtons() invoked on every mode application; zoomed
     flag cleared when leaving single mode.
   - Keyboard: Escape restores previous mode while zoomed; KeyZ toggles zoom.
   - getActiveSlots(): single mode resolves the focused slot with fallback.
2. previousMode history resilience (reference state-machine simulation):
   - 'dual' and 'quad' are preserved accurately when zooming from either mode;
     manual single defaults restore to 'dual'; re-entrant zooms preserve the
     original previousMode.
3. §3.2 In-Pane Zoom Button DOM/SVG/CSS contracts (main.ts, index.html):
   - Magnifying glass SVG (circle + line) and return arrow SVG
     (polyline + path) markup.
   - `.viewport-zoom-btn` styling (absolute top-right, dark glass, hover glow).
   - Click handler toggle semantics wired in createSlot(...).
4. §3.3 Topbar & HUD synchronization:
   - Zoom buttons instantiated for all slots a, b, c, d.
   - #btn-grid-single / #btn-grid-dual / #btn-grid-quad present and kept in
     sync via onModeChange and onZoomChange callbacks.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _extract_block(source: str, opener: str, closers: tuple[str, ...]) -> str:
    """Extract a code block starting at `opener` up to the first of `closers`
    (or end of source). Brace counting keeps the block balanced-ish for
    contract string assertions."""
    start = source.find(opener)
    if start == -1:
        raise AssertionError(f"opener not found: {opener!r}")
    rest = source[start:]
    end = len(rest)
    for closer in closers:
        idx = rest.find(closer, len(opener))
        if idx != -1:
            end = min(end, idx)
    return rest[:end]


class GridControllerSim:
    """Python reference implementation of the SPEC-12 §3.1 state machine.

    Mirrors the exact contract asserted against grid_controller.ts so history
    resilience can be exercised behaviourally, not just textually.
    """

    def __init__(self, slots: tuple[str, ...] = ("a", "b", "c", "d"), mode: str = "dual") -> None:
        self.slots = list(slots)
        self.mode = mode
        self.focused_slot_id = "a"
        self.previous_mode: str | None = None
        self.is_zoomed = False
        self.resize_events: list[str] = []
        self.zoom_events: list[tuple[bool, str, str | None]] = []

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode != "single":
            self.is_zoomed = False
        for slot in self._active_slots():
            self.resize_events.append(slot)
        # updateZoomButtons() always runs on mode application.

    def is_zoom_active(self) -> bool:
        return self.mode == "single" and self.is_zoomed

    def _active_slots(self) -> list[str]:
        if self.mode == "single":
            return [self.focused_slot_id if self.focused_slot_id in self.slots else self.slots[0]]
        if self.mode == "dual":
            return self.slots[:2]
        return self.slots[:4]

    def zoom_slot(self, slot_id: str) -> None:
        # Toggle guard (SPEC-12 TASK-CV-1301).
        if self.is_zoom_active() and self.focused_slot_id == slot_id:
            self.restore_previous_mode()
            return
        self.previous_mode = (self.previous_mode or "dual") if self.mode == "single" else self.mode
        self.focused_slot_id = slot_id
        self.is_zoomed = True
        self.set_mode("single")
        self.zoom_events.append((True, self.focused_slot_id, self.previous_mode))

    def restore_previous_mode(self) -> None:
        target = self.previous_mode or "dual"
        self.is_zoomed = False
        self.set_mode(target)
        self.zoom_events.append((False, self.focused_slot_id, self.previous_mode))

    def press_key(self, key: str) -> None:
        if key in ("1", "2", "4"):
            self.set_mode({"1": "single", "2": "dual", "4": "quad"}[key])
        elif key == "Escape":
            if self.is_zoom_active():
                self.restore_previous_mode()
        elif key in ("z", "Z"):
            if self.is_zoom_active():
                self.restore_previous_mode()
            else:
                slot = self.focused_slot_id if self.focused_slot_id in self.slots else self.slots[0]
                self.zoom_slot(slot)


class TestSpec12GridControllerStateContracts(unittest.TestCase):
    """Verifies §3.1 GridController zoom/focus code contracts in source."""

    def setUp(self) -> None:
        self.grid_ts = (REPO / "src" / "scene" / "grid_controller.ts").read_text()

    # -- State tracking ----------------------------------------------------
    def test_state_properties_declared(self) -> None:
        self.assertIn("focusedSlotId: string = 'a'", self.grid_ts)
        self.assertIn("previousMode: GridMode | null = null", self.grid_ts)
        self.assertIn("isZoomed: boolean = false", self.grid_ts)

    def test_public_api_surface(self) -> None:
        for sig in (
            "public zoomSlot(slotId: string): void",
            "public restorePreviousMode(): void",
            "public isZoomActive(): boolean",
            "public getFocusedSlotId(): string",
            "public getPreviousMode(): GridMode | null",
        ):
            self.assertIn(sig, self.grid_ts, f"missing public API: {sig}")

    # -- Dynamic single-mode targeting (the `i === 0` bug fix) -------------
    def test_single_mode_targets_focused_slot_not_hardcoded_index(self) -> None:
        """applyGridStyles() single branch must target focusedSlotId, never a
        hardcoded `i === 0`."""
        apply = _extract_block(self.grid_ts, "private applyGridStyles()", ("private updateZoomButtons",))
        single = _extract_block(
            apply, "if (this.mode === 'single') {", ("} else if (this.mode === 'dual')",)
        )
        # Contract: resolution of the focused slot with fallback to first slot.
        self.assertIn("this.slots.find(s => s.id === this.focusedSlotId) ?? this.slots[0]", single)
        self.assertIn("if (slot === focusedSlot) {", single)
        # The legacy hardcoded targeting bug must be eradicated.
        self.assertNotIn("if (i === 0)", single)

    def test_focused_slot_gets_full_dimensions(self) -> None:
        apply = _extract_block(self.grid_ts, "private applyGridStyles()", ())
        single = _extract_block(
            apply, "if (this.mode === 'single') {", ("} else if (this.mode === 'dual')",)
        )
        self.assertIn("slot.container.style.display = 'block'", single)
        self.assertIn("slot.container.style.width = '100%'", single)
        self.assertIn("slot.container.style.height = '100%'", single)
        self.assertIn("slot.container.style.display = 'none'", single)
        # Wrapper goes block-level, divider suppressed.
        self.assertIn("this.wrapper.style.display = 'block'", single)
        self.assertIn("divider.style.display = 'none'", single)

    def test_get_active_slots_single_mode_resolves_focused(self) -> None:
        active_fn = _extract_block(
            self.grid_ts, "public getActiveSlots()", ("public setMode",)
        )
        self.assertIn("this.slots.find(s => s.id === this.focusedSlotId)", active_fn)
        self.assertIn("this.slots[0]", active_fn)
        self.assertIn("return [found]", active_fn)

    # -- zoomSlot ----------------------------------------------------------
    def test_zoom_slot_toggle_guard(self) -> None:
        """zoomSlot() must restore instead of re-entering when the same
        focused, zoomed pane is re-clicked."""
        zoom_fn = _extract_block(self.grid_ts, "public zoomSlot(slotId: string): void", ("public restorePreviousMode",))
        self.assertIn("if (this.isZoomActive() && this.focusedSlotId === slotId) {", zoom_fn)
        guard_at = zoom_fn.find("if (this.isZoomActive() && this.focusedSlotId === slotId) {")
        focus_at = zoom_fn.find("this.focusedSlotId = slotId;")
        self.assertLess(guard_at, focus_at, "toggle guard must precede state mutation")
        self.assertIn("this.restorePreviousMode();", zoom_fn[guard_at:focus_at])

    def test_zoom_slot_records_previous_and_enters_single(self) -> None:
        zoom_fn = _extract_block(self.grid_ts, "public zoomSlot(slotId: string): void", ("public restorePreviousMode",))
        self.assertIn(
            "this.previousMode = (this.mode === 'single') ? (this.previousMode ?? 'dual') : this.mode;",
            zoom_fn,
        )
        self.assertIn("this.focusedSlotId = slotId;", zoom_fn)
        self.assertIn("this.isZoomed = true;", zoom_fn)
        self.assertIn("this.setMode('single');", zoom_fn)
        self.assertIn("this.onZoomChangeCb?.(true, this.focusedSlotId, this.previousMode);", zoom_fn)

    # -- restorePreviousMode -----------------------------------------------
    def test_restore_previous_mode(self) -> None:
        fn = _extract_block(self.grid_ts, "public restorePreviousMode(): void", ("public isZoomActive",))
        self.assertIn("const target = this.previousMode ?? 'dual';", fn)
        self.assertIn("this.isZoomed = false;", fn)
        self.assertIn("this.setMode(target);", fn)
        self.assertIn("this.updateZoomButtons();", fn)
        self.assertIn("this.onZoomChangeCb?.(false, this.focusedSlotId, this.previousMode);", fn)

    # -- isZoomActive -------------------------------------------------------
    def test_is_zoom_active(self) -> None:
        fn = _extract_block(self.grid_ts, "public isZoomActive(): boolean", ("public getFocusedSlotId",))
        self.assertIn("return this.mode === 'single' && this.isZoomed;", fn)

    # -- setMode -------------------------------------------------------------
    def test_set_mode_updates_zoom_buttons_and_clears_zoom_flag(self) -> None:
        fn = _extract_block(self.grid_ts, "public setMode(mode: GridMode): void", ("public toggleCameraSync",))
        self.assertIn("this.updateZoomButtons();", fn)
        self.assertIn("if (mode !== 'single') {", fn)
        self.assertIn("this.isZoomed = false;", fn)
        self.assertIn("slot.viewport.onResize();", fn)
        self.assertIn("this.updateSkewMatrixHUD();", fn)
        self.assertIn("this.onModeChangeCb?.(mode);", fn)

    # -- Keyboard handling ----------------------------------------------------
    def test_escape_key_restores_previous_mode(self) -> None:
        keys = _extract_block(self.grid_ts, "private handleKeyDown(", ())
        self.assertIn("case 'Escape':", keys)
        esc = _extract_block(keys, "case 'Escape':", ("case 'z'",))
        self.assertIn("if (this.isZoomActive()) {", esc)
        self.assertIn("this.restorePreviousMode();", esc)

    def test_key_z_toggles_zoom(self) -> None:
        keys = _extract_block(self.grid_ts, "private handleKeyDown(", ())
        self.assertIn("case 'z':", keys)
        self.assertIn("case 'Z':", keys)
        zblock = _extract_block(keys, "case 'z':", ("default:",))
        self.assertIn("if (this.isZoomActive()) {", zblock)
        self.assertIn("this.restorePreviousMode();", zblock)
        self.assertIn("this.zoomSlot(slot.id);", zblock)

    def test_key_handler_ignores_input_fields(self) -> None:
        keys = _extract_block(self.grid_ts, "private handleKeyDown(", ())
        self.assertIn("event.target instanceof HTMLInputElement", keys)
        self.assertIn("event.target instanceof HTMLTextAreaElement", keys)
        self.assertIn("window.addEventListener('keydown'", self.grid_ts)


class TestSpec12PreviousModeResilience(unittest.TestCase):
    """Behavioural simulation of the §3.1 contract: previousMode must
    preserve 'dual' or 'quad' accurately when zooming from either mode."""

    def test_zoom_from_dual_restores_dual(self) -> None:
        g = GridControllerSim(mode="dual")
        g.zoom_slot("b")
        self.assertEqual(g.mode, "single")
        self.assertTrue(g.is_zoom_active())
        self.assertEqual(g.focused_slot_id, "b")
        self.assertEqual(g.previous_mode, "dual")
        g.restore_previous_mode()
        self.assertEqual(g.mode, "dual")
        self.assertFalse(g.is_zoomed)

    def test_zoom_from_quad_restores_quad(self) -> None:
        g = GridControllerSim(mode="quad")
        g.zoom_slot("d")
        self.assertEqual(g.mode, "single")
        self.assertEqual(g.previous_mode, "quad")
        self.assertEqual(g.focused_slot_id, "d")
        g.press_key("Escape")
        self.assertEqual(g.mode, "quad")
        self.assertFalse(g.is_zoom_active())

    def test_manual_single_restores_dual_default(self) -> None:
        g = GridControllerSim(mode="quad")
        g.press_key("1")  # manual single via topbar/key — not a zoom
        self.assertEqual(g.mode, "single")
        self.assertFalse(g.is_zoom_active())
        g.restore_previous_mode()  # previousMode null -> 'dual' default
        self.assertEqual(g.mode, "dual")

    def test_reentrant_zoom_preserves_original_previous_mode(self) -> None:
        g = GridControllerSim(mode="quad")
        g.zoom_slot("c")
        g.zoom_slot("d")  # switch focus while zoomed
        self.assertEqual(g.previous_mode, "quad")
        self.assertEqual(g.focused_slot_id, "d")
        g.restore_previous_mode()
        self.assertEqual(g.mode, "quad")

    def test_toggle_guard_returns_instead_of_rezooming(self) -> None:
        g = GridControllerSim(mode="quad")
        g.zoom_slot("d")
        g.zoom_slot("d")  # same slot, zoomed -> toggles back
        self.assertEqual(g.mode, "quad")
        self.assertFalse(g.is_zoomed)
        # And zoom events recorded: zoom-in then restore.
        self.assertEqual([e[0] for e in g.zoom_events], [True, False])

    def test_switch_focus_while_zoomed_does_not_trigger_toggle(self) -> None:
        g = GridControllerSim(mode="dual")
        g.zoom_slot("a")
        g.zoom_slot("b")  # different slot -> retarget, stays zoomed
        self.assertTrue(g.is_zoom_active())
        self.assertEqual(g.focused_slot_id, "b")
        self.assertEqual(g.previous_mode, "dual")
        g.press_key("z")  # KeyZ toggle out
        self.assertEqual(g.mode, "dual")

    def test_escape_is_noop_when_not_zoomed(self) -> None:
        g = GridControllerSim(mode="quad")
        g.press_key("Escape")
        self.assertEqual(g.mode, "quad")
        self.assertEqual(g.zoom_events, [])

    def test_resize_triggered_on_active_slots(self) -> None:
        g = GridControllerSim(mode="dual")
        g.resize_events.clear()
        g.zoom_slot("b")
        self.assertIn("b", g.resize_events)  # focused slot resized on zoom
        g.resize_events.clear()
        g.restore_previous_mode()
        self.assertEqual(g.resize_events, ["a", "b"])  # both dual slots resized on restore

    def test_single_mode_active_slot_resolution_fallback(self) -> None:
        g = GridControllerSim(mode="single")
        g.focused_slot_id = "nonexistent"
        self.assertEqual(g._active_slots(), ["a"])  # fallback to first slot


class TestSpec12IconButtonContracts(unittest.TestCase):
    """Verifies §3.2 magnifying glass / return arrow SVG markup and the
    `.viewport-zoom-btn` CSS contract."""

    def setUp(self) -> None:
        self.grid_ts = (REPO / "src" / "scene" / "grid_controller.ts").read_text()
        self.main_ts = (REPO / "src" / "main.ts").read_text()
        self.index_html = (REPO / "index.html").read_text()

    def test_magnifying_glass_svg(self) -> None:
        """Zoom icon: circle + handle line (magnifying glass)."""
        for fragment in (
            '<svg class="icon-zoom"',
            '<circle cx="11" cy="11" r="8"></circle>',
            '<line x1="21" y1="21" x2="16.65" y2="16.65"></line>',
        ):
            self.assertIn(fragment, self.grid_ts, f"missing in grid_controller.ts: {fragment}")
            self.assertIn(fragment, self.main_ts, f"missing in main.ts: {fragment}")

    def test_return_arrow_svg(self) -> None:
        """Exit/return icon: polyline chevron + return path."""
        for fragment in (
            '<polyline points="9 14 4 9 9 4"></polyline>',
            '<path d="M20 20v-7a4 4 0 0 0-4-4H4"></path>',
        ):
            self.assertIn(fragment, self.grid_ts)

    def test_zoom_button_css_contract(self) -> None:
        css = _extract_block(self.index_html, ".viewport-zoom-btn {", ("}",))
        self.assertIn("position: absolute;", css)
        self.assertIn("z-index: 50;", css)
        self.assertIn("background: rgba(17, 24, 39, 0.85);", css)
        self.assertIn("border: 1px solid var(--border-subtle);", css)
        self.assertIn("cursor: pointer;", css)
        hover = _extract_block(self.index_html, ".viewport-zoom-btn:hover {", ("}",))
        self.assertIn("border-color: var(--accent-blue);", hover)

    def test_button_instantiated_with_class_in_main(self) -> None:
        self.assertIn("zoomBtn.className = 'viewport-zoom-btn'", self.main_ts)
        self.assertIn("zoomButton: zoomBtn", self.main_ts)

    def test_dynamic_button_titles(self) -> None:
        """Focused/zoomed pane shows 'Return to <mode> View (Exit Zoom)';
        all others show 'Maximize <title> (Zoom In)'."""
        self.assertIn("Return to ${this.previousMode ?? 'Dual'} View (Exit Zoom)", self.grid_ts)
        self.assertIn("Maximize ${slot.title} (Zoom In)", self.grid_ts)
        self.assertIn("Maximize ${title} (Zoom In)", self.main_ts)
        # Icon switch keyed on focused slot in single mode.
        self.assertIn("const isFocused = slot.id === this.focusedSlotId;", self.grid_ts)
        self.assertIn("const isSingleMode = this.mode === 'single';", self.grid_ts)

    def test_click_handler_toggle_semantics_in_main(self) -> None:
        """createSlot click listener must toggle: restore when the zoomed,
        focused pane's button is clicked; otherwise zoom the slot."""
        handler = _extract_block(
            self.main_ts,
            "zoomBtn.addEventListener('click', () => {",
            ("container.appendChild(zoomBtn);",),
        )
        self.assertIn(
            "if (gridController.isZoomActive() && gridController.getFocusedSlotId() === id) {",
            handler,
        )
        self.assertIn("gridController.restorePreviousMode();", handler)
        self.assertIn("gridController.zoomSlot(id);", handler)


class TestSpec12TopbarAndSlotSync(unittest.TestCase):
    """Verifies §3.3 topbar grid-pill synchronization and that zoom buttons
    are instantiated for all four slots (a, b, c, d)."""

    def setUp(self) -> None:
        self.main_ts = (REPO / "src" / "main.ts").read_text()
        self.index_html = (REPO / "index.html").read_text()

    def test_zoom_buttons_for_all_four_slots(self) -> None:
        for slot_id in ("a", "b", "c", "d"):
            self.assertIn(f"createSlot('{slot_id}'", self.main_ts)
            self.assertIn(f'id="viewport-{slot_id}"', self.index_html)
        # All four are pushed through createSlot which wires the zoom button.
        self.assertEqual(
            len(re.findall(r"slots\.push\(createSlot\(", self.main_ts)), 4
        )

    def test_topbar_grid_pills_exist(self) -> None:
        for btn_id in ("btn-grid-single", "btn-grid-dual", "btn-grid-quad"):
            self.assertIn(f'id="{btn_id}"', self.index_html)
            self.assertIn(f"getElementById('{btn_id}')", self.main_ts)

    def test_topbar_pill_click_wiring(self) -> None:
        self.assertIn("gridController.setMode('single')", self.main_ts)
        self.assertIn("gridController.setMode('dual')", self.main_ts)
        self.assertIn("gridController.setMode('quad')", self.main_ts)

    def test_on_mode_change_syncs_pills(self) -> None:
        cb = _extract_block(self.main_ts, "onModeChange: (mode: GridMode) => {", ("onZoomChange:",))
        self.assertIn("btnGridSingle?.classList.toggle('active', mode === 'single')", cb)
        self.assertIn("btnGridDual?.classList.toggle('active', mode === 'dual')", cb)
        self.assertIn("btnGridQuad?.classList.toggle('active', mode === 'quad')", cb)

    def test_on_zoom_change_syncs_pills(self) -> None:
        cb = _extract_block(self.main_ts, "onZoomChange: (isZoomed: boolean", ("},\n    slots",))
        self.assertIn("btnGridSingle?.classList.add('active')", cb)
        self.assertIn("btnGridDual?.classList.remove('active')", cb)
        self.assertIn("btnGridQuad?.classList.remove('active')", cb)
        # On restore, the previous mode's pill regains .active.
        self.assertIn("if (previousMode === 'dual') {", cb)
        self.assertIn("btnGridDual?.classList.add('active')", cb)
        self.assertIn("} else if (previousMode === 'quad') {", cb)
        self.assertIn("btnGridQuad?.classList.add('active')", cb)

    def test_grid_options_accept_zoom_callback(self) -> None:
        grid_ts = (REPO / "src" / "scene" / "grid_controller.ts").read_text()
        self.assertIn(
            "onZoomChange?: (isZoomed: boolean, focusedSlotId: string, previousMode: GridMode | null) => void;",
            grid_ts,
        )
        self.assertIn(
            "onZoomChange: (isZoomed: boolean, _focusedSlotId: string, previousMode: GridMode | null) => {",
            self.main_ts,
        )


class TestSpec12SourceIntegrity(unittest.TestCase):
    """Cross-file sanity: no leftover hardcoded single-mode index targeting
    anywhere in the grid controller's style application."""

    def setUp(self) -> None:
        self.grid_ts = (REPO / "src" / "scene" / "grid_controller.ts").read_text()

    def test_no_hardcoded_i_zero_anywhere_in_apply_grid_styles(self) -> None:
        apply = _extract_block(self.grid_ts, "private applyGridStyles()", ())
        self.assertNotIn("if (i === 0)", apply)

    def test_zoom_methods_defined_after_styles_block_and_bound(self) -> None:
        """zoomSlot/restore/isZoomActive/updateZoomButtons all exist as class
        members and updateZoomButtons is private."""
        for member in (
            "public zoomSlot(",
            "public restorePreviousMode(",
            "public isZoomActive(",
            "private updateZoomButtons(",
        ):
            self.assertIn(member, self.grid_ts)
        # updateZoomButtons is called from setMode, zoomSlot and restore.
        self.assertGreaterEqual(self.grid_ts.count("this.updateZoomButtons();"), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
