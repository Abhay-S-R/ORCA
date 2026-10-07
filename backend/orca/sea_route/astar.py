"""A* pathfinder on the sea-route navigability grid.

8-direction movement; cost and heuristic are haversine distance in
nautical miles so the algorithm explores by real sea distance, not
by grid steps.
"""
from __future__ import annotations

import heapq
import math
from typing import Generator

from orca.sea_route.grid import SeaGrid

_R_NM = 3440.065  # Earth's mean radius in nautical miles


def _haversine_nm(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine great-circle distance in nautical miles."""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return 2 * _R_NM * math.asin(math.sqrt(max(0.0, a)))


def _neighbours(row: int, col: int, grid: SeaGrid) -> Generator[tuple[int, int], None, None]:
    """8-connected navigable neighbours."""
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = row + dr, col + dc
            if not (0 <= r < grid.nrows and 0 <= c < grid.ncols and grid.navigable[r, c]):
                continue
            if dr != 0 and dc != 0:
                # Prevent corner-cutting through blocked corners
                if not (0 <= row + dr < grid.nrows and grid.navigable[row + dr, col]):
                    continue
                if not (0 <= col + dc < grid.ncols and grid.navigable[row, col + dc]):
                    continue
            yield r, c


def astar_route(
    start_row: int, start_col: int,
    end_row: int, end_col: int,
    grid: SeaGrid,
) -> list[tuple[int, int]] | None:
    """A* on the navigability grid.

    Returns a list of (row, col) cells from start to end (inclusive),
    or None if no path exists.
    """
    if not grid.navigable[start_row, start_col] or not grid.navigable[end_row, end_col]:
        return None

    end_lat, end_lng = grid.cell_to_latlon(end_row, end_col)

    def h(row: int, col: int) -> float:
        lat, lng = grid.cell_to_latlon(row, col)
        return _haversine_nm(lat, lng, end_lat, end_lng)

    # g[node] = best known cost from start to node (nm)
    g: dict[tuple[int, int], float] = {(start_row, start_col): 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}

    # Priority queue: (f, row, col)
    open_set: list[tuple[float, int, int]] = [(h(start_row, start_col), start_row, start_col)]
    closed: set[tuple[int, int]] = set()

    while open_set:
        _, row, col = heapq.heappop(open_set)
        if (row, col) in closed:
            continue
        if row == end_row and col == end_col:
            # Reconstruct path.
            path: list[tuple[int, int]] = []
            cur = (end_row, end_col)
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            path.append((start_row, start_col))
            path.reverse()
            return path
        closed.add((row, col))
        cur_lat, cur_lng = grid.cell_to_latlon(row, col)
        for nr, nc in _neighbours(row, col, grid):
            if (nr, nc) in closed:
                continue
            n_lat, n_lng = grid.cell_to_latlon(nr, nc)
            step = _haversine_nm(cur_lat, cur_lng, n_lat, n_lng)
            ng = g[(row, col)] + step
            if ng < g.get((nr, nc), float("inf")):
                g[(nr, nc)] = ng
                came_from[(nr, nc)] = (row, col)
                f = ng + h(nr, nc)
                heapq.heappush(open_set, (f, nr, nc))

    return None  # No path found


def path_distance_nm(path: list[tuple[float, float]]) -> float:
    """Total haversine distance (nm) of a lat/lng polyline."""
    total = 0.0
    for i in range(len(path) - 1):
        total += _haversine_nm(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
    return total
