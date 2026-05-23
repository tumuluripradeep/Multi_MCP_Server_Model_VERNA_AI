# =============================
# Imports & Setup
# =============================
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from typing import Any, List
import httpx
import urllib.parse
import json
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from langchain_openai import AzureChatOpenAI
import re
from Servers.vector_db.vector_search import vector_get_relevant_content
import asyncio
import logging

# Add proper logging configuration after the imports
# Configure logging to stderr to avoid interfering with MCP JSON protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# =============================
# Load Environment Variables
# =============================
load_dotenv()

# =============================
# MCP Server Initialization
# =============================
mcp = FastMCP("service_system_case")

# =============================
# Constants
# =============================
# --- Case Summary/Resolution ---
SUMMARY_API_BASE_URL = "https://aria-llm-dev.adobe.io/api/v1/llm"
GENERATE_URL = "https://aria-llm-dev.adobe.io/api/v1/llm/generate"

# --- D365 & Sales ---
D365_API_BASE_URL = os.getenv("D365_API_BASE_URL")
D365_DYNAMICS_API_URL = os.getenv("D365_DYNAMICS_API_URL")
D365_TENANT_ID = os.getenv("D365_TENANT_ID")
D365_TOKEN_URL = os.getenv("D365_TOKEN_URL")
D365_CLIENT_ID = os.getenv("D365_CLIENT_ID")
D365_CLIENT_SECRET = os.getenv("D365_CLIENT_SECRET")
D365_SCOPE = os.getenv("D365_SCOPE")

# Account-related endpoints
ACCOUNTS_API_URL = os.getenv("ACCOUNTS_API_URL", f"{D365_DYNAMICS_API_URL}/accounts" if D365_DYNAMICS_API_URL else None)

# =============================
# LLM Initialization
# =============================
llm = AzureChatOpenAI(
    azure_deployment="ats-aria-gpt-4o-mini",
    api_version="2024-02-15-preview",
    temperature=0.2,
    max_tokens=1000,
    max_retries=2,
    timeout=60,
    request_timeout=60
)

# =============================
# Prompt Templates
# =============================
PROBLEM_EXTRACTION_PROMPT = """Extract the core problem statement from the user's query:

User Input: {user_query}

Your task is to identify the main technical problem or issue being described. Focus on:
1. The specific product or service mentioned (e.g., Photoshop, Acrobat, Creative Cloud)
2. The specific issue or error (e.g., crashing, installation error, activation problem)
3. Any contextual details that help clarify the problem

Return ONLY the problem statement as a simple phrase that could be used for searching in a case database.
Do not include any explanations, formatting, or additional text.

Examples:
- If input is "I need help with Photoshop crashing on Windows 11", return "Photoshop crashing Windows 11"
- If input is "Customer is having problems with Acrobat Pro activation", return "Acrobat Pro activation issue"
- If input is "Looking for similar cases to E-001234 where Lightroom won't import photos", return "Lightroom import failure"
"""

EXTRACTION_PROMPT = """
Extract the intent and ticket number from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get support engineer and status")
- "ticket_number": the ticket number (e.g., "E-000129309")
"""

ACCOUNT_EXTRACTION_PROMPT = """
Extract the intent and account name from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get account cases and resolutions", "find account support history")
- "account_name": the account/organization name to search for (e.g., "Microsoft Corporation", "Adobe Inc", "Contoso Ltd")
"""

# =============================
# Utility Functions
# =============================

# --- D365 Data Utilities ---

async def make_authenticated_d365_request(
    method: str,
    url: str,
    payload: dict[str, Any] = None,
    timeout_connect: float = 30.0,
    timeout_total: float = 60.0
) -> dict[str, Any] | None:
    """
    Make an authenticated request to D365 API with standardized error handling.
    
    Args:
        method: HTTP method ('GET' or 'POST')
        url: The API endpoint URL
        payload: Request payload for POST requests
        timeout_connect: Connection timeout in seconds
        timeout_total: Total timeout in seconds
    
    Returns:
        API response as dict or None if failed
    """
    token = await get_dynamics_access_token()
    if not token:
        logger.error("Could not authenticate to Dynamics API.")
        return None
    
    headers = get_dynamics_auth_headers_oauth(token)
    timeout = httpx.Timeout(timeout_total, connect=timeout_connect)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if method.upper() == 'POST':
                response = await client.post(url, headers=headers, json=payload)
            elif method.upper() == 'GET':
                response = await client.get(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"D365 API request failed ({method} {url}): {e}")
            return None

async def make_http_request(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] = None,
    data: dict[str, Any] = None,
    timeout_connect: float = 30.0,
    timeout_total: float = 60.0
) -> dict[str, Any] | None:
    """
    Make a generic HTTP request with standardized error handling.
    
    Args:
        method: HTTP method ('GET' or 'POST')
        url: The API endpoint URL
        headers: Request headers
        payload: JSON payload for POST requests
        data: Form data for POST requests
        timeout_connect: Connection timeout in seconds
        timeout_total: Total timeout in seconds
    
    Returns:
        API response as dict or None if failed
    """
    timeout = httpx.Timeout(timeout_total, connect=timeout_connect)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if method.upper() == 'POST':
                if payload:
                    response = await client.post(url, headers=headers, json=payload)
                elif data:
                    response = await client.post(url, headers=headers, data=data)
                else:
                    response = await client.post(url, headers=headers)
            elif method.upper() == 'GET':
                response = await client.get(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"HTTP request failed ({method} {url}): {e}")
            return None

async def make_d365_request(ticket_number: str, user_id: str) -> dict[str, Any] | None:
    """Make a request to retrieve D365 case data."""
    url = f"{D365_API_BASE_URL}/retrieve_d365"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "ticketNumber": ticket_number,
        "user": {
            "userId": user_id
        }
    }
    return await make_http_request("POST", url, headers, payload=payload)

async def get_case_data(ticket_number: str, user_id: str, query: str | None = None) -> dict[str, Any] | None:
    if query:
        logger.info(f"Fetching case data for ticket: {ticket_number} (query: {query})")
    data = await make_d365_request(ticket_number, user_id)
    return data if data else None

async def get_dynamics_access_token() -> str | None:
    """Get D365 OAuth access token."""
    # Construct token URL using tenant ID if TOKEN_URL not provided
    token_url = D365_TOKEN_URL
    if not token_url and D365_TENANT_ID:
        token_url = f"https://login.microsoftonline.com/{D365_TENANT_ID}/oauth2/v2.0/token"
        logger.info(f"Constructed token URL from tenant ID: {D365_TENANT_ID}")
    
    if not token_url:
        logger.error("D365_TOKEN_URL or D365_TENANT_ID must be configured")
        return None
    
    data = {
        "client_id": D365_CLIENT_ID,
        "client_secret": D365_CLIENT_SECRET,
        "scope": D365_SCOPE,
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    response = await make_http_request("POST", token_url, headers, data=data, timeout_total=60.0, timeout_connect=60.0)
    return response.get("access_token") if response else None

def get_dynamics_auth_headers_oauth(token: str) -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

def extract_json_from_text(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned)
        cleaned = cleaned.strip()
    match = re.search(r'({.*?}|\\[.*?\\])', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)
    try:
        result = json.loads(cleaned)
        if isinstance(result, str):
            result = json.loads(result)
        return result
    except Exception as e:
        raise ValueError(f"Could not parse JSON: {e}\nRaw: {text}")

def extract_user_id_from_query(user_question: str) -> tuple[str, str]:
    """
    Extract user ID from enhanced query format and return cleaned question.
    
    Args:
        user_question: The user question, potentially with [USER_ID: xxx] prefix
        
    Returns:
        tuple: (cleaned_question, user_id or None)
    """
    # Check for [USER_ID: xxx] pattern at the beginning
    user_id_pattern = r'^\[USER_ID:\s*([^\]]+)\]\s*(.+)$'
    match = re.match(user_id_pattern, user_question, re.IGNORECASE)
    
    if match:
        user_id = match.group(1).strip()
        cleaned_question = match.group(2).strip()
        logger.info(f"Extracted user ID: {user_id}")
        return cleaned_question, user_id
    
    return user_question, None

async def extract_problem_statement(user_query: str) -> str:
    prompt = PROBLEM_EXTRACTION_PROMPT.format(user_query=user_query)
    response = await llm.ainvoke(prompt)
    return (response.content if hasattr(response, 'content') else str(response)).strip()

# --- Account-related Utilities ---
async def search_account_by_name(account_name: str) -> dict[str, Any] | None:
    """Search for account details by account name."""
    if not ACCOUNTS_API_URL:
        logger.error("ACCOUNTS_API_URL not configured")
        return None
    
    # Properly encode the account name for OData filter
    encoded_account = urllib.parse.quote_plus(account_name)
    url = f"{ACCOUNTS_API_URL}?$select=accountid,name,accountnumber,description,websiteurl,telephone1,emailaddress1,address1_line1,address1_city,address1_stateorprovince,address1_country&$filter=(contains(name,'{encoded_account}'))&$top=5"
    
    data = await make_authenticated_d365_request("GET", url)
    if data:
        accounts = data.get('value', [])
        return accounts[0] if accounts else None
    return None

async def search_cases_by_account_id(account_id: str, max_results: int = 10) -> List[dict[str, Any]] | None:
    """Search for cases related to a specific account ID."""
    # Try multiple possible relationship field names for account-case relationship
    possible_filters = [
        f"(_customerid_value eq '{account_id}')",  # OData format
        f"(customerid eq '{account_id}')",         # Direct field name (from XML example)
        f"(_primarycontactid_value eq '{account_id}')",
        f"(customerid/accountid eq '{account_id}')",
        f"(_accountid_value eq '{account_id}')"
    ]
    
    # Try each filter until one works
    for filter_condition in possible_filters:
        url = f"{D365_DYNAMICS_API_URL}/incidents?$select=incidentid,ticketnumber,title,description,statuscode,prioritycode,createdon,modifiedon,_customerid_value,_primarycontactid_value&$filter={filter_condition}&$orderby=createdon desc&$top={max_results}"
        
        logger.debug(f"Trying filter: {filter_condition}")
        data = await make_authenticated_d365_request("GET", url)
        if data:
            cases = data.get('value', [])
            if cases:  # If we found cases with this filter, return them
                logger.debug(f"Found {len(cases)} cases with filter: {filter_condition}")
                return cases
        logger.debug(f"Filter {filter_condition} failed or returned no results")
    
    # If no filter worked, try a broader search without account filter
    logger.warning(f"No cases found with account ID filters, trying broader search")
    return None

# --- Case Summary Utilities ---
async def make_summary_request(text: str, locale: str = "en-US") -> dict[str, Any] | None:
    """Make a request to generate case summary."""
    url = f"{SUMMARY_API_BASE_URL}/generate"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "model_params": {"key": "AZURE_TURBO_GPT4_0_MINI"},
        "locale": locale,
        "prompt_params": {
            "system_prompt": "",
            "template": "",
            "key": "SUMMARIZE_CASE",
            "items": [
                {"name": "text", "value": text}
            ]
        }
    }
    return await make_http_request("POST", url, headers, payload=payload, timeout_total=60.0, timeout_connect=60.0)

# --- Case Resolution Utilities ---
async def generate_resolution(context: list[dict[str, Any]], query: str, locale: str = "en-US") -> str | None:
    """Generate resolution for a case query."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "model_params": {"key": "AZURE_TURBO_GPT4_0_MINI"},
        "locale": locale,
        "prompt_params": {
            "system_prompt": "",
            "template": "",
            "key": "RESOLUTION",
            "items": [
                {"name": "context", "value": context},
                {"name": "input", "value": query}
            ]
        }
    }
    data = await make_http_request("POST", GENERATE_URL, headers, payload=payload, timeout_total=60.0, timeout_connect=30.0)
    return data.get("result") if data else None

# =============================
# MCP Tool Functions
# =============================
# --- Case Summary Tools ---
@mcp.tool()
async def service_get_case_summary(ticket_number: str, user_id: str, locale: str = "en-US") -> str:
    logger.debug("service_get_case_summary invoked")
    """
    Summarize a specific support case by ticket number.
    Use this tool to get a clear, concise summary of a support case, including the problem statement, activity summary, and next steps.
    Args:
        ticket_number (str): The ticket number to summarize.
        user_id (str): The user ID for authentication (e.g., "d7f489fb-8349-ea11-a815-000d3a593b7c").
        locale (str): The language locale for the summary (default: en-US).
    Returns:
        str: A formatted summary of the case or an error message.
    """
    case_data = await get_case_data(ticket_number, user_id)
    if not case_data:
        return "Failed to retrieve case data."
    summary_data = await make_summary_request(str(case_data), locale)
    if not summary_data:
        return "Failed to generate case summary."
    return summary_data.get("result", "No summary generated.")

@mcp.prompt("case_summary_prompt")
def case_summary_prompt() -> str:
    """
    The prompt template for case summarization.
    """
    return """Guidelines:
        You are summarizing the data related to a specific support case. Ensure the text is clear and easy to understand. Always use simple language, short sentences, and bullet points as appropriate. Avoid technical jargon unless necessary, and explain any complex terms. Identify which parties are the customer and which are the support engineer.

        You will be provided with a combination of case attributes and case activities. The case attributes are informational and should not be used to infer progress or activity. When the only information you have on activity is based on one of these attributes, call it out specifically.

        You should always do this:
        Use simple language, short sentences, and bullet points as appropriate.
        Avoid technical jargon unless necessary, and explain any complex terms.
        Identify which parties are the customer and which are the support engineer.
        Only generate text supported by the context you are provided.
        Avoid repeating information.

        You should never do this:
        Make assumptions or inferences not directly supported by the context you are provided.
        Embellish or ascribe connotation to customer impact or sentiment if those terms are not used in the source context.

        You should generate the summary in three sections.
        Problem Statement: Clearly articulate the core issue faced by the customer in one sentence, be sure to include any key details such as urgency and potential impact.
        Activity Summary: Summarize the key events and actions taken, limiting to five bulleted sentences. Include technical details about the identified issue being reported. Include information about any investigation or findings outlined in the provided context. Ensure each bullet point contains unique information.
        Next Steps: Clearly outline the next steps being taken to address the customer issue, relying exclusively on the activity of the case in the provided context. If the case is closed, use this section to describe the case resolution. If there is no information about next steps, state that explicitly.

        confidence_score: Assign a decimal confidence score on scale of 1, based on the reliability of the provided data.
        Format your response in markdown language and add <br/> tags in place of linebreaks.

        Make sure format is as follows for sections with spacing between each section and sections translated as per locale except confidence_score. Below sections are must show.
        ###Problem Statement
        ###Activity Summary
        ###Next Steps
        Make sure confidence_score are not part of your response but shows as key value pairs json outside the response.

        Context: {text}
        language: {locale}""" 

# --- Case Resolution Tools ---
@mcp.tool()
async def service_get_resolution(query: str, user_id: str, ticketNumber: str | None = None, locale: str = "en-US") -> str:
    logger.debug("service_get_resolution invoked")
    """
    Troubleshoot and resolve software issues, crashes, errors, or problems with Adobe products (e.g., Photoshop, Acrobat, Creative Cloud).
    Use this tool to get step-by-step troubleshooting advice, solutions, or resolutions for software problems described in the user's query, such as application crashes, errors, or how to fix/resolve issues with Adobe software.

    This tool supports:
    - General troubleshooting queries (e.g., "Adobe Photoshop is crashing. help me how can I resolve?")
    - Case-specific queries by providing a support ticket number (e.g., "What is the resolution for ticket E-001159966?")

    Args:
        query (str): The user's problem description (e.g., 'Photoshop is crashing').
        user_id (str): The user ID for authentication (e.g., "d7f489fb-8349-ea11-a815-000d3a593b7c").
        ticketNumber (str | None): Optional support ticket number for case-specific resolution. If provided, the function will use it to fetch and summarize the case along with the query.
        locale (str): The language locale (default: en-US)
    Returns:
        str: Step-by-step resolution, troubleshooting advice, or an error message.
    Note:
        - If ticketNumber is provided, it will be used for case-specific resolution.
        - If ticketNumber is not provided, the function will treat the query as a general troubleshooting request.
    """
    try:
        if ticketNumber:
            case_data = await get_case_data(ticketNumber, user_id)
            if not case_data:
                return "Failed to retrieve case data."
            relevant_content = await vector_get_relevant_content(query, case_data, locale)
        else:
            relevant_content = await vector_get_relevant_content(query, None, locale)
        
        if not relevant_content:
            return "Failed to find relevant content."
        resolution = await generate_resolution(relevant_content, query, locale)
        if not resolution:
            return "Failed to generate resolution."
        return resolution
    except Exception as e:
        return f"An error occurred while generating resolution: {str(e)}"

@mcp.prompt("resolution_prompt")
def resolution_prompt() -> str:
    """
    The prompt template for resolution generation.
    """
    return """
    Based on the provided context and input query, generate a clear and helpful resolution.
    The resolution should:
    1. Address the specific issue or question in the input
    2. Use information from the provided context
    3. Be clear and easy to understand
    4. Include step-by-step instructions when applicable
    5. Provide relevant links or references when available
    
    Context: {context}
    Query: {input}
    """ 

# --- D365 Data Tools ---

async def search_cases_by_problem(problem_statement: str, max_results: int = 5) -> List[dict[str, Any]] | None:
    """
    Search for Dynamics 365 support cases based on a concise problem statement or error description.
    Use this tool to find similar cases in the database for a given issue, error, or problem (e.g., 'Photoshop crashing Windows 11').
    Args:
        problem_statement (str): The core issue or error to search for in case titles.
        max_results (int, optional): Maximum number of cases to return. Default is 5.
    Returns:
        List[dict[str, Any]] | None: A list of case dictionaries matching the problem statement, or None if an error occurs or no results are found.
    """
    logger.debug("search_cases_by_problem invoked")
    encoded_problem = urllib.parse.quote_plus(problem_statement.replace(' ', '%'))
    url = f"{D365_DYNAMICS_API_URL}/incidents?$select=incidentid,ticketnumber,title,description,ent_recordurl&$filter=(contains(title,'{encoded_problem}'))&$top={max_results}"
    
    data = await make_authenticated_d365_request("GET", url)
    return data.get('value', []) if data else None

@mcp.tool()
async def service_search_cases_by_query(user_query: str, max_results: int = 5) -> str:
    logger.debug("service_search_cases_by_query invoked")
    """
    Search for Dynamics 365 support cases by extracting a problem statement from a user's natural language query.
    Use this tool to find similar cases for a described issue, error, or problem using natural language (e.g., 'Find cases where Photoshop is crashing on Mac').
    Args:
        user_query (str): The user's natural language query describing the issue.
        max_results (int, optional): Maximum number of cases to return. Default is 5.
    Returns:
        str: A formatted string of case information matching the extracted problem statement, or an error message if no results are found.
    """
    problem_statement = await extract_problem_statement(user_query)
    cases = await search_cases_by_problem(problem_statement, max_results)
    
    if not cases:
        return f"No cases found matching the problem statement: {problem_statement}"
    
    formatted_cases = []
    for case in cases:
        formatted_cases.append(f"Ticket: {case.get('ticketnumber', 'N/A')}\nTitle: {case.get('title', 'N/A')}\nDescription: {case.get('description', 'N/A')[:200]}...")
    
    return f"Found {len(cases)} cases matching '{problem_statement}':\n\n" + "\n\n".join(formatted_cases)

@mcp.tool()
async def service_handle_case_related_questions(user_question: str, user_id: str = None) -> str:
    logger.debug("service_handle_case_related_questions invoked")
    """
    Answer a user's question about a specific Dynamics 365 support case by extracting the intent and ticket number, retrieving the case data, and generating a concise answer.
    Use this tool to answer questions about case status, support engineer, or other case-specific details (e.g., 'What is the status of E-001159966?').
    Args:
        user_question (str): The user's question, which should mention a ticket number and what they want to know.
        user_id (str): The user ID for authentication (e.g., "d7f489fb-8349-ea11-a815-000d3a593b7c").
    Returns:
        str: A concise, LLM-generated answer to the user's question, or an error message if extraction or retrieval fails.
    """
    try:
        # Extract user ID if present in the query
        cleaned_question, extracted_user_id = extract_user_id_from_query(user_question)
        
        # Use extracted user ID if available, otherwise use provided user_id parameter
        final_user_id = extracted_user_id or user_id
        
        if not final_user_id:
            return "⚠️ User ID is required for service system queries. Please authenticate with your User ID."
        
        logger.debug(f"Processing question: {cleaned_question} with user ID: {final_user_id}")
        
        # Step 1: Extract intent and ticket number
        prompt = EXTRACTION_PROMPT.format(user_question=cleaned_question)
        logger.debug("Extracting intent and ticket number...")
        extraction_response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
        extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
        
        try:
            extraction = extract_json_from_text(extraction_text)
            intent = extraction.get("intent")
            ticket_number = extraction.get("ticket_number")
            logger.debug(f"Extracted - Intent: {intent}, Ticket: {ticket_number}")
        except Exception as e:
            return f"Could not extract intent and ticket number: {e}\nRaw LLM output: {extraction_text}"
        
        if not ticket_number:
            return "Could not find a ticket number in your question."
        
        # Step 2: Get case data
        logger.debug(f"Fetching case data for {ticket_number}...")
        case_data = await asyncio.wait_for(get_case_data(ticket_number, final_user_id), timeout=30.0)
        if not case_data:
            return f"No data found for ticket {ticket_number}."
        
        # Step 3: Generate answer
        logger.debug("Generating answer...")
        answer_prompt = f"""
        The user wants to '{intent}' for the following case data:
        {json.dumps(case_data, indent=2)}

        Write a concise answer for the user.
        """
        answer_response = await asyncio.wait_for(llm.ainvoke(answer_prompt), timeout=30.0)
        answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
        
        logger.debug("Successfully completed processing")
        return answer
        
    except asyncio.TimeoutError:
        return "Request timed out. The operation took too long to complete. Please try again."
    except Exception as e:
        logger.error(f"Error in handle_case_related_questions: {e}")
        return f"An error occurred: {str(e)}" 

@mcp.tool()
async def service_get_account_cases_summary(user_question: str, user_id: str, max_cases: int = 5) -> str:
    """
    Get account details along with related support cases, providing summaries for each case.
    Use this tool to fetch comprehensive account information including all related support cases with individual summaries.
    Args:
        user_question (str): The user's question about an account (e.g., 'Get all cases for Microsoft Corporation account').
        user_id (str): The user ID for authentication (e.g., "d7f489fb-8349-ea11-a815-000d3a593b7c").
        max_cases (int): Maximum number of cases to retrieve and summarize (default: 5).
    Returns:
        str: A comprehensive report with account details and case summaries, or an error message.
    Example:
        result = await service_get_account_cases_summary('Show me all support cases for Adobe Inc', 'user-id-123')
    """
    try:
        logger.debug(f"Processing account question: {user_question}")
        
        # Step 1: Extract intent and account name
        prompt = ACCOUNT_EXTRACTION_PROMPT.format(user_question=user_question)
        extraction_response = await llm.ainvoke(prompt)
        extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
        
        try:
            extraction = extract_json_from_text(extraction_text)
            intent = extraction.get("intent")
            account_name = extraction.get("account_name")
            logger.debug(f"Extracted - Intent: {intent}, Account: {account_name}")
        except Exception as e:
            return f"Could not extract intent and account name: {e}\nRaw LLM output: {extraction_text}"
        
        if not account_name:
            return "Could not find an account name in your question."
        
        # Step 2: Search for account details
        logger.debug(f"Searching for account: {account_name}")
        account = await search_account_by_name(account_name)
        if not account:
            return f"No account found matching: {account_name}"
        
        # Step 3: Get related cases
        account_id = account.get("accountid")
        logger.debug(f"Fetching cases for account ID: {account_id}")
        cases = await search_cases_by_account_id(account_id, max_cases)
        
        if not cases:
            return f"Account found: {account.get('name', 'Unknown')}\nNo support cases found for this account."
        
        # Step 4: Generate summaries for each case
        case_summaries = []
        for case in cases:
            ticket_number = case.get('ticketnumber')
            if ticket_number:
                logger.debug(f"Getting summary for case: {ticket_number}")
                try:
                    # Get detailed case data for summary
                    case_data = await get_case_data(ticket_number, user_id)
                    if case_data:
                        summary = await make_summary_request(str(case_data))
                        if summary:
                            case_summaries.append({
                                "ticket_number": ticket_number,
                                "title": case.get('title', 'N/A'),
                                "status": case.get('statuscode', 'N/A'),
                                "priority": case.get('prioritycode', 'N/A'),
                                "created": case.get('createdon', 'N/A'),
                                "summary": summary.get("result", "Summary not available")
                            })
                        else:
                            case_summaries.append({
                                "ticket_number": ticket_number,
                                "title": case.get('title', 'N/A'),
                                "status": case.get('statuscode', 'N/A'),
                                "priority": case.get('prioritycode', 'N/A'),
                                "created": case.get('createdon', 'N/A'),
                                "summary": "Summary generation failed"
                            })
                    else:
                        case_summaries.append({
                            "ticket_number": ticket_number,
                            "title": case.get('title', 'N/A'),
                            "status": case.get('statuscode', 'N/A'),
                            "priority": case.get('prioritycode', 'N/A'),
                            "created": case.get('createdon', 'N/A'),
                            "summary": "Case data not available"
                        })
                except Exception as e:
                    logger.error(f"Error processing case {ticket_number}: {e}")
                    case_summaries.append({
                        "ticket_number": ticket_number,
                        "title": case.get('title', 'N/A'),
                        "status": case.get('statuscode', 'N/A'),
                        "priority": case.get('prioritycode', 'N/A'),
                        "created": case.get('createdon', 'N/A'),
                        "summary": f"Error processing case: {str(e)}"
                    })
        
        # Step 5: Format comprehensive response
        response_data = {
            "account": account,
            "cases": case_summaries,
            "total_cases": len(cases)
        }
        
        format_prompt = f"""
        The user wants to '{intent}' for the following account and case data:
        {json.dumps(response_data, indent=2)}

        Create a comprehensive, well-formatted report that includes:

        **ACCOUNT DETAILS:**
        - Account name, number, and description
        - Contact information (website, phone, email, address)
        
        **SUPPORT CASES OVERVIEW:**
        - Total number of cases found
        - Brief overview of case distribution by status/priority if relevant
        
        **INDIVIDUAL CASE SUMMARIES:**
        For each case, provide:
        - Ticket number and title
        - Status and priority
        - Creation date
        - Detailed summary (include the full summary content)
        
        Format the response with clear headings, bullet points, and proper spacing.
        Make it easy to read and professional.
        """
        
        final_response = await llm.ainvoke(format_prompt)
        answer = final_response.content if hasattr(final_response, 'content') else str(final_response)
        
        logger.debug("Successfully completed account cases processing")
        return answer
        
    except Exception as e:
        logger.error(f"Error in service_get_account_cases_summary: {e}")
        return f"An error occurred while processing account cases: {str(e)}"

@mcp.tool()
async def service_get_account_cases_resolutions(user_question: str, user_id: str, max_cases: int = 3) -> str:
    """
    Get account details along with related support cases, providing both summaries AND resolutions for each case.
    Use this tool when you need comprehensive account information including detailed troubleshooting resolutions for each case.
    Args:
        user_question (str): The user's question about an account (e.g., 'Get resolutions for all cases for Microsoft Corporation').
        user_id (str): The user ID for authentication (e.g., "d7f489fb-8349-ea11-a815-000d3a593b7c").
        max_cases (int): Maximum number of cases to process with resolutions (default: 3, limited due to processing time).
    Returns:
        str: A comprehensive report with account details, case summaries, and detailed resolutions for each case.
    Example:
        result = await service_get_account_cases_resolutions('Show me resolutions for all Adobe Inc support cases', 'user-id-123')
    """
    try:
        logger.debug(f"Processing account resolutions question: {user_question}")
        
        # Step 1: Extract intent and account name
        prompt = ACCOUNT_EXTRACTION_PROMPT.format(user_question=user_question)
        extraction_response = await llm.ainvoke(prompt)
        extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
        
        try:
            extraction = extract_json_from_text(extraction_text)
            intent = extraction.get("intent")
            account_name = extraction.get("account_name")
            logger.debug(f"Extracted - Intent: {intent}, Account: {account_name}")
        except Exception as e:
            return f"Could not extract intent and account name: {e}\nRaw LLM output: {extraction_text}"
        
        if not account_name:
            return "Could not find an account name in your question."
        
        # Step 2: Search for account details
        logger.debug(f"Searching for account: {account_name}")
        account = await search_account_by_name(account_name)
        if not account:
            return f"No account found matching: {account_name}"
        
        # Step 3: Get related cases
        account_id = account.get("accountid")
        logger.debug(f"Fetching cases for account ID: {account_id}")
        cases = await search_cases_by_account_id(account_id, max_cases)
        
        if not cases:
            return f"Account found: {account.get('name', 'Unknown')}\nNo support cases found for this account."
        
        # Step 4: Generate summaries AND resolutions for each case
        case_details = []
        for case in cases:
            ticket_number = case.get('ticketnumber')
            case_title = case.get('title', 'N/A')
            if ticket_number:
                logger.debug(f"Processing case with summary and resolution: {ticket_number}")
                try:
                    # Get detailed case data
                    case_data = await get_case_data(ticket_number, user_id)
                    
                    case_info = {
                        "ticket_number": ticket_number,
                        "title": case_title,
                        "status": case.get('statuscode', 'N/A'),
                        "priority": case.get('prioritycode', 'N/A'),
                        "created": case.get('createdon', 'N/A'),
                        "summary": "Summary not available",
                        "resolution": "Resolution not available"
                    }
                    
                    if case_data:
                        # Generate summary
                        logger.debug(f"Generating summary for {ticket_number}")
                        summary = await make_summary_request(str(case_data))
                        if summary:
                            case_info["summary"] = summary.get("result", "Summary generation failed")
                        
                        # Generate resolution
                        logger.debug(f"Generating resolution for {ticket_number}")
                        resolution_query = f"Provide troubleshooting steps and resolution for: {case_title}"
                        relevant_content = await vector_get_relevant_content(resolution_query, case_data)
                        if relevant_content:
                            resolution = await generate_resolution(relevant_content, resolution_query)
                            if resolution:
                                case_info["resolution"] = resolution
                            else:
                                case_info["resolution"] = "Resolution generation failed"
                        else:
                            case_info["resolution"] = "No relevant resolution content found"
                    
                    case_details.append(case_info)
                    
                except Exception as e:
                    logger.error(f"Error processing case {ticket_number}: {e}")
                    case_details.append({
                        "ticket_number": ticket_number,
                        "title": case_title,
                        "status": case.get('statuscode', 'N/A'),
                        "priority": case.get('prioritycode', 'N/A'),
                        "created": case.get('createdon', 'N/A'),
                        "summary": f"Error processing case: {str(e)}",
                        "resolution": f"Error generating resolution: {str(e)}"
                    })
        
        # Step 5: Format comprehensive response with resolutions
        response_data = {
            "account": account,
            "cases": case_details,
            "total_cases": len(cases)
        }
        
        format_prompt = f"""
        The user wants to '{intent}' for the following account and detailed case data with resolutions:
        {json.dumps(response_data, indent=2)}

        Create a comprehensive, well-formatted report that includes:

        **ACCOUNT DETAILS:**
        - Account name, number, and description
        - Contact information (website, phone, email, address)
        
        **SUPPORT CASES WITH RESOLUTIONS:**
        For each case, provide a detailed section with:
        
        **Case [Ticket Number]: [Title]**
        - Status: [status]
        - Priority: [priority]  
        - Created: [creation date]
        
        **Summary:**
        [Full summary content]
        
        **Resolution & Troubleshooting:**
        [Full resolution content with step-by-step instructions]
        
        ---
        
        Format the response with clear headings, proper spacing, and professional presentation.
        Make each case section clearly separated and easy to follow.
        Include all resolution details and troubleshooting steps.
        """
        
        final_response = await llm.ainvoke(format_prompt)
        answer = final_response.content if hasattr(final_response, 'content') else str(final_response)
        
        logger.debug("Successfully completed account cases with resolutions processing")
        return answer
        
    except Exception as e:
        logger.error(f"Error in service_get_account_cases_resolutions: {e}")
        return f"An error occurred while processing account cases with resolutions: {str(e)}"

@mcp.tool()
async def service_debug_account_case_relationship(account_name: str, case_id: str) -> str:
    """
    Debug tool to test account-case relationship for a specific case and account.
    Use this to verify if the account search and case filtering are working correctly.
    Args:
        account_name (str): The account name to search for (e.g., 'THE QUANTUM ALLIANCE').
        case_id (str): The case ID to verify (e.g., 'E-001472379').
    Returns:
        str: Debug information showing account search results and case relationship details.
    """
    try:
        debug_info = []
        
        # Step 1: Test account search
        debug_info.append(f"=== DEBUGGING ACCOUNT-CASE RELATIONSHIP ===")
        debug_info.append(f"Account Name: {account_name}")
        debug_info.append(f"Case ID: {case_id}")
        debug_info.append("")
        
        # Search for account
        debug_info.append("Step 1: Searching for account...")
        account = await search_account_by_name(account_name)
        if account:
            debug_info.append(f"✓ Account found:")
            debug_info.append(f"  - Account ID: {account.get('accountid')}")
            debug_info.append(f"  - Account Name: {account.get('name')}")
            debug_info.append(f"  - Account Number: {account.get('accountnumber', 'N/A')}")
        else:
            debug_info.append("✗ Account not found")
            return "\n".join(debug_info)
        
        debug_info.append("")
        
        # Step 2: Test case search with this account
        account_id = account.get('accountid')
        debug_info.append(f"Step 2: Searching for cases with Account ID: {account_id}")
        cases = await search_cases_by_account_id(account_id, 20)  # Get more cases for debugging
        
        if cases:
            debug_info.append(f"✓ Found {len(cases)} cases for this account:")
            target_case_found = False
            for case in cases:
                case_ticket = case.get('ticketnumber', 'N/A')
                case_title = case.get('title', 'N/A')
                if case_ticket == case_id:
                    debug_info.append(f"  ✓ TARGET CASE FOUND: {case_ticket} - {case_title}")
                    target_case_found = True
                else:
                    debug_info.append(f"  - {case_ticket} - {case_title}")
            
            if not target_case_found:
                debug_info.append(f"  ✗ Target case {case_id} NOT found in results")
        else:
            debug_info.append("✗ No cases found for this account")
        
        debug_info.append("")
        
        # Step 3: Try direct case search to verify case exists
        debug_info.append(f"Step 3: Searching for case {case_id} directly...")
        direct_case_url = f"{D365_DYNAMICS_API_URL}/incidents?$select=incidentid,ticketnumber,title,_customerid_value,_primarycontactid_value&$filter=(ticketnumber eq '{case_id}')&$top=1"
        
        data = await make_authenticated_d365_request("GET", direct_case_url)
        if data:
            direct_cases = data.get('value', [])
            
            if direct_cases:
                case_data = direct_cases[0]
                debug_info.append(f"✓ Case found directly:")
                debug_info.append(f"  - Incident ID: {case_data.get('incidentid')}")
                debug_info.append(f"  - Ticket Number: {case_data.get('ticketnumber')}")
                debug_info.append(f"  - Title: {case_data.get('title')}")
                debug_info.append(f"  - Customer ID Value: {case_data.get('_customerid_value', 'N/A')}")
                debug_info.append(f"  - Primary Contact ID Value: {case_data.get('_primarycontactid_value', 'N/A')}")
                
                # Compare with account ID
                if case_data.get('_customerid_value') == account_id:
                    debug_info.append(f"  ✓ Case customer ID matches account ID")
                else:
                    debug_info.append(f"  ✗ Case customer ID does NOT match account ID")
                    debug_info.append(f"    Expected: {account_id}")
                    debug_info.append(f"    Actual: {case_data.get('_customerid_value')}")
            else:
                debug_info.append(f"✗ Case {case_id} not found in system")
        else:
            debug_info.append("✗ Could not get authentication token or API request failed")
        
        return "\n".join(debug_info)
        
    except Exception as e:
        return f"Debug tool error: {str(e)}"


if __name__ == "__main__":
    try:
        logger.info("Starting Case MCP server...")
        import sys
        logger.info(f"Running with Python: {sys.version}")
        logger.info("MCP server initialized")
        
        # Validate critical environment variables before starting
        missing_vars = []
        if not D365_TENANT_ID:
            missing_vars.append("D365_TENANT_ID")
        if not D365_CLIENT_ID:
            missing_vars.append("D365_CLIENT_ID")
        if not D365_CLIENT_SECRET:
            missing_vars.append("D365_CLIENT_SECRET")
        
        if missing_vars:
            logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
            logger.warning("Server will start but D365 API calls may fail")
        
        logger.info("Starting MCP server...")
        from Servers.mcp_http import run_mcp_server

        run_mcp_server(mcp)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error starting MCP server: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

