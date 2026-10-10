"""Unit and integration tests for port authority distress alerts and survival suggestions.

Verifies:
1. Generation of categorized, life-saving survival suggestions (sinking, medical, engine failure, MOB, general).
2. Resolution of coastal authorities for all major ports (Mumbai, Chennai, Thoothukudi, etc.).
3. Distress response formatting containing Coast Guard MRCC, Coastal Authority alert, and survival checklist.
4. Database recording of distress events with assigned port authority and survival suggestions.
5. In-app emergency alert dispatch to the coastal authority's account for the user's home port.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from orca.agents import distress
from orca.db.engine import get_sessionmaker
from orca.db.repositories import create_user
from orca.graph.graph import _distress_update
from orca.ops import distress_queue as dq
from orca.ops.port_authorities import (
    ensure_port_authorities,
    resolve_port_authority_config,
)


@pytest.fixture
def db():
    session = get_sessionmaker()()
    made: dict[str, list] = {"queries": [], "users": [], "notifications": []}
    yield session, made
    session.rollback()
    for nid in made["notifications"]:
        session.execute(text("DELETE FROM notifications WHERE id = :n"), {"n": nid})
    for qid in made["queries"]:
        session.execute(text("DELETE FROM distress_events WHERE query_id = :q"), {"q": qid})
    for uid in made["users"]:
        session.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    session.commit()
    session.close()


def test_survival_suggestions_sinking():
    suggs = distress.get_survival_suggestions(
        distress_type="text_pattern",
        matched_phrase="sinking",
        text="our boat is sinking fast near Mumbai harbor",
    )
    assert suggs["category_key"] == "sinking"
    assert "Sinking" in suggs["category"]
    assert len(suggs["steps"]) >= 4
    # Check that critical life-saving steps are included
    assert any("LIFE JACKET" in s.upper() for s in suggs["steps"])
    assert any("BILGE" in s.upper() or "PUMP" in s.upper() for s in suggs["steps"])
    assert any("VHF" in s.upper() or "MAYDAY" in s.upper() for s in suggs["steps"])


def test_survival_suggestions_medical():
    suggs = distress.get_survival_suggestions(
        distress_type="medical_pattern",
        matched_phrase="bleeding",
        text="crew member has severe injury bleeding",
    )
    assert suggs["category_key"] == "medical"
    assert "Medical" in suggs["category"]
    assert any("PRESSURE" in s.upper() or "BLEED" in s.upper() for s in suggs["steps"])


def test_survival_suggestions_engine_failure():
    suggs = distress.get_survival_suggestions(
        distress_type="text_pattern",
        matched_phrase="engine failure",
        text="engine failure engine stopped adrift at sea",
    )
    assert suggs["category_key"] == "engine_failure"
    assert any("ANCHOR" in s.upper() or "DRIFT" in s.upper() for s in suggs["steps"])


def test_survival_suggestions_man_overboard():
    suggs = distress.get_survival_suggestions(
        distress_type="text_pattern",
        matched_phrase="man overboard",
        text="man overboard in rough seas",
    )
    assert suggs["category_key"] == "man_overboard"
    assert any("FLOTATION" in s.upper() or "LIFE RING" in s.upper() for s in suggs["steps"])


def test_format_survival_advice():
    suggs = distress.get_survival_suggestions("text_pattern", "sinking", "sinking")
    formatted = distress.format_survival_advice(suggs)
    assert "CRITICAL SURVIVAL ACTIONS WHILE AUTHORITIES REACH YOU" in formatted
    assert "1. " in formatted
    assert "2. " in formatted


def test_resolve_port_authority_by_name():
    mumbai_cfg = resolve_port_authority_config(port_name="Mumbai")
    assert mumbai_cfg["port_name"] == "Mumbai"
    assert mumbai_cfg["display_name"] == "Mumbai Coastal Authority"
    assert mumbai_cfg["email"] == "authority.mumbai@orca.test"

    chennai_cfg = resolve_port_authority_config(port_name="Chennai")
    assert chennai_cfg["port_name"] == "Chennai"
    assert chennai_cfg["display_name"] == "Chennai Coastal Authority"


def test_resolve_port_authority_by_coordinates():
    # Near Mumbai (approx 18.9°N, 72.8°E)
    cfg = resolve_port_authority_config(lat=18.95, lon=72.82)
    assert cfg["port_name"] == "Mumbai"
    assert cfg["display_name"] == "Mumbai Coastal Authority"

    # Near Thoothukudi (approx 8.8°N, 78.1°E)
    cfg_tk = resolve_port_authority_config(lat=8.75, lon=78.18)
    assert cfg_tk["port_name"] == "Thoothukudi"


def test_distress_run_and_graph_update_mumbai_user():
    # User in Mumbai experiencing sinking emergency
    state = {
        "query_id": str(uuid.uuid4()),
        "raw_user_query": "Mayday our boat is sinking off Mumbai port",
        "normalized_english_query": "Mayday our boat is sinking off Mumbai port",
        "user_location": {"lat": 18.93, "lon": 72.83, "home_port_name": "Mumbai", "place_name": "Mumbai"},
        "distress_flag": True,
    }
    result = distress.run(state)
    assert result.outputs["detection"]["is_distress"] is True
    assert result.outputs["target_authority"]["port_name"] == "Mumbai"
    assert result.outputs["target_authority"]["authority_name"] == "Mumbai Coastal Authority"
    assert len(result.outputs["survival_suggestions"]) >= 4

    # Graph update check
    entry = {"agent_name": "distress", "outputs": result.outputs}
    update = _distress_update(result, entry, "distress_check")

    assert update["query_outcome"] == "DISTRESS"
    resp = update["final_english_response"]

    # Ground rule assertion: must begin with DISTRESS DETECTED. Coast Guard MRCC:
    assert resp.startswith("DISTRESS DETECTED. Coast Guard MRCC:")
    # Coastal authority notification alert check:
    assert "Alert triggered and sent to Mumbai Coastal Authority" in resp
    # Survival checklist presence check:
    assert "CRITICAL SURVIVAL ACTIONS WHILE AUTHORITIES REACH YOU" in resp
    assert "1. " in resp


def test_distress_queue_records_event_and_triggers_authority_alert(db):
    session, made = db

    # 1. Ensure all authority accounts are created
    auth_accounts = ensure_port_authorities(session)
    emails = [u.email for u in auth_accounts]
    assert "authority.mumbai@orca.test" in emails

    # 2. Create a test Mumbai user
    user = create_user(
        session,
        identifier=f"mumbai-fisher-{uuid.uuid4().hex[:8]}@example.test",
        password_hash="pwd-hash",
        display_name="Ramesh Mumbai Trawler",
    )
    user.home_port_name = "Mumbai"
    session.commit()
    made["users"].append(user.id)

    qid = str(uuid.uuid4())
    made["queries"].append(qid)

    # 3. Simulate distress query state from this user
    final_state = {
        "query_id": qid,
        "user_id": str(user.id),
        "user_location": {"lat": 18.94, "lon": 72.82, "home_port_name": "Mumbai", "place_name": "Mumbai"},
        "audit_trace_log": [{
            "agent_name": "distress",
            "outputs": {
                "detection": {
                    "is_distress": True,
                    "distress_type": "text_pattern",
                    "matched_language": "en",
                    "matched_phrase": "sinking",
                },
                "survival_advice": distress.get_survival_suggestions("text_pattern", "sinking", "sinking near Mumbai"),
                "survival_suggestions": ["1. Don life jackets", "2. Transmit Mayday on VHF 16"],
                "target_authority": {
                    "port_name": "Mumbai",
                    "authority_name": "Mumbai Coastal Authority",
                },
            },
        }],
    }

    # 4. Record event
    dq.record_event(
        session,
        final_state,
        mrcc_contact={"primary": {"name": "MRCC Mumbai", "phone": "+91-22-2438-8065", "vhf_channel": "16"}},
        user_id=user.id,
    )

    # 5. Verify distress event stored with authority assignment
    events = dq.list_events(session, reader_id=uuid.uuid4(), hours=1)
    ev = next(e for e in events if e["query_id"] == qid)
    assert ev["state"] == "open"
    assert ev["target_port"] == "Mumbai"
    assert ev["authority_name"] == "Mumbai Coastal Authority"
    assert len(ev["survival_suggestions"]) > 0

    # 6. Verify emergency alert notification created for Mumbai Coastal Authority account
    mumbai_authority_user = session.execute(
        text("SELECT id FROM users WHERE email = 'authority.mumbai@orca.test'")
    ).scalar()
    assert mumbai_authority_user is not None

    notif = session.execute(
        text(
            "SELECT id, severity, title, body, rendered_payload FROM notifications "
            "WHERE user_id = :uid AND query_id = :qid"
        ),
        {"uid": mumbai_authority_user, "qid": qid},
    ).mappings().first()

    assert notif is not None, "Notification must be created for authority.mumbai@orca.test"
    made["notifications"].append(notif["id"])

    assert notif["severity"] == "danger"
    assert "Mumbai Coastal Sector" in notif["title"]
    assert "Ramesh Mumbai Trawler" in notif["body"]
    assert "Survival suggestions issued to vessel" in notif["body"]

    payload = notif["rendered_payload"]
    assert payload["port_name"] == "Mumbai"
    assert payload["authority_name"] == "Mumbai Coastal Authority"
    assert payload["distress_type"] == "text_pattern"
    assert payload["matched_phrase"] == "sinking"
    assert len(payload["survival_suggestions"]) > 0
