#!/usr/bin/env python3
"""Seed Coastal Authority Accounts for all Major Indian Ports.

Creates or verifies authority accounts for each port:
- Mumbai
- Thoothukudi
- Chennai
- Kochi
- Visakhapatnam
- Mangalore
- Rameswaram
- Kanyakumari
- Paradip
- Veraval
- Kakinada
- Kolkata / Haldia

All created with:
  Role: authority
  Persona: coastal_authority
  Password: orca-authority-local-dev
"""
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from orca.db.engine import get_db
from orca.ops.port_authorities import DEFAULT_AUTHORITY_PASSWORD, PORT_AUTHORITIES, ensure_port_authorities


def main():
    print("=" * 60)
    print("Seeding ORCA Coastal Authority Accounts...")
    print("=" * 60)

    db = next(get_db())
    try:
        users = ensure_port_authorities(db)
        print(f"\nSuccessfully seeded {len(users)} Coastal Authority Accounts:")
        print("-" * 60)
        for u, cfg in zip(users, PORT_AUTHORITIES):
            print(f" - Port: {cfg['port_name']:<15} | Email: {u.email:<32} | Name: {u.display_name}")
        print("-" * 60)
        print(f"Shared Authority Password: '{DEFAULT_AUTHORITY_PASSWORD}'")
        print("Role: 'authority' | Persona: 'coastal_authority'\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
