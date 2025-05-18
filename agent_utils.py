# agent_utils.py
import subprocess
import os
import shutil
import time
import json
import requests # Assuming Ollama interaction, similar to MVP

# --- Ollama Configuration (Should match your setup) ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_DEFAULT_MODEL = "llama3:latest" # Ensure this model is available via `ollama list`
OLLAMA_REQUEST_TIMEOUT = 300 # 5 minutes, adjust as needed for complex generations

# --- Git Utilities ---
def clone_repo(git_url: str, target_parent_dir: str) -> str | None:
    """
    Clones a git repository into a subdirectory within target_parent_dir.
    Returns the path to the cloned repository or None on failure.
    """
    try:
        repo_name = git_url.split('/')[-1].replace('.git', '')
        clone_dir = os.path.join(target_parent_dir, repo_name)

        if os.path.exists(clone_dir):
            print(f"Directory {clone_dir} already exists. Removing old version.")
            shutil.rmtree(clone_dir) # Remove if it exists to ensure a fresh clone

        print(f"Cloning repository {git_url} into {clone_dir}...")
        result = subprocess.run(
            ["git", "clone", git_url, clone_dir],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print("Repository cloned successfully.")
            return clone_dir
        else:
            print(f"Failed to clone repository. Error:\n{result.stderr}")
            return None
    except Exception as e:
        print(f"An error occurred during git clone: {e}")
        return None

# --- File Utilities ---
def scan_files(repo_dir: str, extensions: list = None) -> list:
    """
    Scans a directory for files, optionally filtering by extensions.
    Returns a list of full file paths.
    """
    if extensions is None:
        extensions = ['.py', '.c', '.go', '.md', '.txt', '.json', '.yaml', 'Dockerfile', 'docker-compose.yml'] # Default extensions
    
    relevant_files = []
    for root, _, files in os.walk(repo_dir):
        # Skip .git directory
        if '.git' in root.split(os.sep):
            continue
        for file in files:
            if any(file.endswith(ext) for ext in extensions) or not extensions: # if no extensions specified, take all
                 # A more robust check for file names like Dockerfile (no extension)
                if not extensions and '.' not in file and file not in ['Dockerfile', 'docker-compose.yml']: # crude filter for no-ext
                    if file not in ['Dockerfile', 'docker-compose.yml']: # only include specific no-ext files if filter is empty
                        pass # or include all if truly no filter desired
                
                # Check if file name itself is in extensions (for files like 'Dockerfile')
                is_named_file = file in extensions 
                has_matching_extension = any(file.endswith(ext) for ext in extensions if ext.startswith('.'))

                if is_named_file or has_matching_extension:
                    relevant_files.append(os.path.join(root, file))
    print(f"Found {len(relevant_files)} relevant files for scanning.")
    return relevant_files

def read_file_content(filepath: str) -> str | None:
    """Reads the content of a file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        return None

def save_code_to_file(code: str, filepath: str):
    """Saves the given code content to a specified file."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        print(f"Code saved to {filepath}")
    except Exception as e:
        print(f"Error saving code to {filepath}: {e}")

# --- LLM Interaction ---
def call_ollama_llm(prompt: str, model_name: str = OLLAMA_DEFAULT_MODEL) -> str | None:
    """
    Calls the local Ollama LLM and returns the generated text.
    """
    print(f"\nSending request to Ollama model: {model_name}. Please wait...")
    headers = {"Content-Type": "application/json"}
    data = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": { # General options, can be fine-tuned
            "temperature": 0.3,
            "top_k": 40,
            "top_p": 0.9,
            "num_ctx": 4096 # Adjust if your model and Ollama setup supports larger
        }
    }
    try:
        response = requests.post(OLLAMA_API_URL, headers=headers, data=json.dumps(data), timeout=OLLAMA_REQUEST_TIMEOUT)
        response.raise_for_status()

        response_json = response.json()
        generated_text = response_json.get("response", "").strip()

        # Clean up common markdown code block delimiters
        if generated_text.startswith("```python"):
            generated_text = generated_text[len("```python"):].strip()
        elif generated_text.startswith("```"):
             generated_text = generated_text[len("```"):].strip()
        if generated_text.endswith("```"):
            generated_text = generated_text[:-len("```")].strip()
            
        return generated_text
    except requests.exceptions.Timeout:
        print(f"Error: Request to Ollama API timed out after {OLLAMA_REQUEST_TIMEOUT} seconds.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from Ollama. Raw response: {response.text if 'response' in locals() else 'No response object'}")
        return None

# --- Subprocess Management ---
def start_background_process(script_path: str, args: list = None, cwd: str = None) -> subprocess.Popen | None:
    """Starts a Python script as a background process."""
    command = ["python", script_path] # Or "python3"
    if args:
        command.extend(args)
    try:
        print(f"Starting background process: {' '.join(command)}")
        # For UDP mocks, we might want to capture their stdout for logging/debugging
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(1) # Give it a moment to start up, especially for servers
        
        # Check if process started successfully (optional, basic check)
        if process.poll() is not None: # Process already terminated
            stdout, stderr = process.communicate()
            print(f"Background process {script_path} failed to start or exited quickly.")
            print(f"Stdout:\n{stdout}")
            print(f"Stderr:\n{stderr}")
            return None
        print(f"Background process {script_path} started with PID {process.pid}.")
        return process
    except Exception as e:
        print(f"Error starting background process {script_path}: {e}")
        return None

def stop_background_process(process: subprocess.Popen, script_name: str = "process"):
    """Stops a background process."""
    if process and process.poll() is None: # If process exists and is running
        print(f"Stopping background {script_name} (PID {process.pid})...")
        process.terminate() # Try to terminate gracefully
        try:
            process.wait(timeout=5) # Wait for a few seconds
        except subprocess.TimeoutExpired:
            print(f"Process {script_name} (PID {process.pid}) did not terminate gracefully, killing.")
            process.kill() # Force kill
            process.wait()
        print(f"Background {script_name} (PID {process.pid}) stopped.")
    elif process:
        print(f"Background {script_name} (PID {process.pid}) was already stopped.")


def run_script_and_get_output(script_path: str, args: list = None, cwd: str = None, timeout: int = 60) -> tuple[str, str, int]:
    """
    Runs a script (e.g., a unittest script) and captures its output.
    Returns (stdout, stderr, return_code).
    """
    command = ["python", script_path] # Or "python3"
    if args:
        command.extend(args)
    try:
        print(f"Executing script: {' '.join(command)} in {cwd or '.'}")
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        print(f"Error: Python interpreter or script {script_path} not found.")
        return "", f"Python interpreter or script {script_path} not found.", 1
    except subprocess.TimeoutExpired:
        print(f"Error: Script {script_path} execution timed out after {timeout} seconds.")
        return "", f"Script execution timed out after {timeout} seconds.", 1
    except Exception as e:
        print(f"An error occurred while running script {script_path}: {e}")
        return "", str(e), 1

# --- Directory Management ---
def setup_project_directories(base_dir: str = "generated_udp_qa_suite") -> dict:
    """Creates standard project directories and returns their paths."""
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
        
    print(f"Project directories created under {project_base}")
    return dirs

def cleanup_directory(dir_path: str):
    """Removes a directory and its contents."""
    if os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
            print(f"Cleaned up directory: {dir_path}")
        except Exception as e:
            print(f"Error cleaning up directory {dir_path}: {e}")

