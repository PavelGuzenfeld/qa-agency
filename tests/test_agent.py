# tests/test_agent.py
import os
import unittest
from unittest import mock

from udp_qa_agent.agent import UDPQAAgent


class TestUDPQAAgent(unittest.TestCase):
    
    @mock.patch('udp_qa_agent.agent.clone_repo')
    def test_phase_1_information_gathering_failure(self, mock_clone_repo):
        """Test that information gathering fails when repo clone fails."""
        # Setup
        mock_clone_repo.return_value = None
        agent = UDPQAAgent(model_name="test_model")
        agent.project_dirs = {
            "cloned_repo_parent": "/tmp/test",
            "qa_reference": "/tmp/test/qa_reference"
        }
        
        # Execute
        result = agent._phase_1_information_gathering("https://github.com/fake/repo.git")
        
        # Assert
        self.assertIsNone(result)
        mock_clone_repo.assert_called_once_with("https://github.com/fake/repo.git", "/tmp/test")
    
    @mock.patch('udp_qa_agent.agent.read_file_content')
    def test_qa_reference_file_not_found(self, mock_read_file):
        """Test mock and test generation fails when QA reference file is missing."""
        # Setup
        mock_read_file.return_value = None
        agent = UDPQAAgent(model_name="test_model")
        
        # Execute
        result = agent._phase_2_mock_and_test_generation("/nonexistent/path.json")
        
        # Assert
        self.assertEqual(result, [])
        mock_read_file.assert_called_once_with("/nonexistent/path.json")
    
    @mock.patch('udp_qa_agent.agent._parse_identified_services')
    @mock.patch('udp_qa_agent.agent.call_ollama_llm')
    @mock.patch('udp_qa_agent.agent.read_file_content')
    def test_no_services_identified(self, mock_read_file, mock_call_llm, mock_parse_services):
        """Test that no assets are generated when no services are identified."""
        # Setup
        mock_read_file.return_value = "test content"
        mock_call_llm.return_value = "no clear services can be identified"
        mock_parse_services.return_value = []
        
        agent = UDPQAAgent(model_name="test_model")
        
        # Execute
        result = agent._phase_2_mock_and_test_generation("/path/to/qa_ref.json")
        
        # Assert
        self.assertEqual(result, [])
        mock_read_file.assert_called_once()
        mock_call_llm.assert_called_once()
        mock_parse_services.assert_not_called()  # Should not be called when LLM output contains "no clear services"
    
    @mock.patch('udp_qa_agent.agent.run_script_and_get_output')
    @mock.patch('udp_qa_agent.agent.start_background_process')
    def test_mock_server_start_failure(self, mock_start_process, mock_run_script):
        """Test that testing is skipped when the mock server fails to start."""
        # Setup
        mock_start_process.return_value = None  # Simulate mock server failing to start
        
        agent = UDPQAAgent(model_name="test_model")
        agent.project_dirs = {"mocks": "/tmp/mocks", "tests": "/tmp/tests"}
        
        generated_assets = [{
            "service_name": "test_service",
            "port": 12345,
            "mock_file": "/tmp/mocks/mock_test.py",
            "test_file": "/tmp/tests/test_test.py",
            "original_qa_snippet": "test snippet",
            "functionality": "Test functionality"
        }]
        
        # Execute - should not raise exception
        agent._phase_3_iterative_testing(generated_assets)
        
        # Assert
        mock_start_process.assert_called_once()
        mock_run_script.assert_not_called()  # Should not be called when mock server fails to start
    
    @mock.patch('udp_qa_agent.agent.read_file_content')
    def test_parse_identified_services(self, mock_read_file):
        """Test parsing of LLM output for identified services."""
        # Setup
        mock_read_file.return_value = None  # Not used in this test
        agent = UDPQAAgent(model_name="test_model")
        
        llm_output = """
        Service Name: Test Service 1
        Port: 12345
        Functionality Summary: Test functionality 1
        
        Service Name: Test Service 2
        Port: 54321
        Functionality Summary: Test functionality 2
        
        Service Name: Invalid Service
        Port: not a port
        Functionality Summary: Test functionality 3
        """
        
        # Execute
        result = agent._parse_identified_services(llm_output)
        
        # Assert
        self.assertEqual(len(result), 2)  # Should only have the two valid services
        self.assertEqual(result[0]["name"], "Test Service 1")
        self.assertEqual(result[0]["port"], 12345)
        self.assertEqual(result[0]["functionality"], "Test functionality 1")
        self.assertEqual(result[1]["name"], "Test Service 2")
        self.assertEqual(result[1]["port"], 54321)
        self.assertEqual(result[1]["functionality"], "Test functionality 2")
        
    def test_check_test_passed(self):
        """Test the function that checks if a test passed."""
        agent = UDPQAAgent(model_name="test_model")
        
        # Test passes
        self.assertTrue(agent._check_test_passed(0, "Ran 3 tests in 0.1s\n\nOK"))
        
        # Test fails
        self.assertFalse(agent._check_test_passed(1, "Ran 3 tests in 0.1s\n\nFAILED (failures=1)"))
        
        # Error in test
        self.assertFalse(agent._check_test_passed(1, "Ran 3 tests in 0.1s\n\nERROR"))
        
        # Non-zero return code but no FAIL/ERROR in output
        self.assertFalse(agent._check_test_passed(1, "Ran 3 tests in 0.1s\n\nOK"))


if __name__ == '__main__':
    unittest.main()