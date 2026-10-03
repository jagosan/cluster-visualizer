"""
Latency-based force-directed layout module.

Implements SPEC-07 §3.1: Latency Layout using spring-mass relaxation
with rest lengths derived from network latency and stiffness from RPS.
"""

import math
import random
from typing import Any, Dict, List, Optional


# Constants from SPEC-07
L_MIN = 1.8
S = 6.0
TAU_0 = 1.0
K_BASE = 0.5
DAMPING = 0.85
K_REP = 100.0  # Repulsive force constant
EPSILON = 1e-9  # Small value to avoid division by zero
MAX_ITERATIONS_DEFAULT = 60
DT_DEFAULT = 0.1


def compute_rest_length(latency_ms: float, l_min: float = L_MIN, s: float = S, tau_0: float = TAU_0) -> float:
    """
    Compute the rest length for a spring based on latency.
    
    L_0(u, v) = L_min + S * log10(1 + latency_ms / tau_0)
    
    Args:
        latency_ms: Latency in milliseconds.
        l_min: Minimum rest length.
        s: Scaling factor.
        tau_0: Time constant in ms.
    
    Returns:
        Rest length as a float.
    """
    if latency_ms < 0:
        latency_ms = 0.0
    if tau_0 <= 0:
        tau_0 = TAU_0
    if s < 0:
        s = S
    if l_min < 0:
        l_min = L_MIN
    
    # Guard against overflow in log10
    ratio = latency_ms / tau_0
    if ratio > 1e15:
        ratio = 1e15
    
    log_term = math.log10(1.0 + ratio)
    rest_length = l_min + s * log_term
    
    # Ensure rest length is positive and finite
    if not math.isfinite(rest_length) or rest_length <= 0:
        rest_length = l_min
    
    return rest_length


def compute_spring_stiffness(rps: float, k_base: float = K_BASE) -> float:
    """
    Compute the spring stiffness based on requests per second.
    
    K(u, v) = K_base * min(4.0, 1.0 + log10(1 + RPS(u, v)))
    
    Args:
        rps: Requests per second.
        k_base: Base stiffness constant.
    
    Returns:
        Spring stiffness as a float.
    """
    if rps < 0:
        rps = 0.0
    if k_base < 0:
        k_base = K_BASE
    
    # Guard against overflow in log10
    if rps > 1e15:
        rps = 1e15
    
    log_term = math.log10(1.0 + rps)
    stiffness = k_base * min(4.0, 1.0 + log_term)
    
    # Ensure stiffness is positive and finite
    if not math.isfinite(stiffness) or stiffness <= 0:
        stiffness = k_base
    
    return stiffness


class LatencyForceSimulation:
    """
    Force-directed layout simulation using latency-derived rest lengths
    and RPS-derived spring stiffness.
    """
    
    def __init__(
        self,
        nodes: List[str],
        edges: List[Dict[str, Any]],
        initial_positions: Optional[Dict[str, Dict[str, float]]] = None
    ):
        """
        Initialize the simulation.
        
        Args:
            nodes: List of node identifiers.
            edges: List of edge dictionaries with keys:
                   - 'source': source node id
                   - 'target': target node id
                   - 'latency_ms': latency in milliseconds (optional, default 0)
                   - 'rps': requests per second (optional, default 0)
            initial_positions: Optional initial positions for nodes.
        """
        self.nodes = list(nodes)
        self.edges = edges
        
        # Build adjacency and edge data structures
        self.node_set = set(self.nodes)
        self.edge_list = []
        self.adjacency = {node: [] for node in self.nodes}
        
        for edge in edges:
            src = edge.get('source')
            tgt = edge.get('target')
            if src not in self.node_set or tgt not in self.node_set:
                continue
            if src == tgt:
                continue
            
            latency_ms = edge.get('latency_ms', 0.0)
            rps = edge.get('rps', 0.0)
            
            # Ensure numeric types
            try:
                latency_ms = float(latency_ms)
            except (TypeError, ValueError):
                latency_ms = 0.0
            try:
                rps = float(rps)
            except (TypeError, ValueError):
                rps = 0.0
            
            if latency_ms < 0:
                latency_ms = 0.0
            if rps < 0:
                rps = 0.0
            
            rest_length = compute_rest_length(latency_ms)
            stiffness = compute_spring_stiffness(rps)
            
            self.edge_list.append({
                'source': src,
                'target': tgt,
                'rest_length': rest_length,
                'stiffness': stiffness
            })
            self.adjacency[src].append(tgt)
            self.adjacency[tgt].append(src)
        
        # Initialize positions
        self.positions = {}
        if initial_positions:
            for node in self.nodes:
                if node in initial_positions:
                    pos = initial_positions[node]
                    x = float(pos.get('x', 0.0))
                    y = float(pos.get('y', 0.0))
                    z = float(pos.get('z', 0.0))
                    # Sanitize
                    if not math.isfinite(x):
                        x = 0.0
                    if not math.isfinite(y):
                        y = 0.0
                    if not math.isfinite(z):
                        z = 0.0
                    self.positions[node] = {'x': x, 'y': y, 'z': z}
                else:
                    # Random initial position in a small sphere
                    self.positions[node] = self._random_position()
        else:
            for node in self.nodes:
                self.positions[node] = self._random_position()
        
        # Velocities
        self.velocities = {node: {'x': 0.0, 'y': 0.0, 'z': 0.0} for node in self.nodes}
        
        # Damping
        self.damping = DAMPING
    
    def _random_position(self) -> Dict[str, float]:
        """Generate a random position in a unit sphere."""
        # Use spherical coordinates for uniform distribution in sphere
        u = random.random()
        v = random.random()
        theta = 2.0 * math.pi * u
        phi = math.acos(2.0 * v - 1.0)
        r = random.random() ** (1.0 / 3.0)  # Uniform in volume
        
        x = r * math.sin(phi) * math.cos(theta)
        y = r * math.sin(phi) * math.sin(theta)
        z = r * math.cos(phi)
        
        return {'x': x, 'y': y, 'z': z}
    
    def _compute_repulsive_forces(self) -> Dict[str, Dict[str, float]]:
        """Compute repulsive forces between all pairs of nodes."""
        forces = {node: {'x': 0.0, 'y': 0.0, 'z': 0.0} for node in self.nodes}
        n = len(self.nodes)
        
        for i in range(n):
            node_i = self.nodes[i]
            pos_i = self.positions[node_i]
            for j in range(i + 1, n):
                node_j = self.nodes[j]
                pos_j = self.positions[node_j]
                
                dx = pos_i['x'] - pos_j['x']
                dy = pos_i['y'] - pos_j['y']
                dz = pos_i['z'] - pos_j['z']
                
                dist_sq = dx * dx + dy * dy + dz * dz + EPSILON
                dist = math.sqrt(dist_sq)
                
                # Repulsive force magnitude: k_rep / (d^2 + epsilon)
                force_mag = K_REP / dist_sq
                
                # Direction: away from each other
                if dist > EPSILON:
                    fx = force_mag * (dx / dist)
                    fy = force_mag * (dy / dist)
                    fz = force_mag * (dz / dist)
                else:
                    fx = fy = fz = 0.0
                
                forces[node_i]['x'] += fx
                forces[node_i]['y'] += fy
                forces[node_i]['z'] += fz
                forces[node_j]['x'] -= fx
                forces[node_j]['y'] -= fy
                forces[node_j]['z'] -= fz
        
        return forces
    
    def _compute_attractive_forces(self) -> Dict[str, Dict[str, float]]:
        """Compute attractive spring forces along edges."""
        forces = {node: {'x': 0.0, 'y': 0.0, 'z': 0.0} for node in self.nodes}
        
        for edge in self.edge_list:
            src = edge['source']
            tgt = edge['target']
            rest_length = edge['rest_length']
            stiffness = edge['stiffness']
            
            pos_src = self.positions[src]
            pos_tgt = self.positions[tgt]
            
            dx = pos_tgt['x'] - pos_src['x']
            dy = pos_tgt['y'] - pos_src['y']
            dz = pos_tgt['z'] - pos_src['z']
            
            dist_sq = dx * dx + dy * dy + dz * dz + EPSILON
            dist = math.sqrt(dist_sq)
            
            # Hooke's law: F = K * (d - L_0)
            displacement = dist - rest_length
            force_mag = stiffness * displacement
            
            # Direction: toward each other
            if dist > EPSILON:
                fx = force_mag * (dx / dist)
                fy = force_mag * (dy / dist)
                fz = force_mag * (dz / dist)
            else:
                fx = fy = fz = 0.0
            
            forces[src]['x'] += fx
            forces[src]['y'] += fy
            forces[src]['z'] += fz
            forces[tgt]['x'] -= fx
            forces[tgt]['y'] -= fy
            forces[tgt]['z'] -= fz
        
        return forces
    
    def step(self, dt: float = DT_DEFAULT) -> float:
        """
        Perform one simulation step.
        
        Args:
            dt: Time step.
        
        Returns:
            Maximum movement of any node during this step.
        """
        if dt <= 0:
            dt = DT_DEFAULT
        
        # Compute forces
        repulsive = self._compute_repulsive_forces()
        attractive = self._compute_attractive_forces()
        
        max_movement = 0.0
        
        for node in self.nodes:
            # Total force
            fx = repulsive[node]['x'] + attractive[node]['x']
            fy = repulsive[node]['y'] + attractive[node]['y']
            fz = repulsive[node]['z'] + attractive[node]['z']
            
            # Update velocity with damping
            self.velocities[node]['x'] = (self.velocities[node]['x'] + fx * dt) * self.damping
            self.velocities[node]['y'] = (self.velocities[node]['y'] + fy * dt) * self.damping
            self.velocities[node]['z'] = (self.velocities[node]['z'] + fz * dt) * self.damping
            
            # Sanitize velocities
            if not math.isfinite(self.velocities[node]['x']):
                self.velocities[node]['x'] = 0.0
            if not math.isfinite(self.velocities[node]['y']):
                self.velocities[node]['y'] = 0.0
            if not math.isfinite(self.velocities[node]['z']):
                self.velocities[node]['z'] = 0.0
            
            # Update position
            old_x = self.positions[node]['x']
            old_y = self.positions[node]['y']
            old_z = self.positions[node]['z']
            
            self.positions[node]['x'] += self.velocities[node]['x'] * dt
            self.positions[node]['y'] += self.velocities[node]['y'] * dt
            self.positions[node]['z'] += self.velocities[node]['z'] * dt
            
            # Sanitize positions
            if not math.isfinite(self.positions[node]['x']):
                self.positions[node]['x'] = old_x
                self.velocities[node]['x'] = 0.0
            if not math.isfinite(self.positions[node]['y']):
                self.positions[node]['y'] = old_y
                self.velocities[node]['y'] = 0.0
            if not math.isfinite(self.positions[node]['z']):
                self.positions[node]['z'] = old_z
                self.velocities[node]['z'] = 0.0
            
            # Track max movement
            dx = self.positions[node]['x'] - old_x
            dy = self.positions[node]['y'] - old_y
            dz = self.positions[node]['z'] - old_z
            movement = math.sqrt(dx * dx + dy * dy + dz * dz)
            if movement > max_movement:
                max_movement = movement
        
        return max_movement
    
    def run(self, iterations: int = MAX_ITERATIONS_DEFAULT) -> Dict[str, Dict[str, float]]:
        """
        Run the simulation for a given number of iterations.
        
        Args:
            iterations: Number of iterations to run.
        
        Returns:
            Dictionary mapping node IDs to their final positions.
        """
        if iterations <= 0:
            iterations = MAX_ITERATIONS_DEFAULT
        
        for _ in range(iterations):
            self.step()
        
        # Return a copy of positions
        result = {}
        for node in self.nodes:
            pos = self.positions[node]
            result[node] = {
                'x': pos['x'],
                'y': pos['y'],
                'z': pos['z']
            }
        
        return result


def compute_latency_layout(
    components: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    iterations: int = MAX_ITERATIONS_DEFAULT
) -> Dict[str, Dict[str, float]]:
    """
    Compute latency-based force-directed layout for components.
    
    Args:
        components: List of component dictionaries. Each should have an 'id' key.
        edges: List of edge dictionaries with keys:
               - 'source': source component id
               - 'target': target component id
               - 'latency_ms': latency in milliseconds (optional)
               - 'rps': requests per second (optional)
        iterations: Number of relaxation iterations.
    
    Returns:
        Dictionary mapping component IDs to their positions:
        {component_id: {"x": float, "y": float, "z": float}}
    """
    # Extract node IDs from components
    node_ids = []
    for comp in components:
        if isinstance(comp, dict) and 'id' in comp:
            node_ids.append(comp['id'])
        elif isinstance(comp, str):
            node_ids.append(comp)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_nodes = []
    for nid in node_ids:
        if nid not in seen:
            seen.add(nid)
            unique_nodes.append(nid)
    
    if not unique_nodes:
        return {}
    
    # Create simulation
    sim = LatencyForceSimulation(
        nodes=unique_nodes,
        edges=edges,
        initial_positions=None
    )
    
    # Run simulation
    positions = sim.run(iterations=iterations)
    
    return positions
