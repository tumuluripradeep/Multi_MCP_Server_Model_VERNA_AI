import os
import sys
from typing import Any, Optional, Dict, List
import asyncio
import json
import re
import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Add the Servers directory to the path to import llm_factory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_factory import LLMEnhancedMCP

# Initialize the LLM-enhanced MCP server
logger.info("Initializing LLM-Enhanced Content Analysis MCP server...")
# Build absolute path to config file to ensure it's found regardless of working directory
current_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(current_dir, '..', 'config', 'llm_config.json')
config_path = os.path.abspath(config_path)
logger.info(f"Using config path: {config_path}")
content_server = LLMEnhancedMCP("content-analysis", config_path)
mcp = content_server.get_mcp_server()

# Configuration for different content types
SUPPORTED_CONTENT_TYPES = [
    "text/plain",
    "text/html",
    "text/markdown",
    "application/json",
    "application/xml",
    "text/csv"
]

# Content analysis patterns
CONTENT_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b\d{3}-\d{3}-\d{4}\b|\b\(\d{3}\)\s*\d{3}-\d{4}\b',
    "url": r'https?://[^\s<>"{}|\\^`[\]]+',
    "date": r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b',
    "time": r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b',
    "currency": r'\$\d+(?:,\d{3})*(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP|CAD)\b'
}

def extract_metadata(content: str) -> Dict[str, Any]:
    """Extract metadata from content"""
    metadata = {
        "word_count": len(content.split()),
        "character_count": len(content),
        "line_count": len(content.split('\n')),
        "paragraph_count": len([p for p in content.split('\n\n') if p.strip()]),
        "extracted_data": {}
    }
    
    # Extract structured data
    for pattern_name, pattern in CONTENT_PATTERNS.items():
        matches = re.findall(pattern, content)
        if matches:
            metadata["extracted_data"][pattern_name] = list(set(matches))
    
    return metadata

def analyze_content_structure(content: str) -> Dict[str, Any]:
    """Analyze the structure of content"""
    lines = content.split('\n')
    
    structure = {
        "headings": [],
        "bullet_points": [],
        "numbered_lists": [],
        "code_blocks": [],
        "tables": [],
        "sections": []
    }
    
    current_section = None
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Detect headings (markdown style)
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            heading = line.lstrip('#').strip()
            structure["headings"].append({
                "level": level,
                "text": heading,
                "line_number": i + 1
            })
            current_section = heading
        
        # Detect bullet points
        elif line.startswith(('- ', '* ', '+ ')):
            structure["bullet_points"].append({
                "text": line[2:],
                "line_number": i + 1,
                "section": current_section
            })
        
        # Detect numbered lists
        elif re.match(r'^\d+\.\s', line):
            structure["numbered_lists"].append({
                "text": line,
                "line_number": i + 1,
                "section": current_section
            })
        
        # Detect code blocks
        elif line.startswith('```') or line.startswith('~~~'):
            structure["code_blocks"].append({
                "line_number": i + 1,
                "section": current_section
            })
        
        # Detect tables (simple pipe-separated)
        elif '|' in line and line.count('|') >= 2:
            structure["tables"].append({
                "line_number": i + 1,
                "section": current_section
            })
    
    return structure

def generate_basic_summary(content: str, max_sentences: int = 3) -> str:
    """Generate a basic summary of content (fallback when LLM is not available)"""
    # Simple extractive summarization
    sentences = re.split(r'[.!?]+', content)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 20]
    
    if not sentences:
        return "No meaningful content found to summarize."
    
    # Score sentences based on length and position
    scored_sentences = []
    for i, sentence in enumerate(sentences):
        score = 0
        # Prefer sentences from beginning and end
        if i < len(sentences) * 0.3:
            score += 2
        elif i > len(sentences) * 0.7:
            score += 1
        
        # Prefer longer sentences (but not too long)
        length_score = min(len(sentence.split()) / 20, 1.5)
        score += length_score
        
        scored_sentences.append((score, sentence))
    
    # Sort by score and take top sentences
    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    top_sentences = [s[1] for s in scored_sentences[:max_sentences]]
    
    return '. '.join(top_sentences) + '.'

def generate_fallback_analysis(content: str) -> str:
    """Generate basic content analysis when LLM is not available"""
    metadata = extract_metadata(content)
    structure = analyze_content_structure(content)
    
    analysis = []
    analysis.append("📊 **Content Analysis (Basic Mode)**")
    analysis.append(f"Note: Advanced AI analysis unavailable. Please configure your API credentials for enhanced features.")
    analysis.append("")
    
    # Basic statistics
    analysis.append(f"📈 **Content Statistics:**")
    analysis.append(f"  • Word Count: {metadata['word_count']}")
    analysis.append(f"  • Character Count: {metadata['character_count']}")
    analysis.append(f"  • Paragraphs: {metadata['paragraph_count']}")
    analysis.append(f"  • Lines: {metadata['line_count']}")
    analysis.append("")
    
    # Structure overview
    if structure["headings"]:
        analysis.append(f"📋 **Document Structure:**")
        analysis.append(f"  • Headings: {len(structure['headings'])}")
        for heading in structure["headings"][:5]:  # Show first 5
            analysis.append(f"    - {heading['text']}")
        if len(structure["headings"]) > 5:
            analysis.append(f"    ... and {len(structure['headings']) - 5} more")
        analysis.append("")
    
    # Extracted data
    if metadata["extracted_data"]:
        analysis.append(f"🔍 **Extracted Data:**")
        for data_type, items in metadata["extracted_data"].items():
            analysis.append(f"  • {data_type.title()}: {len(items)} found")
            for item in items[:2]:  # Show first 2 examples
                analysis.append(f"    - {item}")
        analysis.append("")
    
    # Basic summary
    summary = generate_basic_summary(content, max_sentences=3)
    analysis.append(f"📝 **Summary:**")
    analysis.append(f"{summary}")
    
    return "\n".join(analysis)

# ENHANCED CONTENT ANALYSIS TOOLS WITH LLM CAPABILITIES

@mcp.tool()
async def content_analyze_content(content: str, analysis_type: str = "comprehensive") -> str:
    """
    Analyze any type of content and provide insights using LLM.
    
    Args:
        content (str): The content to analyze
        analysis_type (str): Type of analysis - "comprehensive", "summary", "structure", "metadata", "extract", "sentiment", "quality"
    
    Returns:
        str: Analysis results based on the requested type
    """
    logger.info(f"content_analyze_content called with analysis_type: {analysis_type}")
    
    if not content or not content.strip():
        return "No content provided for analysis."
    
    try:
        # Check LLM availability and provide appropriate feedback
        llm_available = content_server.is_llm_available()
        
        if analysis_type == "summary":
            if llm_available:
                return await content_server.summarize_with_llm(content, max_length=200)
            else:
                summary = generate_basic_summary(content)
                return f"📝 **Content Summary (Basic Mode):**\n{summary}\n\n💡 *For enhanced AI-powered summaries, please configure your API credentials.*"
        
        elif analysis_type == "structure":
            structure = analyze_content_structure(content)
            result = []
            
            if structure["headings"]:
                result.append(f"📋 **Headings ({len(structure['headings'])}):**")
                for heading in structure["headings"]:
                    result.append(f"  {'#' * heading['level']} {heading['text']}")
            
            if structure["bullet_points"]:
                result.append(f"\n🔹 **Bullet Points ({len(structure['bullet_points'])}):**")
                for item in structure["bullet_points"][:5]:  # Show first 5
                    result.append(f"  • {item['text']}")
            
            if structure["numbered_lists"]:
                result.append(f"\n🔢 **Numbered Lists ({len(structure['numbered_lists'])}):**")
                for item in structure["numbered_lists"][:5]:  # Show first 5
                    result.append(f"  {item['text']}")
            
            basic_structure = "\n".join(result) if result else "No clear structure detected in content."
            
            # Enhanced with LLM analysis
            if llm_available:
                llm_analysis = await content_server.analyze_with_llm(
                    f"Content Structure Analysis:\n{basic_structure}\n\nFull Content:\n{content[:1000]}...",
                    "content"
                )
                return f"{basic_structure}\n\n🧠 **AI Analysis:**\n{llm_analysis}"
            else:
                return f"{basic_structure}\n\n💡 *For enhanced AI-powered structure analysis, please configure your API credentials.*"
        
        elif analysis_type == "metadata":
            metadata = extract_metadata(content)
            result = []
            result.append(f"📊 **Content Metadata:**")
            result.append(f"  Word Count: {metadata['word_count']}")
            result.append(f"  Character Count: {metadata['character_count']}")
            result.append(f"  Line Count: {metadata['line_count']}")
            result.append(f"  Paragraph Count: {metadata['paragraph_count']}")
            
            if metadata["extracted_data"]:
                result.append("\n🔍 **Extracted Data:**")
                for data_type, items in metadata["extracted_data"].items():
                    result.append(f"  {data_type.title()}: {len(items)} found")
                    for item in items[:3]:  # Show first 3 examples
                        result.append(f"    - {item}")
            
            basic_metadata = "\n".join(result)
            
            # Enhanced with LLM insights
            if llm_available:
                llm_insights = await content_server.analyze_with_llm(
                    f"Content Metadata:\n{basic_metadata}\n\nContent Sample:\n{content[:500]}...",
                    "content"
                )
                return f"{basic_metadata}\n\n🧠 **Content Insights:**\n{llm_insights}"
            else:
                return f"{basic_metadata}\n\n💡 *For enhanced AI-powered insights, please configure your API credentials.*"
        
        elif analysis_type == "sentiment":
            if llm_available:
                return await analyze_sentiment(content)
            else:
                return "🤖 **Sentiment Analysis:**\nSentiment analysis requires AI capabilities. Please configure your API credentials to use this feature.\n\n💡 *Available providers: Azure OpenAI, OpenAI, Google Gemini, Anthropic Claude, Mistral*"
        
        elif analysis_type == "quality":
            if llm_available:
                return await assess_content_quality(content)
            else:
                return "🎯 **Content Quality Assessment:**\nContent quality assessment requires AI capabilities. Please configure your API credentials to use this feature.\n\n💡 *Available providers: Azure OpenAI, OpenAI, Google Gemini, Anthropic Claude, Mistral*"
        
        elif analysis_type == "comprehensive":
            if llm_available:
                # Comprehensive analysis combining multiple aspects
                results = []
                
                # Basic metadata
                metadata = extract_metadata(content)
                results.append(f"📊 **Content Overview:**")
                results.append(f"  Words: {metadata['word_count']}, Characters: {metadata['character_count']}")
                results.append(f"  Lines: {metadata['line_count']}, Paragraphs: {metadata['paragraph_count']}")
                
                # Enhanced with LLM comprehensive analysis
                llm_analysis = await content_server.analyze_with_llm(content, "content")
                results.append(f"\n🧠 **AI Analysis:**\n{llm_analysis}")
                
                return "\n".join(results)
            else:
                # Comprehensive fallback analysis
                return generate_fallback_analysis(content)
        
        else:
            return f"Unknown analysis type: {analysis_type}. Available types: comprehensive, summary, structure, metadata, extract, sentiment, quality"
            
    except Exception as e:
        logger.error(f"Error in analyze_content: {e}")
        return f"Error analyzing content: {str(e)}"

@mcp.tool()
async def content_summarize_page(page_content: str, page_title: Optional[str] = None, page_url: Optional[str] = None) -> str:
    """
    Summarize web page content with enhanced LLM capabilities.
    
    Args:
        page_content (str): Content of the page to summarize
        page_title (str): Title of the page (optional)
        page_url (str): URL of the page (optional)
    
    Returns:
        str: Summary of the page content
    """
    # Handle None values
    page_title = page_title or ""
    page_url = page_url or ""
    
    logger.info(f"summarize_page called for: {page_title or 'Untitled Page'}")
    
    if not page_content or not page_content.strip():
        return "No page content provided for summarization."
    
    try:
        # Enhanced with LLM summarization
        if content_server.is_llm_available():
            system_message = """You are an expert web content summarizer. Create a comprehensive summary that captures:
                1. Main topic and purpose
                2. Key points and findings
                3. Important details and data
                4. Conclusions or recommendations
                5. Actionable insights"""
                
            prompt = f"""Summarize this web page content:

                Title: {page_title or 'Not provided'}
                URL: {page_url or 'Not provided'}

                Content:
                {page_content}

                Please provide a structured detailed summary with key insights."""
            
            llm_summary = await content_server.generate_response(prompt, system_message)
            
            # Add metadata
            metadata = extract_metadata(page_content)
            metadata_str = f"📊 **Page Stats:** {metadata['word_count']} words, {metadata['paragraph_count']} paragraphs"
            
            return f"🌐 **Page Summary:**\n{page_title or 'Web Page'}\n{page_url or ''}\n\n{llm_summary}\n\n{metadata_str}"
        
        else:
            # Fallback to basic summarization
            summary = generate_basic_summary(page_content, max_sentences=5)
            metadata = extract_metadata(page_content)
            
            result = []
            result.append(f"🌐 **Page Summary (Basic Mode):**")
            if page_title:
                result.append(f"**Title:** {page_title}")
            if page_url:
                result.append(f"**URL:** {page_url}")
            result.append(f"\n**Summary:** {summary}")
            result.append(f"\n**Stats:** {metadata['word_count']} words, {metadata['paragraph_count']} paragraphs")
            result.append(f"\n💡 *For enhanced AI-powered summaries, please configure your API credentials.*")
            
            return "\n".join(result)
            
    except Exception as e:
        logger.error(f"Error in summarize_page: {e}")
        return f"Error summarizing page: {str(e)}"

@mcp.tool()
async def content_extract_key_points(content: str, max_points: int = 5) -> str:
    """
    Extract key points from content using LLM.
    
    Args:
        content (str): Content to extract key points from
        max_points (int): Maximum number of key points to extract
    
    Returns:
        str: Key points extracted from the content
    """
    logger.info(f"extract_key_points called with max_points: {max_points}")
    
    if not content or not content.strip():
        return "No content provided for key point extraction."
    
    try:
        if content_server.is_llm_available():
            system_message = f"""You are an expert content analyst. Extract the {max_points} most important key points from the content.
            Focus on:
            1. Main ideas and concepts
            2. Important facts and data
            3. Key insights and conclusions
            4. Actionable information
            5. Critical details
            
            Format as numbered list with brief explanations."""
            
            prompt = f"Extract the {max_points} most important key points from this content:\n\n{content}"
            
            return await content_server.generate_response(prompt, system_message)
        
        else:
            # Fallback to basic extraction
            sentences = re.split(r'[.!?]+', content)
            sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 30]
            
            if not sentences:
                return "No meaningful sentences found for key point extraction."
            
            # Simple scoring based on length and position
            scored_sentences = []
            for i, sentence in enumerate(sentences):
                score = 0
                # Prefer sentences from beginning
                if i < len(sentences) * 0.3:
                    score += 2
                # Prefer longer sentences
                score += len(sentence.split()) / 20
                scored_sentences.append((score, sentence))
            
            # Sort by score and take top sentences
            scored_sentences.sort(key=lambda x: x[0], reverse=True)
            top_sentences = [s[1] for s in scored_sentences[:max_points]]
            
            result = "🔑 **Key Points:**\n"
            for i, point in enumerate(top_sentences, 1):
                result += f"{i}. {point.strip()}\n"
            
            return result
            
    except Exception as e:
        logger.error(f"Error in extract_key_points: {e}")
        return f"Error extracting key points: {str(e)}"

@mcp.tool()
async def content_analyze_document_structure(content: str) -> str:
    """
    Analyze document structure with enhanced LLM insights.
    
    Args:
        content (str): Document content to analyze
    
    Returns:
        str: Detailed structure analysis
    """
    logger.info("content_analyze_document_structure called")
    
    if not content or not content.strip():
        return "No content provided for structure analysis."
    
    try:
        structure = analyze_content_structure(content)
        
        # Basic structure analysis
        result = []
        result.append("📄 **Document Structure Analysis:**")
        
        if structure["headings"]:
            result.append(f"\n🏷️ **Headings ({len(structure['headings'])}):**")
            for heading in structure["headings"]:
                indent = "  " * heading["level"]
                result.append(f"{indent}• {heading['text']} (Line {heading['line_number']})")
        
        if structure["bullet_points"]:
            result.append(f"\n🔸 **Bullet Points ({len(structure['bullet_points'])}):**")
            for item in structure["bullet_points"][:3]:
                result.append(f"  • {item['text']}")
            if len(structure["bullet_points"]) > 3:
                result.append(f"  ... and {len(structure['bullet_points']) - 3} more")
        
        if structure["numbered_lists"]:
            result.append(f"\n🔢 **Numbered Lists ({len(structure['numbered_lists'])}):**")
            for item in structure["numbered_lists"][:3]:
                result.append(f"  {item['text']}")
            if len(structure["numbered_lists"]) > 3:
                result.append(f"  ... and {len(structure['numbered_lists']) - 3} more")
        
        if structure["code_blocks"]:
            result.append(f"\n💻 **Code Blocks:** {len(structure['code_blocks'])} found")
        
        if structure["tables"]:
            result.append(f"\n📊 **Tables:** {len(structure['tables'])} found")
        
        basic_structure = "\n".join(result)
        
        # Enhanced with LLM analysis
        if content_server.is_llm_available():
            system_message = """You are a document structure expert. Analyze the document structure and provide insights about:
                1. Overall organization and flow
                2. Content hierarchy and logic
                3. Completeness and gaps
                4. Readability and accessibility
                5. Suggestions for improvement"""
            
            prompt = f"""Analyze this document structure:

                Structure Analysis:
                {basic_structure}

                Content Sample:
                {content[:1000]}...

                Provide insights about the document's organization and suggestions for improvement."""
                            
            llm_analysis = await content_server.generate_response(prompt, system_message)
            return f"{basic_structure}\n\n🧠 **Structure Insights:**\n{llm_analysis}"
        
        return basic_structure
        
    except Exception as e:
        logger.error(f"Error in analyze_document_structure: {e}")
        return f"Error analyzing document structure: {str(e)}"

# NEW LLM-ENHANCED CONTENT ANALYSIS TOOLS

@mcp.tool()
async def content_analyze_sentiment(content: str) -> str:
    """
    Analyze sentiment and emotional tone of content.
    
    Args:
        content (str): Content to analyze sentiment for
    
    Returns:
        str: Sentiment analysis results
    """
    if not content_server.is_llm_available():
        return "Sentiment analysis requires LLM capabilities."
    
    system_message = """You are a sentiment analysis expert. Analyze the emotional tone and sentiment of the content.
    Provide:
    1. Overall sentiment (positive, negative, neutral)
    2. Emotional tone and mood
    3. Key emotional indicators
    4. Confidence level
    5. Specific examples from the text"""
    
    prompt = f"Analyze the sentiment and emotional tone of this content:\n\n{content}"
    
    return await content_server.generate_response(prompt, system_message)

@mcp.tool()
async def content_assess_content_quality(content: str) -> str:
    """
    Assess the quality of content across multiple dimensions.
    
    Args:
        content (str): Content to assess quality for
    
    Returns:
        str: Content quality assessment
    """
    if not content_server.is_llm_available():
        return "Content quality assessment requires LLM capabilities."
    
    system_message = """You are a content quality expert. Assess the content across these dimensions:
    1. Clarity and readability
    2. Accuracy and factual correctness
    3. Completeness and thoroughness
    4. Organization and structure
    5. Engagement and interest level
    6. Grammar and writing quality
    7. Target audience appropriateness
    
    Provide scores (1-10) and specific feedback for each dimension."""
    
    prompt = f"Assess the quality of this content across multiple dimensions:\n\n{content}"
    
    return await content_server.generate_response(prompt, system_message)

@mcp.tool()
async def content_generate_content_insights(content: str, focus: str = "general") -> str:
    """
    Generate insights and recommendations based on content analysis.
    
    Args:
        content (str): Content to generate insights for
        focus (str): Focus area (general, marketing, technical, educational, etc.)
    
    Returns:
        str: Content insights and recommendations
    """
    if not content_server.is_llm_available():
        return "Content insights generation requires LLM capabilities."
    
    system_message = f"""You are a content strategist with expertise in {focus} content. 
    Analyze the content and provide actionable insights including:
    1. Key themes and topics
    2. Strengths and opportunities
    3. Gaps and areas for improvement
    4. Audience engagement potential
    5. Optimization recommendations
    6. Next steps and action items"""
    
    prompt = f"Generate insights and recommendations for this {focus} content:\n\n{content}"
    
    return await content_server.generate_response(prompt, system_message)

@mcp.tool()
async def content_compare_content_versions(content1: str, content2: str, comparison_type: str = "general") -> str:
    """
    Compare two versions of content and highlight differences.
    
    Args:
        content1 (str): First version of content
        content2 (str): Second version of content
        comparison_type (str): Type of comparison (general, quality, sentiment, etc.)
    
    Returns:
        str: Comparison results and insights
    """
    if not content_server.is_llm_available():
        return "Content comparison requires LLM capabilities."
    
    system_message = f"""You are a content comparison expert. Compare these two content versions focusing on {comparison_type} aspects.
            Analyze:
            1. Key differences and changes
            2. Improvements or degradations
            3. Tone and style changes
            4. Content quality differences
            5. Recommendations for optimization"""
    
    prompt = f"""Compare these two content versions:

            VERSION 1:
            {content1}

            VERSION 2:
            {content2}

            Focus on {comparison_type} aspects and provide detailed comparison insights."""
    
    return await content_server.generate_response(prompt, system_message)

@mcp.tool()
async def content_extract_content_themes(content: str, max_themes: int = 5) -> str:
    """
    Extract main themes and topics from content.
    
    Args:
        content (str): Content to extract themes from
        max_themes (int): Maximum number of themes to extract
    
    Returns:
        str: Extracted themes and topics
    """
    if not content_server.is_llm_available():
        return "Theme extraction requires LLM capabilities."
    
    system_message = f"""You are a content thematic analyst. Extract the {max_themes} most important themes and topics from the content.
        For each theme, provide:
        1. Theme name
        2. Brief description
        3. Supporting evidence from the text
        4. Relevance and importance
        5. Related concepts"""
    
    prompt = f"Extract the main themes and topics from this content:\n\n{content}"
    
    return await content_server.generate_response(prompt, system_message)

@mcp.resource("content://analysis/{content_id}")
def content_analysis_resource(content_id: str) -> str:
    """
    Resource for content analysis results.
    """
    return f"Content analysis resource for ID: {content_id}"

@mcp.prompt("content_analysis")
def content_analysis_prompt(analysis_type: str, content_preview: str) -> str:
    """
    Generate a content analysis prompt template.
    """
    return f"Please analyze this content for {analysis_type}: {content_preview[:100]}..."

@mcp.prompt("content_insights")
def content_insights_prompt(content_type: str, focus_area: str) -> str:
    """
    Generate a content insights prompt template.
    """
    return f"Please provide insights and recommendations for this {content_type} content with focus on {focus_area}."

if __name__ == "__main__":
    logger.info("Content Analysis MCP server initialized successfully")
    logger.info("Available tools: analyze_content, summarize_page, extract_key_points, analyze_document_structure")
    logger.info("Server ready to handle content analysis requests") 
    mcp.run()