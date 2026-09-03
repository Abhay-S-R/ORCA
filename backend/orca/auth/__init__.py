"""orca/auth — registration, login, JWT, RBAC (plan §5.4, D1 Day 9-10).

Ground Rule 1 boundary, load-bearing here: nothing in this package may set
or read the persona field carried on ORCAState (see state.py), and nothing
here is imported by orca/agents/ or orca/graph/ — identity is resolved at
the route boundary and handed to Reporting (Agent 9) as an already-resolved
value, never fed upstream into intent classification. The CI persona-leak
guard scans this package for exactly that reason (plan §5.4 Day 10 risk
register).
"""
