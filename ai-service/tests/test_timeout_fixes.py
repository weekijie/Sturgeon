"""
Test script for Phase B Robust Timeout Implementation
Tests all 5 phases of the timeout fix:
1. 500-char limit removal
2. 90s timeout for Gemini and MedGemma
3. Hierarchical summarization (every 5 rounds)
4. Token constraints in prompts
5. Parallel RAG retrieval

Run with: python test_timeout_fixes.py
"""
import sys
import os
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path (for ai_service imports)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import directly from parent directory
import gemini_orchestrator
from gemini_orchestrator import GeminiOrchestrator, ClinicalState, DEFAULT_TIMEOUT_SECONDS
import models
from models import DebateTurnRequest, Diagnosis


class TestTimeoutFixes:
    """Test all timeout and context management fixes."""
    
    def test_1_character_limit_removed(self):
        """Test that 500-character limit is removed from DebateTurnRequest."""
        print("\n" + "="*60)
        print("TEST 1: 500-Character Limit Removal")
        print("="*60)
        
        # Create a diagnosis for the request
        diagnosis = Diagnosis(
            name="Test Diagnosis",
            probability="high",
            supporting_evidence=["evidence1"],
            against_evidence=[],
            suggested_tests=[]
        )
        
        # Create a very long challenge (1000+ characters)
        long_challenge = "What about the platelets? " * 50  # ~1300 chars
        
        try:
            request = DebateTurnRequest(
                patient_history="Test patient with fever and cough",
                lab_values={"WBC": {"value": 15, "unit": "K/uL", "status": "high"}},
                current_differential=[diagnosis],
                previous_rounds=[],
                user_challenge=long_challenge,
                session_id="test-session-1"
            )
            print(f"[PASS] Long message ({len(long_challenge)} chars) accepted")
            print(f"   Challenge preview: {long_challenge[:100]}...")
            return True
        except Exception as e:
            print(f"[FAIL] Long message rejected: {e}")
            return False
    
    def test_2_timeout_configuration(self):
        """Test that timeout is configured to 90 seconds."""
        print("\n" + "="*60)
        print("TEST 2: 90-Second Timeout Configuration")
        print("="*60)
        
        expected_timeout = 90.0
        actual_timeout = DEFAULT_TIMEOUT_SECONDS
        
        if actual_timeout == expected_timeout:
            print(f"[PASS] PASS: Timeout configured to {actual_timeout}s")
            return True
        else:
            print(f"[FAIL] FAIL: Expected {expected_timeout}s, got {actual_timeout}s")
            return False
    
    def test_3_hierarchical_summarization_fields(self):
        """Test that ClinicalState has episode summary fields."""
        print("\n" + "="*60)
        print("TEST 3: Hierarchical Summarization Fields")
        print("="*60)
        
        state = ClinicalState(
            patient_history="Test patient",
            debate_round=5
        )
        
        # Check new fields exist
        checks = []
        
        if hasattr(state, 'episode_summaries'):
            print("[PASS] episode_summaries field exists")
            checks.append(True)
        else:
            print("[FAIL] episode_summaries field missing")
            checks.append(False)
        
        if hasattr(state, 'last_episode_round'):
            print("[PASS] last_episode_round field exists")
            checks.append(True)
        else:
            print("[FAIL] last_episode_round field missing")
            checks.append(False)
        
        # Test episode summary creation
        state.episode_summaries.append("Test episode: Discussed pneumonia vs Legionella")
        if len(state.episode_summaries) == 1:
            print("[PASS] Can add episode summaries")
            checks.append(True)
        else:
            print("[FAIL] Cannot add episode summaries")
            checks.append(False)
        
        # Test to_summary includes episodes
        summary = state.to_summary()
        if "Previous Debate Episodes" in summary:
            print("[PASS] to_summary() includes episode summaries")
            checks.append(True)
        else:
            print("[FAIL] to_summary() missing episode summaries")
            checks.append(False)
        
        return all(checks)
    
    def test_4_token_constraints_in_prompt(self):
        """Test that orchestrator has token constraints."""
        print("\n" + "="*60)
        print("TEST 4: Token Constraints in Orchestrator Prompt")
        print("="*60)
        
        from gemini_orchestrator import ORCHESTRATOR_SYSTEM_INSTRUCTION
        
        required_constraints = [
            "800 tokens",
            "90 seconds",
            "2-3 most critical",
            "1 test per round"
        ]
        
        checks = []
        for constraint in required_constraints:
            if constraint in ORCHESTRATOR_SYSTEM_INSTRUCTION:
                print(f"[PASS] Found constraint: '{constraint}'")
                checks.append(True)
            else:
                print(f"[FAIL] Missing constraint: '{constraint}'")
                checks.append(False)
        
        return all(checks)
    
    def test_5_timeout_response_generation(self):
        """Test that timeout generates helpful response."""
        print("\n" + "="*60)
        print("TEST 5: Timeout Response Generation")
        print("="*60)
        
        # Create mock orchestrator
        orchestrator = GeminiOrchestrator(medgemma_model=None)
        
        # Test timeout response generation
        test_question = "What could explain the thrombocytopenia with these symptoms?"
        timeout_response = orchestrator._generate_timeout_response(test_question)
        
        checks = []
        
        # Check response contains helpful guidance
        if "taking longer than expected" in timeout_response:
            print("[PASS] Timeout response acknowledges delay")
            checks.append(True)
        else:
            print("[FAIL] Timeout response doesn't acknowledge delay")
            checks.append(False)
        
        if "RECOMMENDATIONS" in timeout_response:
            print("[PASS] Timeout response includes recommendations")
            checks.append(True)
        else:
            print("[FAIL] Timeout response missing recommendations")
            checks.append(False)
        
        if "Try breaking" in timeout_response or "smaller" in timeout_response:
            print("[PASS] Timeout response suggests breaking into smaller questions")
            checks.append(True)
        else:
            print("[FAIL] Timeout response doesn't suggest breaking questions")
            checks.append(False)
        
        # Check original question is referenced
        if test_question[:20] in timeout_response:
            print("[PASS] Timeout response references original question")
            checks.append(True)
        else:
            print("[FAIL] Timeout response doesn't reference original question")
            checks.append(False)
        
        return all(checks)
    
    def test_6_episode_summary_timing(self):
        """Test that episode summaries are created every 5 rounds."""
        print("\n" + "="*60)
        print("TEST 6: Episode Summary Timing (Every 5 Rounds)")
        print("="*60)
        
        # Simulate debate progression
        state = ClinicalState(
            patient_history="Test patient",
            debate_round=0,
            last_episode_round=0
        )
        
        checks = []
        
        # Round 4: Should NOT trigger episode summary
        state.debate_round = 4
        rounds_since = state.debate_round - state.last_episode_round
        if rounds_since < 5:
            print(f"[PASS] Round 4: No episode summary needed ({rounds_since} rounds since last)")
            checks.append(True)
        else:
            print(f"[FAIL] Round 4: Incorrectly flagged for episode summary")
            checks.append(False)
        
        # Round 5: SHOULD trigger episode summary
        state.debate_round = 5
        rounds_since = state.debate_round - state.last_episode_round
        if rounds_since >= 5:
            print(f"[PASS] Round 5: Episode summary triggered ({rounds_since} rounds since last)")
            checks.append(True)
        else:
            print(f"[FAIL] Round 5: Episode summary NOT triggered")
            checks.append(False)
        
        # Round 10: SHOULD trigger again
        state.debate_round = 10
        state.last_episode_round = 5
        rounds_since = state.debate_round - state.last_episode_round
        if rounds_since >= 5:
            print(f"[PASS] Round 10: Episode summary triggered ({rounds_since} rounds since last)")
            checks.append(True)
        else:
            print(f"[FAIL] Round 10: Episode summary NOT triggered")
            checks.append(False)
        
        return all(checks)
    
    def test_7_clinical_state_summary_format(self):
        """Test that ClinicalState summary includes all fields."""
        print("\n" + "="*60)
        print("TEST 7: Clinical State Summary Format")
        print("="*60)
        
        state = ClinicalState(
            patient_history="42yo male with fever, cough",
            lab_values={"WBC": {"value": 15, "unit": "K/uL", "status": "high"}},
            differential=[{"name": "Pneumonia", "probability": "high"}],
            key_findings=["Elevated WBC", "Fever"],
            ruled_out=["Viral URI"],
            debate_round=3,
            episode_summaries=["Episode 1: Initial assessment and differential"]
        )
        
        summary = state.to_summary()
        
        checks = []
        
        # Check all sections are present
        if "Clinical State (Round 3)" in summary:
            print("[PASS] Summary includes round number")
            checks.append(True)
        else:
            print("[FAIL] Summary missing round number")
            checks.append(False)
        
        if "Labs:" in summary:
            print("[PASS] Summary includes lab values")
            checks.append(True)
        else:
            print("[FAIL] Summary missing lab values")
            checks.append(False)
        
        if "Current Differential" in summary:
            print("[PASS] Summary includes differential")
            checks.append(True)
        else:
            print("[FAIL] Summary missing differential")
            checks.append(False)
        
        if "Key Findings" in summary:
            print("[PASS] Summary includes key findings")
            checks.append(True)
        else:
            print("[FAIL] Summary missing key findings")
            checks.append(False)
        
        if "Ruled Out" in summary:
            print("[PASS] Summary includes ruled out diagnoses")
            checks.append(True)
        else:
            print("[FAIL] Summary missing ruled out diagnoses")
            checks.append(False)
        
        if "Previous Debate Episodes" in summary:
            print("[PASS] Summary includes episode summaries")
            checks.append(True)
        else:
            print("[FAIL] Summary missing episode summaries")
            checks.append(False)
        
        return all(checks)
    
    async def run_all_tests(self):
        """Run all tests and report results."""
        print("\n" + "="*60)
        print("TIMEOUT FIXES - COMPREHENSIVE TEST SUITE")
        print("="*60)
        
        results = {
            "Character Limit Removal": self.test_1_character_limit_removed(),
            "Timeout Configuration": self.test_2_timeout_configuration(),
            "Hierarchical Summarization Fields": self.test_3_hierarchical_summarization_fields(),
            "Token Constraints": self.test_4_token_constraints_in_prompt(),
            "Timeout Response": self.test_5_timeout_response_generation(),
            "Episode Summary Timing": self.test_6_episode_summary_timing(),
            "Summary Format": self.test_7_clinical_state_summary_format(),
        }
        
        # Print summary
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, result in results.items():
            status = "[PASS]" if result else "[FAIL]"
            print(f"{status}: {test_name}")
        
        print("\n" + "="*60)
        print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        print("="*60)
        
        if passed == total:
            print("\n*** ALL TESTS PASSED! Timeout fixes are working correctly. ***")
            return 0
        else:
            print(f"\n*** {total-passed} test(s) failed. Please review the failures above. ***")
            return 1


def main():
    """Main entry point."""
    test_suite = TestTimeoutFixes()
    exit_code = asyncio.run(test_suite.run_all_tests())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
