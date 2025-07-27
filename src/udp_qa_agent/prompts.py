# src/udp_qa_agent/prompts.py
from typing import Dict, List, Optional

# Function to generate a prompt for extracting UDP service information from a file
def get_udp_info_extraction_prompt(filepath: str, file_content: str) -> str:
    """
    Generates a prompt for extracting UDP service information from a file.
    
    Args:
        filepath: Path to the file being analyzed
        file_content: Content of the file
        
    Returns:
        Generated prompt
    """
    # Apply maximum length constraints to avoid exceeding context windows
    max_content_length = 6000
    if len(file_content) > max_content_length:
        file_content = file_content[:max_content_length] + "\n\n[CONTENT TRUNCATED DUE TO LENGTH]"

    return f"""
you are a qa information extraction assistant. analyze the following file content from '{filepath}':
---
{file_content}
---
extract any information relevant for testing udp-based services. this includes, but is not limited to:
- udp port numbers used by services.
- ip addresses or hostnames services might bind to or expect communication from (e.g., 0.0.0.0, 127.0.0.1, specific ips).
- message formats (e.g., plain text, json, binary structures, protobuf, custom protocols over udp). provide examples if found.
- expected sequences of messages or interaction patterns.
- any acknowledgment mechanisms or expected response packets (if the udp protocol is designed to send them).
- business logic or rules triggered by specific udp messages.
- validation rules for incoming udp packet payloads.
- potential error conditions or how the service behaves with malformed/unexpected packets.
- dependencies on other services (even if over udp).
- potential edge cases for udp communication (e.g., large payloads, rapid bursts of packets).

format the extracted information clearly and concisely. if no relevant udp qa information is found, state that explicitly.
organize the findings by potential service or port if discernible.
example of desired output format for a finding:
port: [port number, e.g., 5005]
message format: [description, e.g., json: {{"action": "...", "payload": "..."}}]
expected behavior: [description, e.g., responds with an ack packet if action is 'register']
---
extracted information:
"""

def get_identify_udp_services_prompt(qa_reference_content: str) -> str:
    """
    Generates a prompt to identify distinct UDP services from the QA reference.
    
    Args:
        qa_reference_content: Content of the QA reference
        
    Returns:
        Generated prompt
    """
    max_content_length = 7000
    if len(qa_reference_content) > max_content_length:
        qa_reference_content = qa_reference_content[:max_content_length] + "\n\n[QA REFERENCE TRUNCATED]"

    return f"""
based on the following qa reference document, which contains extracted information about potential udp services:
---
{qa_reference_content}
---
list all distinct udp services that should be tested. for each service, provide:
1. a descriptive name (e.g., "telemetry service", "game state updater").
2. the primary udp port number associated with it.
3. a brief summary of its expected message interaction or functionality.

format each service as:
service name: [name]
port: [port number]
functionality summary: [summary]

if no clear services can be identified, state that.
---
identified udp services:
"""

def get_mock_udp_listener_prompt(port_number: int, service_functionality: str, relevant_qa_snippet: str) -> str:
    """
    Generates a prompt for creating a mock UDP listener.
    
    Args:
        port_number: Port number for the UDP service
        service_functionality: Description of the service functionality
        relevant_qa_snippet: Relevant portion of the QA reference
        
    Returns:
        Generated prompt
    """
    max_content_length = 6000
    if len(relevant_qa_snippet) > max_content_length:
        relevant_qa_snippet = relevant_qa_snippet[:max_content_length] + "\n\n[QA SNIPPET TRUNCATED]"

    return f"""
you are a mock udp service generator. based on the following qa information for the udp service on port {port_number} expecting messages related to '{service_functionality}':
---
{relevant_qa_snippet}
---
generate a python script for a mock udp listener using the 'socket' library.
- the mock should listen on '0.0.0.0' and the specified port {port_number}.
- it should receive udp packets in a loop.
- based on the qa information (expected message formats/content), it should:
    - print (log to stdout) the received message content and the sender's address (ip, port).
    - if the service is supposed to send a response packet after receiving a specific type of message (as indicated in the qa info), simulate that response by sending a reply packet back to the source ip/port of the incoming packet.
    - if different incoming messages trigger different mock behaviors or responses, implement simple conditional logic for this.
    - if message formats are specified (e.g., json), attempt to decode/parse them and log appropriately. handle potential decoding errors gracefully.
- make the mock runnable as a standalone python script.
- it should print a message like "mock udp listener started on 0.0.0.0:{port_number}" when it successfully binds the socket.
- include basic error handling for socket operations.
- ensure the script can be terminated gracefully (e.g., with ctrl+c).

provide only the python code block, without any surrounding text or explanations.
"""

def get_udp_test_script_prompt(port_number: int, service_functionality: str, relevant_qa_snippet: str, mock_listener_code: str) -> str:
    """
    Generates a prompt for creating a UDP test script.
    
    Args:
        port_number: Port number for the UDP service
        service_functionality: Description of the service functionality
        relevant_qa_snippet: Relevant portion of the QA reference
        mock_listener_code: Code for the mock UDP listener
        
    Returns:
        Generated prompt
    """
    max_qa_len = 3000
    max_mock_code_len = 3000
    
    if len(relevant_qa_snippet) > max_qa_len:
        relevant_qa_snippet = relevant_qa_snippet[:max_qa_len] + "\n\n[QA SNIPPET TRUNCATED]"
        
    if len(mock_listener_code) > max_mock_code_len:
        mock_listener_code = mock_listener_code[:max_mock_code_len] + "\n\n[MOCK CODE TRUNCATED]"

    return f"""
you are a python qa test script generator for udp services.
qa information for udp service on port {port_number} related to '{service_functionality}':
---
{relevant_qa_snippet}
---
mock udp listener code (for reference, this mock will be running on localhost:{port_number}):
---
{mock_listener_code}
---
generate a python test script using the 'unittest' and 'socket' libraries to test this udp service.
- the tests must target a local mock udp listener running on 'localhost' and port {port_number}.
- the test script should define a class inheriting from `unittest.testcase`.
- each test method should:
    - create a udp socket.
    - construct and send udp packets with payloads as suggested by the qa information. encode strings to bytes (e.g., using utf-8).
    - if the mock is expected to send a response packet (based on the qa info or mock code), the test should attempt to receive it using `socket.recvfrom()` with a reasonable timeout (e.g., 1-2 seconds).
    - include assertions for:
        - the content of received response packets (if applicable), after decoding bytes to string.
        - if no direct response is expected, the test might focus on sending specific sequences of packets. (for this mvp, focus on tests that expect a direct response if one is implied by the qa info).
- use `self.assertequal()`, `self.assertin()`, `self.asserttrue()`, etc., for assertions.
- handle socket timeouts gracefully in tests that expect responses (e.g., assert that a timeout occurred if no response was expected, or fail the test if a response was expected but timed out).
- include a `if __name__ == '__main__': unittest.main(verbosity=2)` block for detailed output.
- add comments to explain the test logic.

provide only the python code block, without any surrounding text or explanations.
"""

def get_udp_fix_failure_prompt(port_number: int, qa_snippet: str, mock_code: str, test_code: str, test_stdout: str, test_stderr: str, mock_logs: str) -> str:
    """
    Generates a prompt for fixing failed UDP tests.
    
    Args:
        port_number: Port number for the UDP service
        qa_snippet: Relevant portion of the QA reference
        mock_code: Code for the mock UDP listener
        test_code: Code for the test script
        test_stdout: Output of the test script
        test_stderr: Error output of the test script
        mock_logs: Logs from the mock listener
        
    Returns:
        Generated prompt
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
the udp test script for the service on port {port_number} failed.
original qa information snippet:
---
{qa_snippet}
---
current mock udp listener code:
---
{mock_code}
---
current test script code:
---
{test_code}
---
test execution output (stdout):
---
{test_stdout}
---
test execution details/errors (stderr):
---
{test_stderr}
---
mock listener logs (if available):
---
{mock_logs}
---
please analyze the failure. identify whether the issue is likely in the test script (e.g., wrong payload, incorrect listening/assertion logic, encoding/decoding issue) or the mock listener code (e.g., not responding correctly, mishandling incoming packet, port binding issue).
based on your analysis, provide the necessary changes to the incorrect file(s) to make the test pass according to the original qa information.
if modifying code, provide the complete updated code for only the changed file(s). clearly indicate which file the code belongs to (e.g., "updated mock code:" or "updated test script code:").
if the issue is ambiguous, explain your reasoning and suggest what to check or try next.
"""

def get_udp_edge_case_generation_prompt(port_number: int, qa_snippet: str, mock_code: str, test_code: str) -> str:
    """
    Generates a prompt for suggesting UDP edge cases.
    
    Args:
        port_number: Port number for the UDP service
        qa_snippet: Relevant portion of the QA reference
        mock_code: Code for the mock UDP listener
        test_code: Code for the test script
        
    Returns:
        Generated prompt
    """
    max_len = 2500
    qa_snippet = qa_snippet[:max_len] if len(qa_snippet) > max_len else qa_snippet
    mock_code = mock_code[:max_len] if len(mock_code) > max_len else mock_code
    test_code = test_code[:max_len] if len(test_code) > max_len else test_code

    return f"""
the following tests for the udp service on port {port_number} are now passing when run against its mock server.
qa information snippet:
---
{qa_snippet}
---
current mock udp listener code:
---
{mock_code}
---
current test script code (contains a unittest.testcase class):
---
{test_code}
---
based on the qa information and general udp testing best practices, suggest additional edge cases or boundary conditions that should be tested for this udp service.
for each suggested edge case:
1. provide a brief description of the edge case.
2. provide the complete python `unittest` test method code to cover this edge case. this new test method should be designed to be added to the existing test class in the current test script. ensure it uses 'localhost' and port {port_number} for the mock.
3. if the current mock server code needs modification to correctly simulate or handle this edge case (e.g., to respond in a specific way to a malformed packet, or to handle large payloads), provide the complete updated mock server code. if no mock changes are needed for this specific edge case, state that clearly.

focus on distinct and meaningful edge cases.
example of a test method:
```python
    def test_edge_case_empty_payload(self):
        # description: test sending an empty payload
        # ... socket setup ...
        # self.client_socket.sendto(b"", (self.mock_host, self.mock_port))
        # ... assertions or response handling ...```