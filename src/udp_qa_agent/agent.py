# src/udp_qa_agent/agent.py
import json
import os
import time
from typing import Dict, List, Optional, Tuple

from udp_qa_agent.prompts import (
    get_identify_udp_services_prompt,
    get_mock_udp_listener_prompt,
    get_udp_edge_case_generation_prompt,
    get_udp_fix_failure_prompt,
    get_udp_info_extraction_prompt,
    get_udp_test_script_prompt,
)
from udp_qa_agent.utils import (
    LLMError,
    call_ollama_llm,
    cleanup_directory,
    clone_repo,
    read_file_content,
    run_script_and_get_output,
    save_code_to_file,
    scan_files,
    setup_project_directories,
    start_background_process,
    stop_background_process,
)

# --- Types ---
ServiceInfo = Dict[str, str]
ProjectDirs = Dict[str, str]
GeneratedAsset = Dict[str, str]

# --- Configuration ---
MAX_REFINEMENT_RETRIES = 3  # Max attempts to fix a failing test/mock


class UDPQAAgent:
    """Advanced QA Automation Agent for UDP Endpoint Testing."""
    
    def __init__(self, model_name: str = "llama3:latest"):
        """
        Initialize the UDP QA Agent.
        
        Args:
            model_name: Name of the LLM model to use
        """
        self.model_name = model_name
        self.project_dirs: Optional[ProjectDirs] = None
    
    def run(self, git_url: str) -> str:
        """
        Run the complete UDP QA process.
        
        Args:
            git_url: URL of the Git repository to analyze
            
        Returns:
            Path to the generated test suite
        """
        print("--- advanced udp qa automation agent ---")
        
        if not git_url:
            raise ValueError("git url cannot be empty")
            
        self.project_dirs = setup_project_directories()
        # Modify project_dirs to have a parent for cloned_repo for easier cleanup
        self.project_dirs["cloned_repo_parent"] = self.project_dirs["cloned_repo"]
        
        try:
            # Phase 1: Information Gathering
            qa_reference_file = self._phase_1_information_gathering(git_url)
            if not qa_reference_file:
                raise RuntimeError("failed to gather qa information")

            # Phase 2: Mock & Test Generation
            generated_assets = self._phase_2_mock_and_test_generation(qa_reference_file)
            if not generated_assets:
                raise RuntimeError("failed to generate mocks and tests")
                
            # Phase 3: Iterative Testing
            self._phase_3_iterative_testing(generated_assets)
            
            # Phase 4: Packaging & Output
            self._phase_4_packaging_and_output(generated_assets)
            
            return self.project_dirs["base"]
            
        except Exception as e:
            print(f"\n--- an unhandled error occurred in the agent ---")
            print(f"error: {e}")
            import traceback
            traceback.print_exc()
            raise

    