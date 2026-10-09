"""Compatibility shim — voyage routing uses Floyd–Warshall (`warshall.py`)."""
from orca.sea_route.warshall import path_distance_nm, warshall_route as astar_route

__all__ = ["astar_route", "path_distance_nm"]
