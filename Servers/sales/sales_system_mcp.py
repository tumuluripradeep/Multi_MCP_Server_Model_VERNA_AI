# =============================
# Unified Dynamics 365 Sales System MCP Server
# Combines Leads, Opportunities, Quotes, and Organizations
# =============================
from typing import Any
import httpx
import os
import json
import urllib.parse
import re
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from langchain_openai import AzureChatOpenAI

# =============================
# Load Environment Variables
# =============================
load_dotenv()

# =============================
# MCP Server Initialization
# =============================
mcp = FastMCP("sales_system")

# =============================
# Constants
# =============================
DYNAMICS_SALES_URL_BASE = os.getenv("DYNAMICS_SALES_URL_BASE")
DYNAMICS_SALES_CLIENT_ID = os.getenv("DYNAMICS_SALES_CLIENT_ID")
DYNAMICS_SALES_CLIENT_SECRET = os.getenv("DYNAMICS_SALES_CLIENT_SECRET")
DYNAMICS_SALES_TENANT_ID = os.getenv("DYNAMICS_SALES_TENANT_ID")
DYNAMICS_SALES_SCOPE = os.getenv("DYNAMICS_SALES_SCOPE")
DYNAMICS_SALES_TOKEN_URL = os.getenv("DYNAMICS_SALES_TOKEN_URL")

# Entity-specific URLs
LEADS_URL_BASE = DYNAMICS_SALES_URL_BASE
OPPORTUNITIES_URL_BASE = os.getenv("OPPORTUNITIES_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/opportunities"))
QUOTES_URL_BASE = os.getenv("QUOTES_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/quotes"))
QUOTE_DETAILS_URL_BASE = os.getenv("QUOTE_DETAILS_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/quotedetails"))
CAMPAIGNS_URL_BASE = os.getenv("CAMPAIGNS_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/campaigns"))
ACCOUNTS_URL_BASE = os.getenv("ACCOUNTS_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/accounts"))
CONTACTS_URL_BASE = os.getenv("CONTACTS_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/contacts"))
PRODUCTS_URL_BASE = os.getenv("PRODUCTS_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/products"))
PRODUCT_ENTITLEMENTS_URL_BASE = os.getenv("PRODUCT_ENTITLEMENTS_URL_BASE", f"{DYNAMICS_SALES_URL_BASE}".replace("/leads", "/ent_productentitlements"))

# =============================
# AI Prompts
# =============================
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

ORGANIZATION_EXTRACTION_PROMPT = '''
Extract the intent and account name for a Dynamics Sales organization query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get organization details", "find organization info")
- "account_name": the account/organization name to search for (e.g., "Microsoft Corporation", "Contoso Ltd")
'''

OPPORTUNITY_EXTRACTION_PROMPT = '''
Extract the intent and search criteria for a Dynamics Sales opportunity query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get opportunity details", "find opportunities by account", "search opportunities by product")
- "search_field": the field to search in (e.g., "name", "account", "product", "owner", "stage")
- "search_value": the value to search for (e.g., "Microsoft Deal", "Contoso", "Adobe Photoshop")
- "additional_filters": any additional filters mentioned (e.g., "closed won", "high value", "this quarter")
'''

OPPORTUNITY_STATUS_PROMPT = '''
Extract the intent and status criteria for a Dynamics Sales opportunity status query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get opportunities by status", "find won opportunities", "show pipeline")
- "status_filter": the status to filter by (e.g., "open", "won", "lost", "qualified", "proposal")
- "time_filter": any time-based filter (e.g., "this quarter", "last month", "2024")
- "additional_criteria": any other criteria (e.g., "high value", "specific owner", "account type")
'''

QUOTE_EXTRACTION_PROMPT = '''
Extract the intent and search criteria for a Dynamics Sales quote query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get quote details", "find quotes by customer", "search quotes by status")
- "search_field": the field to search in (e.g., "name", "customer", "opportunity", "status", "value")
- "search_value": the value to search for (e.g., "Adobe License Quote", "Microsoft Corporation", "active")
- "additional_filters": any additional filters mentioned (e.g., "high value", "pending approval", "this month")
'''

QUOTE_STATUS_PROMPT = '''
Extract the intent and status criteria for a Dynamics Sales quote status query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants (e.g., "get quotes by status", "find approved quotes", "show pending quotes")
- "status_filter": the status to filter by (e.g., "draft", "active", "won", "closed", "revised")
- "time_filter": any time-based filter (e.g., "this quarter", "last month", "2024")
- "value_filter": any value-based criteria (e.g., "high value", "over $50K", "under $10K")
'''

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
# Utility Functions
# =============================
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

async def get_dynamics_sales_access_token() -> str | None:
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
            return response.json().get("access_token")
        except Exception as e:
            print(f"Failed to obtain Dynamics Sales access token: {e}")
            return None

# =============================
# LEADS MANAGEMENT TOOLS
# =============================
@mcp.tool()
async def sales_handle_sales_lead_question(user_question: str) -> str:
    """
    Answer a user's question about Dynamics Sales leads by extracting the intent and subject, retrieving matching leads, and generating a concise answer.
    This tool uses an LLM to extract the user's intent and the subject (e.g., product or campaign), fetches matching leads from Dynamics Sales, and then uses the LLM to generate a user-friendly answer.
    Args:
        user_question (str): The user's question about sales leads. Example: 'Show me all leads for Adobe Photoshop'.
    Returns:
        str: A concise, LLM-generated answer to the user's question, or an error message if extraction or retrieval fails.
    Example:
        answer = await sales_handle_sales_lead_question('Find leads for Acrobat Pro')
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
        f"{LEADS_URL_BASE}"
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
async def sales_handle_campaign_question(user_question: str) -> str:
    """
    Answer a user's question about Dynamics Marketing campaigns by extracting the intent and campaign name, retrieving matching campaigns, and generating a concise answer.
    This tool uses an LLM to extract the user's intent and the campaign name, fetches matching campaigns from Dynamics Marketing, and then uses the LLM to generate a user-friendly answer.
    Args:
        user_question (str): The user's question about campaigns. Example: 'Show me all campaigns for Adobe Photoshop'.
    Returns:
        str: A concise, LLM-generated answer to the user's question, or an error message if extraction or retrieval fails.
    Example:
        answer = await sales_handle_campaign_question('Get campaign details for Acrobat Pro')
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

@mcp.tool()
async def sales_handle_organization_question(user_question: str) -> str:
    """
    Answer a user's question about Dynamics Sales organizations/accounts by extracting the intent and account name, retrieving matching organizations with their product entitlements, and generating a concise answer.
    This tool uses an LLM to extract the user's intent and the account name, fetches matching organizations and their associated product entitlements from Dynamics Sales, and then uses the LLM to generate a user-friendly answer.
    Args:
        user_question (str): The user's question about organizations/accounts. Example: 'Show me details for Microsoft Corporation account and their products'.
    Returns:
        str: A concise, LLM-generated answer to the user's question including organization details and product entitlements, or an error message if extraction or retrieval fails.
    Example:
        answer = await sales_handle_organization_question('Get organization details and products for Contoso Ltd')
    """
    prompt = ORGANIZATION_EXTRACTION_PROMPT.format(user_question=user_question)
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
        account_name = extraction.get("account_name")
    except Exception as e:
        return f"Could not extract intent and account name: {e}\nRaw LLM output: {extraction_text}"
    
    if not account_name:
        return "Could not find an account name in your question."
    
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # First, get account details with comprehensive attributes based on the XML example
    encoded_account = urllib.parse.quote_plus(account_name.replace(' ', '%'))
    filter_str = f"(contains(name, '{encoded_account}'))"
    accounts_url = (
        f"{ACCOUNTS_URL_BASE}"
        f"?$select=accountid,name,accountnumber,description,websiteurl,telephone1,telephone2,telephone3,emailaddress1,emailaddress2,emailaddress3,"
        f"address1_line1,address1_line2,address1_city,address1_stateorprovince,address1_country,address1_postalcode,"
        f"industrycode,revenue,numberofemployees,customersizecode,accountratingcode,tickersymbol,stockexchange,"
        f"ent_accountstatus,ent_accounttier,ent_orgregion,ent_country,ent_dxaccountstatus,ent_dxcustomersegment,"
        f"ent_escalationstatus,ent_value,businesstypecode,ownerid,createdon,modifiedon"
        f"&$filter={filter_str}"
        f"&$top=10"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get account details
            accounts_response = await client.get(accounts_url, headers=headers)
            accounts_response.raise_for_status()
            accounts_data = accounts_response.json()
            
            accounts = accounts_data.get("value", [])
            if not accounts:
                return f"No organizations found for account name: {account_name}"
            
            # For each account found, get their product entitlements
            all_account_data = []
            for account in accounts:
                account_id = account.get("accountid")
                if account_id:
                    # Get product entitlements for this account
                    entitlements_filter = f"(_ent_organization_value eq '{account_id}')"
                    entitlements_url = (
                        f"{PRODUCT_ENTITLEMENTS_URL_BASE}"
                        f"?$select=ent_productentitlementid,ent_purchasedquantity,ent_provisionedquantity,ent_delegatedquantity,"
                        f"ent_dealregnumber,ent_contractstatus,ent_contractstartdate,ent_contractenddate,ent_contractid,"
                        f"ent_licensetype,ent_licensingtechnology,_ent_productid_value"
                        f"&$filter={entitlements_filter}"
                        f"&$orderby=ent_contractenddate desc"
                        f"&$top=100"
                    )
                    
                    try:
                        entitlements_response = await client.get(entitlements_url, headers=headers)
                        if entitlements_response.status_code == 200:
                            entitlements_data = entitlements_response.json()
                            entitlements = entitlements_data.get("value", [])
                            
                            # For each entitlement, fetch the product details
                            for entitlement in entitlements:
                                product_id = entitlement.get("_ent_productid_value")
                                if product_id:
                                    try:
                                        product_url = f"{PRODUCTS_URL_BASE}({product_id})?$select=productid,productnumber,name,description,ent_productlevel"
                                        product_response = await client.get(product_url, headers=headers)
                                        if product_response.status_code == 200:
                                            product_data = product_response.json()
                                            entitlement["product_details"] = product_data
                                        else:
                                            entitlement["product_details"] = {"name": f"Product ID: {product_id}"}
                                    except Exception as pe:
                                        print(f"Warning: Could not fetch product details for {product_id}: {pe}")
                                        entitlement["product_details"] = {"name": f"Product ID: {product_id}"}
                                else:
                                    entitlement["product_details"] = {"name": "Unknown Product"}
                            
                            account["product_entitlements"] = entitlements
                        else:
                            account["product_entitlements"] = []
                    except Exception as e:
                        print(f"Warning: Could not fetch product entitlements for account {account_id}: {e}")
                        account["product_entitlements"] = []
                
                all_account_data.append(account)
                
    except Exception as e:
        return f"Error fetching organization details: {e}"
    
    answer_prompt = f"""
    The user wants to '{intent}' for the following comprehensive organization/account data with product entitlements:
    {json.dumps(all_account_data, indent=2)}

    Write a detailed, well-formatted answer for the user that includes:
    
    **Organization Details:**
    - Organization name, account number, and description
    - Contact information (address, phone numbers, email addresses, website)
    - Business details (industry, revenue, number of employees, customer size, rating)
    - Account status and tier information
    - Regional and country information
    
    **Product Entitlements (if any):**
    - Product names and descriptions
    - License types and quantities (purchased, provisioned, delegated)
    - Contract details (status, start/end dates, contract ID)
    - Deal registration numbers
    - Licensing technology information
    
    Present the information in a clear, well-structured format with appropriate headings and bullet points.
    If there are no product entitlements, mention that no products are currently assigned to this account.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

# =============================
# OPPORTUNITIES MANAGEMENT TOOLS
# =============================
@mcp.tool()
async def sales_handle_opportunity_search(user_question: str) -> str:
    """
    Search and retrieve Dynamics 365 Sales opportunities based on user queries. This tool can search by opportunity name, 
    account, product, owner, stage, or other criteria, and provides detailed opportunity information including related 
    account and contact details.
    
    Args:
        user_question (str): The user's question about opportunities. Examples: 
                           'Show me all opportunities for Microsoft account', 
                           'Find opportunities worth over $100K',
                           'Get opportunity details for Adobe Photoshop deal'
    
    Returns:
        str: A comprehensive, LLM-generated answer with opportunity details, or an error message if extraction or retrieval fails.
    
    Example:
        answer = await sales_handle_opportunity_search('Show me high-value opportunities for Q4')
    """
    prompt = OPPORTUNITY_EXTRACTION_PROMPT.format(user_question=user_question)
    extraction_response = await llm.ainvoke(prompt)
    extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
    
    try:
        extraction = extract_json_from_text(extraction_text)
        intent = extraction.get("intent")
        search_field = extraction.get("search_field", "name")
        search_value = extraction.get("search_value")
        additional_filters = extraction.get("additional_filters")
    except Exception as e:
        return f"Could not extract search criteria: {e}\nRaw LLM output: {extraction_text}"
    
    if not search_value:
        return "Could not find a search value in your question."
    
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Build the filter based on search field
    encoded_search = urllib.parse.quote_plus(search_value.replace(' ', '%'))
    
    if search_field.lower() in ["name", "opportunity"]:
        filter_str = f"(contains(name, '{encoded_search}'))"
    elif search_field.lower() == "account":
        filter_str = f"(contains(_customerid_value, '{encoded_search}') or contains(_parentaccountid_value, '{encoded_search}'))"
    elif search_field.lower() == "product":
        filter_str = f"(contains(description, '{encoded_search}'))"
    elif search_field.lower() == "owner":
        filter_str = f"(contains(_ownerid_value, '{encoded_search}'))"
    else:
        filter_str = f"(contains(name, '{encoded_search}'))"
    
    # Add additional filters if specified
    if additional_filters:
        if "won" in additional_filters.lower():
            filter_str += " and (statecode eq 1 and statuscode eq 3)"  # Won
        elif "lost" in additional_filters.lower():
            filter_str += " and (statecode eq 1 and statuscode eq 4)"  # Lost
        elif "open" in additional_filters.lower():
            filter_str += " and (statecode eq 0)"  # Open
        elif "high value" in additional_filters.lower():
            filter_str += " and (estimatedvalue gt 100000)"  # > $100K
    
    # Comprehensive opportunity fields
    select_fields = (
        "opportunityid,name,description,estimatedvalue,actualvalue,closeprobability,"
        "estimatedclosedate,actualclosedate,statecode,statuscode,salesstage,"
        "_customerid_value,_parentaccountid_value,_ownerid_value,_originatingleadid_value,"
        "budgetamount,budgetstatus,purchaseprocess,purchasetimeframe,decisionmaker,"
        "need,timeline,createdon,modifiedon,stepname,salesstagecode"
    )
    
    url = (
        f"{OPPORTUNITIES_URL_BASE}"
        f"?$select={select_fields}"
        f"&$filter={filter_str}"
        f"&$orderby=estimatedvalue desc,modifiedon desc"
        f"&$top=50"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            opportunities_data = response.json()
            
            opportunities = opportunities_data.get("value", [])
            if not opportunities:
                return f"No opportunities found for search criteria: {search_value}"
            
            # Enhance opportunities with related data
            enhanced_opportunities = []
            for opp in opportunities:
                enhanced_opp = opp.copy()
                
                # Get account details if available
                customer_id = opp.get("_customerid_value")
                if customer_id:
                    try:
                        account_url = f"{ACCOUNTS_URL_BASE}({customer_id})?$select=name,accountnumber,telephone1,emailaddress1,websiteurl,industrycode"
                        account_response = await client.get(account_url, headers=headers)
                        if account_response.status_code == 200:
                            enhanced_opp["account_details"] = account_response.json()
                    except Exception as e:
                        print(f"Warning: Could not fetch account details for {customer_id}: {e}")
                
                enhanced_opportunities.append(enhanced_opp)
                
    except Exception as e:
        return f"Error fetching opportunities: {e}"
    
    answer_prompt = f"""
    The user wants to '{intent}' for the following opportunities data:
    {json.dumps(enhanced_opportunities, indent=2)}

    Write a comprehensive, well-formatted answer for the user that includes:
    
    **Opportunity Summary:**
    - Total number of opportunities found
    - Total estimated value and actual value (if available)
    
    **Individual Opportunity Details:**
    For each opportunity, include:
    - Opportunity name and description
    - Estimated value, actual value (if closed), and close probability
    - Sales stage and status (open/won/lost)
    - Estimated close date and actual close date (if available)
    - Account details (name, contact info if available)
    - Budget information and purchase process
    - Key dates (created, modified)
    
    Present the information in a clear, well-structured format with appropriate headings and bullet points.
    Include summary statistics and highlight important opportunities based on value or status.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

@mcp.tool()
async def sales_handle_opportunity_pipeline(user_question: str) -> str:
    """
    Analyze and report on the sales opportunity pipeline, including opportunities by stage, status, and time periods.
    This tool provides pipeline analysis, forecasting insights, and opportunity status summaries.
    
    Args:
        user_question (str): The user's question about the sales pipeline. Examples:
                           'Show me the sales pipeline for this quarter',
                           'What opportunities are in the proposal stage?',
                           'Give me pipeline analysis by status'
    
    Returns:
        str: A detailed pipeline analysis with statistics, stage breakdown, and insights.
    
    Example:
        answer = await sales_handle_opportunity_pipeline('Show me the current sales pipeline')
    """
    prompt = OPPORTUNITY_STATUS_PROMPT.format(user_question=user_question)
    extraction_response = await llm.ainvoke(prompt)
    extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
    
    try:
        extraction = extract_json_from_text(extraction_text)
        intent = extraction.get("intent")
        status_filter = extraction.get("status_filter")
        time_filter = extraction.get("time_filter")
        additional_criteria = extraction.get("additional_criteria")
    except Exception as e:
        return f"Could not extract pipeline criteria: {e}\nRaw LLM output: {extraction_text}"
    
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Build filter based on status and time
    filter_parts = []
    
    if status_filter:
        if "open" in status_filter.lower():
            filter_parts.append("(statecode eq 0)")
        elif "won" in status_filter.lower():
            filter_parts.append("(statecode eq 1 and statuscode eq 3)")
        elif "lost" in status_filter.lower():
            filter_parts.append("(statecode eq 1 and statuscode eq 4)")
        elif "qualified" in status_filter.lower():
            filter_parts.append("(salesstagecode eq 1)")
        elif "proposal" in status_filter.lower():
            filter_parts.append("(salesstagecode eq 2)")
    
    # Add time filters
    if time_filter:
        if "quarter" in time_filter.lower():
            filter_parts.append("(estimatedclosedate ge 2024-01-01 and estimatedclosedate le 2024-12-31)")
        elif "month" in time_filter.lower():
            filter_parts.append("(modifiedon ge 2024-01-01)")
    
    # Add additional criteria
    if additional_criteria:
        if "high value" in additional_criteria.lower():
            filter_parts.append("(estimatedvalue gt 100000)")
    
    filter_str = " and ".join(filter_parts) if filter_parts else "(statecode eq 0)"
    
    select_fields = (
        "opportunityid,name,description,estimatedvalue,actualvalue,closeprobability,"
        "estimatedclosedate,actualclosedate,statecode,statuscode,salesstage,salesstagecode,"
        "_customerid_value,_ownerid_value,budgetamount,stepname,createdon,modifiedon"
    )
    
    url = (
        f"{OPPORTUNITIES_URL_BASE}"
        f"?$select={select_fields}"
        f"&$filter={filter_str}"
        f"&$orderby=estimatedvalue desc,estimatedclosedate asc"
        f"&$top=100"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            opportunities_data = response.json()
            
            opportunities = opportunities_data.get("value", [])
            if not opportunities:
                return f"No opportunities found for the specified pipeline criteria."
            
            # Calculate pipeline statistics
            pipeline_stats = {
                "total_opportunities": len(opportunities),
                "total_estimated_value": sum(float(opp.get("estimatedvalue", 0)) for opp in opportunities),
                "total_actual_value": sum(float(opp.get("actualvalue", 0)) for opp in opportunities if opp.get("actualvalue")),
                "average_close_probability": sum(float(opp.get("closeprobability", 0)) for opp in opportunities) / len(opportunities) if opportunities else 0,
                "by_stage": {},
                "by_status": {},
                "high_value_count": len([opp for opp in opportunities if float(opp.get("estimatedvalue", 0)) > 100000])
            }
            
            # Group by stage and status
            for opp in opportunities:
                stage = opp.get("salesstage", "Unknown")
                status = "Open" if opp.get("statecode") == 0 else ("Won" if opp.get("statuscode") == 3 else "Lost")
                
                if stage not in pipeline_stats["by_stage"]:
                    pipeline_stats["by_stage"][stage] = {"count": 0, "value": 0}
                pipeline_stats["by_stage"][stage]["count"] += 1
                pipeline_stats["by_stage"][stage]["value"] += float(opp.get("estimatedvalue", 0))
                
                if status not in pipeline_stats["by_status"]:
                    pipeline_stats["by_status"][status] = {"count": 0, "value": 0}
                pipeline_stats["by_status"][status]["count"] += 1
                pipeline_stats["by_status"][status]["value"] += float(opp.get("estimatedvalue", 0))
                
    except Exception as e:
        return f"Error fetching pipeline data: {e}"
    
    answer_prompt = f"""
    The user wants to '{intent}' for the following sales pipeline data and statistics:
    
    Pipeline Statistics:
    {json.dumps(pipeline_stats, indent=2)}
    
    Top Opportunities:
    {json.dumps(opportunities[:10], indent=2)}

    Write a comprehensive sales pipeline analysis that includes:
    
    **Pipeline Overview:**
    - Total number of opportunities
    - Total estimated pipeline value
    - Average close probability
    - Number of high-value opportunities (>$100K)
    
    **Stage Analysis:**
    - Breakdown by sales stage with counts and values
    - Stage progression insights
    
    **Status Analysis:**
    - Open vs Closed opportunities
    - Win/loss analysis if applicable
    
    **Key Opportunities:**
    - Highlight top opportunities by value
    - Opportunities with high close probability
    - Opportunities with upcoming close dates
    
    **Insights and Recommendations:**
    - Pipeline health assessment
    - Areas needing attention
    - Forecasting insights
    
    Present the information in a clear, executive-friendly format with appropriate headings, bullet points, and key metrics highlighted.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

@mcp.tool()
async def sales_handle_opportunity_forecasting(user_question: str) -> str:
    """
    Provide sales forecasting analysis based on opportunity data, including revenue projections, close date analysis,
    and probability-weighted forecasts. This tool helps with sales planning and revenue prediction.
    
    Args:
        user_question (str): The user's question about sales forecasting. Examples:
                           'What is our sales forecast for next quarter?',
                           'Show me revenue projections based on current opportunities',
                           'Analyze close probability trends'
    
    Returns:
        str: A detailed forecasting analysis with projections, trends, and recommendations.
    
    Example:
        answer = await sales_handle_opportunity_forecasting('Generate sales forecast for Q1 2024')
    """
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Get open opportunities for forecasting
    select_fields = (
        "opportunityid,name,estimatedvalue,closeprobability,estimatedclosedate,"
        "salesstage,salesstagecode,_customerid_value,createdon,modifiedon"
    )
    
    # Focus on open opportunities with future close dates
    filter_str = "(statecode eq 0 and estimatedclosedate ge 2024-01-01)"
    
    url = (
        f"{OPPORTUNITIES_URL_BASE}"
        f"?$select={select_fields}"
        f"&$filter={filter_str}"
        f"&$orderby=estimatedclosedate asc,estimatedvalue desc"
        f"&$top=200"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            opportunities_data = response.json()
            
            opportunities = opportunities_data.get("value", [])
            if not opportunities:
                return "No open opportunities found for forecasting analysis."
            
            # Calculate forecasting metrics
            forecast_data = {
                "total_pipeline_value": sum(float(opp.get("estimatedvalue", 0)) for opp in opportunities),
                "weighted_forecast": sum(float(opp.get("estimatedvalue", 0)) * float(opp.get("closeprobability", 0)) / 100 for opp in opportunities),
                "opportunity_count": len(opportunities),
                "high_probability_value": sum(float(opp.get("estimatedvalue", 0)) for opp in opportunities if float(opp.get("closeprobability", 0)) >= 75),
                "medium_probability_value": sum(float(opp.get("estimatedvalue", 0)) for opp in opportunities if 50 <= float(opp.get("closeprobability", 0)) < 75),
                "low_probability_value": sum(float(opp.get("estimatedvalue", 0)) for opp in opportunities if float(opp.get("closeprobability", 0)) < 50),
                "by_quarter": {},
                "by_stage": {},
                "average_close_probability": sum(float(opp.get("closeprobability", 0)) for opp in opportunities) / len(opportunities)
            }
            
            # Group by quarters and stages
            for opp in opportunities:
                close_date = opp.get("estimatedclosedate", "")
                stage = opp.get("salesstage", "Unknown")
                value = float(opp.get("estimatedvalue", 0))
                probability = float(opp.get("closeprobability", 0))
                weighted_value = value * probability / 100
                
                # Quarter grouping (simplified)
                if "2024-01" in close_date or "2024-02" in close_date or "2024-03" in close_date:
                    quarter = "Q1 2024"
                elif "2024-04" in close_date or "2024-05" in close_date or "2024-06" in close_date:
                    quarter = "Q2 2024"
                elif "2024-07" in close_date or "2024-08" in close_date or "2024-09" in close_date:
                    quarter = "Q3 2024"
                else:
                    quarter = "Q4 2024"
                
                if quarter not in forecast_data["by_quarter"]:
                    forecast_data["by_quarter"][quarter] = {"count": 0, "pipeline_value": 0, "weighted_value": 0}
                forecast_data["by_quarter"][quarter]["count"] += 1
                forecast_data["by_quarter"][quarter]["pipeline_value"] += value
                forecast_data["by_quarter"][quarter]["weighted_value"] += weighted_value
                
                if stage not in forecast_data["by_stage"]:
                    forecast_data["by_stage"][stage] = {"count": 0, "pipeline_value": 0, "weighted_value": 0}
                forecast_data["by_stage"][stage]["count"] += 1
                forecast_data["by_stage"][stage]["pipeline_value"] += value
                forecast_data["by_stage"][stage]["weighted_value"] += weighted_value
                
    except Exception as e:
        return f"Error generating sales forecast: {e}"
    
    answer_prompt = f"""
    The user wants sales forecasting analysis based on the following data:
    
    Forecast Data:
    {json.dumps(forecast_data, indent=2)}
    
    Sample Opportunities:
    {json.dumps(opportunities[:20], indent=2)}

    Write a comprehensive sales forecasting analysis that includes:
    
    **Executive Summary:**
    - Total pipeline value
    - Probability-weighted forecast
    - Expected conversion rate
    - Confidence level assessment
    
    **Quarterly Forecast:**
    - Revenue projections by quarter
    - Opportunity counts by quarter
    - Weighted vs. pipeline values
    
    **Probability Analysis:**
    - High probability opportunities (75%+)
    - Medium probability opportunities (50-74%)
    - Low probability opportunities (<50%)
    - Risk assessment
    
    **Stage Analysis:**
    - Forecast by sales stage
    - Stage progression trends
    - Conversion likelihood by stage
    
    **Key Insights:**
    - Forecast accuracy indicators
    - Risk factors and opportunities
    - Recommendations for pipeline improvement
    - Actions needed to achieve targets
    
    **Recommendations:**
    - Focus areas for sales teams
    - Opportunities to accelerate
    - Risk mitigation strategies
    
    Present the information in a clear, executive-friendly format with key metrics highlighted and actionable insights.
    Format monetary values with appropriate currency symbols and formatting.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

# =============================
# QUOTES MANAGEMENT TOOLS
# =============================
@mcp.tool()
async def sales_handle_quote_search(user_question: str) -> str:
    """
    Search and retrieve Dynamics 365 Sales quotes based on user queries. This tool can search by quote name,
    customer, opportunity, status, or other criteria, and provides detailed quote information including line items,
    pricing, and related opportunity details.
    
    Args:
        user_question (str): The user's question about quotes. Examples:
                           'Show me all quotes for Microsoft account',
                           'Find quotes worth over $50K',
                           'Get quote details for Adobe license proposal'
    
    Returns:
        str: A comprehensive, LLM-generated answer with quote details, or an error message if extraction or retrieval fails.
    
    Example:
        answer = await sales_handle_quote_search('Show me active quotes for this quarter')
    """
    prompt = QUOTE_EXTRACTION_PROMPT.format(user_question=user_question)
    extraction_response = await llm.ainvoke(prompt)
    extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
    
    try:
        extraction = extract_json_from_text(extraction_text)
        intent = extraction.get("intent")
        search_field = extraction.get("search_field", "name")
        search_value = extraction.get("search_value")
        additional_filters = extraction.get("additional_filters")
    except Exception as e:
        return f"Could not extract search criteria: {e}\nRaw LLM output: {extraction_text}"
    
    if not search_value:
        return "Could not find a search value in your question."
    
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Build the filter based on search field
    encoded_search = urllib.parse.quote_plus(search_value.replace(' ', '%'))
    
    if search_field.lower() in ["name", "quote"]:
        filter_str = f"(contains(name, '{encoded_search}'))"
    elif search_field.lower() == "customer":
        filter_str = f"(contains(_customerid_value, '{encoded_search}'))"
    elif search_field.lower() == "opportunity":
        filter_str = f"(contains(_opportunityid_value, '{encoded_search}'))"
    elif search_field.lower() == "status":
        if "active" in search_value.lower():
            filter_str = "(statecode eq 1)"  # Active
        elif "draft" in search_value.lower():
            filter_str = "(statecode eq 0)"  # Draft
        elif "won" in search_value.lower():
            filter_str = "(statecode eq 2)"  # Won
        elif "closed" in search_value.lower():
            filter_str = "(statecode eq 3)"  # Closed
        else:
            filter_str = f"(contains(name, '{encoded_search}'))"
    else:
        filter_str = f"(contains(name, '{encoded_search}'))"
    
    # Add additional filters if specified
    if additional_filters:
        if "high value" in additional_filters.lower():
            filter_str += " and (totalamount gt 50000)"  # > $50K
        elif "pending" in additional_filters.lower():
            filter_str += " and (statecode eq 0)"  # Draft/Pending
        elif "approved" in additional_filters.lower():
            filter_str += " and (statecode eq 1)"  # Active/Approved
    
    # Comprehensive quote fields
    select_fields = (
        "quoteid,quotenumber,name,description,totalamount,totallineitemamount,totaldiscountamount,"
        "totaltax,statecode,statuscode,validfrom,validto,effectivefrom,effectiveto,"
        "_customerid_value,_opportunityid_value,_ownerid_value,_pricelevelid_value,"
        "paymenttermscode,freighttermscode,shippingmethodcode,willcall,"
        "createdon,modifiedon,versionnumber,revisionnumber"
    )
    
    url = (
        f"{QUOTES_URL_BASE}"
        f"?$select={select_fields}"
        f"&$filter={filter_str}"
        f"&$orderby=totalamount desc,modifiedon desc"
        f"&$top=50"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            quotes_data = response.json()
            
            quotes = quotes_data.get("value", [])
            if not quotes:
                return f"No quotes found for search criteria: {search_value}"
            
            # Enhance quotes with related data
            enhanced_quotes = []
            for quote in quotes:
                enhanced_quote = quote.copy()
                
                # Get customer/account details if available
                customer_id = quote.get("_customerid_value")
                if customer_id:
                    try:
                        account_url = f"{ACCOUNTS_URL_BASE}({customer_id})?$select=name,accountnumber,telephone1,emailaddress1,websiteurl"
                        account_response = await client.get(account_url, headers=headers)
                        if account_response.status_code == 200:
                            enhanced_quote["customer_details"] = account_response.json()
                    except Exception as e:
                        print(f"Warning: Could not fetch customer details for {customer_id}: {e}")
                
                # Get opportunity details if available
                opportunity_id = quote.get("_opportunityid_value")
                if opportunity_id:
                    try:
                        opp_url = f"{OPPORTUNITIES_URL_BASE}({opportunity_id})?$select=name,estimatedvalue,estimatedclosedate,salesstage"
                        opp_response = await client.get(opp_url, headers=headers)
                        if opp_response.status_code == 200:
                            enhanced_quote["opportunity_details"] = opp_response.json()
                    except Exception as e:
                        print(f"Warning: Could not fetch opportunity details for {opportunity_id}: {e}")
                
                # Get quote line items
                quote_id = quote.get("quoteid")
                if quote_id:
                    try:
                        details_url = (
                            f"{QUOTE_DETAILS_URL_BASE}"
                            f"?$select=quotedetailid,productid,productdescription,quantity,priceperunit,extendedamount,manualdiscountamount"
                            f"&$filter=(_quoteid_value eq '{quote_id}')"
                            f"&$top=100"
                        )
                        details_response = await client.get(details_url, headers=headers)
                        if details_response.status_code == 200:
                            details_data = details_response.json()
                            enhanced_quote["line_items"] = details_data.get("value", [])
                    except Exception as e:
                        print(f"Warning: Could not fetch quote line items for {quote_id}: {e}")
                        enhanced_quote["line_items"] = []
                
                enhanced_quotes.append(enhanced_quote)
                
    except Exception as e:
        return f"Error fetching quotes: {e}"
    
    answer_prompt = f"""
    The user wants to '{intent}' for the following quotes data:
    {json.dumps(enhanced_quotes, indent=2)}

    Write a comprehensive, well-formatted answer for the user that includes:
    
    **Quote Summary:**
    - Total number of quotes found
    - Total quote value and average quote size
    
    **Individual Quote Details:**
    For each quote, include:
    - Quote number, name, and description
    - Total amount, line item amount, discount amount, and tax
    - Status (draft, active, won, closed) and validity period
    - Customer/account details (name, contact info if available)
    - Related opportunity information (if available)
    - Payment terms and shipping information
    - Key dates (created, modified, valid from/to)
    
    **Line Items (if available):**
    - Product descriptions and quantities
    - Pricing per unit and extended amounts
    - Discounts applied
    
    Present the information in a clear, well-structured format with appropriate headings and bullet points.
    Include summary statistics and highlight important quotes based on value or status.
    Format monetary values with appropriate currency symbols and formatting.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

@mcp.tool()
async def sales_handle_quote_pipeline(user_question: str) -> str:
    """
    Analyze and report on the sales quote pipeline, including quotes by status, approval stages, and revenue potential.
    This tool provides quote pipeline analysis, approval tracking, and revenue forecasting from quotes.
    
    Args:
        user_question (str): The user's question about the quote pipeline. Examples:
                           'Show me the quote pipeline for this quarter',
                           'What quotes are pending approval?',
                           'Give me quote analysis by status'
    
    Returns:
        str: A detailed quote pipeline analysis with statistics, status breakdown, and insights.
    
    Example:
        answer = await sales_handle_quote_pipeline('Show me the current quote pipeline')
    """
    prompt = QUOTE_STATUS_PROMPT.format(user_question=user_question)
    extraction_response = await llm.ainvoke(prompt)
    extraction_text = extraction_response.content if hasattr(extraction_response, 'content') else str(extraction_response)
    
    try:
        extraction = extract_json_from_text(extraction_text)
        intent = extraction.get("intent")
        status_filter = extraction.get("status_filter")
        time_filter = extraction.get("time_filter")
        value_filter = extraction.get("value_filter")
    except Exception as e:
        return f"Could not extract pipeline criteria: {e}\nRaw LLM output: {extraction_text}"
    
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Build filter based on status and criteria
    filter_parts = []
    
    if status_filter:
        if "draft" in status_filter.lower() or "pending" in status_filter.lower():
            filter_parts.append("(statecode eq 0)")
        elif "active" in status_filter.lower() or "approved" in status_filter.lower():
            filter_parts.append("(statecode eq 1)")
        elif "won" in status_filter.lower():
            filter_parts.append("(statecode eq 2)")
        elif "closed" in status_filter.lower():
            filter_parts.append("(statecode eq 3)")
    
    # Add time filters
    if time_filter:
        if "quarter" in time_filter.lower():
            filter_parts.append("(createdon ge 2024-01-01 and createdon le 2024-12-31)")
        elif "month" in time_filter.lower():
            filter_parts.append("(modifiedon ge 2024-01-01)")
    
    # Add value filters
    if value_filter:
        if "high value" in value_filter.lower() or "50k" in value_filter.lower():
            filter_parts.append("(totalamount gt 50000)")
        elif "10k" in value_filter.lower():
            filter_parts.append("(totalamount lt 10000)")
    
    filter_str = " and ".join(filter_parts) if filter_parts else "(statecode ne null)"
    
    select_fields = (
        "quoteid,quotenumber,name,totalamount,totallineitemamount,totaldiscountamount,"
        "statecode,statuscode,validfrom,validto,_customerid_value,_opportunityid_value,"
        "createdon,modifiedon,revisionnumber"
    )
    
    url = (
        f"{QUOTES_URL_BASE}"
        f"?$select={select_fields}"
        f"&$filter={filter_str}"
        f"&$orderby=totalamount desc,modifiedon desc"
        f"&$top=100"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            quotes_data = response.json()
            
            quotes = quotes_data.get("value", [])
            if not quotes:
                return f"No quotes found for the specified pipeline criteria."
            
            # Calculate pipeline statistics
            pipeline_stats = {
                "total_quotes": len(quotes),
                "total_quote_value": sum(float(quote.get("totalamount", 0)) for quote in quotes),
                "total_line_item_value": sum(float(quote.get("totallineitemamount", 0)) for quote in quotes),
                "total_discount_amount": sum(float(quote.get("totaldiscountamount", 0)) for quote in quotes),
                "by_status": {},
                "high_value_count": len([quote for quote in quotes if float(quote.get("totalamount", 0)) > 50000]),
                "average_quote_value": 0,
                "average_discount_percentage": 0
            }
            
            # Calculate averages
            if quotes:
                pipeline_stats["average_quote_value"] = pipeline_stats["total_quote_value"] / len(quotes)
                if pipeline_stats["total_line_item_value"] > 0:
                    pipeline_stats["average_discount_percentage"] = (pipeline_stats["total_discount_amount"] / pipeline_stats["total_line_item_value"]) * 100
            
            # Group by status
            status_names = {0: "Draft", 1: "Active", 2: "Won", 3: "Closed"}
            for quote in quotes:
                status_code = quote.get("statecode", 0)
                status_name = status_names.get(status_code, "Unknown")
                
                if status_name not in pipeline_stats["by_status"]:
                    pipeline_stats["by_status"][status_name] = {"count": 0, "value": 0}
                pipeline_stats["by_status"][status_name]["count"] += 1
                pipeline_stats["by_status"][status_name]["value"] += float(quote.get("totalamount", 0))
                
    except Exception as e:
        return f"Error fetching quote pipeline data: {e}"
    
    answer_prompt = f"""
    The user wants to '{intent}' for the following quote pipeline data and statistics:
    
    Pipeline Statistics:
    {json.dumps(pipeline_stats, indent=2)}
    
    Top Quotes:
    {json.dumps(quotes[:15], indent=2)}

    Write a comprehensive quote pipeline analysis that includes:
    
    **Pipeline Overview:**
    - Total number of quotes
    - Total quote pipeline value
    - Average quote value
    - Number of high-value quotes (>$50K)
    - Average discount percentage
    
    **Status Analysis:**
    - Breakdown by quote status (Draft, Active, Won, Closed)
    - Status progression insights
    - Conversion analysis
    
    **Value Analysis:**
    - Quote value distribution
    - Discount analysis
    - Revenue potential
    
    **Key Quotes:**
    - Highlight top quotes by value
    - Recently modified quotes
    - Quotes requiring attention
    
    **Insights and Recommendations:**
    - Quote pipeline health assessment
    - Approval bottlenecks
    - Revenue forecasting from quotes
    - Actions needed for quote conversion
    
    **Process Insights:**
    - Quote revision patterns
    - Time-to-approval analysis
    - Win rate by quote value ranges
    
    Present the information in a clear, executive-friendly format with appropriate headings, bullet points, and key metrics highlighted.
    Format monetary values with appropriate currency symbols and formatting.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer

@mcp.tool()
async def sales_handle_quote_analysis(user_question: str) -> str:
    """
    Provide detailed quote analysis including pricing analysis, discount patterns, product mix analysis,
    and competitive insights. This tool helps with quote optimization and pricing strategy.
    
    Args:
        user_question (str): The user's question about quote analysis. Examples:
                           'Analyze pricing trends in our quotes',
                           'Show me discount patterns by customer',
                           'What products are most quoted?'
    
    Returns:
        str: A detailed quote analysis with pricing insights, product analysis, and recommendations.
    
    Example:
        answer = await sales_handle_quote_analysis('Analyze quote performance and pricing trends')
    """
    token = await get_dynamics_sales_access_token()
    if not token:
        return "Could not authenticate to Dynamics Sales API."
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Get comprehensive quote data for analysis
    select_fields = (
        "quoteid,quotenumber,name,totalamount,totallineitemamount,totaldiscountamount,totaltax,"
        "statecode,statuscode,_customerid_value,_opportunityid_value,createdon,modifiedon,"
        "revisionnumber,validfrom,validto"
    )
    
    # Get recent quotes for analysis
    filter_str = "(createdon ge 2023-01-01)"
    
    url = (
        f"{QUOTES_URL_BASE}"
        f"?$select={select_fields}"
        f"&$filter={filter_str}"
        f"&$orderby=createdon desc"
        f"&$top=200"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get quotes
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            quotes_data = response.json()
            
            quotes = quotes_data.get("value", [])
            if not quotes:
                return "No quotes found for analysis."
            
            # Get quote line items for product analysis
            all_line_items = []
            for quote in quotes[:50]:  # Limit to avoid too many API calls
                quote_id = quote.get("quoteid")
                if quote_id:
                    try:
                        details_url = (
                            f"{QUOTE_DETAILS_URL_BASE}"
                            f"?$select=quotedetailid,productid,productdescription,quantity,priceperunit,extendedamount,manualdiscountamount,_quoteid_value"
                            f"&$filter=(_quoteid_value eq '{quote_id}')"
                            f"&$top=50"
                        )
                        details_response = await client.get(details_url, headers=headers)
                        if details_response.status_code == 200:
                            details_data = details_response.json()
                            line_items = details_data.get("value", [])
                            for item in line_items:
                                item["quote_status"] = quote.get("statecode")
                                item["quote_total"] = quote.get("totalamount", 0)
                            all_line_items.extend(line_items)
                    except Exception as e:
                        print(f"Warning: Could not fetch line items for quote {quote_id}: {e}")
            
            # Calculate analysis metrics
            analysis_data = {
                "quote_metrics": {
                    "total_quotes": len(quotes),
                    "total_value": sum(float(q.get("totalamount", 0)) for q in quotes),
                    "total_discounts": sum(float(q.get("totaldiscountamount", 0)) for q in quotes),
                    "average_quote_value": 0,
                    "average_discount_percentage": 0,
                    "win_rate": 0
                },
                "status_distribution": {},
                "pricing_analysis": {
                    "high_value_quotes": len([q for q in quotes if float(q.get("totalamount", 0)) > 100000]),
                    "medium_value_quotes": len([q for q in quotes if 50000 <= float(q.get("totalamount", 0)) <= 100000]),
                    "low_value_quotes": len([q for q in quotes if float(q.get("totalamount", 0)) < 50000])
                },
                "product_analysis": {},
                "discount_patterns": {
                    "quotes_with_discounts": len([q for q in quotes if float(q.get("totaldiscountamount", 0)) > 0]),
                    "average_discount_amount": 0
                }
            }
            
            # Calculate metrics
            if quotes:
                analysis_data["quote_metrics"]["average_quote_value"] = analysis_data["quote_metrics"]["total_value"] / len(quotes)
                won_quotes = len([q for q in quotes if q.get("statecode") == 2])
                analysis_data["quote_metrics"]["win_rate"] = (won_quotes / len(quotes)) * 100
                
                total_line_amount = sum(float(q.get("totallineitemamount", 0)) for q in quotes)
                if total_line_amount > 0:
                    analysis_data["quote_metrics"]["average_discount_percentage"] = (analysis_data["quote_metrics"]["total_discounts"] / total_line_amount) * 100
                
                discounted_quotes = [q for q in quotes if float(q.get("totaldiscountamount", 0)) > 0]
                if discounted_quotes:
                    analysis_data["discount_patterns"]["average_discount_amount"] = sum(float(q.get("totaldiscountamount", 0)) for q in discounted_quotes) / len(discounted_quotes)
            
            # Status distribution
            status_names = {0: "Draft", 1: "Active", 2: "Won", 3: "Closed"}
            for quote in quotes:
                status = status_names.get(quote.get("statecode", 0), "Unknown")
                if status not in analysis_data["status_distribution"]:
                    analysis_data["status_distribution"][status] = {"count": 0, "value": 0}
                analysis_data["status_distribution"][status]["count"] += 1
                analysis_data["status_distribution"][status]["value"] += float(quote.get("totalamount", 0))
            
            # Product analysis from line items
            product_stats = {}
            for item in all_line_items:
                product = item.get("productdescription", "Unknown Product")
                if product not in product_stats:
                    product_stats[product] = {
                        "quote_count": 0,
                        "total_quantity": 0,
                        "total_value": 0,
                        "win_count": 0
                    }
                product_stats[product]["quote_count"] += 1
                product_stats[product]["total_quantity"] += float(item.get("quantity", 0))
                product_stats[product]["total_value"] += float(item.get("extendedamount", 0))
                if item.get("quote_status") == 2:  # Won
                    product_stats[product]["win_count"] += 1
            
            # Top products by value
            analysis_data["product_analysis"] = dict(sorted(product_stats.items(), 
                                                          key=lambda x: x[1]["total_value"], 
                                                          reverse=True)[:10])
                
    except Exception as e:
        return f"Error performing quote analysis: {e}"
    
    answer_prompt = f"""
    The user wants quote analysis based on the following comprehensive data:
    
    Analysis Data:
    {json.dumps(analysis_data, indent=2)}
    
    Sample Line Items:
    {json.dumps(all_line_items[:20], indent=2)}

    Write a comprehensive quote analysis report that includes:
    
    **Executive Summary:**
    - Total quotes analyzed and time period
    - Overall quote value and average deal size
    - Win rate and conversion metrics
    - Key performance indicators
    
    **Pricing Analysis:**
    - Quote value distribution (high/medium/low value)
    - Average quote values by status
    - Pricing trends and patterns
    
    **Discount Analysis:**
    - Percentage of quotes with discounts
    - Average discount amounts and percentages
    - Discount impact on win rates
    - Discount patterns by quote value
    
    **Product Mix Analysis:**
    - Top quoted products by value and frequency
    - Product win rates
    - Cross-selling opportunities
    - Product performance insights
    
    **Status and Conversion Analysis:**
    - Quote pipeline by status
    - Conversion rates from draft to won
    - Time-to-close analysis
    - Bottlenecks in the quote process
    
    **Strategic Insights:**
    - Opportunities for pricing optimization
    - Product portfolio performance
    - Competitive positioning insights
    - Revenue optimization recommendations
    
    **Action Items:**
    - Specific recommendations for improvement
    - Focus areas for sales teams
    - Pricing strategy adjustments
    - Process optimization opportunities
    
    Present the information in a clear, analytical format with appropriate headings, bullet points, and key insights highlighted.
    Include specific metrics, percentages, and monetary values formatted appropriately.
    Focus on actionable insights that can drive business decisions.
    """
    answer_response = await llm.ainvoke(answer_prompt)
    answer = answer_response.content if hasattr(answer_response, 'content') else str(answer_response)
    return answer
