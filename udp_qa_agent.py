# udp_qa_agent.py
import os
import json
import time
from agent_utils import (
    clone_repo, scan_files, read_file_content, save_code_to_file,
    call_ollama_llm, start_background_process, stop_background_process,
    run_script_and_get_output, setup_project_directories, cleanup_directory
)
from agent_prompts import (
    get_udp_info_extraction_prompt, get_identify_udp_services_prompt,
    get_mock_udp_listener_prompt, get_udp_test_script_prompt,
    get_udp_fix_failure_prompt, get_udp_edge_case_generation_prompt
)

# --- Configuration ---
# Ensure this model is available in Ollama and suitable for your hardware
# For 32GB RAM, llama3:latest (the 8B version, ~4.7GB) is a good choice.
AGENT_LLM_MODEL = "llama3:latest" 
MAX_REFINEMENT_RETRIES = 3 # Max attempts to fix a failing test/mock

def phase_1_information_gathering(git_url: str, project_dirs: dict) -> str:
    """
    Phase 1: Clones repo, scans files, and extracts QA information using LLM.
    Returns the path to the consolidated QA reference file.
    """
    print("\n--- PHASE 1: Information Gathering ---")
    cloned_repo_path = clone_repo(git_url, project_dirs["cloned_repo_parent"]) # utils handles subfolder
    if not cloned_repo_path:
        print("Failed to clone repository. Exiting.")
        return None

    # Specify file extensions to scan, or None to attempt all (might be slow)
    # Add more extensions relevant to your target repositories
    extensions_to_scan = ['.py', '.go', '.c', '.cpp', '.java', '.js', '.ts', '.md', '.txt', 
                          '.json', '.yaml', '.yml', 'Dockerfile', 'docker-compose.yml']
    
    source_files = scan_files(cloned_repo_path, extensions=extensions_to_scan)
    
    qa_reference_data = []
    print(f"\nScanning {len(source_files)} files for UDP QA information...")

    for filepath in source_files:
        print(f"  Processing file: {filepath}")
        content = read_file_content(filepath)
        if content:
            # Handle very large files - basic truncation here, advanced would be chunking
            if len(content) > 20000: # Arbitrary limit before sending to LLM prompt function
                print(f"    File {filepath} is very large, truncating for initial scan.")
                # The prompt function itself also has truncation
            
            prompt = get_udp_info_extraction_prompt(filepath, content)
            extracted_info = call_ollama_llm(prompt, model_name=AGENT_LLM_MODEL)
            
            if extracted_info and "no relevant udp qa information" not in extracted_info.lower():
                qa_reference_data.append({
                    "source_file": filepath.replace(cloned_repo_path, "").lstrip(os.sep), # Relative path
                    "extracted_info": extracted_info
                })
                print(f"    Extracted information from {filepath}")
            else:
                print(f"    No specific UDP QA info found or LLM call failed for {filepath}")
        time.sleep(1) # Small delay to avoid overwhelming Ollama if many files

    qa_reference_filepath = os.path.join(project_dirs["qa_reference"], "consolidated_qa_reference.json")
    try:
        with open(qa_reference_filepath, 'w', encoding='utf-8') as f:
            json.dump(qa_reference_data, f, indent=2)
        print(f"\nConsolidated QA Reference saved to: {qa_reference_filepath}")
        return qa_reference_filepath
    except Exception as e:
        print(f"Error saving QA Reference to JSON: {e}")
        # Fallback: save as text
        qa_reference_filepath_txt = os.path.join(project_dirs["qa_reference"], "consolidated_qa_reference.txt")
        text_content = ""
        for item in qa_reference_data:
            text_content += f"Source File: {item['source_file']}\nExtracted Info:\n{item['extracted_info']}\n---\n"
        save_code_to_file(text_content, qa_reference_filepath_txt)
        print(f"Consolidated QA Reference saved as TEXT to: {qa_reference_filepath_txt}")
        return qa_reference_filepath_txt


def phase_2_mock_and_test_generation(qa_reference_filepath: str, project_dirs: dict) -> list:
    """
    Phase 2: Identifies UDP services, generates mocks and test scripts.
    Returns a list of dicts, each containing paths to 'mock_file' and 'test_file'.
    """
    print("\n--- PHASE 2: Mock & Test Generation ---")
    if not qa_reference_filepath or not os.path.exists(qa_reference_filepath):
        print("QA Reference file not found. Cannot proceed.")
        return []

    qa_ref_content = read_file_content(qa_reference_filepath)
    if not qa_ref_content:
        print("Could not read QA Reference file.")
        return []
    
    # If it was saved as JSON, load it, otherwise use as text
    if qa_reference_filepath.endswith(".json"):
        try:
            data = json.loads(qa_ref_content)
            # Reconstruct a text version for the LLM to parse services, or use a more structured approach
            text_for_service_id_prompt = ""
            for item in data:
                text_for_service_id_prompt += f"Source: {item['source_file']}\nInfo: {item['extracted_info']}\n\n"
            qa_ref_content = text_for_service_id_prompt
        except json.JSONDecodeError:
            print("QA Reference is JSON but failed to parse. Using as raw text.")
            # qa_ref_content remains as read


    prompt_identify_services = get_identify_udp_services_prompt(qa_ref_content)
    identified_services_text = call_ollama_llm(prompt_identify_services, model_name=AGENT_LLM_MODEL)

    if not identified_services_text or "no clear services can be identified" in identified_services_text.lower():
        print("No UDP services identified by the LLM from QA Reference.")
        return []

    print("\nIdentified potential UDP services by LLM:\n", identified_services_text)
    
    # Rudimentary parsing of LLM output for services. This needs to be robust.
    # Example: "Service Name: Auth UDP\nPort: 1234\nFunctionality Summary: Handles user auth packets."
    services_to_test = []
    current_service = {}
    for line in identified_services_text.splitlines():
        if line.startswith("Service Name:"):
            if current_service: services_to_test.append(current_service)
            current_service = {"name": line.split(":", 1)[1].strip()}
        elif line.startswith("Port:") and current_service:
            try:
                current_service["port"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                print(f"Warning: Could not parse port from line: {line}")
                current_service["port"] = None # Mark as invalid
        elif line.startswith("Functionality Summary:") and current_service:
            current_service["functionality"] = line.split(":", 1)[1].strip()
    if current_service and "port" in current_service and current_service["port"] is not None: # Ensure last service is added
        services_to_test.append(current_service)

    if not services_to_test:
        print("Could not parse any valid services from LLM output.")
        return []

    print(f"\nParsed {len(services_to_test)} services for mock/test generation.")
    generated_assets = []

    for i, service_info in enumerate(services_to_test):
        service_name = service_info.get("name", f"udp_service_{i+1}").replace(" ", "_").lower()
        port = service_info.get("port")
        functionality = service_info.get("functionality", "N/A")

        if not port:
            print(f"Skipping service '{service_name}' due to missing port information.")
            continue

        print(f"\nGenerating mock for: {service_name} on port {port}")
        # For relevant_qa_snippet, ideally, we'd semantically find the most relevant parts.
        # For now, we might pass a summary or the whole (truncated) qa_ref_content.
        # A better approach: During Phase 1, associate extracted info directly with identified ports/services.
        relevant_qa_snippet_for_service = f"Service: {service_name}, Port: {port}, Functionality: {functionality}\nDetails from QA Reference:\n{qa_ref_content}" # Simplified

        mock_prompt = get_mock_udp_listener_prompt(port, functionality, relevant_qa_snippet_for_service)
        mock_code = call_ollama_llm(mock_prompt, model_name=AGENT_LLM_MODEL)
        
        if not mock_code:
            print(f"Failed to generate mock code for {service_name}. Skipping.")
            continue
        
        mock_file_path = os.path.join(project_dirs["mocks"], f"mock_{service_name}_port{port}.py")
        save_code_to_file(mock_code, mock_file_path)

        print(f"\nGenerating test script for: {service_name} on port {port}")
        test_prompt = get_udp_test_script_prompt(port, functionality, relevant_qa_snippet_for_service, mock_code)
        test_code = call_ollama_llm(test_prompt, model_name=AGENT_LLM_MODEL)

        if not test_code:
            print(f"Failed to generate test code for {service_name}. Skipping mock as well.")
            if os.path.exists(mock_file_path): os.remove(mock_file_path) # Clean up orphaned mock
            continue

        test_file_path = os.path.join(project_dirs["tests"], f"test_{service_name}_port{port}.py")
        save_code_to_file(test_code, test_file_path)
        
        generated_assets.append({
            "service_name": service_name,
            "port": port,
            "functionality": functionality,
            "mock_file": mock_file_path,
            "test_file": test_file_path,
            "original_qa_snippet": relevant_qa_snippet_for_service # Store for refinement
        })
        time.sleep(1) # Delay

    return generated_assets


def phase_3_iterative_testing(generated_assets: list, project_dirs: dict):
    """
    Phase 3: Runs tests against mocks and attempts to refine them using LLM feedback.
    """
    print("\n--- PHASE 3: Iterative Testing & Refinement ---")
    if not generated_assets:
        print("No assets generated in Phase 2. Skipping testing.")
        return

    all_tests_passed_overall = True

    for asset in generated_assets:
        service_name = asset["service_name"]
        port = asset["port"]
        mock_file = asset["mock_file"]
        test_file = asset["test_file"]
        qa_snippet = asset["original_qa_snippet"] # For refinement prompts

        print(f"\n--- Testing Service: {service_name} (Port: {port}) ---")
        
        current_mock_code = read_file_content(mock_file)
        current_test_code = read_file_content(test_file)

        for attempt in range(MAX_REFINEMENT_RETRIES + 1): # +1 for initial run
            if attempt > 0:
                print(f"  Refinement attempt {attempt} for {service_name}...")

            mock_process = None
            mock_stdout_log = ""
            mock_stderr_log = "" # For mock's own errors

            try:
                # Start Mock Server
                # For UDP, mock needs to know its port, but it's usually hardcoded from generation.
                # If dynamic ports were used, test script would need to be told.
                mock_process = start_background_process(mock_file, cwd=project_dirs["mocks"])
                if not mock_process:
                    print(f"  Failed to start mock server {mock_file}. Skipping this service.")
                    all_tests_passed_overall = False
                    break # Break from retry loop for this service
                
                time.sleep(2) # Give mock a moment to bind port

                # Run Test Script
                # Test script should target localhost:port
                test_stdout, test_stderr, return_code = run_script_and_get_output(
                    test_file, cwd=project_dirs["tests"]
                )
                
                # Try to get logs from mock (basic approach)
                # A more robust mock would write to a log file or have a way to query logs.
                # For now, we assume mock prints to its stdout/stderr.
                # This part is tricky with background processes.
                # For simplicity, we'll rely on test output for now.
                # A better mock would log to a known file.
                # mock_stdout_log, mock_stderr_log = mock_process.communicate(timeout=5) # This would block if mock doesn't exit

                print(f"  Test Script Stdout:\n{test_stdout[:500]}...") # Print snippet
                print(f"  Test Script Stderr:\n{test_stderr[:500]}...")
                print(f"  Test Script Return Code: {return_code}")

                # Basic success check (unittest usually exits 0 on success, prints to stderr)
                # "OK" in stderr is a good sign. "FAIL" or "ERROR" in stderr means failure.
                passed = False
                if return_code == 0 and ("OK" in test_stderr and "FAIL" not in test_stderr and "ERROR" not in test_stderr):
                    passed = True
                elif "FAIL" in test_stderr or "ERROR" in test_stderr:
                    passed = False
                # Add more sophisticated parsing of unittest results if needed

                if passed:
                    print(f"  Tests for {service_name} PASSED on attempt {attempt+1}.")
                    
                    # --- Incorporate Edge Cases (Step 3.2) ---
                    print(f"\n  Attempting to generate and test edge cases for {service_name}...")
                    edge_case_prompt = get_udp_edge_case_generation_prompt(
                        port, qa_snippet, current_mock_code, current_test_code
                    )
                    edge_case_suggestions = call_ollama_llm(edge_case_prompt, AGENT_LLM_MODEL)

                    if edge_case_suggestions and "no mock changes are needed" not in edge_case_suggestions.lower():
                        # This part is complex: parse LLM output for new test methods AND potential mock updates
                        # For MVP, we might just log the suggestions.
                        # A full implementation would parse, integrate, and re-test.
                        print(f"    LLM suggested edge cases (and potential mock updates):\n{edge_case_suggestions[:1000]}...")
                        # TODO: Implement parsing and integration of edge cases
                        # This would involve adding new test methods to the test script,
                        # potentially updating the mock, and re-running tests.
                        # For now, we'll consider the main tests passing as success for this asset.
                    elif edge_case_suggestions:
                         print(f"    LLM suggested edge cases (no mock changes needed):\n{edge_case_suggestions[:1000]}...")
                         # TODO: Implement parsing and integration of edge case test methods.
                    else:
                        print(f"    No edge cases suggested or failed to get suggestions for {service_name}.")
                    break # Exit retry loop for this service, as main tests passed

                # If tests failed and we have retries left
                if not passed and attempt < MAX_REFINEMENT_RETRIES:
                    print(f"  Tests for {service_name} FAILED on attempt {attempt+1}. Attempting to fix...")
                    all_tests_passed_overall = False
                    fix_prompt = get_udp_fix_failure_prompt(
                        port, qa_snippet, current_mock_code, current_test_code,
                        test_stdout, test_stderr, "Mock logs not captured in this version." # Placeholder
                    )
                    fix_suggestion = call_ollama_llm(fix_prompt, AGENT_LLM_MODEL)

                    if not fix_suggestion:
                        print("    LLM failed to provide a fix. Stopping retries for this service.")
                        break 

                    # This parsing is critical and needs to be robust.
                    # LLM should indicate if it's updating mock, test, or both.
                    print(f"    LLM Fix Suggestion:\n{fix_suggestion[:500]}...")
                    
                    # Naive update: Assume LLM provides full code for one or both.
                    # A more robust parser would look for "Updated Mock Code:" and "Updated Test Script Code:"
                    # For simplicity, let's assume it might provide one or the other, or indicate.
                    # This part needs significant improvement for reliability.
                    
                    # Example of how you might try to parse (VERY SIMPLISTIC):
                    new_mock_code_marker = "Updated Mock Code:"
                    new_test_code_marker = "Updated Test Script Code:"

                    if new_mock_code_marker in fix_suggestion:
                        potential_new_mock = fix_suggestion.split(new_mock_code_marker, 1)[1]
                        if new_test_code_marker in potential_new_mock: # if test code follows
                            potential_new_mock = potential_new_mock.split(new_test_code_marker,1)[0]
                        current_mock_code = potential_new_mock.strip()
                        save_code_to_file(current_mock_code, mock_file)
                        print("    Applied LLM suggestion to mock file.")

                    if new_test_code_marker in fix_suggestion:
                        potential_new_test = fix_suggestion.split(new_test_code_marker, 1)[1]
                        if new_mock_code_marker in potential_new_test: # if mock code follows
                            potential_new_test = potential_new_test.split(new_mock_code_marker,1)[0]
                        current_test_code = potential_new_test.strip()
                        save_code_to_file(current_test_code, test_file)
                        print("    Applied LLM suggestion to test file.")
                    
                    if not (new_mock_code_marker in fix_suggestion or new_test_code_marker in fix_suggestion):
                        print("    LLM did not provide clear code updates in the expected format. Stopping retries.")
                        break
                
                elif not passed and attempt == MAX_REFINEMENT_RETRIES:
                    print(f"  Tests for {service_name} FAILED after {MAX_REFINEMENT_RETRIES} refinement attempts.")
                    all_tests_passed_overall = False
                    # Log this failure persistently

            except Exception as e:
                print(f"  An unexpected error occurred during testing of {service_name}: {e}")
                all_tests_passed_overall = False
                break # Stop retries for this service on major error
            finally:
                if mock_process:
                    stop_background_process(mock_process, f"Mock for {service_name}")
        
        if not all_tests_passed_overall and not passed: # If loop finished due to retries for this service
             print(f"--- Service {service_name} did not achieve passing tests. ---")


    if all_tests_passed_overall:
        print("\n--- All identified services with generated tests seem to have passed their main tests! ---")
    else:
        print("\n--- Some services had tests that failed or could not be fixed. Check logs. ---")


def phase_4_packaging_and_output(project_dirs: dict, generated_assets: list):
    """
    Phase 4: Organizes files and generates a README and run script.
    """
    print("\n--- PHASE 4: Packaging & Output ---")
    if not generated_assets:
        print("No assets were successfully generated or tested. Skipping packaging.")
        return

    # Files are already in project_dirs["tests"] and project_dirs["mocks"]
    # QA reference is in project_dirs["qa_reference"]

    # Generate Master Run Script (run_udp_suite.py)
    master_run_script_content = f"""#!/usr/bin/env python
# Master script to run all generated UDP tests against their mocks.
import subprocess
import os
import time

MOCKS_DIR = "mocks"
TESTS_DIR = "tests"
PYTHON_EXE = "python" # Or "python3"

# Assuming assets are pairs like mock_service_X.py and test_service_X.py
# This needs to be more robust, using the 'generated_assets' list
# For simplicity, this example just lists them. A real script would iterate `generated_assets`.

generated_tests_and_mocks = {json.dumps(generated_assets, indent=2)}

def run_test_suite():
    print("Starting UDP Test Suite Runner...")
    all_passed = True
    
    for asset in generated_tests_and_mocks:
        service_name = asset['service_name']
        mock_file = os.path.join(MOCKS_DIR, os.path.basename(asset['mock_file']))
        test_file = os.path.join(TESTS_DIR, os.path.basename(asset['test_file']))
        port = asset['port'] # Mocks should use this port

        print(f"\\n--- Running tests for {service_name} (Port: {port}) ---")
        
        mock_process = None
        try:
            print(f"  Starting mock: {mock_file} on port {port}")
            # Mocks should be designed to listen on the port derived from their name or passed via arg/env
            mock_process = subprocess.Popen([PYTHON_EXE, mock_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(2) # Give mock time to start

            if mock_process.poll() is not None:
                print(f"  ERROR: Mock server {mock_file} failed to start or exited prematurely.")
                print(f"  Mock stdout:\\n{mock_process.stdout.read() if mock_process.stdout else ''}")
                print(f"  Mock stderr:\\n{mock_process.stderr.read() if mock_process.stderr else ''}")
                all_passed = False
                continue

            print(f"  Running test script: {test_file}")
            # Test script needs to know to target localhost:port
            test_result = subprocess.run(
                [PYTHON_EXE, test_file], capture_output=True, text=True, timeout=120
            )
            
            print(f"  Test Stdout:\\n{test_result.stdout}")
            print(f"  Test Stderr:\\n{test_result.stderr}")
            
            if "OK" in test_result.stderr and "FAIL" not in test_result.stderr and "ERROR" not in test_result.stderr:
                print(f"  RESULT: {service_name} tests PASSED.")
            else:
                print(f"  RESULT: {service_name} tests FAILED or had errors.")
                all_passed = False

        except Exception as e:
            print(f"  An error occurred running tests for {service_name}: {e}")
            all_passed = False
        finally:
            if mock_process and mock_process.poll() is None:
                print(f"  Stopping mock: {mock_file}")
                mock_process.terminate()
                mock_process.wait(timeout=5)
                if mock_process.poll() is None:
                    mock_process.kill()

    if all_passed:
        print("\\n--- UDP Test Suite: ALL TESTS PASSED ---")
    else:
        print("\\n--- UDP Test Suite: SOME TESTS FAILED ---")

if __name__ == "__main__":
    run_test_suite()
"""
    run_suite_path = os.path.join(project_dirs["base"], "run_udp_suite.py")
    save_code_to_file(master_run_script_content, run_suite_path)
    os.chmod(run_suite_path, 0o755) # Make it executable

    # Generate README.md
    readme_content = f"""# Generated UDP QA Test Suite

This suite was automatically generated by the UDP QA Agent.

## Description
This test suite includes mock UDP listeners and corresponding test scripts for UDP services identified from the source repository.

## Prerequisites
- Python 3.x
- `requests` library (for the agent itself, not strictly for running these tests if they only use `socket`)
  ```bash
  pip install requests 
  ```
  (The generated tests primarily use the standard `socket` and `unittest` libraries).

## Structure
- `mocks/`: Contains Python scripts for mock UDP listeners.
- `tests/`: Contains Python `unittest` scripts for testing the UDP services against the mocks.
- `qa_reference/`: Contains the consolidated information extracted by the LLM used to generate these tests.
- `run_udp_suite.py`: A master script to execute all tests.

## How to Run
1. Navigate to this directory (`{os.path.basename(project_dirs["base"])}`) in your terminal.
2. Ensure you have Python installed.
3. Make the run script executable (if not already):
   ```bash
   chmod +x run_udp_suite.py
   ```
4. Execute the test suite:
   ```bash
   ./run_udp_suite.py
   ```
   Or:
   ```bash
   python run_udp_suite.py
   ```

## Services Covered
The following UDP services/ports were targeted (refer to `generated_assets` in `run_udp_suite.py` for details):
"""
    for asset in generated_assets:
        readme_content += f"- {asset['service_name']} on port {asset['port']}\n"
    
    readme_content += "\n## Notes\n- These tests run against locally started mock servers, not live services.\n- UDP is connectionless; tests focus on sending packets and checking for expected responses (if any) from the mock.\n"

    readme_path = os.path.join(project_dirs["base"], "README.md")
    save_code_to_file(readme_content, readme_path)

    print(f"\nPackaging complete. Test suite generated in: {project_dirs['base']}")
    print(f"To run the suite, navigate to '{project_dirs['base']}' and execute './run_udp_suite.py'")


def main():
    print("--- Advanced UDP QA Automation Agent ---")
    # git_url = input("Enter the Git repository URL: ").strip()
    # For testing, using a known small repo. Replace with input for real use.
    git_url = "https://github.com/pavelzhuravlev/python-udp-simple-chat.git" # Example, replace
    if not git_url:
        print("Git URL cannot be empty. Exiting.")
        return

    project_dirs = setup_project_directories()
    # Modify project_dirs to have a parent for cloned_repo for easier cleanup/management
    project_dirs["cloned_repo_parent"] = project_dirs["cloned_repo"] # utils.clone_repo will make subfolder
    
    try:
        qa_reference_file = phase_1_information_gathering(git_url, project_dirs)
        if not qa_reference_file:
            return

        generated_assets = phase_2_mock_and_test_generation(qa_reference_file, project_dirs)
        if not generated_assets:
            return
            
        phase_3_iterative_testing(generated_assets, project_dirs)
        
        phase_4_packaging_and_output(project_dirs, generated_assets)

    except Exception as e:
        print(f"\n--- An Unhandled Error Occurred in the Agent ---")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Optional: cleanup cloned repo if desired, or leave for inspection
        # cleanup_directory(project_dirs["cloned_repo_parent"]) # Careful with this
        print("\n--- Agent Finished ---")


if __name__ == "__main__":
    main()
