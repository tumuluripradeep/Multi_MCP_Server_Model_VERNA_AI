# =============================
# Environment Setup & Imports
# =============================
from typing import Any, List
import httpx
import urllib.parse
import json
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from langchain_openai import AzureChatOpenAI
import re

# =============================
# Load Environment Variables
# =============================
load_dotenv()

# =============================
# MCP Server Initialization
# =============================
mcp = FastMCP("d365_data")

# =============================
# Dynamics 365 & Sales Constants
# =============================
# Customer Service System
D365_API_BASE_URL = os.getenv("D365_API_BASE_URL")
D365_DYNAMICS_API_URL = os.getenv("D365_DYNAMICS_API_URL")
D365_TOKEN_URL = os.getenv("D365_TOKEN_URL")
D365_CLIENT_ID = os.getenv("D365_CLIENT_ID")
D365_CLIENT_SECRET = os.getenv("D365_CLIENT_SECRET")
D365_SCOPE = os.getenv("D365_SCOPE")
# Sales and Marketing Systems
DYNAMICS_SALES_URL_BASE = os.getenv("DYNAMICS_SALES_URL_BASE")
DYNAMICS_SALES_CLIENT_ID = os.getenv("DYNAMICS_SALES_CLIENT_ID")
DYNAMICS_SALES_CLIENT_SECRET = os.getenv("DYNAMICS_SALES_CLIENT_SECRET")
DYNAMICS_SALES_TENANT_ID = os.getenv("DYNAMICS_SALES_TENANT_ID")
DYNAMICS_SALES_SCOPE = os.getenv("DYNAMICS_SALES_SCOPE")
DYNAMICS_SALES_TOKEN_URL = os.getenv("DYNAMICS_SALES_TOKEN_URL")
CAMPAIGNS_URL_BASE = os.getenv("CAMPAIGNS_URL_BASE")

# =============================
# LLM Initialization
# =============================
llm = AzureChatOpenAI(
    azure_deployment="ats-aria-gpt-4o-mini",
    api_version="2024-02-15-preview",
    temperature=0.2,
    max_tokens=1000,
    max_retries=3
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

SALES_EXTRACTION_PROMPT = '''
Extract the intent and subject for a Dynamics Sales lead query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get lead details", "find leads for campaign")
- "subject": the subject to search for (e.g., "Adobe Photoshop license needed")
'''

CAMPAIGN_EXTRACTION_PROMPT = '''
Extract the intent and campaign name for a Dynamics Sales campaign query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get campaign details", "find campaigns")
- "campaign_name": the campaign name to search for (e.g., "Adobe Photoshop")
'''

# =============================
# Utility Functions
# =============================

async def make_d365_request(ticket_number: str) -> dict[str, Any] | None:
    """
    Make a request to the D365 API and return the response as a dictionary.
    """
    url = f"{D365_API_BASE_URL}/retrieve_d365"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "ticketNumber": ticket_number
    }
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as e:
            print(f"Request timed out for ticket {ticket_number}: {str(e)}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred for ticket {ticket_number}: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error occurred for ticket {ticket_number}: {str(e)}")
            return None

async def get_case_data(ticket_number: str, query: str | None = None) -> dict[str, Any] | None:
    """
    Get case data for a given ticket number.
    """
    if query:
        print(f"Fetching case data for ticket: {ticket_number} (query: {query})")
    data = await make_d365_request(ticket_number)
    if not data:
        return None
    return data

async def get_dynamics_access_token() -> str | None:
    """
    Fetch an OAuth2 access token for Dynamics API using client credentials flow.
    """
    data = {
        "client_id": D365_CLIENT_ID,
        "client_secret": D365_CLIENT_SECRET,
        "scope": D365_SCOPE,
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(D365_TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
            token = response.json().get("access_token")
            if not token:
                print("Failed to obtain access token: No token in response")
            return token
        except Exception as e:
            print(f"Failed to obtain access token: {e}")
            return None

def get_dynamics_auth_headers_oauth(token: str) -> dict:
    """
    Get headers for Dynamics API with Bearer token.
    """
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

def extract_json_from_text(text):
    """
    Extract and parse a JSON object from a string, handling code block formatting.
    """
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

async def extract_problem_statement(user_query: str) -> str:
    """
    Use LLM to extract a problem statement from the user's query.
    """
    prompt = PROBLEM_EXTRACTION_PROMPT.format(user_query=user_query)
    response = await llm.ainvoke(prompt)
    problem_statement = response.content if hasattr(response, 'content') else str(response)
    return problem_statement.strip()

async def get_dynamics_sales_access_token() -> str | None:
    """
    Fetch an OAuth2 access token for Dynamics Sales API using client credentials flow.
    """
    data = {
        "client_id": DYNAMICS_SALES_CLIENT_ID,
        "client_secret": DYNAMICS_SALES_CLIENT_SECRET,
        "scope": DYNAMICS_SALES_SCOPE,
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(DYNAMICS_SALES_TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
            token = response.json().get("access_token")
            if not token:
                print("Failed to obtain access token for Dynamics Sales: No token in response")
            return token
        except Exception as e:
            print(f"Failed to obtain access token for Dynamics Sales: {e}")
            return None

# =============================
# MCP Tool Functions
# =============================

@mcp.tool()
async def search_cases_by_problem(problem_statement: str, max_results: int = 5) -> List[dict[str, Any]] | None:
    """
    Search for Dynamics 365 cases based on a concise problem statement.

    Args:
        problem_statement (str): The core issue or error to search for in case titles. Example: 'Photoshop crashing Windows 11'.
        max_results (int, optional): Maximum number of cases to return. Default is 5.

    Returns:
        List[dict[str, Any]] | None: A list of case dictionaries matching the problem statement, or None if an error occurs or no results are found.

    Example:
        results = await search_cases_by_problem('Acrobat activation issue', max_results=3)
    """
    encoded_problem = urllib.parse.quote_plus(problem_statement.replace(' ', '%'))
    url = f"{D365_DYNAMICS_API_URL}/incidents?$select=incidentid,ticketnumber,title,description,ent_recordurl&$filter=(contains(title,'{encoded_problem}'))&$top={max_results}"
    token = await get_dynamics_access_token()
    if not token:
        print("Could not authenticate to Dynamics API.")
        return None
    headers = get_dynamics_auth_headers_oauth(token)
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get('value', [])
        except httpx.TimeoutException as e:
            print(f"Request timed out for problem '{problem_statement}': {str(e)}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred for problem '{problem_statement}': {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error occurred for problem '{problem_statement}': {str(e)}")
            return None

@mcp.tool()
async def search_cases_by_query(user_query: str, max_results: int = 5) -> List[dict[str, Any]] | None:
    """
    Search for Dynamics 365 cases by extracting a problem statement from a user's natural language query.

    This tool uses an LLM to extract the core problem from the user's input, then searches for relevant cases.

    Args:
        user_query (str): The user's natural language query. Example: 'Find cases where Photoshop is crashing on Mac'.
        max_results (int, optional): Maximum number of cases to return. Default is 5.

    Returns:
        List[dict[str, Any]] | None: A list of case dictionaries matching the extracted problem statement, or None if an error occurs or no results are found.

    Example:
        results = await search_cases_by_query('Lightroom import failure on Windows 10', max_results=2)
    """
    print(f"Analyzing query: {user_query}")
    problem_statement = await extract_problem_statement(user_query)
    print(f"Extracted problem statement: {problem_statement}")
    return await search_cases_by_problem(problem_statement, max_results)

@mcp.tool()
async def d365_handle_case_question(user_question: str) -> str:
    """
    Answer a user's question about a specific Dynamics 365 case by extracting the intent and ticket number, retrieving the case data, and generating a concise answer.

    This tool uses an LLM to extract the user's intent and the ticket number from their question, fetches the case data, and then uses the LLM to generate a user-friendly answer.

    Args:
        user_question (str): The user's question, which should mention a ticket number and what they want to know. Example: 'Get support engineer details for E-001159966'.

    Returns:
        str: A concise, LLM-generated answer to the user's question, or an error message if extraction or retrieval fails.

    Example:
        answer = await handle_case_question('What is the status of E-001159966?')
    """
    prompt = EXTRACTION_PROMPT.format(user_question=user_question)
    extraction_response = await llm.ainvoke(prompt)
    extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
    try:
        extraction = extract_json_from_text(extraction_text)
        intent = extraction.get("intent")
        ticket_number = extraction.get("ticket_number")
    except Exception as e:
        return f"Could not extract intent and ticket number: {e}\nRaw LLM output: {extraction_text}"
    if not ticket_number:
        return "Could not find a ticket number in your question."
    case_data = await get_case_data(ticket_number)
    if not case_data:
        return f"No data found for ticket {ticket_number}."
    answer_prompt = f"""
    The user wants to '{intent}' for the following case data:
    {json.dumps(case_data, indent=2)}

    Write a concise answer for the user.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

@mcp.tool()
async def d365_handle_sales_lead_question(user_question: str) -> str:
    """
    Answer a user's question about Dynamics Sales leads by extracting the intent and subject, retrieving matching leads, and generating a concise answer.

    This tool uses an LLM to extract the user's intent and the subject (e.g., product or campaign), fetches matching leads from Dynamics Sales, and then uses the LLM to generate a user-friendly answer.

    Args:
        user_question (str): The user's question about sales leads. Example: 'Show me all leads for Adobe Photoshop'.

    Returns:
        str: A concise, LLM-generated answer to the user's question, or an error message if extraction or retrieval fails.

    Example:
        answer = await handle_sales_lead_question('Find leads for Acrobat Pro')
    """
    prompt = SALES_EXTRACTION_PROMPT.format(user_question=user_question)
    extraction_response = await llm.ainvoke(prompt)
    extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
    try:
        cleaned = extraction_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned)
            cleaned = cleaned.strip()
        extraction = json.loads(cleaned)
        if isinstance(extraction, str):
            extraction = json.loads(extraction)
        intent = extraction.get("intent")
        subject = extraction.get("subject")
    except Exception as e:
        return f"Could not extract intent and subject: {e}\nRaw LLM output: {extraction_text}"
    if not subject:
        return "Could not find a subject in your question."
    encoded_subject = urllib.parse.quote_plus(subject.replace(' ', '%'))
    filter_str = f"(contains(subject, '{encoded_subject}'))"
    url = (
        f"{DYNAMICS_SALES_URL_BASE}"
        f"?$select=_campaignid_value,firstname,lastname,lastusedincampaign,leadsourcecode,subject"
        f"&$filter={filter_str}"
        f"&$top=50"
    )
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            leads_data = response.json()
    except Exception as e:
        return f"Error fetching leads: {e}"
    leads = leads_data.get("value", [])
    if not leads:
        return f"No leads found for subject: {subject}"
    answer_prompt = f"""
    The user wants to '{intent}' for the following sales leads data:
    {json.dumps(leads, indent=2)}

    Write a concise answer for the user.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

@mcp.tool()
async def d365_handle_campaign_question(user_question: str) -> str:
    """
    Answer a user's question about Dynamics Marketing campaigns by extracting the intent and campaign name, retrieving matching campaigns, and generating a concise answer.

    This tool uses an LLM to extract the user's intent and the campaign name, fetches matching campaigns from Dynamics Marketing, and then uses the LLM to generate a user-friendly answer.

    Args:
        user_question (str): The user's question about campaigns. Example: 'Show me all campaigns for Adobe Photoshop'.

    Returns:
        str: A concise, LLM-generated answer to the user's question, or an error message if extraction or retrieval fails.

    Example:
        answer = await handle_campaign_question('Get campaign details for Acrobat Pro')
    """
    prompt = CAMPAIGN_EXTRACTION_PROMPT.format(user_question=user_question)
    extraction_response = await llm.ainvoke(prompt)
    extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
    try:
        cleaned = extraction_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned)
            cleaned = cleaned.strip()
        extraction = json.loads(cleaned)
        if isinstance(extraction, str):
            extraction = json.loads(extraction)
        intent = extraction.get("intent")
        campaign_name = extraction.get("campaign_name")
    except Exception as e:
        return f"Could not extract intent and campaign name: {e}\nRaw LLM output: {extraction_text}"
    if not campaign_name:
        return "Could not find a campaign name in your question."
    encoded_campaign = urllib.parse.quote_plus(campaign_name.replace(' ', '%'))
    filter_str = f"(contains(name, '{encoded_campaign}'))"
    url = (
        f"{CAMPAIGNS_URL_BASE}"
        f"?$select=description,expectedrevenue,message,name,objective,statecode,_transactioncurrencyid_value"
        f"&$filter={filter_str}"
        f"&$top=50"
    )
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            campaigns_data = response.json()
    except Exception as e:
        return f"Error fetching campaigns: {e}"
    campaigns = campaigns_data.get("value", [])
    if not campaigns:
        return f"No campaigns found for name: {campaign_name}"
    answer_prompt = f"""
    The user wants to '{intent}' for the following campaigns data:
    {json.dumps(campaigns, indent=2)}

    Write a concise answer for the user.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer


