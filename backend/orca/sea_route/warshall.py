"""Floyd–Warshall pathfinder on the sea-route navigability grid.

The India bbox is a hard threshold (cells outside it do not exist). Land,
the land standoff, and blocking restricted areas are already False in
`grid.navigable` — those edges are infinite cost, not negative.

A full-grid Warshall is O(N³) on ~150k cells, so this samples a corridor
around start/end (or across the southern peninsula when sailing between
the Arabian Sea and the Bay of Bengal). Nodes are connected with line-of-sight
navigable chords, and Floyd–Warshall finds the optimal shortest path.
"""
from __future__ import annotations

import math

import numpy as np

from orca.sea_route.grid import SeaGrid

_R_NM = 3440.065
_INF = 1.0e12
_MAX_FW_AXIS = 26
_PAD_DEG = 4.0


def _haversine_nm(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return 2 * _R_NM * math.asin(math.sqrt(max(0.0, a)))


def path_distance_nm(path: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        total += _haversine_nm(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
    return total


def _chord_navigable(r0: int, c0: int, r1: int, c1: int, grid: SeaGrid) -> bool:
    steps = max(abs(r1 - r0), abs(c1 - c0), 1)
    for t in range(1, steps):
        r = r0 + round((r1 - r0) * t / steps)
        c = c0 + round((c1 - c0) * t / steps)
        if not grid.navigable[r, c]:
            return False
    return True


def _blocked_proximity_penalty(row: int, col: int, grid: SeaGrid) -> float:
    """Avoidance penalty pushing the route away from land and boundary thresholds.
    Implements repulsion weight so the route stays in open sea:
    - 1-cell distance from land/threshold: +25.0 nm penalty
    - 2-cell distance from land/threshold: +10.0 nm penalty
    - Open water: 0.0 penalty
    """
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = row + dr, col + dc
            if not (0 <= r < grid.nrows and 0 <= c < grid.ncols) or not grid.navigable[r, c]:
                return 25.0
    for dr in (-2, -1, 0, 1, 2):
        for dc in (-2, -1, 0, 1, 2):
            if abs(dr) <= 1 and abs(dc) <= 1:
                continue
            r, c = row + dr, col + dc
            if not (0 <= r < grid.nrows and 0 <= c < grid.ncols) or not grid.navigable[r, c]:
                return 10.0
    return 0.0


def _near_blocked(row: int, col: int, grid: SeaGrid) -> bool:
    return _blocked_proximity_penalty(row, col, grid) > 0.0


def _dense_warshall(dist: np.ndarray) -> np.ndarray:
    n = dist.shape[0]
    nxt = np.full((n, n), -1, dtype=np.int32)
    finite = dist < _INF / 2
    ii, jj = np.where(finite)
    nxt[ii, jj] = jj
    for i in range(n):
        nxt[i, i] = i
        dist[i, i] = 0.0
    for k in range(n):
        via = dist[:, k, None] + dist[k, None, :]
        better = via < dist
        dist[better] = via[better]
        src = np.broadcast_to(nxt[:, k, None], (n, n))
        nxt[better] = src[better]
    return nxt


def _reconstruct(nxt: np.ndarray, src: int, dst: int) -> list[int] | None:
    if src == dst:
        return [src]
    if nxt[src, dst] < 0:
        return None
    path = [src]
    cur = src
    n = nxt.shape[0]
    for _ in range(n + 1):
        cur = int(nxt[cur, dst])
        if cur < 0:
            return None
        path.append(cur)
        if cur == dst:
            return path
    return None


def warshall_route(
    start_row: int, start_col: int,
    end_row: int, end_col: int,
    grid: SeaGrid,
) -> list[tuple[int, int]] | None:
    """Floyd–Warshall on a land-checked corridor of the navigability grid."""
    if not grid.navigable[start_row, start_col] or not grid.navigable[end_row, end_col]:
        return None
    if (start_row, start_col) == (end_row, end_col):
        return [(start_row, start_col)]

    s_cell = (start_row, start_col)
    e_cell = (end_row, end_col)

    s_lat, s_lng = grid.cell_to_latlon(start_row, start_col)
    e_lat, e_lng = grid.cell_to_latlon(end_row, end_col)

    pad_cells = max(int(_PAD_DEG / grid.cell_deg), 8)

    # Detect if crossing peninsula between Arabian Sea and Bay of Bengal,
    # or if direct chord crosses land: in both cases the southern passage around
    # Kanyakumari / Sri Lanka (grid row -> nrows - 1) must be included.
    peninsula_crossing = (s_lng < 78.0 and e_lng > 78.0) or (e_lng < 78.0 and s_lng > 78.0)
    chord_crosses_blocked = not _chord_navigable(start_row, start_col, end_row, end_col, grid)

    r_min = min(start_row, end_row)
    r_max = max(start_row, end_row)
    c_min = min(start_col, end_col)
    c_max = max(start_col, end_col)

    if peninsula_crossing or (chord_crosses_blocked and min(s_lat, e_lat) > 8.0):
        r0 = max(0, r_min - pad_cells)
        r1 = grid.nrows - 1
        c_south_w = int((74.0 - grid.lng_min) / grid.cell_deg)
        c_south_e = int((82.0 - grid.lng_min) / grid.cell_deg)
        c0 = max(0, min(c_min, c_south_w) - pad_cells)
        c1 = min(grid.ncols - 1, max(c_max, c_south_e) + pad_cells)
    else:
        r0 = max(0, r_min - pad_cells)
        r1 = min(grid.nrows - 1, r_max + pad_cells)
        c0 = max(0, c_min - pad_cells)
        c1 = min(grid.ncols - 1, c_max + pad_cells)

    stride_r = max(1, math.ceil((r1 - r0 + 1) / _MAX_FW_AXIS))
    stride_c = max(1, math.ceil((c1 - c0 + 1) / _MAX_FW_AXIS))

    base_rows = list(range(r0, r1 + 1, stride_r))
    base_cols = list(range(c0, c1 + 1, stride_c))

    grid_nodes = [(r, c) for r in base_rows for c in base_cols if grid.navigable[r, c]]
    all_nodes = [s_cell] + [n for n in grid_nodes if n != s_cell and n != e_cell]
    if e_cell != s_cell and e_cell not in all_nodes:
        all_nodes.append(e_cell)

    n = len(all_nodes)
    if n < 2:
        return None

    coords = [grid.cell_to_latlon(r, c) for r, c in all_nodes]
    s_idx = 0
    e_idx = all_nodes.index(e_cell)

    dist = np.full((n, n), _INF, dtype=np.float64)
    np.fill_diagonal(dist, 0.0)

    max_dlat = stride_r * grid.cell_deg * 1.55
    max_dlng = stride_c * grid.cell_deg * 1.55
    max_dist_nm = max(max_dlat, max_dlng) * 60.0 * 1.45

    for i in range(n):
        r1_c, c1_c = all_nodes[i]
        lat1, lng1 = coords[i]
        p1 = _blocked_proximity_penalty(r1_c, c1_c, grid)
        for j in range(i + 1, n):
            r2_c, c2_c = all_nodes[j]
            lat2, lng2 = coords[j]
            if abs(lat1 - lat2) > max_dlat or abs(lng1 - lng2) > max_dlng:
                continue
            d = _haversine_nm(lat1, lng1, lat2, lng2)
            if d > max_dist_nm:
                continue
            if not _chord_navigable(r1_c, c1_c, r2_c, c2_c, grid):
                continue
            p2 = _blocked_proximity_penalty(r2_c, c2_c, grid)
            w = d + max(p1, p2)
            dist[i, j] = w
            dist[j, i] = w

    # Ensure start and end connect to nearby navigable lattice nodes
    for target_idx in (s_idx, e_idx):
        if np.sum(dist[target_idx] < _INF / 2) <= 1:
            lat_t, lng_t = coords[target_idx]
            r_t, c_t = all_nodes[target_idx]
            p_t = _blocked_proximity_penalty(r_t, c_t, grid)
            dists = [(_haversine_nm(lat_t, lng_t, coords[k][0], coords[k][1]), k) for k in range(n) if k != target_idx]
            dists.sort()
            conn = 0
            for d_k, k in dists:
                if d_k > 200.0 or conn >= 4:
                    break
                r_k, c_k = all_nodes[k]
                if _chord_navigable(r_t, c_t, r_k, c_k, grid):
                    p_k = _blocked_proximity_penalty(r_k, c_k, grid)
                    w = d_k + max(p_t, p_k)
                    dist[target_idx, k] = w
                    dist[k, target_idx] = w
                    conn += 1

    nxt = _dense_warshall(dist)
    if dist[s_idx, e_idx] >= _INF / 2:
        return _astar_route(start_row, start_col, end_row, end_col, grid)
    path_idx = _reconstruct(nxt, s_idx, e_idx)
    if path_idx is None:
        return _astar_route(start_row, start_col, end_row, end_col, grid)
    return [all_nodes[i] for i in path_idx]


def _astar_route(
    start_row: int, start_col: int,
    end_row: int, end_col: int,
    grid: SeaGrid,
) -> list[tuple[int, int]] | None:
    """A* pathfinder on the full-resolution sea navigability grid.

    Used when the coarse-lattice Floyd–Warshall is partitioned by narrow
    inlets, bays, or complex gulfs (e.g. Gulf of Kutch, Gulf of Khambhat, Palk Strait).
    """
    import heapq

    if not grid.navigable[start_row, start_col] or not grid.navigable[end_row, end_col]:
        return None
    if (start_row, start_col) == (end_row, end_col):
        return [(start_row, start_col)]

    end_lat, end_lng = grid.cell_to_latlon(end_row, end_col)

    def h(r: int, c: int) -> float:
        lat, lng = grid.cell_to_latlon(r, c)
        return _haversine_nm(lat, lng, end_lat, end_lng)

    start_cell = (start_row, start_col)
    goal_cell = (end_row, end_col)

    g: dict[tuple[int, int], float] = {start_cell: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    open_set: list[tuple[float, int, int]] = [(h(start_row, start_col), start_row, start_col)]
    closed: set[tuple[int, int]] = set()

    while open_set:
        _, row, col = heapq.heappop(open_set)
        if (row, col) in closed:
            continue
        if row == end_row and col == end_col:
            path: list[tuple[int, int]] = []
            cur = goal_cell
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            path.append(start_cell)
            path.reverse()
            return path
        closed.add((row, col))
        cur_lat, cur_lng = grid.cell_to_latlon(row, col)

        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if not (0 <= nr < grid.nrows and 0 <= nc < grid.ncols and grid.navigable[nr, nc]):
                    continue
                if dr != 0 and dc != 0 and not (grid.navigable[row + dr, col] and grid.navigable[row, col + dc]):
                    # Prevent diagonal corner-cutting through blocked corners
                    continue
                if (nr, nc) in closed:
                    continue
                n_lat, n_lng = grid.cell_to_latlon(nr, nc)
                step = _haversine_nm(cur_lat, cur_lng, n_lat, n_lng)
                p = _blocked_proximity_penalty(nr, nc, grid) * 0.1
                ng = g[(row, col)] + step + p
                if ng < g.get((nr, nc), float("inf")):
                    g[(nr, nc)] = ng
                    came_from[(nr, nc)] = (row, col)
                    heapq.heappush(open_set, (ng + h(nr, nc), nr, nc))

    return None

