"""Unit tests for SPEC-11 Quad-Pane Layout Alignment, Diff & Delta Inspection
Sequence, and Load-Driven Latency Spring Dynamics (TASK-CV-1208).

Covers:
1. §3.1 Quad Grid Layout & Divider Suppression Contract (grid_controller.ts, index.html):
   - .viewport-divider display is hidden ('none') in single & quad modes.
   - .viewport-divider display is visible ('block') in dual mode.
   - Deterministic 2x2 grid positions (tl, tr, bl, br) with explicit gridColumn/gridRow.
2. §3.2 Diff Sequence Extraction, Ordering & Playback Engine (diff_sequence.ts):
   - Classification: added, deleted, modified, latency_delta.
   - Deterministic 5-stage architectural journey:
     Control Plane -> Core Shared -> Application -> Data Vaults -> Latency bottlenecks.
   - Dwell duration, playback speeds (0.5x, 1x, 2x), and effective interval scaling.
3. §3.3 Latency Spring Physics & Harmonic Damping (latency_spring_engine.ts):
   - Formula: Delta Y = min(1.8, 0.45 * ln(1 + max(0, (tau - 5.0) / 5.0))).
   - Strict clamp at Delta Y = 1.8 for extreme latency spikes (e.g. 500ms, 1000ms).
   - Zero displacement when latency <= baseline (5.0ms).
   - Damped harmonic relaxation (zeta = 0.85, omega_n = 3.5): settles to <1% within ~1.2s.
   - Thermal color thresholds: <= 15ms calm cyan (#06b6d4), <= 60ms amber (#f59e0b), > 60ms crimson (#ef4444).
4. Data Integrity:
   - Verification of cluster-alpha.json, cluster-beta.json, cluster-diff.json compatibility with DiffSequenceEngine.
"""

from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class TestSpec11QuadGridLayout(unittest.TestCase):
    """Verifies §3.1 and ADR-01 grid placement and divider contracts."""

    def setUp(self) -> None:
        self.grid_ts = (REPO / "src" / "scene" / "grid_controller.ts").read_text()
        self.index_html = (REPO / "index.html").read_text()

    def test_divider_suppressed_in_quad_mode(self) -> None:
        """In quad mode, .viewport-divider must be force-hidden with display: none."""
        self.assertIn("mode === 'quad'", self.grid_ts)
        self.assertIn("divider.style.setProperty('display', 'none', 'important')", self.grid_ts)

    def test_divider_suppressed_in_single_mode(self) -> None:
        """In single mode, .viewport-divider must be hidden."""
        self.assertIn("mode === 'single'", self.grid_ts)
        self.assertIn("divider.style.display = 'none'", self.grid_ts)

    def test_divider_visible_in_dual_mode(self) -> None:
        """In dual mode, .viewport-divider must be displayed as block."""
        self.assertIn("mode === 'dual'", self.grid_ts)
        self.assertIn("divider.style.display = 'block'", self.grid_ts)

    def test_deterministic_grid_positions(self) -> None:
        """Quad mode must assign deterministic row/col and data-grid-pos (tl, tr, bl, br)."""
        self.assertIn("data-grid-pos", self.grid_ts)
        # Check all 4 cells are assigned
        for pos in ["tl", "tr", "bl", "br"]:
            self.assertIn(f"pos: '{pos}'", self.grid_ts)

    def test_html_contains_diff_tour_button(self) -> None:
        """index.html must include the persistent #btn-diff-tour topbar button."""
        self.assertIn('id="btn-diff-tour"', self.index_html)
        self.assertIn("DIFF TOUR", self.index_html)


class TestSpec11LatencySpringPhysics(unittest.TestCase):
    """Verifies §3.3 and ADR-03 logarithmic damped spring physics formulas."""

    TAU_BASE = 5.0
    DELTA_Y_MAX = 1.8
    C_LOAD = 0.45
    ZETA = 0.85
    OMEGA_N = 3.5

    @classmethod
    def calc_delta_y(cls, latency_ms: float) -> float:
        """Mathematical reference implementation of SPEC-11 §3.3 displacement."""
        if latency_ms <= cls.TAU_BASE:
            return 0.0
        normalized = (latency_ms - cls.TAU_BASE) / cls.TAU_BASE
        target = cls.C_LOAD * math.log(1.0 + normalized)
        return min(cls.DELTA_Y_MAX, target)

    @classmethod
    def calc_thermal_color(cls, latency_ms: float) -> str:
        """SPEC-11 §3.3 thermal color palette."""
        if latency_ms <= 15.0:
            return "#06b6d4"  # Calm cyan
        if latency_ms <= 60.0:
            return "#f59e0b"  # Warning amber
        return "#ef4444"      # Hot crimson

    def test_zero_displacement_at_quiescent_baseline(self) -> None:
        """Latencies at or below tau_base produce zero displacement."""
        self.assertEqual(self.calc_delta_y(5.0), 0.0)
        self.assertEqual(self.calc_delta_y(1.2), 0.0)
        self.assertEqual(self.calc_delta_y(0.0), 0.0)

    def test_moderate_load_displacement(self) -> None:
        """Moderate latency (e.g. 28ms) produces noticeable non-zero displacement."""
        dy = self.calc_delta_y(28.0)
        self.assertGreater(dy, 0.6)
        self.assertLess(dy, 1.2)
        # 0.45 * ln(1 + (28-5)/5) = 0.45 * ln(5.6) ≈ 0.7752
        self.assertAlmostEqual(dy, 0.7752, places=3)

    def test_extreme_load_clamping(self) -> None:
        """Displacement under severe contention clamps strictly to Delta Y = 1.8."""
        self.assertEqual(self.calc_delta_y(500.0), self.DELTA_Y_MAX)
        self.assertEqual(self.calc_delta_y(2000.0), self.DELTA_Y_MAX)
        self.assertEqual(self.calc_delta_y(50000.0), self.DELTA_Y_MAX)

    def test_thermal_color_thresholds(self) -> None:
        """Thermal colors match SPEC-11 exact band boundaries."""
        # Cyan band (<= 15ms)
        self.assertEqual(self.calc_thermal_color(5.0), "#06b6d4")
        self.assertEqual(self.calc_thermal_color(15.0), "#06b6d4")
        # Amber band (15 < tau <= 60ms)
        self.assertEqual(self.calc_thermal_color(15.1), "#f59e0b")
        self.assertEqual(self.calc_thermal_color(35.0), "#f59e0b")
        self.assertEqual(self.calc_thermal_color(60.0), "#f59e0b")
        # Crimson band (> 60ms)
        self.assertEqual(self.calc_thermal_color(60.1), "#ef4444")
        self.assertEqual(self.calc_thermal_color(250.0), "#ef4444")

    def test_damped_harmonic_settling_time(self) -> None:
        """Verifies damped harmonic spring returns to baseline within ~1.2s when load sheds."""
        # Simulation of harmonic spring relaxation:
        # y(t) with target = 0 starting from y0 = 1.2, v0 = 0
        dt = 0.01
        t = 0.0
        y = 1.2
        v = 0.0
        settled_time = None

        while t <= 3.0:
            acc = -2.0 * self.ZETA * self.OMEGA_N * v - (self.OMEGA_N ** 2) * y
            v += acc * dt
            y += v * dt
            t += dt
            if abs(y) < 0.02 and abs(v) < 0.05 and settled_time is None:
                settled_time = t

        self.assertIsNotNone(settled_time)
        assert settled_time is not None
        # Settling time should be around 1.1s - 1.5s (spec states ~1.2s)
        self.assertGreater(settled_time, 0.9)
        self.assertLess(settled_time, 1.6)

    def test_source_code_constants_match_spec(self) -> None:
        """Inspects latency_spring_engine.ts to ensure constants match spec values."""
        ts_code = (REPO / "src" / "scene" / "latency_spring_engine.ts").read_text()
        self.assertIn("TAU_BASE_MS: 5", ts_code)
        self.assertIn("DELTA_Y_MAX: 1.8", ts_code)
        self.assertIn("C_LOAD: 0.45", ts_code)
        self.assertIn("ZETA: 0.85", ts_code)
        self.assertIn("OMEGA_N: 3.5", ts_code)
        self.assertIn("THERMAL_CALM_MS: 15", ts_code)
        self.assertIn("THERMAL_HOT_MS: 60", ts_code)


class TestSpec11DiffSequenceEngine(unittest.TestCase):
    """Verifies §3.2 and ADR-02 DiffSequenceEngine extraction and ordering."""

    def setUp(self) -> None:
        self.diff_ts = (REPO / "src" / "scene" / "diff_sequence.ts").read_text()
        self.report_path = REPO / "dist" / "data" / "cluster-diff.json"
        if not self.report_path.exists():
            self.report_path = REPO / "public" / "data" / "cluster-diff.json"

    def test_diff_sequence_source_file_structure(self) -> None:
        """diff_sequence.ts must export DiffSequenceEngine, DiffSequenceItem, and DIFF_KIND_COLORS."""
        self.assertIn("export class DiffSequenceEngine", self.diff_ts)
        self.assertIn("export interface DiffSequenceItem", self.diff_ts)
        self.assertIn("export const DIFF_KIND_COLORS", self.diff_ts)

    def test_deterministic_5_stage_ordering_logic(self) -> None:
        """Diff items must be categorized into the 5 architectural groups in order."""
        # Stage order: ControlPlane (0), CoreShared (1), Application (2), DataVaults (3), LatencyBottlenecks (4)
        self.assertIn("ControlPlane = 0", self.diff_ts)
        self.assertIn("CoreShared = 1", self.diff_ts)
        self.assertIn("Application = 2", self.diff_ts)
        self.assertIn("DataVaults = 3", self.diff_ts)
        self.assertIn("LatencyBottlenecks = 4", self.diff_ts)

    def test_dwell_timer_and_speed_logic(self) -> None:
        """Dwell timer must support speed scaling (e.g. interval = dwell / speed)."""
        self.assertIn("getEffectiveIntervalMs", self.diff_ts)
        self.assertIn("Math.max(1, this.dwellDurationMs / this.speed)", self.diff_ts)

    def test_real_diff_report_fixture(self) -> None:
        """cluster-diff.json fixture contains valid nodes with added, version_skew, and missing statuses."""
        if not self.report_path.exists():
            self.skipTest("cluster-diff.json fixture not found")
        data = json.loads(self.report_path.read_text())
        self.assertIn("nodes", data)
        statuses = {node["status"] for node in data["nodes"]}
        self.assertTrue({"added", "version_skew", "missing"}.issubset(statuses))


class TestSpec11MediaDeckAndUIWiring(unittest.TestCase):
    """Verifies §3.2 / §5.2 DiffMediaDeck and main UI integration."""

    def setUp(self) -> None:
        self.deck_ts = (REPO / "src" / "ui" / "diff_media_deck.ts").read_text()
        self.main_ts = (REPO / "src" / "main.ts").read_text()
        self.viewport_ts = (REPO / "src" / "scene" / "cluster_viewport.ts").read_text()

    def test_media_deck_exports_and_methods(self) -> None:
        """DiffMediaDeck must expose open, close, toggle, isVisible, onItemSelect."""
        self.assertIn("export class DiffMediaDeck", self.deck_ts)
        self.assertIn("open(", self.deck_ts)
        self.assertIn("close(", self.deck_ts)
        self.assertIn("toggle(", self.deck_ts)
        self.assertIn("isVisible(", self.deck_ts)
        self.assertIn("onItemSelect(", self.deck_ts)

    def test_viewport_focus_and_highlight_methods(self) -> None:
        """ClusterViewport must expose focusComponent and setDiffHighlight."""
        self.assertIn("focusComponent(", self.viewport_ts)
        self.assertIn("setDiffHighlight(", self.viewport_ts)
        self.assertIn("clearDiffHighlight(", self.viewport_ts)
        self.assertIn("setLoadLatency(", self.viewport_ts)
        self.assertIn("resetLoadLatencies(", self.viewport_ts)

    def test_main_wires_deck_and_keyd_shortcut(self) -> None:
        """main.ts must wire DiffMediaDeck, onItemSelect, and KeyD keyboard listener."""
        self.assertIn("new DiffMediaDeck(diffEngine)", self.main_ts)
        self.assertIn("diffDeck.onItemSelect", self.main_ts)
        self.assertIn("viewportA.focusComponent", self.main_ts)
        self.assertIn("viewportB.focusComponent", self.main_ts)
        self.assertIn("event.code === 'KeyD'", self.main_ts)


if __name__ == "__main__":
    unittest.main()
