"""Port service: list ports and find their nearest sea cell."""
from __future__ import annotations

from orca.sea_route.datasets import Port, load_ports


def list_ports() -> tuple[Port, ...]:
    return load_ports()


def get_port(port_id: str) -> Port | None:
    if not port_id:
        return None
    target = port_id.strip().lower()
    for p in load_ports():
        if p.id.lower() == target or p.name.lower() == target or (p.code and p.code.lower() == target):
            return p
    return None


def port_to_latlon(port: Port) -> tuple[float, float]:
    return port.lat, port.lng
