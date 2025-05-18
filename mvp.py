import json
import requests # Make sure to install this: pip install requests
import subprocess # Added for running the generated script
import os # Added for file operations
import tempfile # Added for creating a temporary file for the script

# Configuration for the local Ollama LLM
OLLAMA_API_URL = "http://localhost:11434/api/generate" # Default Ollama API endpoint

# With 32GB RAM, you can comfortably run 7B, 8B, or even 13B parameter models.
# Your `ollama list` shows `llama3:latest` (4.7GB), which is suitable.
# We will use this model.
OLLAMA_MODEL = "llama3.3:latest" # <<< UPDATED based on your `ollama list` output
OLLAMA_REQUEST_TIMEOUT = 240 # Timeout for Ollama API requests in seconds

def ask_question(question_text: str, default_value: str = None, validation_type: str = None) -> str:
    """
    Asks the user a question, returns their input, and optionally validates it.
    validation_type can be 'integer'.
    """
    if default_value:
        prompt = f"{question_text} (default: {default_value}): "
    else:
        prompt = f"{question_text}: "

    while True:
        user_input = input(prompt).strip()
        if user_input:
            if validation_type == 'integer':
                try:
                    int(user_input) # Check if it can be converted to an integer
                    return user_input
                except ValueError:
                    print("Invalid input. Please enter a whole number.")
                    continue # Ask again
            else: # No specific validation type or other types
                return user_input
        elif default_value: # If user presses Enter and there's a default
            if validation_type == 'integer': # Validate default if type is integer
                try:
                    int(default_value)
                    return default_value
                except ValueError: # This should ideally not happen if default is well-defined
                    print(f"Internal: Default value '{default_value}' is not a valid integer. Please provide a value.")
                    # Fall through to ask for non-empty input without default
            else:
                return default_value
        
        # If input is empty and no default, or default was invalid for type
        if not default_value or (validation_type == 'integer' and default_value and not default_value.isdigit()):
             print("Input cannot be empty. Please provide a value.")


def interview_user_for_api_test_requirements() -> dict:
    """Conducts an interview with the user to gather API test requirements."""
    print("\n--- QA Requirement Interview ---")
    print("I'll ask a few questions to generate a Python API test script.")

    requirements = {}
    # For testing, you might want to use a public API like JSONPlaceholder
    requirements["base_url"] = ask_question("What is the base URL of the API?", "https://jsonplaceholder.typicode.com")
    requirements["endpoint"] = ask_question("Which specific endpoint do you want to test (e.g., /users, /todos/1)?", "/todos/1")
    requirements["http_method"] = ask_question("What HTTP method (GET, POST, PUT, DELETE)?", "GET").upper()

    if requirements["http_method"] in ["POST", "PUT"]:
        requirements["json_body_example"] = ask_question(
            "What should the JSON body look like for the request? (Provide a simple JSON string or 'skip' if not applicable)",
            '{"title": "foo", "body": "bar", "userId": 1}' # Example for JSONPlaceholder /posts
        )
        if requirements["json_body_example"].lower() == 'skip':
            requirements["json_body_example"] = None
    else:
        requirements["json_body_example"] = None

    # Updated to use validation_type
    requirements["expected_status_code"] = ask_question(
        "Expected HTTP status code for success?",
        "200",
        validation_type='integer'
    )
    requirements["required_headers"] = ask_question(
        "Any specific headers required? (e.g., Authorization:Bearer XXX, Content-Type:application/json or 'none')",
        "Content-Type:application/json; charset=utf-8" # Common for JSON APIs
    )
    if requirements["required_headers"].lower() == 'none':
        requirements["required_headers"] = None


    requirements["response_body_checks"] = ask_question(
        "What key aspects of the response body to verify? (e.g., 'ensure userId field exists and is 1', 'title is not empty', or 'none')",
        "ensure userId field exists" # Example for JSONPlaceholder /todos/1
    )
    if requirements["response_body_checks"].lower() == 'none':
        requirements["response_body_checks"] = None

    print("\n--- Interview Complete. Thank you! ---")
    return requirements

def generate_prompt_for_llm(requirements: dict) -> str:
    """Generates a detailed prompt for the LLM based on gathered requirements."""

    prompt = f"""
You are an expert QA Automation Engineer specializing in Python.
Your task is to generate a Python script for testing a single API endpoint.
The script should use the `requests` library for making HTTP calls and the `unittest` library for structuring the test.
The script must be self-contained and directly runnable with `python <filename>.py`.

Here are the requirements gathered from the user:
- Base URL: {requirements['base_url']}
- Endpoint: {requirements['endpoint']}
- HTTP Method: {requirements['http_method']}
"""
    if requirements['json_body_example']:
        prompt += f"- JSON Body Example for {requirements['http_method']}: {requirements['json_body_example']}\n"

    prompt += f"- Expected HTTP Status Code: {requirements['expected_status_code']}\n"

    if requirements['required_headers']:
        prompt += f"- Required Headers: {requirements['required_headers']}\n"
    else:
        prompt += "- Required Headers: None\n"

    if requirements['response_body_checks']:
        prompt += f"- Response Body Checks: {requirements['response_body_checks']}\n"
    else:
        prompt += "- Response Body Checks: None (but ensure the response can be parsed as JSON if applicable, and basic status assertion)\n"

    prompt += """
Please generate a complete, runnable Python script.
The script should:
1. Import `unittest`, `requests`, and `json`.
2. Define a test class inheriting from `unittest.TestCase`.
3. Include a test method (e.g., `test_api_endpoint`).
4. Construct the full URL.
5. Prepare headers: If headers were specified as a string like "Header1:Value1, Header2:Value2", parse this into a Python dictionary. Handle potential variations in spacing.
6. Prepare the JSON body if it's a POST/PUT request and a body was specified. Ensure it's correctly formatted as a Python dictionary for the `json` parameter of `requests.post` or `requests.put`. If the input is already a valid JSON string, parse it.
7. Make the API call using `requests` within a try-except block to catch potential `requests.exceptions.RequestException`.
8. Assert the HTTP status code using `self.assertEqual()`.
9. If response body checks were specified:
   a. Attempt to parse the response as JSON using `response.json()` within a try-except block for `requests.exceptions.JSONDecodeError`.
   b. Perform the checks using `unittest` assertions (e.g., `self.assertIn`, `self.assertEqual`, `self.assertIsNotNone`). For example, if checking "ensure userId field exists and is 1", use `self.assertIn('userId', response_data)` and `self.assertEqual(response_data.get('userId'), 1)`.
   c. Be robust: if the response is not JSON or a field is missing, the assertions should fail gracefully or be handled.
10. Include a `if __name__ == '__main__': unittest.main(verbosity=2)` block for more detailed output.
11. Add comments to explain the code.

Provide only the Python code block, without any surrounding text or explanations before or after the code block.
"""
    return prompt.strip()

def call_ollama_llm(prompt: str) -> str | None:
    """Calls the local Ollama LLM and returns the generated text."""
    print(f"\nSending request to Ollama model: {OLLAMA_MODEL}. Please wait...")
    headers = {"Content-Type": "application/json"}
    data = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False, # Get the full response at once
        "options": {
            "temperature": 0.2, # Lower temperature for more deterministic and accurate code
            "top_k": 30,
            "top_p": 0.8,
            # "num_ctx": 4096 # If model supports larger context, can be set
        }
    }
    try:
        response = requests.post(OLLAMA_API_URL, headers=headers, data=json.dumps(data), timeout=OLLAMA_REQUEST_TIMEOUT)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        response_json = response.json()
        generated_text = response_json.get("response", "").strip()

        # Clean up common markdown code block delimiters
        if generated_text.startswith("```python"):
            generated_text = generated_text[len("```python"):].strip()
        elif generated_text.startswith("```"): # More generic ``` opening
             generated_text = generated_text[len("```"):].strip()

        if generated_text.endswith("```"):
            generated_text = generated_text[:-len("```")].strip()

        return generated_text

    except requests.exceptions.Timeout:
        print(f"Error: Request to Ollama API timed out after {OLLAMA_REQUEST_TIMEOUT} seconds.")
        print("The model might be too large for quick responses or Ollama might be under heavy load.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        print("Please ensure Ollama is running and the model name is correct and available.")
        print(f"Attempted to connect to: {OLLAMA_API_URL} with model: {OLLAMA_MODEL}")
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON response from Ollama. Raw response:")
        print(response.text if 'response' in locals() else "No response object")
        return None

def run_generated_script(script_content: str) -> tuple[str, str, int]:
    """
    Saves the script content to a temporary file and runs it using subprocess.
    Returns (stdout, stderr, return_code).
    """
    temp_script_path = "temp_test_script.py"
    try:
        with open(temp_script_path, "w", encoding='utf-8') as f:
            f.write(script_content)
        
        print(f"\nExecuting generated script: {temp_script_path}...")
        process = subprocess.run(
            ["python", temp_script_path], # Or "python3" if that's your command
            capture_output=True,
            text=True,
            timeout=90,  # Timeout for the script execution, slightly increased
            check=False 
        )
        print("Script execution finished.")
        return process.stdout, process.stderr, process.returncode
        
    except FileNotFoundError:
        print(f"Error: Python interpreter not found. Make sure 'python' (or 'python3') is in your PATH.")
        return "", "Python interpreter not found.", 1
    except subprocess.TimeoutExpired:
        print("Error: Script execution timed out.")
        return "", "Script execution timed out.", 1
    except Exception as e:
        print(f"An error occurred while trying to run the script: {e}")
        return "", str(e), 1
    finally:
        if os.path.exists(temp_script_path):
            try:
                os.remove(temp_script_path)
            except OSError as e:
                print(f"Error removing temporary script {temp_script_path}: {e}")


def main():
    """Main function to run the QA agent MVP."""
    print("--- Welcome to the QA Automation Agent MVP ---")

    requirements = interview_user_for_api_test_requirements()
    llm_prompt = generate_prompt_for_llm(requirements)
    generated_script = call_ollama_llm(llm_prompt)

    if generated_script:
        print("\n--- Generated Python QA Script ---")
        print(generated_script)
        print("--- End of Generated Script ---")

        stdout, stderr, return_code = run_generated_script(generated_script)

        print("\n--- Script Execution Results ---")
        if stdout:
            print("Output (stdout):\n", stdout)
        # unittest prints its summary to stderr, even for successes
        if stderr: 
            print("Execution Details (stderr):\n", stderr)
        
        print(f"Return Code: {return_code}")

        # Check for unittest success patterns in stderr
        test_passed = False
        if "OK" in stderr and "FAIL" not in stderr and "ERROR" not in stderr:
            test_passed = True
        
        if test_passed:
            print("\nTest script seems to have PASSED.")
        elif "FAIL" in stderr or "ERROR" in stderr:
            print("\nTest script seems to have FAILED or encountered errors during execution.")
        elif return_code != 0: # Catch-all for other non-zero exits
             print("\nTest script execution encountered an issue (non-zero return code).")
        else: # return_code == 0 but no clear "OK"
            print("\nTest script executed. Review output and details for pass/fail status.")
        
        print("\nFurther actions:")
        print("1. Review the execution output above.")
        print("2. If needed, you can still manually save the generated script (printed earlier) for detailed inspection or modification.")

    else:
        print("\nFailed to generate QA script.")

if __name__ == "__main__":
    main()
