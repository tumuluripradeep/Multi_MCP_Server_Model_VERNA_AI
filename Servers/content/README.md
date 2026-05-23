# Content Analysis MCP Server

## Overview

The Content Analysis MCP Server provides comprehensive content analysis capabilities for any type of text content. It can analyze, summarize, extract key information, and understand the structure of documents, web pages, and other text-based content.

## Features

### 🔍 Content Analysis Tools

1. **analyze_content** - Comprehensive content analysis with multiple analysis types
2. **summarize_page** - Specialized web page summarization
3. **extract_key_points** - Extract the most important points from content
4. **analyze_document_structure** - Detailed document structure analysis

### 📊 Analysis Types

- **Comprehensive** - Complete analysis including summary, structure, and metadata
- **Summary** - Generate concise summaries of content
- **Structure** - Analyze document structure (headings, lists, code blocks, etc.)
- **Metadata** - Extract statistics and structured data
- **Extract** - Extract specific data types (emails, URLs, dates, etc.)

### 🎯 Use Cases

- **Page Summarization**: "Summarize this web page"
- **Document Analysis**: "Analyze this document structure"
- **Content Extraction**: "Extract key information from this text"
- **Content Insights**: "What are the main topics in this content?"
- **Structure Analysis**: "How is this document organized?"

## Tool Reference

### analyze_content(content, analysis_type="comprehensive")

Analyze any type of content and provide insights.

**Parameters:**
- `content` (str): The content to analyze
- `analysis_type` (str): Type of analysis - "comprehensive", "summary", "structure", "metadata", "extract"

**Returns:**
- Analysis results based on the requested type

### summarize_page(page_content, page_title="", page_url="")

Summarize a web page's content with context.

**Parameters:**
- `page_content` (str): The main content of the page
- `page_title` (str, optional): The title of the page
- `page_url` (str, optional): The URL of the page

**Returns:**
- Comprehensive page summary with key information

### extract_key_points(content, max_points=5)

Extract the most important points from content.

**Parameters:**
- `content` (str): The content to extract key points from
- `max_points` (int): Maximum number of key points to extract

**Returns:**
- Numbered list of key points

### analyze_document_structure(content)

Analyze the structure of a document in detail.

**Parameters:**
- `content` (str): The document content to analyze

**Returns:**
- Detailed structure analysis including headings, lists, code blocks, and tables

## Content Pattern Detection

The server automatically detects and extracts:

- **Email addresses**: Contact information
- **Phone numbers**: Various formats (XXX-XXX-XXXX, (XXX) XXX-XXXX)
- **URLs**: Web links and references
- **Dates**: Multiple date formats
- **Times**: Time stamps with AM/PM
- **Currency**: Dollar amounts and international currencies

## Structure Analysis

Automatically identifies:

- **Headings**: Markdown-style headings with levels
- **Bullet Points**: Lists with -, *, or + markers
- **Numbered Lists**: Ordered lists with numbers
- **Code Blocks**: Code sections with ``` or ~~~ markers
- **Tables**: Pipe-separated table structures
- **Sections**: Content organization by headings

## Configuration

The server runs on port 8011 and uses Azure OpenAI for enhanced analysis capabilities.

**Environment Variables:**
- `AZURE_OPENAI_API_KEY`: Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI endpoint URL
- `AZURE_OPENAI_DEPLOYMENT`: Deployment name
- `MCP_HOST`: Server host (default: 127.0.0.1)
- `MCP_PORT`: Server port (default: 8011)

## Usage Examples

### Basic Content Analysis
```
Query: "Analyze this document content"
Server Response: Comprehensive analysis including summary, structure, and metadata
```

### Page Summarization
```
Query: "Summarize this web page content"
Server Response: Page summary with key information, structure overview, and content stats
```

### Key Point Extraction
```
Query: "Extract the main points from this article"
Server Response: Numbered list of the most important points
```

### Structure Analysis
```
Query: "How is this document organized?"
Server Response: Detailed breakdown of headings, lists, code blocks, and overall structure
```

## Integration

The content-analysis server integrates seamlessly with the Verna AI system and can be triggered automatically when users request content analysis tasks. It's particularly useful for:

- Chrome extension content analysis
- Document processing workflows
- Web page summarization
- Content extraction and insights
- Academic and business document analysis

## Authentication

This server does not require authentication and is immediately available for use.

## Performance

The server provides fast content analysis with:
- Efficient text processing algorithms
- Lightweight metadata extraction
- Scalable structure analysis
- Optimized summarization techniques

## Error Handling

The server includes comprehensive error handling for:
- Empty or invalid content
- Unsupported analysis types
- Content parsing errors
- Network or processing issues

All errors are logged and return user-friendly error messages. 