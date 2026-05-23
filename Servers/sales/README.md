# Dynamics 365 Sales Management MCP Servers

This comprehensive sales system provides complete Dynamics 365 Sales management capabilities through multiple specialized MCP servers, including leads, opportunities, quotes, and intelligent query processing using AI-powered intent extraction.

## Sales System Architecture

The sales system is now organized into multiple specialized MCP servers, each handling specific aspects of the Dynamics 365 Sales ecosystem:

### 🎯 Sales Leads Server (`sales_leads`)
- **File**: `Servers/sales/lead/lead_mcp.py`
- **Port**: 8007
- **Purpose**: Handles leads, campaigns, and organization data
- **Tools**: 
  - `sales_handle_sales_lead_question` - Lead search and analysis
  - `sales_handle_campaign_question` - Campaign data and metrics
  - `sales_handle_organization_question` - Account and product entitlements

### 💼 Sales Opportunities Server (`sales_opportunities`)
- **File**: `Servers/sales/opportunity/opportunity_mcp.py`
- **Port**: 8008
- **Purpose**: Manages opportunities, pipeline analysis, and forecasting
- **Tools**:
  - `sales_handle_opportunity_search` - Opportunity search and details
  - `sales_handle_opportunity_pipeline` - Pipeline analysis and reporting
  - `sales_handle_opportunity_forecasting` - Revenue forecasting and projections

### 📋 Sales Quotes Server (`sales_quotes`)
- **File**: `Servers/sales/quote/quote_mcp.py`
- **Port**: 8009
- **Purpose**: Handles quotes, proposals, and pricing analysis
- **Tools**:
  - `sales_handle_quote_search` - Quote search and line item details
  - `sales_handle_quote_pipeline` - Quote pipeline and approval tracking
  - `sales_handle_quote_analysis` - Pricing and discount analysis

## Architecture

### AI-Powered Query Processing
1. **Intent Extraction**: LLM analyzes user questions to identify intent and subject
2. **Dynamic Search**: Constructs targeted searches based on extracted parameters
3. **Data Retrieval**: Fetches relevant leads/campaigns from Dynamics 365
4. **Response Generation**: AI generates human-friendly answers from structured data

### Authentication & Security
- **OAuth2**: Client credentials flow for secure API access
- **Token Management**: Automatic token refresh and error handling
- **Environment Variables**: Secure credential storage

## Configuration

### Environment Variables Required
```bash
# Dynamics 365 Sales API
DYNAMICS_SALES_URL_BASE=https://your-org.api.crm.dynamics.com/api/data/v9.2/leads
DYNAMICS_SALES_CLIENT_ID=your_client_id
DYNAMICS_SALES_CLIENT_SECRET=your_client_secret
DYNAMICS_SALES_TENANT_ID=your_tenant_id
DYNAMICS_SALES_SCOPE=https://your-org.crm.dynamics.com/.default
DYNAMICS_SALES_TOKEN_URL=https://login.microsoftonline.com/your_tenant/oauth2/v2.0/token

# Marketing Campaigns API
CAMPAIGNS_URL_BASE=https://your-org.api.crm.dynamics.com/api/data/v9.2/campaigns
```

### MCP Server Configuration
```json
{
  "sales_leads": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "Servers/sales/lead/lead_mcp.py"],
    "transport": "stdio",
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8007"
    },
    "description": "Handles Dynamics 365 Sales leads, campaigns, and organization data."
  },
  "sales_opportunities": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "Servers/sales/opportunity/opportunity_mcp.py"],
    "transport": "stdio",
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8008"
    },
    "description": "Handles Dynamics 365 Sales opportunities, pipeline analysis, and sales forecasting."
  },
  "sales_quotes": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "Servers/sales/quote/quote_mcp.py"],
    "transport": "stdio",
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8009"
    },
    "description": "Handles Dynamics 365 Sales quotes, proposals, and pricing analysis."
  }
}
```

## Comprehensive Sales Tools

### 🎯 Leads Server Tools

#### 1. sales_handle_sales_lead_question
```python
# Natural language lead queries
await sales_handle_sales_lead_question("Show me all leads for Adobe Photoshop")
await sales_handle_sales_lead_question("Find leads for Acrobat Pro license")
await sales_handle_sales_lead_question("Get leads from marketing campaign XYZ")
```

#### 2. sales_handle_campaign_question  
```python
# Campaign analysis queries
await sales_handle_campaign_question("Show me all campaigns for Adobe Photoshop")
await sales_handle_campaign_question("Get campaign performance for Q4 2024")
```

#### 3. sales_handle_organization_question
```python
# Organization and product entitlement queries
await sales_handle_organization_question("Show me details for Microsoft Corporation account")
await sales_handle_organization_question("Get product entitlements for Contoso Ltd")
```

### 💼 Opportunities Server Tools

#### 1. sales_handle_opportunity_search
```python
# Opportunity search and details
await sales_handle_opportunity_search("Show me all opportunities for Microsoft account")
await sales_handle_opportunity_search("Find opportunities worth over $100K")
await sales_handle_opportunity_search("Get opportunity details for Adobe Photoshop deal")
```

#### 2. sales_handle_opportunity_pipeline
```python
# Pipeline analysis and reporting
await sales_handle_opportunity_pipeline("Show me the sales pipeline for this quarter")
await sales_handle_opportunity_pipeline("What opportunities are in the proposal stage?")
await sales_handle_opportunity_pipeline("Give me pipeline analysis by status")
```

#### 3. sales_handle_opportunity_forecasting
```python
# Revenue forecasting and projections
await sales_handle_opportunity_forecasting("What is our sales forecast for next quarter?")
await sales_handle_opportunity_forecasting("Show me revenue projections based on current opportunities")
await sales_handle_opportunity_forecasting("Analyze close probability trends")
```

### 📋 Quotes Server Tools

#### 1. sales_handle_quote_search
```python
# Quote search and line item details
await sales_handle_quote_search("Show me all quotes for Microsoft account")
await sales_handle_quote_search("Find quotes worth over $50K")
await sales_handle_quote_search("Get quote details for Adobe license proposal")
```

#### 2. sales_handle_quote_pipeline
```python
# Quote pipeline and approval tracking
await sales_handle_quote_pipeline("Show me the quote pipeline for this quarter")
await sales_handle_quote_pipeline("What quotes are pending approval?")
await sales_handle_quote_pipeline("Give me quote analysis by status")
```

#### 3. sales_handle_quote_analysis
```python
# Pricing and discount analysis
await sales_handle_quote_analysis("Analyze pricing trends in our quotes")
await sales_handle_quote_analysis("Show me discount patterns by customer")
await sales_handle_quote_analysis("What products are most quoted?")
```

## AI Integration

### LLM Configuration
- **Model**: Azure GPT-4o Mini
- **Temperature**: 0.2 (factual responses)
- **Max Tokens**: 1000
- **Retry Logic**: 3 attempts with exponential backoff

### Prompt Templates

#### Sales Extraction Prompt
```
Extract the intent and subject for a Dynamics Sales lead query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants
- "subject": the subject to search for
```

#### Campaign Extraction Prompt
```
Extract the intent and campaign name for a Dynamics Sales campaign query from the following user question.

Question: "{user_question}"

Return a JSON object with:
- "intent": a short description of what the user wants  
- "campaign_name": the campaign name to search for
```

## Usage Examples

### Example Queries
The sales system automatically handles natural language queries across all entities:

**Lead Queries:**
- "Show me all leads for Adobe Creative Cloud"
- "Find leads generated from the holiday marketing campaign"
- "Get me leads for customers interested in Photoshop licenses"

**Opportunity Queries:**
- "What opportunities are in the pipeline for Microsoft?"
- "Show me high-value opportunities closing this quarter"
- "Generate a sales forecast for Q1 2024"

**Quote Queries:**
- "Show me all active quotes over $50K"
- "Analyze discount patterns in our pricing"
- "What quotes are pending approval?"

**Campaign Queries:**
- "What campaigns are running for Acrobat Pro?"
- "Show campaign performance for email marketing initiatives"

### Response Format
```
Based on your query about Adobe Photoshop leads, I found 15 matching leads:

• John Smith (Adobe Inc.) - Photoshop license inquiry
  - Campaign: Holiday Creative Suite Promotion
  - Lead Source: Web form
  - Status: Qualified

• Sarah Johnson (Design Studio LLC) - Adobe Photoshop training
  - Campaign: Educational Outreach Q4
  - Lead Source: Partner referral
  - Status: New

[Additional leads...]

These leads show strong interest in Adobe Photoshop solutions, 
with 60% coming from digital marketing campaigns and 40% from partner referrals.
```

## Error Handling

### Authentication Errors
- Token refresh failures
- Invalid credentials
- Expired tokens
- Scope authorization issues

### API Errors
- Rate limiting
- Network timeouts
- Invalid filter parameters
- Data access permissions

### AI Processing Errors
- Intent extraction failures
- JSON parsing errors
- LLM timeout handling
- Invalid query formats

## Data Processing

### Lead Data Fields
- `_campaignid_value`: Associated campaign ID
- `firstname`, `lastname`: Contact information
- `lastusedincampaign`: Campaign interaction date
- `leadsourcecode`: Lead generation source
- `subject`: Lead topic/interest

### Search Capabilities
- Subject-based filtering using `contains()` operator
- Campaign association filtering
- Lead source filtering
- Date range filtering (future enhancement)

## Performance

### Optimization Features
- Efficient OData filtering
- Limited result sets (max 50)
- Caching of authentication tokens
- Concurrent API request handling

### Monitoring
- Request/response logging
- Error tracking and reporting
- Performance metrics collection
- API usage monitoring

## Integration

### Dynamics 365 Integration
- **Sales Hub**: Lead management and tracking
- **Marketing Hub**: Campaign data and analytics
- **Customer Service**: Lead-to-case conversion
- **Power Platform**: Workflow automation

### External Integrations
- **Power Automate**: Automated lead processing
- **Power BI**: Advanced analytics and reporting
- **Azure AD**: Identity and access management
- **Microsoft Graph**: Additional data sources

---

*This server provides intelligent lead management capabilities by combining Dynamics 365 data with AI-powered natural language processing.* 