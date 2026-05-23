#!/usr/bin/env python3
"""
Web Search, Scrape & RAG MCP Server

This server implements a 5-step process:
1. Take user query
2. Refine the query using LLM call
3. Perform web search to get top 3 relevant results
4. Scrape through each URL and get the content
5. Pass refined query as problem statement and results as context to make LLM call

Returns final solution for the problem along with list of source links.
"""

import asyncio
import sys
import json
import logging
from typing import List, Optional, Union
from dataclasses import dataclass
from urllib.parse import urlparse
import re
import time
import random
import aiohttp
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

# Configure logging to stderr to avoid interfering with MCP JSON protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Suppress Google API verbose logging
logging.getLogger('googleapiclient').setLevel(logging.WARNING)

try:
    from googleapiclient.discovery import build
    import os
except ImportError as e:
    logger.error(f"Failed to import Google API client: {e}")
    build = None

# Add the Servers directory to the path to import llm_factory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from llm_factory import LLMEnhancedMCP
    logger.info("LLM Factory imported successfully")
except ImportError as e:
    logger.error(f"Failed to import LLM Factory: {e}")
    raise

# =============================
# MCP Server Initialization
# =============================
try:
    # Initialize the LLM-enhanced MCP server
    logger.info("Initializing LLM-Enhanced Web Search MCP server...")
    web_search_server = LLMEnhancedMCP("web-search-scrape-rag")
    mcp = web_search_server.get_mcp_server()
    logger.info("LLM-Enhanced MCP server instance created successfully")
except Exception as e:
    logger.error(f"Failed to create LLM-Enhanced MCP server instance: {e}")
    raise

# Configuration constants
MAX_SEARCH_RESULTS = 3
SCRAPE_TIMEOUT = 3  # Reduced for faster MCP responses
OVERALL_TIMEOUT = 25  # Increased for intelligent web search depth analysis
MAX_CONTENT_LENGTH = 1000000
QUERY_REFINE_TIMEOUT = 6  # Increased for better query refinement
SOLUTION_TIMEOUT = 12  # Increased for comprehensive LLM analysis
SEARCH_TIMEOUT = 5  # Reduced for faster search operations
SCRAPING_TIMEOUT = 3  # Reduced for faster content extraction

# Load environment variables from .env file
load_dotenv()

# Google Custom Search configuration
GOOGLE_SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')  # User's provided search engine ID
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')  # Should be set in environment variables

# Rate limiting configuration
MAX_SEARCH_RETRIES = 2  # Allow 2 retries for better reliability
RETRY_DELAY_BASE = 0.5  # Base delay in seconds
RETRY_DELAY_MAX = 2  # Maximum delay in seconds

# LLM is now initialized through the LLMEnhancedMCP server
# Access it through web_search_server.llm or web_search_server.is_llm_available()

# =============================
# Data Models
# =============================
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    relevance_score: float = 0.0
    scraped_content: str = ""
    scrape_success: bool = False

@dataclass
class RefinedQuery:
    original_query: str
    refined_query: str
    problem_statement: str
    search_terms: List[str]

# =============================
# Utility Functions
# =============================
def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip())
    text = re.sub(r'[^\w\s\-.,!?;:()\[\]{}"]', '', text)
    return text[:MAX_CONTENT_LENGTH]

def score_relevance(query: str, title: str, snippet: str, content: str = "") -> float:
    """Calculate relevance score based on query matches."""
    score = 0.0
    query_lower = query.lower()
    query_words = [word for word in query_lower.split() if len(word) > 2]
    
    # If no meaningful query words, give base score
    if not query_words:
        return 1.0
    
    # Title relevance (highest weight)
    title_lower = title.lower()
    title_matches = sum(1 for word in query_words if word in title_lower)
    score += title_matches * 5.0
    
    # Snippet relevance
    snippet_lower = snippet.lower()
    snippet_matches = sum(1 for word in query_words if word in snippet_lower)
    score += snippet_matches * 3.0
    
    # Content relevance
    if content:
        content_lower = content.lower()
        content_matches = sum(1 for word in query_words if word in content_lower)
        score += content_matches * 1.0
    
    # Partial matching for better coverage
    all_text = f"{title_lower} {snippet_lower} {content.lower() if content else ''}"
    partial_matches = sum(1 for word in query_words if any(word in text_word for text_word in all_text.split()))
    score += partial_matches * 0.5
    
    # Give base score if no matches but result exists
    return max(score, 0.1)  # Ensure minimum score for all results

def extract_content(content: str) -> str:
    """Extract meaningful content and filter out noise."""
    lines = content.split('\n')
    meaningful_lines = []
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 15:
            continue
            
        # Skip navigation-like content
        if any(nav_word in line.lower() for nav_word in ['home', 'menu', 'login', 'search', 'contact']):
            continue
            
        # Prefer longer, sentence-like content
        if '.' in line or len(line) > 30:
            meaningful_lines.append(line)
    
    result = ' '.join(meaningful_lines)
    return ' '.join(result.split())

async def wait_with_backoff(attempt: int) -> None:
    """Apply exponential backoff delay for retries."""
    if attempt > 0:
        delay = min(RETRY_DELAY_BASE * (2 ** attempt) + random.uniform(0, 1), RETRY_DELAY_MAX)
        logger.info(f"Rate limit hit, waiting {delay:.2f} seconds before retry {attempt + 1}")
        await asyncio.sleep(delay)

async def google_custom_search(query: str, num_results: int = MAX_SEARCH_RESULTS, site_filters: Optional[List[str]] = None) -> List[SearchResult]:
    """Perform Google Custom Search API query with support for multiple site filters."""
    if not build or not GOOGLE_API_KEY:
        logger.error("Google API client or API key not available")
        return []
    
    logger.info(f"Performing Google Custom Search for: '{query}'")
    
    def _google_search():
        try:
            # Build the Google Custom Search service
            service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
            
            # Prepare search parameters
            search_params = {
                'q': query,
                'cx': GOOGLE_SEARCH_ENGINE_ID,
                'num': min(num_results * 2, 10),  # Get more results to filter
            }
            
            # Add site filters if provided
            if site_filters:
                clean_sites = []
                for site in site_filters:
                    clean_site = site.replace('http://', '').replace('https://', '').rstrip('/')
                    clean_sites.append(clean_site)
                
                # Create site filter query - use OR logic for multiple sites
                site_query = " OR ".join([f"site:{site}" for site in clean_sites])
                search_params['q'] = f"({site_query}) {query}"
                logger.info(f"Added site filters: {clean_sites}")
            
            logger.info(f"Google search parameters: {search_params}")
            
            # Execute the search
            result = service.cse().list(**search_params).execute()
            
            search_results = []
            items = result.get('items', [])
            logger.info(f"Google API returned {len(items)} results")
            
            for item in items:
                title = item.get('title', '').strip()
                url = item.get('link', '').strip()
                snippet = item.get('snippet', '').strip()
                
                if title and url:
                    search_results.append({
                        'title': title,
                        'href': url,
                        'body': snippet
                    })
                    logger.info(f"Added result: {title}")
            
            return search_results
            
        except Exception as e:
            logger.error(f"Google Custom Search API error: {e}")
            return []
    
    try:
        loop = asyncio.get_event_loop()
        search_data = await asyncio.wait_for(
            loop.run_in_executor(None, _google_search),
            timeout=6.0  # Reduced timeout for faster response
        )
        
        if not search_data:
            return []
        
        # Process results
        results = []
        for result in search_data:
            try:
                title = result.get('title', '').strip()
                url = result.get('href', '').strip()
                snippet = result.get('body', '').strip()
                
                if title and url:
                    search_result = SearchResult(
                        title=clean_text(title),
                        url=url,
                        snippet=clean_text(snippet) if snippet else 'No description available'
                    )
                    results.append(search_result)
                    
            except Exception as e:
                logger.warning(f"Error processing Google result: {e}")
                continue
        
        logger.info(f"Google Custom Search returning {len(results)} results")
        return results[:num_results]
        
    except asyncio.TimeoutError:
        logger.error("Google Custom Search timed out")
        return []
    except Exception as e:
        logger.error(f"Google Custom Search error: {e}")
        return []

# =============================
# Web Operations
# =============================
async def fetch_webpage(url: str, timeout: int = SCRAPE_TIMEOUT) -> str:
    """Make HTTP request with proper error handling and timeout."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, 
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            ) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'text/html' in content_type or 'text/plain' in content_type:
                        return await response.text()
                return ""
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return ""

async def enhance_query(original_query: str) -> RefinedQuery:
    """Refine the user query using LLM to create better search terms."""
    if not web_search_server.is_llm_available():
        logger.warning("LLM not available, using simple query refinement")
        return RefinedQuery(
            original_query=original_query,
            refined_query=original_query,
            problem_statement=f"Find information about: {original_query}",
            search_terms=original_query.split()
        )
    
    try:
        refine_prompt = f"""You are a search query optimization expert. Given a user's question, create:
                        1. A refined search query optimized for web search engines
                        2. A clear problem statement that captures what the user wants to solve
                        3. Key search terms that would find relevant information

                        User's Original Query: {original_query}

                        Respond in this exact JSON format:
                        {{
                            "refined_query": "optimized search query here",
                            "problem_statement": "clear problem the user wants to solve",
                            "search_terms": ["term1", "term2", "term3"]
                        }}"""
        
        response = await web_search_server.generate_response(refine_prompt, timeout=QUERY_REFINE_TIMEOUT)
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return RefinedQuery(
                    original_query=original_query,
                    refined_query=parsed.get("refined_query", original_query),
                    problem_statement=parsed.get("problem_statement", original_query),
                    search_terms=parsed.get("search_terms", [original_query])
                )
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM JSON response")
        
        return RefinedQuery(
            original_query=original_query,
            refined_query=original_query,
            problem_statement=original_query,
            search_terms=[original_query]
        )
        
    except Exception as e:
        logger.error(f"Error refining query: {e}")
        return RefinedQuery(
            original_query=original_query,
            refined_query=original_query,
            problem_statement=original_query,
            search_terms=[original_query]
        )

async def search_web(query: str, num_results: int = MAX_SEARCH_RESULTS, site_filters: Optional[List[str]] = None) -> List[SearchResult]:
    """Search using Google Custom Search API with retry logic and multiple site filter support."""
    if not build or not GOOGLE_API_KEY:
        logger.error("Google Custom Search API not available - missing API key or client library")
        return []
        
    cleaned_query = query.strip()
    if not cleaned_query:
        logger.error("Empty query provided")
        return []
    
    cleaned_query = re.sub(r'\s+', ' ', cleaned_query)
    logger.info(f"Searching Google for: '{cleaned_query}'")
    if site_filters:
        logger.info(f"With site filters: {site_filters}")
    
    # Use Google Custom Search directly with retry logic
    search_data = None
    for attempt in range(MAX_SEARCH_RETRIES):
        try:
            # Apply delay for retries
            await wait_with_backoff(attempt)
            
            logger.info(f"Google search attempt {attempt + 1}/{MAX_SEARCH_RETRIES}")
            search_results = await google_custom_search(cleaned_query, num_results * 2, site_filters)
            
            if search_results:
                logger.info(f"Google search successful on attempt {attempt + 1}")
                search_data = search_results
                break
            else:
                logger.warning(f"No results on attempt {attempt + 1}")
                if attempt == MAX_SEARCH_RETRIES - 1:
                    logger.error("All Google search attempts returned no results")
                    
        except Exception as e:
            logger.error(f"Google search error on attempt {attempt + 1}: {e}")
            if attempt == MAX_SEARCH_RETRIES - 1:
                logger.error("All Google search attempts failed")
                break
            continue
    
    if not search_data:
        logger.error("All Google search attempts failed")
        return []
    
    # Process and rank results with faster processing
    results = []
    for result in search_data[:num_results * 2]:
        try:
            # Skip duplicates
            if any(existing.url == result.url for existing in results):
                continue
            
            result.relevance_score = score_relevance(
                cleaned_query, result.title, result.snippet
            )
            
            # Always include results
            results.append(result)
            
        except Exception as e:
            logger.warning(f"Error processing search result: {e}")
            continue
    
    # Sort by relevance and return top results
    results.sort(key=lambda x: x.relevance_score, reverse=True)
    final_results = results[:num_results]
    logger.info(f"Returning {len(final_results)} processed and ranked results")
    return final_results

async def scrape_content(url: str) -> str:
    """Scrape website content and extract meaningful text."""
    logger.info(f"DEBUG: Starting to scrape URL: {url}")
    try:
        logger.info(f"DEBUG: Fetching webpage with {SCRAPE_TIMEOUT}s timeout")
        html_content = await asyncio.wait_for(
            fetch_webpage(url, timeout=SCRAPE_TIMEOUT), 
            timeout=SCRAPE_TIMEOUT
        )
        logger.info(f"DEBUG: Webpage fetch completed, got {len(html_content) if html_content else 0} characters")
        if not html_content:
            logger.info("DEBUG: No HTML content received")
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]):
            element.decompose()
        
        # Try to find main content
        main_content = ""
        content_selectors = [
            'main', 'article', '[role="main"]',
            '.content', '.post-content', '.entry-content',
            '#content', '#main-content'
        ]
        
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                main_content = ' '.join([elem.get_text() for elem in elements])
                break
        
        if not main_content:
            paragraphs = soup.find_all('p')
            if paragraphs:
                main_content = ' '.join([p.get_text() for p in paragraphs])
            else:
                main_content = soup.get_text()
        
        text = extract_content(main_content)
        cleaned_text = clean_text(text)
        logger.info(f"DEBUG: Scraping completed for {url}, extracted {len(cleaned_text)} characters")
        return cleaned_text
        
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        logger.error(f"DEBUG: Exception type: {type(e)}")
        return ""

def detect_question_intent(query: str) -> dict:
    """Detect the type and intent of the user's question to customize response structure."""
    query_lower = query.lower()
    
    # Define question type patterns
    question_patterns = {
        'how_to': ['how to', 'how do i', 'how can i', 'how would i', 'how should i'],
        'what_is': ['what is', 'what are', 'what does', 'define', 'meaning of'],
        'why': ['why', 'why does', 'why do', 'why is', 'why are'],
        'when': ['when', 'when should', 'when do', 'when is', 'when are'],
        'where': ['where', 'where can', 'where do', 'where is', 'where are'],
        'comparison': ['vs', 'versus', 'compare', 'difference between', 'better than', 'or'],
        'troubleshooting': ['error', 'issue', 'problem', 'fix', 'troubleshoot', 'not working', 'broken'],
        'list': ['list', 'examples', 'types of', 'kinds of', 'options'],
        'best_practices': ['best', 'recommend', 'should', 'good', 'practice', 'tips'],
        'pricing': ['cost', 'price', 'pricing', 'expensive', 'free', 'paid'],
        'installation': ['install', 'setup', 'configure', 'download'],
        'tutorial': ['tutorial', 'guide', 'learn', 'course', 'teach me']
    }
    
    # Detect primary intent
    detected_types = []
    for intent_type, patterns in question_patterns.items():
        if any(pattern in query_lower for pattern in patterns):
            detected_types.append(intent_type)
    
    # Determine primary intent (first match or most specific)
    primary_intent = detected_types[0] if detected_types else 'general'
    
    # Detect context clues
    context_clues = {
        'technical': any(term in query_lower for term in ['code', 'programming', 'api', 'software', 'development']),
        'business': any(term in query_lower for term in ['business', 'marketing', 'sales', 'revenue', 'strategy']),
        'beginner': any(term in query_lower for term in ['beginner', 'new to', 'start', 'basic', 'simple']),
        'advanced': any(term in query_lower for term in ['advanced', 'complex', 'detailed', 'expert']),
        'urgent': any(term in query_lower for term in ['urgent', 'asap', 'quickly', 'fast', 'immediate']),
        'step_by_step': any(term in query_lower for term in ['step', 'steps', 'guide', 'tutorial', 'walkthrough'])
    }
    
    return {
        'primary_intent': primary_intent,
        'detected_types': detected_types,
        'context_clues': context_clues,
        'is_technical': context_clues['technical'],
        'is_beginner': context_clues['beginner'],
        'needs_steps': context_clues['step_by_step'] or primary_intent in ['how_to', 'tutorial', 'installation'],
        'needs_comparison': primary_intent == 'comparison',
        'needs_troubleshooting': primary_intent == 'troubleshooting'
    }

async def generate_solution(refined_query: RefinedQuery, search_results: List[SearchResult], site_filters: Optional[List[str]] = None, fast_mode: bool = False) -> str:
    """Generate final solution using LLM with dynamic sections based on question intent."""
    if not web_search_server.is_llm_available():
        logger.warning("LLM not available for solution generation, using summary fallback")
        return await create_summary(refined_query, search_results, site_filters)
    
    try:
        # Detect question intent for dynamic response structure
        intent = detect_question_intent(refined_query.original_query)
        
        # Use simplified approach for fast mode
        if fast_mode:
            logger.info("Fast mode enabled - using simplified LLM prompt")
            context_parts = []
            source_links = []
            
            for result in search_results[:2]:  # Only use top 2 results for speed
                source_links.append(result.url)
                if result.scraped_content:
                    # Limit content length for faster processing
                    content_preview = result.scraped_content[:800]
                    context_parts.append(f"SOURCE: {result.title}\n{content_preview}")
                elif result.snippet:
                    context_parts.append(f"SNIPPET: {result.title}\n{result.snippet}")
            
            fast_context = '\n\n'.join(context_parts)
            
            fast_prompt = f"""You are an expert providing a quick, clear answer. Be concise but helpful.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{fast_context}

Provide a focused answer with:

# 🎯 Quick Answer
[Direct answer to their question]

## 📝 Key Points
[2-3 main points from the research]

## 💡 Action Items
[What they should do next]

IMPORTANT: If the user is asking for current information like "today's date", "current time", "current weather", or "latest news", 
DO NOT provide specific dates, times, or data from the research as these are likely outdated. Instead, explain that this 
information needs to be checked from current sources.

Keep it clear, actionable, and under 400 words."""
            
            try:
                solution = await web_search_server.generate_response(fast_prompt, timeout=6)
                logger.info("Fast mode LLM response received successfully")
                
                # Add sources
                sources_section = "\n\n---\n\n## 🔍 **Sources**\n"
                for i, url in enumerate(source_links, 1):
                    try:
                        domain = urlparse(url).netloc
                        sources_section += f"- **[{domain}]({url})**\n"
                    except:
                        sources_section += f"- **[Source {i}]({url})**\n"
                
                return solution + sources_section
            except asyncio.TimeoutError:
                logger.warning("Fast mode LLM timed out, using basic summary")
                return await create_summary(refined_query, search_results, site_filters)
        
        sorted_results = sorted(search_results, key=lambda x: x.relevance_score, reverse=True)
        
        # Build context from results
        context_parts = []
        source_links = []
        
        for result in sorted_results[:3]:
            if result.scraped_content:
                context_parts.append(f"SOURCE: {result.title}\n{result.scraped_content}")
                source_links.append(result.url)
            elif result.snippet:
                context_parts.append(f"SNIPPET: {result.title}\n{result.snippet}")
                source_links.append(result.url)
        
        context = '\n\n'.join(context_parts)
        
        # Create dynamic prompt based on intent
        if intent['primary_intent'] == 'how_to':
            prompt = f"""You are an expert providing clear, actionable instructions. The user wants to learn HOW TO do something specific.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context}

PROVIDE A COMPREHENSIVE HOW-TO GUIDE WITH THESE SECTIONS:

# 🎯 Quick Answer
[One clear sentence stating what they need to do]

## 🔧 Step-by-Step Instructions
[Provide numbered, specific steps - be exact about what to click, where to go, what to type]

## ⚠️ Prerequisites & Requirements
[List what they need before starting]

## 💡 Pro Tips & Best Practices
[Helpful shortcuts, common mistakes to avoid, expert recommendations]

## 🔍 Alternative Methods
[If applicable, mention other ways to achieve the same result]

STYLE: Use simple, direct language. Be specific about button names, menu locations, exact steps."""

        elif intent['primary_intent'] == 'what_is':
            prompt = f"""You are an expert providing clear explanations. The user wants to UNDERSTAND what something is.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context}

PROVIDE A COMPREHENSIVE EXPLANATION WITH THESE SECTIONS:

# 📖 Definition & Overview
[Clear, concise definition in simple terms]

## 🔍 Key Characteristics
[Main features, properties, or attributes]

## 🎯 Purpose & Use Cases
[What it's used for, why it matters, real-world applications]

## 📊 How It Works
[Basic mechanism or process, if applicable]

## 🔗 Related Concepts
[Connected ideas, similar concepts, or broader category]

STYLE: Start simple, then add detail. Use analogies if helpful. Make it accessible."""

        elif intent['primary_intent'] == 'troubleshooting':
            prompt = f"""You are a technical support expert helping solve a problem. The user has an ISSUE that needs fixing.

USER'S PROBLEM: {refined_query.problem_statement}

RESEARCH DATA:
{context}

PROVIDE A SYSTEMATIC TROUBLESHOOTING GUIDE WITH THESE SECTIONS:

# 🚨 Problem Summary
[Clearly state what's wrong and likely causes]

## 🔧 Quick Fixes (Try These First)
[1-3 most common solutions that often work]

## 🔍 Detailed Troubleshooting Steps
[Systematic approach to identify and fix the issue]

## 🛠️ Advanced Solutions
[More complex fixes if basic ones don't work]

## 🚫 Common Mistakes to Avoid
[What NOT to do, pitfalls to watch out for]

## 🆘 When to Seek Help
[Signs you need professional assistance]

STYLE: Be systematic, start with simple fixes, escalate complexity gradually."""

        elif intent['primary_intent'] == 'comparison':
            prompt = f"""You are a comparison expert helping the user make an informed decision. They want to COMPARE options.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context}

PROVIDE A COMPREHENSIVE COMPARISON WITH THESE SECTIONS:

# ⚖️ Quick Comparison Summary
[Brief overview of main differences]

## 📊 Feature Comparison
[Side-by-side comparison of key features]

## 👍 Pros & Cons
[Advantages and disadvantages of each option]

## 💰 Cost Analysis
[Price comparison if applicable]

## 🎯 Best Use Cases
[When to choose each option]

## 🏆 Final Recommendation
[Which option is best for different scenarios]

STYLE: Be balanced, present facts objectively, help them decide."""

        elif intent['primary_intent'] == 'best_practices':
            prompt = f"""You are a best practices expert providing professional recommendations. The user wants to know the BEST way to do something.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context}

PROVIDE EXPERT RECOMMENDATIONS WITH THESE SECTIONS:

# 🌟 Key Recommendations
[Top 3-5 most important best practices]

## 🎯 Implementation Guide
[How to apply these practices step-by-step]

## ⚡ Quick Wins
[Easy improvements they can make immediately]

## 🚫 Common Pitfalls
[What to avoid, frequent mistakes]

## 📈 Advanced Techniques
[For those ready to go further]

## 📊 How to Measure Success
[How to know if they're doing it right]

STYLE: Be authoritative but practical, focus on actionable advice."""

        else:
            # General intent - comprehensive answer
            prompt = f"""You are an expert providing comprehensive, helpful information. Analyze the user's question and provide the most useful response.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context}

PROVIDE A COMPREHENSIVE ANSWER WITH THESE DYNAMIC SECTIONS:

# 🎯 Direct Answer
[Clear, concise answer to their specific question]

## 📝 Detailed Explanation
[More thorough explanation with context]

## 🔧 Practical Steps
[If applicable, actionable steps they can take]

## 💡 Key Insights
[Important things to know or remember]

## 🔍 Additional Resources
[Related information or next steps]

STYLE: Be clear, helpful, and comprehensive. Adapt sections based on what the user needs most."""

        # Add common instructions for all prompts
        prompt += f"""

CRITICAL REQUIREMENTS:
- Write in clear, simple language
- Use specific examples when possible
- Include exact names, numbers, or details from the research
- Be actionable and practical
- Use emojis sparingly for visual organization
- Focus on what the user can DO with this information

IMPORTANT: If the user is asking for current information like "today's date", "current time", "current weather", or "latest news", 
DO NOT provide specific dates, times, or data from the research as these are likely outdated. Instead, explain that this 
information needs to be checked from current sources and provide guidance on where to find accurate current information.

Context Notes:
- User expertise level: {'Beginner' if intent['is_beginner'] else 'General'}
- Technical content: {'Yes' if intent['is_technical'] else 'No'}
- Site filters: {', '.join(site_filters) if site_filters else 'None'}"""

        logger.info(f"Generating solution with intent: {intent['primary_intent']}")
        
        # Try with full timeout first
        try:
            solution = await web_search_server.generate_response(prompt, timeout=SOLUTION_TIMEOUT)
            logger.info("LLM response received successfully")
        except asyncio.TimeoutError:
            logger.warning(f"LLM timed out after {SOLUTION_TIMEOUT}s, trying with simplified prompt")
            
            # Create simplified fallback prompt
            simplified_prompt = f"""You are an expert providing a clear, helpful answer. Be concise but comprehensive.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context[:2000]}  # Limit context for faster processing

Provide a clear answer with these sections:

# 🎯 Answer
[Direct answer to their question]

## 📝 Key Points
[3-4 main points from the research]

## 💡 Next Steps
[What they should do next]

IMPORTANT: If the user is asking for current information like "today's date", "current time", "current weather", or "latest news", 
DO NOT provide specific dates, times, or data from the research as these are likely outdated. Instead, explain that this 
information needs to be checked from current sources.

Keep it clear, actionable, and under 500 words."""
            
            try:
                solution = await web_search_server.generate_response(simplified_prompt, timeout=8)
                logger.info("Simplified LLM response received successfully")
            except asyncio.TimeoutError:
                logger.error("Even simplified LLM request timed out, using summary fallback")
                return await create_summary(refined_query, search_results, site_filters)
        
        # Add sources
        sources_section = "\n\n---\n\n## 🔍 **Sources**\n"
        for i, url in enumerate(source_links, 1):
            try:
                domain = urlparse(url).netloc
                sources_section += f"- **[{domain}]({url})**\n"
            except:
                sources_section += f"- **[Source {i}]({url})**\n"
        
        final_response = solution + sources_section
        logger.info(f"Generated solution with {len(source_links)} sources, intent: {intent['primary_intent']}")
        return final_response
        
    except asyncio.TimeoutError:
        logger.error(f"LLM solution generation timed out after {SOLUTION_TIMEOUT} seconds")
        raise Exception(f"LLM timeout after {SOLUTION_TIMEOUT}s")
    except Exception as e:
        logger.error(f"Error generating LLM solution: {e}")
        raise e

async def create_summary(refined_query: RefinedQuery, search_results: List[SearchResult], site_filters: Optional[List[str]] = None) -> str:
    """Generate a structured summary with LLM when available, with dynamic sections based on question intent."""
    if not search_results:
        filter_msg = f" on {', '.join(site_filters)}" if site_filters else ""
        return f"""# ❌ No Results Found

No search results found for: **{refined_query.original_query}**{filter_msg}

## Possible Reasons:
- Query too specific or uncommon
- Network connectivity issues  
- Search service temporarily unavailable
- Site filters too restrictive

## 💡 Suggestions:
- Try simpler, more general terms
- Check your internet connection
- Remove or broaden site filters
- Retry in a few moments"""

    # Sort by relevance
    sorted_results = sorted(search_results[:3], key=lambda x: x.relevance_score, reverse=True)
    
    # Build context from results
    context_parts = []
    source_links = []
    
    for result in sorted_results:
        source_links.append(result.url)
        if result.scraped_content:
            context_parts.append(f"SOURCE: {result.title}\n{result.scraped_content}")
        elif result.snippet:
            context_parts.append(f"SNIPPET: {result.title}\n{result.snippet}")
    
    context = '\n\n'.join(context_parts)
    
    # Try LLM-enhanced summary if available
    if web_search_server.is_llm_available():
        try:
            # Detect question intent for dynamic response
            intent = detect_question_intent(refined_query.original_query)
            
            summary_prompt = f"""You are an expert information synthesizer. Create a clear, structured summary from the research data.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context}

Create a comprehensive summary with these dynamic sections based on the question type:

# 📋 Summary

## 🎯 Key Answer
[Direct answer to their question in 1-2 sentences]

## 📝 Main Points
[3-5 key findings from the research]

## 🔍 Important Details
[Specific information, numbers, examples they should know]

{('## 🔧 Action Steps' if intent['needs_steps'] else '## 💡 Key Insights')}
[Either actionable steps or important insights depending on question type]

{'## ⚠️ Considerations' if intent['needs_troubleshooting'] else '## 🔗 Related Information'}
[Either warnings/considerations or additional context]

REQUIREMENTS:
- Be concise but comprehensive
- Use information directly from the research
- Focus on what's most relevant to their question
- Use clear, simple language
- Include specific details when available

IMPORTANT: If the user is asking for current information like "today's date", "current time", "current weather", or "latest news", 
DO NOT provide specific dates, times, or data from the research as these are likely outdated. Instead, explain that this 
information needs to be checked from current sources.

Question type detected: {intent['primary_intent']}"""
            
            logger.info(f"Generating LLM summary with intent: {intent['primary_intent']}")
            
            # Try with full timeout first
            try:
                summary = await web_search_server.generate_response(summary_prompt, timeout=SOLUTION_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(f"LLM summary timed out after {SOLUTION_TIMEOUT}s, trying simplified version")
                
                # Create simplified summary prompt
                simplified_summary_prompt = f"""Create a concise summary from the research data.

USER'S QUESTION: {refined_query.problem_statement}

RESEARCH DATA:
{context[:1500]}  # Limit context for faster processing

Provide a brief summary with:

# 📋 Summary
[Direct answer in 1-2 sentences]

## 📝 Key Points
[3 main findings]

## 💡 Important
[What they should know]

IMPORTANT: If the user is asking for current information like "today's date", "current time", "current weather", or "latest news", 
DO NOT provide specific dates, times, or data from the research as these are likely outdated. Instead, explain that this 
information needs to be checked from current sources.

Keep it under 300 words."""
                
                try:
                    summary = await web_search_server.generate_response(simplified_summary_prompt, timeout=6)
                    logger.info("Simplified LLM summary received successfully")
                except asyncio.TimeoutError:
                    logger.warning("LLM summary timed out completely, using basic summary")
                    # Fall through to basic summary
            
            # Add sources
            sources_section = "\n\n---\n\n## 🔍 **Sources**\n"
            for i, url in enumerate(source_links, 1):
                try:
                    domain = urlparse(url).netloc
                    sources_section += f"- **[{domain}]({url})**\n"
                except:
                    sources_section += f"- **[Source {i}]({url})**\n"
            
            final_response = summary + sources_section
            logger.info(f"Generated LLM summary with {len(source_links)} sources")
            return final_response
            
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}, falling back to basic summary")
            # Fall through to basic summary
    
    # Basic summary fallback (when LLM not available)
    logger.info("Generating basic summary without LLM")
    intent = detect_question_intent(refined_query.original_query)
    
    # Extract information from results
    key_points = []
    practical_steps = []
    
    for result in sorted_results:
        if result.scraped_content and len(result.scraped_content) > 100:
            sentences = [s.strip() for s in result.scraped_content.split('.') if len(s.strip()) > 20]
            query_words = [word.lower() for word in refined_query.original_query.split() if len(word) > 2]
            
            relevant_sentences = []
            for sentence in sentences[:15]:
                if any(word in sentence.lower() for word in query_words):
                    clean_sentence = sentence.strip()
                    if clean_sentence and len(clean_sentence) > 30:
                        if any(step_word in clean_sentence.lower() for step_word in ['step', 'first', 'then', 'next', 'click', 'select', 'open', 'create', 'go to']):
                            practical_steps.append(clean_sentence)
                        else:
                            key_points.append(clean_sentence)
                        relevant_sentences.append(clean_sentence)
                if len(relevant_sentences) >= 3:
                    break
        elif result.snippet:
            key_points.append(result.snippet)
    
    # Build structured response based on intent
    if intent['primary_intent'] == 'how_to':
        response = f"""# 🔧 How-To Guide

## 📋 Quick Answer
"""
        if key_points:
            response += f"{key_points[0][:300]}{'...' if len(key_points[0]) > 300 else ''}\n"
        
        if practical_steps:
            response += f"\n## 🔧 Steps to Follow\n\n"
            for i, step in enumerate(practical_steps[:5], 1):
                response += f"{i}. {step.strip().rstrip('.')}\n"
        
        if len(key_points) > 1:
            response += f"\n## 💡 Additional Tips\n\n"
            for point in key_points[1:3]:
                response += f"• {point.strip()[:200]}{'...' if len(point) > 200 else ''}\n"
    
    elif intent['primary_intent'] == 'what_is':
        response = f"""# 📖 Definition & Explanation

## 🎯 What It Is
"""
        if key_points:
            response += f"{key_points[0][:400]}{'...' if len(key_points[0]) > 400 else ''}\n"
        
        if len(key_points) > 1:
            response += f"\n## 🔍 Key Details\n\n"
            for point in key_points[1:4]:
                response += f"• {point.strip()[:200]}{'...' if len(point) > 200 else ''}\n"
    
    elif intent['primary_intent'] == 'troubleshooting':
        response = f"""# 🔧 Troubleshooting Guide

## 🚨 Problem Summary
"""
        if key_points:
            response += f"{key_points[0][:300]}{'...' if len(key_points[0]) > 300 else ''}\n"
        
        if practical_steps:
            response += f"\n## 🔧 Solutions\n\n"
            for i, step in enumerate(practical_steps[:5], 1):
                response += f"{i}. {step.strip().rstrip('.')}\n"
        
        if len(key_points) > 1:
            response += f"\n## 💡 Additional Information\n\n"
            for point in key_points[1:3]:
                response += f"• {point.strip()[:200]}{'...' if len(point) > 200 else ''}\n"
    
    else:
        # General format
        response = f"""# ✅ Research Summary

## 📋 Key Findings
"""
        if key_points:
            response += f"{key_points[0][:300]}{'...' if len(key_points[0]) > 300 else ''}\n"
        
        if practical_steps:
            response += f"\n## 🔧 Action Items\n\n"
            for i, step in enumerate(practical_steps[:5], 1):
                response += f"{i}. {step.strip().rstrip('.')}\n"
        
        if len(key_points) > 1:
            response += f"\n## 📝 Additional Details\n\n"
            for point in key_points[1:3]:
                response += f"• {point.strip()[:200]}{'...' if len(point) > 200 else ''}\n"
    
    # Add sources
    response += f"\n---\n\n## 🔍 **Sources**\n"
    for i, url in enumerate(source_links, 1):
        try:
            domain = urlparse(url).netloc
            response += f"- **[{domain}]({url})**\n"
        except:
            response += f"- **[Source {i}]({url})**\n"
    
    return response

def generate_fallback_analysis(query: str, search_results: List[SearchResult], site_filters: Optional[List[str]] = None) -> str:
    """Generate basic web search analysis when LLM is not available."""
    analysis = []
    analysis.append("🔍 **Web Search Analysis (Basic Mode)**")
    analysis.append(f"Note: Advanced AI analysis unavailable. Please configure your LLM provider for enhanced features.")
    analysis.append("")
    
    # Search statistics
    analysis.append(f"📊 **Search Statistics:**")
    analysis.append(f"  • Query: {query}")
    analysis.append(f"  • Results Found: {len(search_results)}")
    if site_filters:
        analysis.append(f"  • Site Filters: {', '.join(site_filters)}")
    analysis.append("")
    
    # Results overview
    if search_results:
        analysis.append(f"📋 **Top Results:**")
        for i, result in enumerate(search_results[:3], 1):
            analysis.append(f"  {i}. **{result.title}**")
            analysis.append(f"     • URL: {result.url}")
            analysis.append(f"     • Relevance: {result.relevance_score:.2f}")
            if result.scraped_content:
                content_preview = result.scraped_content[:100] + "..." if len(result.scraped_content) > 100 else result.scraped_content
                analysis.append(f"     • Content: {content_preview}")
            analysis.append("")
    
    # Simple aggregation
    if search_results:
        analysis.append(f"📝 **Quick Summary:**")
        analysis.append(f"Found {len(search_results)} relevant results for your query.")
        scraped_count = sum(1 for result in search_results if result.scraped_content)
        analysis.append(f"Successfully scraped content from {scraped_count} sources.")
        analysis.append("")
    
    return "\n".join(analysis)

def format_results(search_results: List[SearchResult], query: str, site_filters: Optional[List[str]] = None) -> str:
    """Format search results when scraping fails."""
    formatted_results = []
    for i, result in enumerate(search_results, 1):
        formatted_results.append(f"""
{i}. **{result.title}**
   Summary: {result.snippet}
""")
    
    filter_info = f" (filtered to {', '.join(site_filters)})" if site_filters else ""
    
    # Build consistent sources section
    sources_section = "\n\n---\n\n## 🔍 **Sources**\n"
    for i, result in enumerate(search_results, 1):
        try:
            domain = urlparse(result.url).netloc
            sources_section += f"- **[{domain}]({result.url})**\n"
        except:
            sources_section += f"- **[Source {i}]({result.url})**\n"
    
    return f"""# Search Results for: '{query}'{filter_info}

{chr(10).join(formatted_results)}

*Note: Content scraping was not available, showing search results with summaries.*
{sources_section}"""

async def execute_intelligent_search(query: str, num_sources: int, fast_mode: bool = False, site_filters: Optional[List[str]] = None) -> str:
    """Internal function to perform websearch following the 5-step process with optimized performance."""
    num_sources = 3  # Fixed at 3 as per specification
    
    logger.info("Step 1: Processing user query...")
    if site_filters:
        logger.info(f"Using site filters: {site_filters}")
    
    # Step 2: Refine query (or skip in fast mode)
    if fast_mode:
        logger.info("Step 2: Fast mode - skipping LLM query refinement")
        refined_query = RefinedQuery(
            original_query=query,
            refined_query=query,
            problem_statement=f"Find information about: {query}",
            search_terms=query.split()
        )
    else:
        logger.info("Step 2: Refining query using LLM...")
        try:
            refined_query = await asyncio.wait_for(
                enhance_query(query), 
                timeout=QUERY_REFINE_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("Query refinement timed out, using original query")
            refined_query = RefinedQuery(
                original_query=query,
                refined_query=query,
                problem_statement=f"Find information about: {query}",
                search_terms=query.split()
            )
    
    # Step 3: Perform search
    logger.info("Step 3: Performing web search...")
    try:
        search_results = await asyncio.wait_for(
            search_web(refined_query.refined_query, num_sources, site_filters), 
            timeout=SEARCH_TIMEOUT
        )
        logger.info(f"Step 3: Search completed, got {len(search_results) if search_results else 0} results")
    except asyncio.TimeoutError:
        logger.error(f"Step 3: Search timed out after {SEARCH_TIMEOUT} seconds")
        raise
    except Exception as e:
        logger.error(f"Step 3: Search failed with error: {e}")
        raise
    
    if not search_results:
        logger.error("Step 3: No search results found, skipping Steps 4 and 5")
        filter_msg = f" on {', '.join(site_filters)}" if site_filters else ""
        return f"""# No Results Found

            I couldn't find any web results for your query: '{query}'{filter_msg}. 

            This could be due to:
            1. **Network connectivity issues**
            2. **Search service temporarily unavailable** 
            3. **Query too specific** - try broader terms
            4. **Site filters too restrictive**{f" for {', '.join(site_filters)}" if site_filters else ""}

            **Suggestions:**
            - Try a simpler version of your query
            - Check your internet connection
            - Remove or broaden site filters
            - Try again in a few moments

            ---

            ## 🔍 **Sources**
            *No sources available - search returned no results*"""

    # Step 4: Scrape content with optimized approach
    if fast_mode:
        # In fast mode, only scrape first URL to save time
        logger.info("Step 4: Fast mode - scraping only first URL...")
        scrape_results = search_results[:1]
        scrape_timeout = 2  # Very fast for MCP
    else:
        # In full mode, scrape all URLs concurrently for speed
        logger.info(f"Step 4: Scraping content from {len(search_results[:3])} URLs concurrently...")
        scrape_results = search_results[:3]
        scrape_timeout = SCRAPING_TIMEOUT
    
    # Parallel scraping for better performance
    scrape_tasks = [scrape_content(result.url) for result in scrape_results]
    
    try:
        scraped_contents = await asyncio.wait_for(
            asyncio.gather(*scrape_tasks, return_exceptions=True),
            timeout=scrape_timeout
        )
        logger.info("Step 4: Content scraping completed successfully")
    except asyncio.TimeoutError:
        logger.warning(f"Step 4: Scraping timed out after {scrape_timeout} seconds")
        scraped_contents = [""] * len(scrape_results)
    except Exception as e:
        logger.error(f"Step 4: Scraping failed with exception: {e}")
        scraped_contents = [""] * len(scrape_results)
    
    # Process results efficiently
    all_results = []
    scraped_count = 0
    
    for i, result in enumerate(search_results[:3]):
        if i < len(scraped_contents):
            content = scraped_contents[i]
            if isinstance(content, str) and content:
                result.scraped_content = content
                result.scrape_success = True
                scraped_count += 1
            else:
                result.scrape_success = False
                result.scraped_content = ""
        else:
            result.scrape_success = False
            result.scraped_content = ""
        
        # Quick relevance scoring
        result.relevance_score = score_relevance(
            refined_query.refined_query, 
            result.title, 
            result.snippet, 
            result.scraped_content
        )
        all_results.append(result)
    
    all_results.sort(key=lambda x: x.relevance_score, reverse=True)
    logger.info(f"Step 4 Results: {scraped_count}/{len(search_results[:3])} URLs successfully scraped")
    
    # Step 5: Generate solution optimized for performance
    if fast_mode:
        logger.info("Step 5: Fast mode - generating simple summary without LLM")
        return await create_summary(refined_query, all_results, site_filters)
    else:
        logger.info("Step 5: Using LLM for intelligent solution generation...")
        try:
            solution = await generate_solution(refined_query, all_results, site_filters, fast_mode)
            logger.info("Step 5: LLM solution generation completed successfully")
            return solution
        except Exception as e:
            logger.error(f"Step 5: LLM solution generation failed: {e}, falling back to summary")
            return await create_summary(refined_query, all_results, site_filters)



# =============================
# MCP Tool Functions
# =============================
@mcp.tool()
async def web_search_test_google_search_connectivity() -> str:
    """
    Test Google Custom Search API connectivity and configuration.
    
    This tool verifies that:
    1. Google API client library is available
    2. API key is configured
    3. Search engine ID is configured
    4. API connection is working
    
    Returns:
        str: Connectivity test results with configuration status
    """
    logger.info("Testing Google Custom Search API connectivity...")
    
    test_results = []
    test_results.append("🔧 **Google Custom Search API Connectivity Test**\n")
    
    # Test 1: Check if Google API client is available
    if not build:
        test_results.append("❌ **Google API Client Library**: NOT AVAILABLE")
        test_results.append("   • Install: `pip install google-api-python-client`")
        test_results.append("")
        return "\n".join(test_results)
    else:
        test_results.append("✅ **Google API Client Library**: Available")
    
    # Test 2: Check API key
    if not GOOGLE_API_KEY:
        test_results.append("❌ **Google API Key**: NOT CONFIGURED")
        test_results.append("   • Set GOOGLE_API_KEY environment variable")
        test_results.append("")
        return "\n".join(test_results)
    else:
        api_key_preview = f"{GOOGLE_API_KEY[:8]}..." if len(GOOGLE_API_KEY) > 8 else "configured"
        test_results.append(f"✅ **Google API Key**: {api_key_preview}")
    
    # Test 3: Check search engine ID
    if not GOOGLE_SEARCH_ENGINE_ID:
        test_results.append("❌ **Search Engine ID**: NOT CONFIGURED")
        test_results.append("   • Set GOOGLE_SEARCH_ENGINE_ID environment variable")
        test_results.append("")
        return "\n".join(test_results)
    else:
        test_results.append(f"✅ **Search Engine ID**: {GOOGLE_SEARCH_ENGINE_ID}")
    
    # Test 4: Try actual API call
    test_results.append("\n🔍 **Testing API Connection...**")
    
    try:
        # Try a simple search to test connectivity
        test_search_results = await asyncio.wait_for(
            google_custom_search("test connectivity", 1),
            timeout=5.0
        )
        
        if test_search_results:
            test_results.append("✅ **API Connection**: WORKING")
            test_results.append(f"   • Successfully retrieved {len(test_search_results)} test result(s)")
            test_results.append(f"   • Test result: {test_search_results[0].title[:50]}...")
        else:
            test_results.append("⚠️ **API Connection**: No results returned")
            test_results.append("   • API is responding but returned no results")
            test_results.append("   • This may be normal for test queries")
        
        test_results.append("")
        test_results.append("🎉 **Overall Status**: READY FOR USE")
        test_results.append("   • All systems operational")
        test_results.append("   • You can now use intelligent_web_search and other tools")
        
    except asyncio.TimeoutError:
        test_results.append("❌ **API Connection**: TIMEOUT")
        test_results.append("   • API request timed out after 5 seconds")
        test_results.append("   • Check your internet connection")
        
    except Exception as e:
        test_results.append("❌ **API Connection**: FAILED")
        test_results.append(f"   • Error: {str(e)}")
        test_results.append("   • Check your API key and search engine ID")
    
    test_results.append("")
    test_results.append("## 📋 **Configuration Summary:**")
    test_results.append(f"• **API Key**: {api_key_preview}")
    test_results.append(f"• **Search Engine ID**: {GOOGLE_SEARCH_ENGINE_ID}")
    test_results.append(f"• **LLM Available**: {'Yes' if web_search_server.is_llm_available() else 'No'}")
    
    return "\n".join(test_results)


@mcp.tool()
async def web_search_intelligent_web_search(query: str, num_sources: int = 3, fast_mode: bool = False, site_filters: Optional[List[str]] = None) -> str:
    """
    Perform intelligent web search with scraping and solution generation.
    
    This tool executes a 5-step research process for comprehensive analysis:
    1. Take user query and analyze the problem
    2. Refine the query using LLM (skipped in fast_mode)
    3. Perform web search to get top 3 relevant results  
    4. Scrape content (1 URL in fast_mode, 3 URLs in full mode)
    5. Generate solution (simple summary in fast_mode, comprehensive LLM analysis in full mode)
    
    Args:
        query (str): Your question or problem statement
        num_sources (int): Number of web sources to scrape (fixed at 3)
        fast_mode (bool): Fast mode for quick results under 10s (default: False for depth analysis)
        site_filters (Optional[List[str]]): Optional list of domain filters (e.g., ["learn.microsoft.com", "docs.python.org"])
    
    Returns:
        str: Comprehensive solution with source links, optimized for deep analysis by default
        
    Note: Set fast_mode=True for quick responses. Default is comprehensive analysis mode.
    """
    logger.info(f"Starting intelligent web search for query: {query}")
    if site_filters:
        logger.info(f"Filtering results to sites: {site_filters}")
    
    try:
        # Use the configured timeout for proper processing
        logger.info(f"Starting search with timeout: {OVERALL_TIMEOUT} seconds, fast_mode: {fast_mode}")
        return await asyncio.wait_for(
            execute_intelligent_search(query, 3, fast_mode, site_filters), 
            timeout=OVERALL_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error(f"Search operation timed out after {OVERALL_TIMEOUT} seconds")
        # If already in fast mode, try with even more aggressive timeout
        if fast_mode:
            try:
                logger.info("Attempting ultra-fast fallback...")
                return await asyncio.wait_for(
                    execute_intelligent_search(query, 3, True, site_filters), 
                    timeout=6  # Ultra-fast timeout for fallback
                )
            except asyncio.TimeoutError:
                return f"Search timed out even in fast mode. For faster results, try a simpler query or use the simple_web_search tool."
            except Exception as e:
                return f"Search failed: {str(e)}"
        else:
            # Try once more with fast mode as fallback
            try:
                logger.info("Comprehensive search timed out, attempting fast mode fallback...")
                return await asyncio.wait_for(
                    execute_intelligent_search(query, 3, True, site_filters), 
                    timeout=10  # Reasonable timeout for fast mode fallback
                )
            except asyncio.TimeoutError:
                return f"Search timed out. The query might be too complex. Please try using fast_mode=True or the quick_web_search tool."
            except Exception as e:
                return f"Search failed: {str(e)}"
    except Exception as e:
        logger.error(f"Error in intelligent web search: {e}")
        return f"Search error: {str(e)}. Please try the simple_web_search tool for faster results."


@mcp.tool()
async def web_search_quick_web_search(query: str, site_filters: Optional[List[str]] = None) -> str:
    """
    Perform a quick web search with AI analysis optimized for speed.
    
    This tool provides fast results with simplified LLM analysis, designed for when you need
    quick answers without waiting for full comprehensive analysis.
    
    Args:
        query (str): Your search query
        site_filters (Optional[List[str]]): Optional list of domain filters
    
    Returns:
        str: Quick analysis with key points and actionable information
    """
    logger.info(f"Starting quick web search for query: {query}")
    if site_filters:
        logger.info(f"Filtering results to sites: {site_filters}")
    
    try:
        # Use reduced timeout for faster response
        return await asyncio.wait_for(
            execute_intelligent_search(query, 3, True, site_filters),  # Force fast_mode=True
            timeout=8  # Reduced overall timeout for MCP
        )
    except asyncio.TimeoutError:
        logger.error("Quick search timed out, trying simple search")
        # Fallback to simple search
        try:
            search_results = await asyncio.wait_for(
                search_web(query, 3, site_filters), 
                timeout=4  # Very fast timeout for fallback
            )
            return format_results(search_results, query, site_filters)
        except Exception as e:
            return f"Quick search failed: {str(e)}. Please try a simpler query."
    except Exception as e:
        logger.error(f"Error in quick web search: {e}")
        return f"Quick search error: {str(e)}. Please try again."


@mcp.tool()
async def web_search_simple_web_search(query: str, site_filters: Optional[List[str]] = None) -> str:
    """
    Perform a simple web search without AI analysis.
    
    This tool provides basic search results with titles, URLs, and snippets.
    Useful for quick searches when you don't need full analysis.
    
    Args:
        query (str): Your search query
        site_filters (Optional[List[str]]): Optional list of domain filters (e.g., ["github.com", "stackoverflow.com"])
    
    Returns:
        str: Formatted search results with titles, URLs, and snippets
    """
    logger.info(f"Starting simple web search for query: {query}")
    if site_filters:
        logger.info(f"Filtering results to sites: {site_filters}")
    
    try:
        # Perform basic search with optimized timeout
        search_results = await asyncio.wait_for(
            search_web(query, 5, site_filters), 
            timeout=4  # Fast timeout for MCP simple search
        )
        
        if not search_results:
            filter_msg = f" on {', '.join(site_filters)}" if site_filters else ""
            return f"""# No Results Found

            No search results found for: **{query}**{filter_msg}

            ## Suggestions:
            - Try different keywords
            - Check your internet connection
            - Remove or broaden site filters if used"""
        
        # Format results without analysis
        return format_results(search_results, query, site_filters)
        
    except Exception as e:
        logger.error(f"Error in simple web search: {e}")
        return f"Search error: {str(e)}. Please try again."


@mcp.tool()
async def web_search_analyze_url(url: str, analysis_type: str = "content") -> str:
    """
    Analyze a specific URL's content using LLM.
    
    This tool scrapes content from a URL and provides AI-powered analysis.
    
    Args:
        url (str): The URL to analyze
        analysis_type (str): Type of analysis ("content", "summary", "structure")
    
    Returns:
        str: Analysis results with insights and key points
    """
    logger.info(f"Starting URL analysis for: {url}")
    
    try:
        # Scrape the URL with optimized timeout
        content = await asyncio.wait_for(
            scrape_content(url), 
            timeout=SCRAPE_TIMEOUT
        )
        
        if not content:
            return f"""# Unable to Analyze URL

            Could not scrape content from: **{url}**

            ## Possible Reasons:
            - URL is not accessible
            - Content is behind authentication
            - Site blocks automated access
            - Network connectivity issues"""
        
        # Use LLM for analysis if available
        if web_search_server.is_llm_available():
            try:
                analysis_prompt = f"""Analyze the following web content and provide insights:

                URL: {url}
                Analysis Type: {analysis_type}

                CONTENT:
                {content[:3000]}  # Limit content for LLM processing

                Please provide a comprehensive analysis including:
                1. Main topic and purpose
                2. Key points and insights
                3. Content structure and organization
                4. Quality and usefulness assessment
                5. Target audience

                Format your response clearly with headers and bullet points."""
                
                analysis = await web_search_server.generate_response(analysis_prompt, timeout=SOLUTION_TIMEOUT)
                
                return f"""# 📊 URL Analysis

                **URL:** {url}
                **Analysis Type:** {analysis_type}

                {analysis}

                ---

                ## 🔍 **Source**
                - **[{urlparse(url).netloc}]({url})**"""
                
            except Exception as e:
                logger.error(f"LLM analysis failed: {e}")
                # Fall back to basic analysis
                pass
        
        # Basic analysis fallback
        word_count = len(content.split())
        char_count = len(content)
        
        return f"""# 📄 URL Content Analysis (Basic Mode)

        **URL:** {url}
        **Analysis Type:** {analysis_type}

        ## 📊 **Content Statistics:**
        • Word Count: {word_count}
        • Character Count: {char_count}

        ## 📝 **Content Preview:**
        {content[:50000]}...

        ## 💡 **Note:**
        Advanced AI analysis unavailable. Please configure your LLM provider for enhanced features.

        ---

        ## 🔍 **Source**
        - **[{urlparse(url).netloc}]({url})**"""
        
    except Exception as e:
        logger.error(f"Error analyzing URL: {e}")
        return f"URL analysis error: {str(e)}. Please check the URL and try again."



logger.info("Web Search Scrape RAG MCP server initialized successfully!")
logger.info("Features: Dynamic intent detection, Google Custom Search, content scraping, multi-provider LLM support, connectivity testing")
logger.info("Tools registered: web_search_test_google_search_connectivity, web_search_intelligent_web_search, web_search_quick_web_search, web_search_simple_web_search, web_search_analyze_url")
logger.info("Site filters now support multiple domains for targeted searching")
logger.info("Performance optimized: Extended timeouts for complex LLM prompts, progressive fallback strategies")
logger.info("New features: Intent-based dynamic responses, fast mode for quick results, timeout handling with fallbacks")
if web_search_server.is_llm_available():
    logger.info("Ready to perform intelligent web research using Google Custom Search API with enhanced LLM capabilities!")
else:
    logger.info("Ready to perform web research using Google Custom Search API (LLM features disabled - check configuration)")

if __name__ == "__main__":
    mcp.run()