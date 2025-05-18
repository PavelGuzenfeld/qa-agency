# agent_prompts.py

# --- Phase 1: Information Gathering ---

def get_udp_info_extraction_prompt(filepath: str, file_content: str) -> str:
    """
    Generates the prompt for extracting UDP service information from a file.
    """
    # Basic truncation if file_content is too long for the context window
    # A more sophisticated approach would involve chunking or summarization.
    max_content_length = 6000 # Adjusted for an 8k context, leaving room for prompt and response
    if len(file_content) > max_content_length:
        file_content = file_content[:max_content_length] + "\n\n[CONTENT TRUNCATED DUE TO LENGTH]"

    return f"""
You are a QA information extraction assistant. Analyze the following file content from '{filepath}':
---
{file_content}
---
Extract any information relevant for testing UDP-based services. This includes, but is not limited to:
- UDP port numbers used by services.
- IP addresses or hostnames services might bind to or expect communication from (e.g., 0.0.0.0, 127.0.0.1, specific IPs).
- Message formats (e.g., plain text, JSON, binary structures, Protobuf, custom protocols over UDP). Provide examples if found.
- Expected sequences of messages or interaction patterns.
- Any acknowledgment mechanisms or expected response packets (if the UDP protocol is designed to send them).
- Business logic or rules triggered by specific UDP messages.
- Validation rules for incoming UDP packet payloads.
- Potential error conditions or how the service behaves with malformed/unexpected packets.
- Dependencies on other services (even if over UDP).
- Potential edge cases for UDP communication (e.g., large payloads, rapid bursts of packets).

Format the extracted information clearly and concisely. If no relevant UDP QA information is found, state that explicitly.
Organize the findings by potential service or port if discernible.
Example of desired output format for a finding:
Port: [Port Number, e.g., 5005]
Message Format: [Description, e.g., JSON: {{"action": "...", "payload": "..."}}]
Expected Behavior: [Description, e.g., Responds with an ACK packet if action is 'register']
---
Extracted Information:
"""

# --- Phase 2: Mock & Test Generation ---

def get_identify_udp_services_prompt(qa_reference_content: str) -> str:
    """
    Generates the prompt to identify distinct UDP services from the QA reference.
    """
    max_content_length = 7000
    if len(qa_reference_content) > max_content_length:
        qa_reference_content = qa_reference_content[:max_content_length] + "\n\n[QA REFERENCE TRUNCATED]"

    return f"""
Based on the following QA Reference document, which contains extracted information about potential UDP services:
---
{qa_reference_content}
---
List all distinct UDP services that should be tested. For each service, provide:
1. A descriptive name (e.g., "Telemetry Service", "Game State Updater").
2. The primary UDP port number associated with it.
3. A brief summary of its expected message interaction or functionality.

Format each service as:
Service Name: [Name]
Port: [Port Number]
Functionality Summary: [Summary]

If no clear services can be identified, state that.
---
Identified UDP Services:
"""

def get_mock_udp_listener_prompt(port_number: int, service_functionality: str, relevant_qa_snippet: str) -> str:
    """
    Generates the prompt for creating a mock UDP listener.
    """
    max_content_length = 6000
    if len(relevant_qa_snippet) > max_content_length:
        relevant_qa_snippet = relevant_qa_snippet[:max_content_length] + "\n\n[QA SNIPPET TRUNCATED]"

    return f"""
You are a Mock UDP Service Generator. Based on the following QA information for the UDP service on port {port_number} expecting messages related to '{service_functionality}':
---
{relevant_qa_snippet}
---
Generate a Python script for a mock UDP listener using the 'socket' library.
- The mock should listen on '0.0.0.0' and the specified port {port_number}.
- It should receive UDP packets in a loop.
- Based on the QA information (expected message formats/content), it should:
    - Print (log to stdout) the received message content and the sender's address (IP, port).
    - If the service is supposed to send a response packet after receiving a specific type of message (as indicated in the QA info), simulate that response by sending a reply packet back to the source IP/port of the incoming packet.
    - If different incoming messages trigger different mock behaviors or responses, implement simple conditional logic for this.
    - If message formats are specified (e.g., JSON), attempt to decode/parse them and log appropriately. Handle potential decoding errors gracefully.
- Make the mock runnable as a standalone Python script.
- It should print a message like "Mock UDP listener started on 0.0.0.0:{port_number}" when it successfully binds the socket.
- Include basic error handling for socket operations.
- Ensure the script can be terminated gracefully (e.g., with Ctrl+C).

Provide only the Python code block, without any surrounding text or explanations.
"""

def get_udp_test_script_prompt(port_number: int, service_functionality: str, relevant_qa_snippet: str, mock_listener_code: str) -> str:
    """
    Generates the prompt for creating a UDP test script.
    """
    max_qa_len = 3000
    max_mock_code_len = 3000
    if len(relevant_qa_snippet) > max_qa_len:
        relevant_qa_snippet = relevant_qa_snippet[:max_qa_len] + "\n\n[QA SNIPPET TRUNCATED]"
    if len(mock_listener_code) > max_mock_code_len:
        mock_listener_code = mock_listener_code[:max_mock_code_len] + "\n\n[MOCK CODE TRUNCATED]"


    return f"""
You are a Python QA Test Script Generator for UDP services.
QA Information for UDP service on port {port_number} related to '{service_functionality}':
---
{relevant_qa_snippet}
---
Mock UDP Listener code (for reference, this mock will be running on localhost:{port_number}):
---
{mock_listener_code}
---
Generate a Python test script using the 'unittest' and 'socket' libraries to test this UDP service.
- The tests MUST target a local mock UDP listener running on 'localhost' and port {port_number}.
- The test script should define a class inheriting from `unittest.TestCase`.
- Each test method should:
    - Create a UDP socket.
    - Construct and send UDP packets with payloads as suggested by the QA information. Encode strings to bytes (e.g., using UTF-8).
    - If the mock is expected to send a response packet (based on the QA info or mock code), the test should attempt to receive it using `socket.recvfrom()` with a reasonable timeout (e.g., 1-2 seconds).
    - Include assertions for:
        - The content of received response packets (if applicable), after decoding bytes to string.
        - If no direct response is expected, the test might focus on sending specific sequences of packets. (For this MVP, focus on tests that expect a direct response if one is implied by the QA info).
- Use `self.assertEqual()`, `self.assertIn()`, `self.assertTrue()`, etc., for assertions.
- Handle socket timeouts gracefully in tests that expect responses (e.g., assert that a timeout occurred if no response was expected, or fail the test if a response was expected but timed out).
- Include a `if __name__ == '__main__': unittest.main(verbosity=2)` block for detailed output.
- Add comments to explain the test logic.

Provide only the Python code block, without any surrounding text or explanations.
"""

# --- Phase 3: Iterative Testing & Refinement ---

def get_udp_fix_failure_prompt(port_number: int, qa_snippet: str, mock_code: str, test_code: str, test_stdout: str, test_stderr: str, mock_logs: str) -> str:
    """
    Generates the prompt for fixing failed UDP tests.
    """
    # Truncate inputs to manage context window
    max_len = 2000
    qa_snippet = qa_snippet[:max_len] if len(qa_snippet) > max_len else qa_snippet
    mock_code = mock_code[:max_len] if len(mock_code) > max_len else mock_code
    test_code = test_code[:max_len] if len(test_code) > max_len else test_code
    test_stdout = test_stdout[:max_len//2] if len(test_stdout) > max_len//2 else test_stdout
    test_stderr = test_stderr[:max_len//2] if len(test_stderr) > max_len//2 else test_stderr
    mock_logs = mock_logs[:max_len//2] if len(mock_logs) > max_len//2 else mock_logs

    return f"""
The UDP test script for the service on port {port_number} failed.
Original QA Information Snippet:
---
{qa_snippet}
---
Current Mock UDP Listener Code:
---
{mock_code}
---
Current Test Script Code:
---
{test_code}
---
Test Execution Output (stdout):
---
{test_stdout}
---
Test Execution Details/Errors (stderr):
---
{test_stderr}
---
Mock Listener Logs (if available):
---
{mock_logs}
---
Please analyze the failure. Identify whether the issue is likely in the test script (e.g., wrong payload, incorrect listening/assertion logic, encoding/decoding issue) or the mock listener code (e.g., not responding correctly, mishandling incoming packet, port binding issue).
Based on your analysis, provide the necessary changes to the incorrect file(s) to make the test pass according to the original QA information.
If modifying code, provide the complete updated code for ONLY the changed file(s). Clearly indicate which file the code belongs to (e.g., "Updated Mock Code:" or "Updated Test Script Code:").
If the issue is ambiguous, explain your reasoning and suggest what to check or try next.
"""

def get_udp_edge_case_generation_prompt(port_number: int, qa_snippet: str, mock_code: str, test_code: str) -> str:
    """
    Generates the prompt for suggesting UDP edge cases.
    """
    max_len = 2500
    qa_snippet = qa_snippet[:max_len] if len(qa_snippet) > max_len else qa_snippet
    mock_code = mock_code[:max_len] if len(mock_code) > max_len else mock_code
    test_code = test_code[:max_len] if len(test_code) > max_len else test_code

    return f"""
The following tests for the UDP service on port {port_Number} are now passing when run against its mock server.
QA Information Snippet:
---
{qa_snippet}
---
Current Mock UDP Listener Code:
---
{mock_code}
---
Current Test Script Code (contains a unittest.TestCase class):
---
{test_code}
---
Based on the QA information and general UDP testing best practices, suggest additional edge cases or boundary conditions that should be tested for this UDP service.
For each suggested edge case:
1. Provide a brief description of the edge case.
2. Provide the complete Python `unittest` test method code to cover this edge case. This new test method should be designed to be added to the existing test class in the current test script. Ensure it uses 'localhost' and port {port_number} for the mock.
3. If the current mock server code needs modification to correctly simulate or handle this edge case (e.g., to respond in a specific way to a malformed packet, or to handle large payloads), provide the complete updated mock server code. If no mock changes are needed for this specific edge case, state that clearly.

Focus on distinct and meaningful edge cases.
Example of a test method:
```python
    def test_edge_case_empty_payload(self):
        # Description: Test sending an empty payload
        # ... socket setup ...
        # self.client_socket.sendto(b"", (self.mock_host, self.mock_port))
        # ... assertions or response handling ...
```
"""

# --- Phase 4: Packaging & Output ---
# Prompts for generating run scripts or READMEs can be simpler,
# mostly instructing the LLM on the structure and content based on collected data.
# For brevity, these are omitted here but would follow a similar pattern.

