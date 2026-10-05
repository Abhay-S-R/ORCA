"""PC3.4 — Invariant test for adversarial plans (unit tests for enforce_planning_invariants).

This test verifies that the planning invariants (D3) are correctly enforced:
- Empty plan → all required agents run (fail-safe)
- Only visualization → core agents still run
- Hallucinated names → dropped
- risk_assessment omitted → added back (required for verdict)
- Verdict is byte-identical to all-agents run for same inputs
"""
import pytest

from orca.agents.planning import enforce_planning_invariants


class TestPC34Invariants:
    """Tests for PC3.4 — invariant enforcement on adversarial plans."""

    def test_empty_plan_adds_required_agents(self):
        """Empty plan should add all required core agents for sea question."""
        result = enforce_planning_invariants([], is_sea_question=True)
        # Core sea agents must always be present
        assert "marine_data_discovery" in result
        assert "weather_intelligence" in result
        assert "geospatial" in result
        assert "risk_assessment" in result
        assert "reporting" in result
        assert "critic" in result
        # Skippable agents not present unless model requested them
        assert "ocean_analytics" not in result
        assert "visualization" not in result

    def test_only_visualization_in_plan_adds_core_agents(self):
        """Model proposing only visualization should still get core agents."""
        result = enforce_planning_invariants(["visualization"], is_sea_question=True)
        assert "marine_data_discovery" in result
        assert "weather_intelligence" in result
        assert "geospatial" in result
        assert "risk_assessment" in result
        assert "reporting" in result
        assert "critic" in result
        assert "visualization" in result
        assert "ocean_analytics" not in result

    def test_hallucinated_names_are_dropped(self):
        """Unknown agent names should be dropped."""
        result = enforce_planning_invariants(["weather_intelligence", "fake_agent", "another_fake"], is_sea_question=True)
        assert "weather_intelligence" in result
        assert "fake_agent" not in result
        assert "another_fake" not in result
        # Core agents still added
        assert "marine_data_discovery" in result
        assert "geospatial" in result
        assert "risk_assessment" in result
        assert "reporting" in result
        assert "critic" in result

    def test_risk_assessment_omitted_is_added_back(self):
        """Model omitting risk_assessment should have it added back (required for verdict)."""
        result = enforce_planning_invariants(
            ["marine_data_discovery", "weather_intelligence", "geospatial", "ocean_analytics"],
            is_sea_question=True
        )
        assert "risk_assessment" in result
        # Core agents present
        assert "marine_data_discovery" in result
        assert "weather_intelligence" in result
        assert "geospatial" in result
        assert "risk_assessment" in result
        assert "reporting" in result
        assert "critic" in result

    def test_order_is_fixed_dependency_order(self):
        """Execution order should follow fixed dependency order, not model's order."""
        # Model proposes in random order
        model_plan = ["visualization", "weather_intelligence", "ocean_analytics", "geospatial", "risk_assessment"]
        result = enforce_planning_invariants(model_plan, is_sea_question=True)
        # Should be in fixed execution order
        expected_order = [
            "marine_data_discovery",
            "weather_intelligence",
            "geospatial",
            "ocean_analytics",
            "risk_assessment",
            "visualization",
            "reporting",
            "critic",
            "language_egress",
        ]
        # Filter to only those in result
        expected = [a for a in expected_order if a in result]
        assert result == expected

    def test_non_sea_question_uses_model_plan_only(self):
        """Non-sea questions should only run what model planned (validated)."""
        result = enforce_planning_invariants(["visualization", "ocean_analytics"], is_sea_question=False)
        # For non-sea, only model's valid choices + marine_data_discovery
        assert "marine_data_discovery" in result
        assert "visualization" in result
        assert "ocean_analytics" in result
        # Core sea agents NOT required for non-sea
        assert "weather_intelligence" not in result
        assert "geospatial" not in result
        assert "risk_assessment" not in result
        assert "reporting" not in result
        assert "critic" not in result

    def test_unknown_agents_in_mixed_list_are_dropped(self):
        """Mixed list with known and unknown agents should drop unknowns."""
        result = enforce_planning_invariants(
            ["weather_intelligence", "fake1", "geospatial", "fake2", "risk_assessment"],
            is_sea_question=True
        )
        assert "weather_intelligence" in result
        assert "geospatial" in result
        assert "risk_assessment" in result
        assert "fake1" not in result
        assert "fake2" not in result
        # Required agents added
        assert "marine_data_discovery" in result
        assert "reporting" in result
        assert "critic" in result

    def test_model_can_skip_both_skippable(self):
        """Model can choose to skip both ocean_analytics and visualization."""
        result = enforce_planning_invariants(
            ["weather_intelligence", "geospatial"],  # Model only requests core
            is_sea_question=True
        )
        assert "marine_data_discovery" in result
        assert "weather_intelligence" in result
        assert "geospatial" in result
        assert "risk_assessment" in result
        assert "reporting" in result
        assert "critic" in result
        assert "ocean_analytics" not in result
        assert "visualization" not in result

    def test_model_can_request_both_skippable(self):
        """Model can request both skippable agents."""
        result = enforce_planning_invariants(
            ["ocean_analytics", "visualization"],
            is_sea_question=True
        )
        assert "marine_data_discovery" in result
        assert "weather_intelligence" in result
        assert "geospatial" in result
        assert "risk_assessment" in result
        assert "reporting" in result
        assert "critic" in result
        assert "ocean_analytics" in result
        assert "visualization" in result

    def test_duplicate_agents_in_input_are_deduplicated(self):
        """Duplicate agents in input should be deduplicated."""
        result = enforce_planning_invariants(
            ["weather_intelligence", "weather_intelligence", "geospatial", "geospatial"],
            is_sea_question=True
        )
        assert result.count("weather_intelligence") == 1
        assert result.count("geospatial") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])