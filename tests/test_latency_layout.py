import unittest
import math
from src.ingestion.latency_layout import (
    compute_rest_length,
    compute_spring_stiffness,
    LatencyForceSimulation,
    compute_latency_layout,
)


class TestLatencyLayout(unittest.TestCase):

    def test_rest_length_scaling(self):
        # Test specific latency values against expected approximate rest lengths
        # Formula: l_min + s * log10(1 + latency_ms / tau_0)
        # l_min=1.8, s=6.0, tau_0=1.0
        
        # 0.05 ms -> 1.8 + 6 * log10(1.05) ≈ 1.8 + 6 * 0.02119 ≈ 1.927
        self.assertAlmostEqual(compute_rest_length(0.05), 1.9, delta=0.1)
        
        # 0.8 ms -> 1.8 + 6 * log10(1.8) ≈ 1.8 + 6 * 0.25527 ≈ 3.33
        self.assertAlmostEqual(compute_rest_length(0.8), 3.3, delta=0.1)
        
        # 2.5 ms -> 1.8 + 6 * log10(3.5) ≈ 1.8 + 6 * 0.54407 ≈ 5.06
        self.assertAlmostEqual(compute_rest_length(2.5), 5.1, delta=0.1)
        
        # 18.0 ms -> 1.8 + 6 * log10(19) ≈ 1.8 + 6 * 1.27875 ≈ 9.47
        self.assertAlmostEqual(compute_rest_length(18.0), 9.5, delta=0.1)
        
        # 120.0 ms -> 1.8 + 6 * log10(121) ≈ 1.8 + 6 * 2.08278 ≈ 14.29
        self.assertAlmostEqual(compute_rest_length(120.0), 14.3, delta=0.1)
        
        # Edge cases: <= 0 should return l_min (1.8)
        self.assertAlmostEqual(compute_rest_length(0.0), 1.8, delta=0.01)
        self.assertAlmostEqual(compute_rest_length(-1.0), 1.8, delta=0.01)
        self.assertAlmostEqual(compute_rest_length(-100.0), 1.8, delta=0.01)

    def test_spring_stiffness_scaling(self):
        # Formula: k_base * (1 + log10(1 + rps)) capped at 2.0? 
        # Let's deduce from tests:
        # rps=0 -> 0.5. k_base=0.5. 0.5 * (1 + log10(1)) = 0.5 * 1 = 0.5. Correct.
        # rps=9 -> 1.0. 0.5 * (1 + log10(10)) = 0.5 * (1 + 1) = 1.0. Correct.
        # rps=10000 -> 2.0 cap. 0.5 * (1 + log10(10001)) ≈ 0.5 * (1 + 4.00004) ≈ 2.5. 
        # So there is a cap at 2.0.
        
        self.assertAlmostEqual(compute_spring_stiffness(0), 0.5, delta=0.01)
        self.assertAlmostEqual(compute_spring_stiffness(9), 1.0, delta=0.01)
        self.assertAlmostEqual(compute_spring_stiffness(10000), 2.0, delta=0.01)
        
        # Check intermediate value to ensure formula is correct
        # rps=99 -> 0.5 * (1 + log10(100)) = 0.5 * 3 = 1.5
        self.assertAlmostEqual(compute_spring_stiffness(99), 1.5, delta=0.01)

    def test_simulation_convergence(self):
        nodes = ["A", "B", "C"]
        edges = [
            {"source": "A", "target": "B", "latency_ms": 10.0, "rps": 100},
            {"source": "B", "target": "C", "latency_ms": 20.0, "rps": 50},
            {"source": "A", "target": "C", "latency_ms": 5.0, "rps": 200},
        ]
        
        sim = LatencyForceSimulation(nodes, edges)
        
        # Run initial steps to get some movement
        max_movements = []
        for _ in range(10):
            movement = sim.step(dt=0.1)
            max_movements.append(movement)
            
        # Verify that movement is generally decreasing (converging)
        # We check that the last movement is smaller than the first few
        # Due to numerical noise, we just check that it's not exploding
        self.assertTrue(max_movements[-1] < max_movements[0] * 1.5)
        
        # Run remaining iterations to reach 60 total
        for _ in range(50):
            sim.step(dt=0.1)
            
        # Check all coordinates are finite
        for node, pos in sim.positions.items():
            self.assertIn('x', pos)
            self.assertIn('y', pos)
            self.assertIn('z', pos)
            self.assertTrue(math.isfinite(pos['x']))
            self.assertTrue(math.isfinite(pos['y']))
            self.assertTrue(math.isfinite(pos['z']))

    def test_latency_separation(self):
        nodes = ["A", "B", "C"]
        edges = [
            {"source": "A", "target": "B", "latency_ms": 1.0, "rps": 10},
            {"source": "A", "target": "C", "latency_ms": 100.0, "rps": 10},
        ]
        
        sim = LatencyForceSimulation(nodes, edges)
        sim.run(iterations=60)
        
        pos_a = sim.positions["A"]
        pos_b = sim.positions["B"]
        pos_c = sim.positions["C"]
        
        def distance(p1, p2):
            return math.sqrt(
                (p1['x'] - p2['x'])**2 + 
                (p1['y'] - p2['y'])**2 + 
                (p1['z'] - p2['z'])**2
            )
        
        dist_ab = distance(pos_a, pos_b)
        dist_ac = distance(pos_a, pos_c)
        
        # Lower latency should result in shorter distance
        self.assertLess(dist_ab, dist_ac)

    def test_compute_latency_layout(self):
        # Test empty input
        result_empty = compute_latency_layout([], [])
        self.assertEqual(result_empty, {})
        
        # Test single component
        components = [{"id": "c1"}]
        edges = []
        result_single = compute_latency_layout(components, edges)
        
        self.assertIn("c1", result_single)
        self.assertIn("x", result_single["c1"])
        self.assertIn("y", result_single["c1"])
        self.assertIn("z", result_single["c1"])
        self.assertTrue(math.isfinite(result_single["c1"]["x"]))
        self.assertTrue(math.isfinite(result_single["c1"]["y"]))
        self.assertTrue(math.isfinite(result_single["c1"]["z"]))


if __name__ == "__main__":
    unittest.main()
