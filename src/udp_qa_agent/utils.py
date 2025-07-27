# src/udp_qa_agent/utils.py
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import requests

# --- Configuration ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_DEFAULT_MODEL = "llama3:latest"  # Ensure this model is available
OLLAMA_REQUEST_TIMEOUT = 300  # 5 minutes

class ProcessError(Exception):
    """Exception raised when a subprocess fails."""
    pass

class LLMError(Exception):
    """Exception raised when the LLM call fails."""
    pass

def clone_repo(git_url: str, target_parent_dir: str) -> Optional[str]:
    """
    Clones a git repository into a subdirectory within target_parent_dir.
    
    Args:
        git_url: URL of the git repository to clone
        target_parent_dir: Directory where the repository should be cloned
        
    Returns:
        Path to the cloned repository or None on failure
    """
    try:
        repo_name = git_url.split('/')[-1].replace('.git', '')
        clone_dir = os.path.join(target_parent_dir, repo_name)

        if os.path.exists(clone_dir):
            print(f"directory {clone_dir} already exists. removing old version.")
            shutil.rmtree(clone_dir)  # Remove if it exists to ensure a fresh clone

        print(f"cloning repository {git_url} into {clone_dir}...")
        result = subprocess.run(
            ["git", "clone", git_url, clone_dir],
            capture_output=True, text=True, check=False
        )
        
        if result.returncode == 0:
            print("repository cloned successfully.")
            return clone_dir
        else:
            print(f"failed to clone repository. error:\n{result.stderr}")
            return None
    except Exception as e:
        print(f"an error occurred during git clone: {e}")
        return None

def scan_files(repo_dir: str, extensions: Optional[List[str]] = None) -> List[str]:
    """
    Scans a directory for files, optionally filtering by extensions.
    
    Args:
        repo_dir: Directory to scan
        extensions: List of file extensions to include, or None for default set
        
    Returns:
        List of full file paths
    """
    if extensions is None:
        extensions = [
            '.py', '.go', '.c', '.cpp', '.java', '.js', '.ts', '.md', '.txt',
            '.json', '.yaml', '.yml', 'Dockerfile', 'docker-compose.yml'
        ]
    
    relevant_files = []
    repo_path = Path(repo_dir)
    
    for path in repo_path.rglob("*"):
        # Skip .git directory
        if '.git' in path.parts:
            continue
            
        # Check if file has an approved extension or matches a special filename
        if path.is_file():
            if any(str(path).endswith(ext) for ext in extensions) or path.name in extensions:
                relevant_files.append(str(path))
    
    print(f"found {len(relevant_files)} relevant files for scanning.")
    return relevant_files

def read_file_content(filepath: str) -> Optional[str]:
    """
    Reads the content of a file.
    
    Args:
        filepath: Path to the file to read
        
    Returns:
        Content of the file or None if the file cannot be read
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"error reading file {filepath}: {e}")
        return None

def save_code_to_file(code: str, filepath: str) -> None:
    """
    Saves the given code content to a specified file.
    
    Args:
        code: Code content to save
        filepath: Path where the file should be saved
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        print(f"code saved to {filepath}")
    except Exception as e:
        print(f"error saving code to {filepath}: {e}")
        raise

def call_ollama_llm(prompt: str, model_name: str = OLLAMA_DEFAULT_MODEL) -> str:
    """
    Calls the local Ollama LLM and returns the generated text.
    
    Args:
        prompt: Prompt to send to the LLM
        model_name: Name of the model to use
        
    Returns:
        Generated text from the LLM
        
    Raises:
        LLMError: If the LLM call fails
    """
    print(f"\nsending request to ollama model: {model_name}. please wait...")
    
    headers = {"Content-Type": "application/json"}
    data = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "top_k": 40,
            "top_p": 0.9,
            "num_ctx": 4096  # Adjust if your model and Ollama setup supports larger
        }
    }
    
    try:
        response = requests.post(
            OLLAMA_API_URL, 
            headers=headers, 
            data=json.dumps(data), 
            timeout=OLLAMA_REQUEST_TIMEOUT
        )
        response.raise_for_status()

        response_json = response.json()
        generated_text = response_json.get("response", "").strip()

        # Clean up common markdown code block delimiters
        generated_text = _clean_code_block(generated_text)
            
        return generated_text
    except requests.exceptions.Timeout:
        error_msg = f"error: request to ollama api timed out after {OLLAMA_REQUEST_TIMEOUT} seconds."
        print(error_msg)
        raise LLMError(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"error calling ollama api: {e}"
        print(error_msg)
        raise LLMError(error_msg)
    except json.JSONDecodeError:
        error_msg = "error decoding json response from ollama"
        print(error_msg)
        raise LLMError(error_msg)

def _clean_code_block(text: str) -> str:
    """Cleans markdown code block delimiters from text."""
    if text.startswith("```python"):
        text = text[len("```python"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()
        
    if text.endswith("```"):
        text = text[:-len("```")].strip()
        
    return text

def start_background_process(
    script_path: str, 
    args: Optional[List[str]] = None, 
    cwd: Optional[str] = None
) -> Optional[subprocess.Popen]:
    """
    Starts a Python script as a background process.
    
    Args:
        script_path: Path to the script to run
        args: Additional arguments for the script
        cwd: Working directory for the script
        
    Returns:
        Popen object for the process or None if the process failed to start
    """
    command = ["python", script_path]  # Or "python3" on some systems
    if args:
        command.extend(args)
        
    try:
        print(f"starting background process: {' '.join(command)}")
        process = subprocess.Popen(
            command, 
            cwd=cwd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        time.sleep(1)  # Give it a moment to start up
        
        # Check if process started successfully
        if process.poll() is not None:  # Process already terminated
            stdout, stderr = process.communicate()
            print(f"background process {script_path} failed to start or exited quickly.")
            print(f"stdout:\n{stdout}")
            print(f"stderr:\n{stderr}")
            return None
            
        print(f"background process {script_path} started with pid {process.pid}.")
        return process
    except Exception as e:
        print(f"error starting background process {script_path}: {e}")
        return None

def stop_background_process(
    process: subprocess.Popen, 
    script_name: str = "process"
) -> None:
    """
    Stops a background process.
    
    Args:
        process: Process to stop
        script_name: Name of the process for logging
    """
    if process and process.poll() is None:  # If process exists and is running
        print(f"stopping background {script_name} (pid {process.pid})...")
        process.terminate()  # Try to terminate gracefully
        
        try:
            process.wait(timeout=5)  # Wait for a few seconds
        except subprocess.TimeoutExpired:
            print(f"process {script_name} (pid {process.pid}) did not terminate gracefully, killing.")
            process.kill()  # Force kill
            process.wait()
            
        print(f"background {script_name} (pid {process.pid}) stopped.")
    elif process:
        print(f"background {script_name} (pid {process.pid}) was already stopped.")

def run_script_and_get_output(
    script_path: str, 
    args: Optional[List[str]] = None, 
    cwd: Optional[str] = None, 
    timeout: int = 60
) -> Tuple[str, str, int]:
    """
    Runs a script and captures its output.
    
    Args:
        script_path: Path to the script to run
        args: Additional arguments for the script
        cwd: Working directory for the script
        timeout: Timeout for the script execution in seconds
        
    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    command = ["python", script_path]  # Or "python3" on some systems
    if args:
        command.extend(args)
        
    try:
        print(f"executing script: {' '.join(command)} in {cwd or '.'}")
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            timeout=timeout, 
            check=False, 
            cwd=cwd
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        error_msg = f"error: python interpreter or script {script_path} not found."
        print(error_msg)
        return "", error_msg, 1
    except subprocess.TimeoutExpired:
        error_msg = f"error: script {script_path} execution timed out after {timeout} seconds."
        print(error_msg)
        return "", error_msg, 1
    except Exception as e:
        error_msg = f"an error occurred while running script {script_path}: {e}"
        print(error_msg)
        return "", str(e), 1

def setup_project_directories(base_dir: str = "generated_udp_qa_suite") -> Dict[str, str]:
    """
    Creates standard project directories.
    
    Args:
        base_dir: Base directory name
        
    Returns:
        Dictionary of directory paths
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_base = f"{base_dir}_{timestamp}"
    
    dirs = {
        "base": project_base,
        "cloned_repo": os.path.join(project_base, "cloned_repo_src"),
        "qa_reference": os.path.join(project_base, "qa_reference"),
        "mocks": os.path.join(project_base, "mocks"),
        "tests": os.path.join(project_base, "tests"),
    }
    
    for dir_path in dirs.values():
        os.makedirs(dir_path, exist_ok=True)
        
    print(f"project directories created under {project_base}")
    return dirs

def cleanup_directory(dir_path: str) -> None:
    """
    Removes a directory and its contents.
    
    Args:
        dir_path: Path to the directory to remove
    """
    if os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
            print(f"cleaned up directory: {dir_path}")
        except Exception as e:
            print(f"error cleaning up directory {dir_path}: {e}")