# Audio/Video RAG System

A comprehensive Retrieval-Augmented Generation (RAG) system for audio and video content using Databricks Vector Search, built with advanced features inspired by [Ragie's multimodal platform](https://www.ragie.ai/multimodal). This system can process video URLs, audio files, and video files to extract transcripts and visual content, then perform semantic search and generate AI-powered answers.

## Features

### Core Capabilities (Ragie-inspired)
- **Native Format Support**: Comprehensive support for MP3, WAV, MP4, WebM, MOV, AVI, FLV, MKV, and many more formats
- **Multilingual Transcription**: Automatic transcription for 100+ languages using OpenAI Whisper
- **Smart Chunking**: Audio/video-aware chunking that respects scene breaks, speaker changes, and topic shifts
- **Visual Parsing**: Frame-level sampling with AI-generated visual descriptions
- **Fast Indexing**: Efficient processing from upload to searchable content
- **Timestamped Results**: Every result links to exact moments with streamable URLs

### Advanced Features
- **Speaker Diarization**: Automatic speaker detection and identification
- **Scene Change Detection**: Intelligent scene boundary detection in video content
- **Visual Context Integration**: Enhanced search with visual elements and descriptions
- **Multi-modal Search**: Unified search across audio, video, and visual content
- **Streaming URLs**: Direct playback links with timestamp navigation
- **Production-Ready**: Scalable architecture with comprehensive error handling

## Supported Formats

### Audio Formats
- MP3
- WAV
- FLAC
- M4A
- OGG
- WMA
- AAC

### Video Formats
- MP4
- AVI
- MOV
- WMV
- FLV
- MKV
- WEBM

## Prerequisites

### System Dependencies
- FFmpeg (for audio/video processing)
- Google Speech Recognition API access
- OpenCV (for video frame extraction)

### Python Dependencies
All Python dependencies are listed in `requirements.txt` and will be installed automatically:
- `SpeechRecognition>=3.10.0`
- `pydub>=0.25.1`
- `opencv-python>=4.8.0`
- `Pillow>=10.0.0`
- `ffmpeg-python>=0.2.0`

### Databricks Configuration
You need to set up the following environment variables:

```bash
# Databricks Configuration
DATABRICKS_WORKSPACE_URL=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your-databricks-token
DATABRICKS_CLUSTER_ID=your-cluster-id
DATABRICKS_VECTOR_SEARCH_ENDPOINT=your-vector-search-endpoint
DATABRICKS_VECTOR_INDEX_NAME=audio_video_rag_index

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=your-azure-openai-key
AZURE_OPENAI_ENDPOINT=your-azure-openai-endpoint
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
```

## Installation

1. Install system dependencies:
   ```bash
   # On Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install ffmpeg

   # On macOS
   brew install ffmpeg

   # On Windows
   # Download FFmpeg from https://ffmpeg.org/download.html
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables in your `.env` file or system environment.

## Usage

### Available Tools

#### 1. `process_video_url(url: str)`
Process a video URL with enhanced multilingual transcription and visual parsing.

```python
result = await process_video_url("https://www.youtube.com/watch?v=VIDEO_ID")
# Returns: Enhanced metadata with timestamps, speaker detection, and visual context
```

#### 2. `process_file_attachment(file_data: str, filename: str)`
Process audio/video file attachments with smart chunking and scene detection.

```python
# file_data should be base64 encoded
result = await process_file_attachment(base64_encoded_data, "presentation.mp4")
# Returns: Smart chunks with speaker diarization and visual descriptions
```

#### 3. `semantic_search_content(query: str, top_k: int = 5, content_type: str = None)`
Perform semantic search with enhanced metadata and visual context.

```python
results = await semantic_search_content(
    "How to fix audio issues?", 
    top_k=5, 
    content_type="audio_file"
)
# Returns: Results with timestamps, speaker info, and streaming URLs
```

#### 4. `generate_rag_answer(query: str, top_k: int = 5, content_type: str = None)`
Generate comprehensive answers with timestamped references and visual context.

```python
answer = await generate_rag_answer(
    "What are the main points discussed in the video?",
    top_k=5
)
# Returns: Structured answer with timestamps, speaker attribution, and streaming links
```

#### 5. `list_processed_content()`
List all processed content with enhanced metadata.

```python
content_list = await list_processed_content()
# Returns: Content with language, duration, smart chunks, and visual info
```

#### 6. `get_timestamped_content(content_id: str, start_time: float = None, end_time: float = None)`
Retrieve timestamped content with streaming URLs (Ragie-like feature).

```python
content = await get_timestamped_content(
    "content_id_123", 
    start_time=120.0, 
    end_time=180.0
)
# Returns: Timestamped chunks with streaming URLs for direct playback
```

#### 7. `search_with_visual_context(query: str, include_visual: bool = True, top_k: int = 5)`
Enhanced multimodal search with visual context integration.

```python
results = await search_with_visual_context(
    "presentation slides about machine learning",
    include_visual=True,
    top_k=5
)
# Returns: Results with visual descriptions and scene information
```

### Example Workflow

1. **Process a YouTube video**:
   ```python
   result = await process_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
   ```

2. **Search for specific content**:
   ```python
   results = await semantic_search_content("music production techniques")
   ```

3. **Generate an answer**:
   ```python
   answer = await generate_rag_answer("What are the key steps in music production?")
   ```

## Architecture

### Data Flow

1. **Content Ingestion**:
   - Video URLs are processed to extract video IDs
   - Transcripts are retrieved from video platforms (YouTube, etc.)
   - Audio/video files are processed locally

2. **Content Processing**:
   - Audio is extracted from video files
   - Speech recognition converts audio to text
   - Video frames are extracted and encoded
   - Content is chunked for optimal retrieval

3. **Storage**:
   - Chunks are stored in Databricks Vector Search
   - Metadata includes timestamps, content type, and source information

4. **Retrieval**:
   - Semantic search using Databricks Vector Search
   - Results are ranked by relevance
   - Context is prepared for RAG generation

5. **Generation**:
   - Azure OpenAI generates comprehensive answers
   - Context chunks provide grounding for responses

### Key Components

- **AudioVideoRAGProcessor**: Main processing class
- **Speech Recognition**: Google Speech Recognition API
- **Video Processing**: OpenCV for frame extraction
- **Vector Search**: Databricks Vector Search for semantic similarity
- **LLM Integration**: Azure OpenAI for RAG generation

## Configuration

### Chunk Settings
- `CHUNK_SIZE`: 1000 characters (configurable)
- `OVERLAP_SIZE`: 200 characters (configurable)

### Processing Limits
- Maximum frames per video: 10 (configurable)
- Audio chunk silence threshold: 1 second
- Timeout for API calls: 30 seconds

## Troubleshooting

### Common Issues

1. **FFmpeg not found**:
   - Install FFmpeg system-wide
   - Add FFmpeg to your PATH

2. **Speech recognition errors**:
   - Check internet connection
   - Verify audio quality
   - Consider using alternative recognition engines

3. **Databricks connection issues**:
   - Verify workspace URL and token
   - Check cluster status
   - Ensure vector search endpoint is active

4. **Memory issues with large files**:
   - Process files in smaller chunks
   - Consider using streaming processing
   - Monitor system resources

### Performance Optimization

1. **Audio Processing**:
   - Use lower quality audio for faster processing
   - Pre-process audio to remove silence
   - Consider parallel processing for multiple files

2. **Video Processing**:
   - Extract fewer frames for faster processing
   - Use lower resolution for frame extraction
   - Process video and audio separately

3. **Vector Search**:
   - Optimize chunk size for your use case
   - Use appropriate top_k values
   - Consider caching frequent searches

## API Reference

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABRICKS_WORKSPACE_URL` | Databricks workspace URL | Yes |
| `DATABRICKS_TOKEN` | Databricks access token | Yes |
| `DATABRICKS_CLUSTER_ID` | Databricks cluster ID | Optional |
| `DATABRICKS_VECTOR_SEARCH_ENDPOINT` | Vector search endpoint | Optional |
| `DATABRICKS_VECTOR_INDEX_NAME` | Vector index name | Optional |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Yes |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint | Yes |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI deployment name | Yes |

### Response Formats

#### Processing Response
```json
{
  "success": true,
  "chunks_stored": 25,
  "content_id": "abc123",
  "processing_summary": {
    "transcript_length": 5000,
    "frames_extracted": 10,
    "chunks_created": 25
  }
}
```

#### Search Results
```json
[
  {
    "content": "This is a relevant chunk of content...",
    "metadata": {
      "content_id": "abc123",
      "type": "video_url",
      "timestamp": "2024-01-01T00:00:00",
      "chunk_index": 0
    }
  }
]
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 