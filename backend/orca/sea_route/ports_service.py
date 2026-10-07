"""Port service: list ports and find their nearest sea cell."""
from __future__ import annotations

import math

from orca.sea_route.datasets import Port, load_ports
from orca.sea_route.grid import SeaGrid


def list_ports() -> tuple[Port, ...]:
    return load_ports()


def get_port(port_id: str) -> Port | None:
    for p in load_ports():
        if p.id == port_id:
            return p
    return None


def port_to_latlon(port: Port) -> tuple[float, float]:
    return port.lat, port.lng
