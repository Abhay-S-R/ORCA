"""Compatibility shim — voyage routing uses Floyd–Warshall (`warshall.py`) with A* fallback."""
from orca.sea_route.warshall import _astar_route as astar_route
from orca.sea_route.warshall import path_distance_nm

__all__ = ["astar_route", "path_distance_nm"]

