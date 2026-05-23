#!/usr/bin/env python3
"""
Enhanced Audio/Video RAG MCP Server with LLM Integration

This server provides comprehensive multimedia content analysis and retrieval capabilities:
- Advanced video transcript extraction and analysis
- Audio content processing and indexing
- YouTube video analysis with metadata extraction
- Document-based question answering for multimedia content
- Semantic search across video/audio content
- Multi-language support for international content
- LLM-powered content summarization and insights

Features:
- YouTube transcript extraction with multiple fallback methods
- Audio file processing and speech-to-text conversion
- Intelligent content chunking and indexing
- Vector-based semantic search
- Context-aware question answering
- Multi-modal content analysis
- Enhanced error handling and recovery
"""

import asyncio
import sys
import os
import json
import logging
import tempfile
import hashlib
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import uuid

# Add the parent directory to the path to import from Servers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))  # Add project root

from mcp.server.fastmcp import FastMCP
try:
    from llm_factory import LLMEnhancedMCP
except ImportError:
    # Fallback if llm_factory is not available
    class LLMEnhancedMCP:
        def __init__(self, name):
            self.name = name
            self.mcp = FastMCP(name)
        
        def get_mcp_server(self):
            return self.mcp
        
        def is_llm_available(self):
            return False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import external libraries with fallback handling
try:
    import yt_dlp
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.formatters import TextFormatter
    logger.info("YouTube processing libraries loaded successfully")
except ImportError as e:
    logger.warning(f"YouTube libraries not available: {e}")
    yt_dlp = None
    YouTubeTranscriptApi = None
    TextFormatter = None

try:
    import speech_recognition as sr
    from pydub import AudioSegment
    logger.info("Audio processing libraries loaded successfully")
except ImportError as e:
    logger.warning(f"Audio processing libraries not available: {e}")
    sr = None
    AudioSegment = None

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    logger.info("Vector processing libraries loaded successfully")
except ImportError as e:
    logger.warning(f"Vector processing libraries not available: {e}")
    np = None
    TfidfVectorizer = None
    cosine_similarity = None

# =============================
# MCP Server Initialization
# =============================
mcp = FastMCP("audio_video_rag")

# Additional aliases for server discovery
server = mcp
app = mcp

# =============================
# Configuration Constants
# =============================
MAX_TRANSCRIPT_LENGTH = 50000
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MAX_SEARCH_RESULTS = 5
DEFAULT_LANGUAGE = 'en'
AUDIO_CHUNK_DURATION = 30  # seconds

# =============================
# Data Models
# =============================
@dataclass
class MediaContent:
    """Container for multimedia content"""
    id: str
    title: str
    url: str
    content_type: str  # 'video', 'audio', 'transcript'
    transcript: str
    duration: Optional[int] = None
    language: str = DEFAULT_LANGUAGE
    metadata: Dict[str, Any] = None
    chunks: List[str] = None
    indexed_at: datetime = None
    
    def __post_init__(self):
        if self.indexed_at is None:
            self.indexed_at = datetime.now()
        if self.chunks is None:
            self.chunks = []
        if self.metadata is None:
            self.metadata = {}

@dataclass
class SearchResult:
    """Search result with relevance scoring"""
    content: MediaContent
    relevant_chunks: List[str]
    relevance_score: float
    matched_segments: List[Dict[str, Any]]
    context: str = ""

# =============================
# Enhanced Audio/Video RAG Server
# =============================
class AudioVideoRAGServer(LLMEnhancedMCP):
    def __init__(self):
        super().__init__("audio_video_rag_server")
        
        # In-memory storage for processed content
        self.content_store: Dict[str, MediaContent] = {}
        self.vector_store: Dict[str, Any] = {}
        
        # Initialize TF-IDF vectorizer if available
        if TfidfVectorizer:
            self.vectorizer = TfidfVectorizer(
                max_features=5000,
                stop_words='english',
                ngram_range=(1, 2)
            )
        else:
            self.vectorizer = None
        
        # Enhanced prompts for better analysis
        self.transcript_analysis_prompt = """You are a multimedia content analysis expert. Analyze the following video/audio transcript to provide comprehensive insights.

Transcript Content:
{transcript}

User Query: {user_query}

Please provide a detailed analysis including:

1. **Content Summary**: Brief overview of the main topics and themes
2. **Key Points**: Most important information and takeaways
3. **Relevant Segments**: Parts that directly address the user's question
4. **Context & Background**: Important context for understanding the content
5. **Actionable Insights**: Practical advice or next steps mentioned
6. **Technical Details**: Any specific technical information discussed

Format your response with clear sections and bullet points for easy reading.
Focus on information that directly answers the user's question while providing valuable context."""

        self.content_qa_prompt = """You are an expert at answering questions based on multimedia content. Use the provided transcript segments to answer the user's question comprehensively.

User Question: {user_question}

Relevant Content Segments:
{content_segments}

Content Metadata:
{metadata}

Instructions:
1. **Answer the Question**: Provide a direct, comprehensive answer
2. **Use Evidence**: Reference specific parts of the content
3. **Provide Context**: Give background information when helpful
4. **Be Specific**: Include details, examples, and explanations mentioned
5. **Acknowledge Limitations**: Note if the content doesn't fully address the question

Create a structured response with:
- **Direct Answer**: Clear response to the question
- **Supporting Evidence**: Quotes and references from the content
- **Additional Context**: Relevant background information
- **Related Topics**: Other relevant points mentioned in the content

If the content doesn't contain information to answer the question, clearly state this and suggest what type of content might be more helpful."""

        self.content_summarization_prompt = """You are a content summarization expert. Create a comprehensive summary of this multimedia content.

Content Information:
Title: {title}
Type: {content_type}
Duration: {duration}
Language: {language}

Full Transcript:
{transcript}

Create a structured summary including:

1. **Overview**: 2-3 sentence summary of the entire content
2. **Main Topics**: Key themes and subjects discussed (with timestamps if available)
3. **Key Takeaways**: Most important points and insights
4. **Structure**: How the content is organized and flows
5. **Notable Quotes**: Important or memorable statements
6. **Practical Information**: Any actionable advice or instructions
7. **Technical Details**: Specific technical information mentioned
8. **Conclusion**: Overall assessment and final thoughts

Format the summary for easy scanning with clear headers and bullet points.
Make it comprehensive enough to understand the content without watching/listening to it."""

        self.search_intent_prompt = """Analyze the user's search query to understand their intent and optimize search strategy.

User Query: {user_query}

Analyze this query to determine:
1. **Search Intent**: What is the user looking for?
2. **Content Type**: What type of multimedia content would be most helpful?
3. **Specificity**: How specific or general is the query?
4. **Context Needed**: What context might be important?
5. **Keywords**: Key terms for effective search

Return a JSON object with:
{{
    "intent": "learning/troubleshooting/research/entertainment",
    "content_type_preference": "video/audio/any",
    "specificity": "high/medium/low",
    "search_keywords": ["keyword1", "keyword2", "keyword3"],
    "context_requirements": "what context is needed",
    "expected_content_length": "short/medium/long"
}}"""

    def _validate_dependencies(self) -> tuple[bool, str]:
        """Validate required dependencies"""
        missing_deps = []
        
        if not yt_dlp or not YouTubeTranscriptApi:
            missing_deps.append("YouTube processing (yt-dlp, youtube-transcript-api)")
        
        if not sr or not AudioSegment:
            missing_deps.append("Audio processing (SpeechRecognition, pydub)")
        
        if missing_deps:
            return False, f"Missing dependencies: {', '.join(missing_deps)}"
        
        return True, "All dependencies available"

    def _generate_content_id(self, url: str) -> str:
        """Generate unique ID for content"""
        return hashlib.md5(url.encode()).hexdigest()[:16]

    def _extract_youtube_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL"""
        import re
        
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _chunk_text(self, text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
        """Split text into overlapping chunks"""
        if not text:
            return []
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Try to end at a sentence boundary
            if end < len(text):
                # Look for sentence ending within the last 10% of chunk
                boundary_start = max(start + int(chunk_size * 0.9), start + 1)
                boundary_text = text[boundary_start:end]
                
                sentence_end = -1
                for delimiter in ['. ', '! ', '? ', '\n\n']:
                    pos = boundary_text.rfind(delimiter)
                    if pos > sentence_end:
                        sentence_end = pos
                
                if sentence_end > -1:
                    end = boundary_start + sentence_end + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap
            if start >= len(text):
                break
        
        return chunks

    def _calculate_relevance(self, query: str, content: str) -> float:
        """Calculate relevance score between query and content"""
        if not query or not content:
            return 0.0
        
        query_lower = query.lower()
        content_lower = content.lower()
        
        # Simple keyword matching
        query_words = [word for word in query_lower.split() if len(word) > 2]
        if not query_words:
            return 0.0
        
        matches = sum(1 for word in query_words if word in content_lower)
        return matches / len(query_words)

    def _vectorize_content(self, content_list: List[str]) -> Optional[Any]:
        """Create vector representations of content"""
        if not self.vectorizer or not content_list:
            return None
        
        try:
            return self.vectorizer.fit_transform(content_list)
        except Exception as e:
            self.logger.error(f"Error vectorizing content: {e}")
            return None

    def _find_similar_content(self, query: str, max_results: int = MAX_SEARCH_RESULTS) -> List[SearchResult]:
        """Find content similar to query using vector similarity"""
        if not self.content_store:
            return []
        
        results = []
        
        # Simple text matching fallback
        for content_id, content in self.content_store.items():
            if not content.chunks:
                continue
            
            relevant_chunks = []
            total_relevance = 0.0
            
            for chunk in content.chunks:
                relevance = self._calculate_relevance(query, chunk)
                if relevance > 0.2:  # Threshold for relevance
                    relevant_chunks.append(chunk)
                    total_relevance += relevance
            
            if relevant_chunks:
                avg_relevance = total_relevance / len(relevant_chunks)
                results.append(SearchResult(
                    content=content,
                    relevant_chunks=relevant_chunks[:3],  # Top 3 chunks
                    relevance_score=avg_relevance,
                    matched_segments=[],
                    context=f"Found {len(relevant_chunks)} relevant segments"
                ))
        
        # Sort by relevance
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:max_results]

    async def _get_youtube_transcript(self, video_id: str, language: str = DEFAULT_LANGUAGE) -> Optional[str]:
        """Extract transcript from YouTube video"""
        if not YouTubeTranscriptApi:
            return None
        
        try:
            # Try multiple language codes
            language_codes = [language, 'en', 'en-US', 'en-GB']
            if language not in language_codes:
                language_codes.insert(0, language)
            
            transcript = None
            for lang_code in language_codes:
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang_code])
                    if transcript_list:
                        transcript = transcript_list
                        break
                except Exception:
                    continue
            
            # If no manual transcript, try auto-generated
            if not transcript:
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                    transcript = transcript_list
                except Exception:
                    pass
            
            if not transcript:
                return None
            
            # Format transcript
            formatter = TextFormatter()
            formatted_transcript = formatter.format_transcript(transcript)
            
            return formatted_transcript[:MAX_TRANSCRIPT_LENGTH]
            
        except Exception as e:
            self.logger.error(f"Error extracting transcript: {e}")
            return None

    async def _get_youtube_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata from YouTube video"""
        if not yt_dlp:
            return {}
        
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'format': 'worst',  # Don't download video
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                return {
                    'title': info.get('title', ''),
                    'duration': info.get('duration', 0),
                    'description': info.get('description', ''),
                    'uploader': info.get('uploader', ''),
                    'upload_date': info.get('upload_date', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'channel': info.get('channel', ''),
                    'tags': info.get('tags', []),
                    'language': info.get('language', DEFAULT_LANGUAGE)
                }
        except Exception as e:
            self.logger.error(f"Error extracting metadata: {e}")
            return {}

    async def _process_audio_file(self, audio_path: str, language: str = DEFAULT_LANGUAGE) -> Optional[str]:
        """Process audio file and extract transcript"""
        if not sr or not AudioSegment:
            return None
        
        try:
            # Load audio file
            audio = AudioSegment.from_file(audio_path)
            
            # Convert to wav for speech recognition
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                audio.export(tmp_file.name, format='wav')
                wav_path = tmp_file.name
            
            # Initialize speech recognizer
            recognizer = sr.Recognizer()
            
            # Process audio in chunks
            transcript_parts = []
            chunk_duration = AUDIO_CHUNK_DURATION * 1000  # Convert to milliseconds
            
            for i in range(0, len(audio), chunk_duration):
                chunk = audio[i:i + chunk_duration]
                
                # Export chunk to temporary file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as chunk_file:
                    chunk.export(chunk_file.name, format='wav')
                    
                    # Recognize speech
                    try:
                        with sr.AudioFile(chunk_file.name) as source:
                            audio_data = recognizer.record(source)
                            text = recognizer.recognize_google(audio_data, language=language)
                            transcript_parts.append(text)
                    except sr.UnknownValueError:
                        continue  # Skip chunks with no recognizable speech
                    except sr.RequestError as e:
                        self.logger.error(f"Speech recognition error: {e}")
                        continue
                    finally:
                        os.unlink(chunk_file.name)
            
            # Clean up temporary wav file
            os.unlink(wav_path)
            
            return ' '.join(transcript_parts) if transcript_parts else None
            
        except Exception as e:
            self.logger.error(f"Error processing audio: {e}")
            return None

    async def _generate_enhanced_answer(self, question: str, search_results: List[SearchResult]) -> str:
        """Generate comprehensive answer using LLM"""
        if not self.is_llm_available() or not search_results:
            return self._create_basic_answer(question, search_results)
        
        try:
            # Prepare content segments
            content_segments = []
            metadata_parts = []
            
            for result in search_results:
                content_segments.extend(result.relevant_chunks)
                metadata_parts.append(f"Title: {result.content.title}")
                metadata_parts.append(f"Type: {result.content.content_type}")
                if result.content.duration:
                    metadata_parts.append(f"Duration: {result.content.duration} seconds")
            
            # Generate comprehensive answer
            response = await self.analyze_with_llm(
                self.content_qa_prompt.format(
                    user_question=question,
                    content_segments='\n\n'.join(content_segments),
                    metadata='\n'.join(metadata_parts)
                )
            )
            
            # Add source information
            sources_info = "\n\n---\n\n## 📺 **Sources**\n"
            for i, result in enumerate(search_results, 1):
                sources_info += f"**{i}. {result.content.title}**\n"
                sources_info += f"   - Type: {result.content.content_type}\n"
                if result.content.url:
                    sources_info += f"   - URL: {result.content.url}\n"
                sources_info += f"   - Relevance: {result.relevance_score:.2f}\n\n"
            
            return response + sources_info
            
        except Exception as e:
            self.logger.error(f"Error generating enhanced answer: {e}")
            return self._create_basic_answer(question, search_results)

    def _create_basic_answer(self, question: str, search_results: List[SearchResult]) -> str:
        """Create basic answer without LLM"""
        if not search_results:
            return f"""# ❌ No Relevant Content Found

I couldn't find any audio/video content to answer your question: **{question}**

## 💡 Suggestions:
- Try indexing relevant videos or audio files first
- Use more specific keywords in your question
- Check if the content has been properly processed

## 📝 Available Content:
{len(self.content_store)} items currently indexed"""

        # Build answer from search results
        answer = f"""# 🎯 Answer from Multimedia Content

## 📝 Response to: {question}

Based on the indexed multimedia content, here's what I found:

"""
        
        # Add relevant segments
        for i, result in enumerate(search_results, 1):
            answer += f"### 📺 From: {result.content.title}\n\n"
            
            for j, chunk in enumerate(result.relevant_chunks[:2], 1):
                clean_chunk = chunk.strip()[:300] + "..." if len(chunk) > 300 else chunk.strip()
                answer += f"**Segment {j}**: {clean_chunk}\n\n"
            
            if len(result.relevant_chunks) > 2:
                answer += f"*({len(result.relevant_chunks) - 2} more relevant segments found)*\n\n"
        
        # Add sources
        answer += "---\n\n## 📺 **Sources**\n"
        for i, result in enumerate(search_results, 1):
            answer += f"**{i}. {result.content.title}**\n"
            answer += f"   - Type: {result.content.content_type}\n"
            if result.content.url:
                answer += f"   - URL: {result.content.url}\n"
            answer += f"   - Relevance: {result.relevance_score:.2f}\n\n"
        
        return answer

# Initialize the enhanced server
audio_video_server = AudioVideoRAGServer()

# =============================
# MCP Tool Functions
# =============================
@mcp.tool()
async def rag_index_youtube_video(url: str, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Index a YouTube video for searchable content analysis.
    
    Args:
        url (str): YouTube video URL
        language (str): Language code for transcript extraction (default: 'en')
    
    Returns:
        str: Status message with indexing results
    """
    try:
        # Validate dependencies
        is_valid, message = audio_video_server._validate_dependencies()
        if not is_valid:
            return f"❌ **Dependencies Missing**: {message}\n\nPlease install required packages: yt-dlp, youtube-transcript-api"
        
        # Extract video ID
        video_id = audio_video_server._extract_youtube_id(url)
        if not video_id:
            return f"❌ **Invalid URL**: Could not extract video ID from {url}"
        
        # Generate content ID
        content_id = audio_video_server._generate_content_id(url)
        
        # Check if already indexed
        if content_id in audio_video_server.content_store:
            existing = audio_video_server.content_store[content_id]
            return f"✅ **Already Indexed**: {existing.title}\n\n📊 **Stats**: {len(existing.chunks)} chunks available for search"
        
        # Get metadata
        metadata = await audio_video_server._get_youtube_metadata(url)
        title = metadata.get('title', f'Video {video_id}')
        
        # Extract transcript
        transcript = await audio_video_server._get_youtube_transcript(video_id, language)
        if not transcript:
            return f"❌ **No Transcript Available**: Could not extract transcript for {title}\n\nThis might be because:\n- Video has no captions\n- Captions are disabled\n- Language '{language}' not available"
        
        # Create content chunks
        chunks = audio_video_server._chunk_text(transcript)
        
        # Store content
        content = MediaContent(
            id=content_id,
            title=title,
            url=url,
            content_type='video',
            transcript=transcript,
            duration=metadata.get('duration'),
            language=language,
            metadata=metadata,
            chunks=chunks
        )
        
        audio_video_server.content_store[content_id] = content
        
        result = f"✅ **Successfully Indexed**: {title}\n\n"
        result += f"📊 **Processing Stats**:\n"
        result += f"   - Video ID: {video_id}\n"
        result += f"   - Duration: {metadata.get('duration', 'Unknown')} seconds\n"
        result += f"   - Language: {language}\n"
        result += f"   - Transcript Length: {len(transcript)} characters\n"
        result += f"   - Content Chunks: {len(chunks)}\n"
        result += f"   - Channel: {metadata.get('channel', 'Unknown')}\n\n"
        result += f"🔍 **Ready for Search**: You can now ask questions about this video content!"
        
        return result
        
    except Exception as e:
        return f"❌ **Indexing Error**: {str(e)}"

@mcp.tool()
async def rag_index_audio_file(file_path: str, title: str = None, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Index an audio file for searchable content analysis.
    
    Args:
        file_path (str): Path to the audio file
        title (str): Optional title for the audio content
        language (str): Language code for speech recognition (default: 'en')
    
    Returns:
        str: Status message with indexing results
    """
    try:
        # Validate dependencies
        if not sr or not AudioSegment:
            return "❌ **Dependencies Missing**: Audio processing requires SpeechRecognition and pydub packages"
        
        # Check if file exists
        if not os.path.exists(file_path):
            return f"❌ **File Not Found**: {file_path}"
        
        # Generate content ID
        content_id = audio_video_server._generate_content_id(file_path)
        
        # Check if already indexed
        if content_id in audio_video_server.content_store:
            existing = audio_video_server.content_store[content_id]
            return f"✅ **Already Indexed**: {existing.title}\n\n📊 **Stats**: {len(existing.chunks)} chunks available for search"
        
        # Set title
        if not title:
            title = os.path.basename(file_path)
        
        # Process audio file
        transcript = await audio_video_server._process_audio_file(file_path, language)
        if not transcript:
            return f"❌ **No Speech Detected**: Could not extract speech from {title}\n\nThis might be because:\n- Audio quality is poor\n- No speech in the file\n- Language '{language}' not supported"
        
        # Get audio metadata
        try:
            audio = AudioSegment.from_file(file_path)
            duration = len(audio) // 1000  # Convert to seconds
        except:
            duration = None
        
        # Create content chunks
        chunks = audio_video_server._chunk_text(transcript)
        
        # Store content
        content = MediaContent(
            id=content_id,
            title=title,
            url=file_path,
            content_type='audio',
            transcript=transcript,
            duration=duration,
            language=language,
            metadata={'file_path': file_path},
            chunks=chunks
        )
        
        audio_video_server.content_store[content_id] = content
        
        result = f"✅ **Successfully Indexed**: {title}\n\n"
        result += f"📊 **Processing Stats**:\n"
        result += f"   - File: {os.path.basename(file_path)}\n"
        result += f"   - Duration: {duration or 'Unknown'} seconds\n"
        result += f"   - Language: {language}\n"
        result += f"   - Transcript Length: {len(transcript)} characters\n"
        result += f"   - Content Chunks: {len(chunks)}\n\n"
        result += f"🔍 **Ready for Search**: You can now ask questions about this audio content!"
        
        return result
        
    except Exception as e:
        return f"❌ **Indexing Error**: {str(e)}"

@mcp.tool()
async def rag_search_multimedia_content(query: str, max_results: int = 3) -> str:
    """
    Search indexed multimedia content and get comprehensive answers.
    
    Args:
        query (str): Your question or search query
        max_results (int): Maximum number of content sources to use (default: 3)
    
    Returns:
        str: Comprehensive answer with source references
    """
    try:
        if not query.strip():
            return "❌ **Empty Query**: Please provide a search query."
        
        # Check if any content is indexed
        if not audio_video_server.content_store:
            return f"""# ❌ No Content Indexed

No multimedia content has been indexed yet. To search content, you need to:

## 📺 **Index YouTube Videos**:
Use `index_youtube_video` with a YouTube URL

## 🎵 **Index Audio Files**:
Use `index_audio_file` with an audio file path

## 💡 **Example**:
```
index_youtube_video("https://www.youtube.com/watch?v=VIDEO_ID")
```

Then you can search the content with questions like:
- "What are the main topics discussed?"
- "How does the speaker explain X?"
- "What recommendations are made?"
"""
        
        # Perform search
        search_results = audio_video_server._find_similar_content(query, max_results)
        
        if not search_results:
            available_content = list(audio_video_server.content_store.values())
            content_list = "\n".join([f"- {content.title} ({content.content_type})" for content in available_content])
            
            return f"""# 🔍 No Relevant Content Found

Your query "**{query}**" didn't match any indexed content.

## 📚 **Available Content**:
{content_list}

## 💡 **Search Tips**:
- Use specific keywords from the content
- Try different phrasing
- Ask more general questions about the topics
- Check if the content language matches your query language
"""
        
        # Generate comprehensive answer
        answer = await audio_video_server._generate_enhanced_answer(query, search_results)
        
        return answer
        
    except Exception as e:
        return f"❌ **Search Error**: {str(e)}"

@mcp.tool()
async def rag_summarize_content(content_id: str = None, url: str = None) -> str:
    """
    Generate a comprehensive summary of indexed multimedia content.
    
    Args:
        content_id (str): ID of indexed content (optional)
        url (str): URL of content to summarize (optional)
    
    Returns:
        str: Comprehensive content summary
    """
    try:
        # Find content
        content = None
        if content_id:
            content = audio_video_server.content_store.get(content_id)
        elif url:
            search_id = audio_video_server._generate_content_id(url)
            content = audio_video_server.content_store.get(search_id)
        
        if not content:
            available_content = list(audio_video_server.content_store.values())
            if not available_content:
                return "❌ **No Content Available**: No multimedia content has been indexed yet."
            
            content_list = "\n".join([
                f"- **{content.title}** (ID: {content.id}) - {content.content_type}"
                for content in available_content
            ])
            
            return f"""# ❌ Content Not Found

Could not find content with the specified ID or URL.

## 📚 **Available Content**:
{content_list}

## 💡 **Usage**:
- Use `content_id` parameter with one of the IDs above
- Use `url` parameter with the original URL
"""
        
        # Generate summary
        if audio_video_server.is_llm_available():
            summary = await audio_video_server.analyze_with_llm(
                audio_video_server.content_summarization_prompt.format(
                    title=content.title,
                    content_type=content.content_type,
                    duration=f"{content.duration} seconds" if content.duration else "Unknown",
                    language=content.language,
                    transcript=content.transcript
                )
            )
        else:
            # Basic summary without LLM
            summary = f"""## 📋 Basic Summary

**Content**: {content.title}
**Type**: {content.content_type}
**Duration**: {content.duration} seconds
**Language**: {content.language}

**Transcript Preview**:
{content.transcript[:500]}...

💡 **Note**: Enhanced summarization requires LLM configuration. Please check your LLM settings for comprehensive analysis."""
        
        # Add metadata
        metadata_section = f"""

---

## 📊 **Content Details**
- **Title**: {content.title}
- **Type**: {content.content_type}
- **Duration**: {content.duration or 'Unknown'} seconds
- **Language**: {content.language}
- **Indexed**: {content.indexed_at.strftime('%Y-%m-%d %H:%M:%S')}
- **Chunks**: {len(content.chunks)} searchable segments
- **Content ID**: {content.id}
"""
        
        if content.url:
            metadata_section += f"- **URL**: {content.url}\n"
        
        return summary + metadata_section
        
    except Exception as e:
        return f"❌ **Summary Error**: {str(e)}"

@mcp.tool()
async def rag_list_indexed_content() -> str:
    """
    List all indexed multimedia content with details.
    
    Returns:
        str: List of all indexed content with metadata
    """
    try:
        if not audio_video_server.content_store:
            return f"""# 📚 No Content Indexed

No multimedia content has been indexed yet.

## 🚀 **Getting Started**:

### 📺 **Index YouTube Videos**:
```
index_youtube_video("https://www.youtube.com/watch?v=VIDEO_ID")
```

### 🎵 **Index Audio Files**:
```
index_audio_file("/path/to/audio.mp3", "My Audio Title")
```

### 🔍 **Search Content**:
```
search_multimedia_content("What are the main topics?")
```
"""
        
        content_list = list(audio_video_server.content_store.values())
        content_list.sort(key=lambda x: x.indexed_at, reverse=True)
        
        result = f"# 📚 Indexed Multimedia Content\n\n"
        result += f"**Total Content**: {len(content_list)} items\n\n"
        
        for i, content in enumerate(content_list, 1):
            result += f"## {i}. {content.title}\n\n"
            result += f"   - **Type**: {content.content_type}\n"
            result += f"   - **Duration**: {content.duration or 'Unknown'} seconds\n"
            result += f"   - **Language**: {content.language}\n"
            result += f"   - **Chunks**: {len(content.chunks)} searchable segments\n"
            result += f"   - **Indexed**: {content.indexed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            result += f"   - **Content ID**: `{content.id}`\n"
            
            if content.url:
                result += f"   - **URL**: {content.url}\n"
            
            # Add preview
            preview = content.transcript[:200] + "..." if len(content.transcript) > 200 else content.transcript
            result += f"   - **Preview**: {preview}\n\n"
        
        result += f"## 🔍 **Usage Tips**:\n"
        result += f"- Use `search_multimedia_content` to ask questions\n"
        result += f"- Use `summarize_content` with content ID for detailed summaries\n"
        result += f"- Search works across all indexed content simultaneously\n"
        
        return result
        
    except Exception as e:
        return f"❌ **Listing Error**: {str(e)}"

@mcp.tool()
async def rag_analyze_search_intent(user_query: str) -> str:
    """
    Analyze user's search intent for multimedia content and provide optimization suggestions.
    
    Args:
        user_query (str): The user's search query to analyze
    
    Returns:
        str: Analysis of search intent and optimization recommendations
    """
    try:
        # Check LLM availability
        if not audio_video_server.is_llm_available():
            return "❌ **LLM Analysis Unavailable**: This feature requires LLM configuration. Please check your LLM settings."
        
        # Analyze search intent
        intent_analysis = await audio_video_server.analyze_with_llm(
            audio_video_server.search_intent_prompt.format(user_query=user_query)
        )
        
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', intent_analysis, re.DOTALL)
            if json_match:
                intent_data = json.loads(json_match.group())
                
                result = f"🎯 **Search Intent Analysis**\n\n"
                result += f"**Your Query**: {user_query}\n\n"
                result += f"**Detected Intent**: {intent_data.get('intent', 'Unknown')}\n"
                result += f"**Content Type Preference**: {intent_data.get('content_type_preference', 'Any')}\n"
                result += f"**Query Specificity**: {intent_data.get('specificity', 'Unknown')}\n"
                result += f"**Expected Content Length**: {intent_data.get('expected_content_length', 'Unknown')}\n\n"
                
                result += f"**Optimized Keywords**: {', '.join(intent_data.get('search_keywords', []))}\n\n"
                result += f"**Context Requirements**: {intent_data.get('context_requirements', 'General context')}\n\n"
                
                # Add recommendations
                result += f"## 💡 **Recommendations**\n\n"
                
                intent_type = intent_data.get('intent', '').lower()
                if 'learning' in intent_type:
                    result += "- Focus on educational content and tutorials\n"
                    result += "- Look for step-by-step explanations\n"
                    result += "- Consider longer-form content for comprehensive understanding\n"
                elif 'troubleshooting' in intent_type:
                    result += "- Search for problem-solving content\n"
                    result += "- Look for specific error messages or symptoms\n"
                    result += "- Focus on practical solutions and workarounds\n"
                elif 'research' in intent_type:
                    result += "- Search across multiple sources for comprehensive information\n"
                    result += "- Look for different perspectives and approaches\n"
                    result += "- Consider both technical and conceptual content\n"
                
                result += f"\n**Next Step**: Use `search_multimedia_content` with your query or try: `{', '.join(intent_data.get('search_keywords', [user_query]))}`"
                
                return result
            else:
                return f"🎯 **Search Intent Analysis**\n\n{intent_analysis}"
                
        except json.JSONDecodeError:
            return f"🎯 **Search Intent Analysis**\n\n{intent_analysis}"
        
    except Exception as e:
        return f"❌ **Analysis Error**: {str(e)}"

if __name__ == "__main__":
    logger.info("Enhanced Audio/Video RAG MCP server initialized!")
    logger.info("Features: YouTube video indexing, audio file processing, semantic search, LLM analysis")
    logger.info("Tools: index_youtube_video, index_audio_file, search_multimedia_content, summarize_content, list_indexed_content, analyze_search_intent")
    logger.info("Ready for multimedia content analysis!")
    mcp.run()
