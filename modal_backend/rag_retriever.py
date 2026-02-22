"""
RAG Retriever Module for Clinical Guidelines

Provides secure, rate-limited vector retrieval of medical guidelines using ChromaDB
with sentence-transformers embeddings. Includes comprehensive security measures
to prevent prompt injection and ensure auditability.
"""

import os
import re
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict
import yaml
import torch

# Monkey-patch for ROCm/AMD GPU compatibility
# Fixes: "module 'torch.distributed' has no attribute 'is_initialized'"
# See: https://github.com/huggingface/transformers/issues/26039
# This must be done before importing sentence-transformers
if not hasattr(torch.distributed, 'is_initialized'):
    torch.distributed.is_initialized = lambda: False

# Optional imports - graceful degradation if not available
try:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """Represents a retrieved guideline chunk with metadata."""
    content: str
    title: str
    organization: str
    topic: str
    source_url: str
    chunk_id: str
    distance: float


class SecurityValidator:
    """
    Security validation layer to prevent prompt injection and abuse.
    """
    
    # Maximum query length
    MAX_QUERY_LENGTH = 500
    
    # Forbidden patterns for prompt injection prevention
    FORBIDDEN_PATTERNS = [
        r"ignore\s+(all\s+|previous\s+)?instructions",
        r"system\s+prompt",
        r"you\s+are\s+(now\s+|an?\s+)",
        r"disregard\s+(the\s+|all\s+)?(above|previous)",
        r"forget\s+(everything|all)\s+(above|before)",
        r"roleplay\s+as",
        r"pretend\s+(to\s+be|you\s+are)",
        r"new\s+persona",
        r"override\s+(safety|security)",
        r"bypass\s+(restrictions|filters)",
        r"act\s+as\s+(if\s+)?",
        r"simulate\s+(being|acting)",
        r"<\s*script\s*>",
        r"\{\{.*\}\}",  # Template injection patterns
    ]
    
    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.FORBIDDEN_PATTERNS]
    
    def validate_query_length(self, query: str) -> Tuple[bool, str]:
        """
        Check if query exceeds maximum length.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(query) > self.MAX_QUERY_LENGTH:
            return False, f"Query exceeds maximum length of {self.MAX_QUERY_LENGTH} characters"
        return True, ""
    
    def check_forbidden_patterns(self, query: str) -> Tuple[bool, str, List[str]]:
        """
        Check for prompt injection patterns in query.
        
        Returns:
            Tuple of (is_safe, error_message, detected_patterns)
        """
        detected = []
        for pattern in self.compiled_patterns:
            if pattern.search(query):
                detected.append(pattern.pattern)
        
        if detected:
            return False, f"Potentially malicious patterns detected: {detected[:3]}", detected
        return True, "", []
    
    def validate_query(self, query: str) -> Tuple[bool, str]:
        """
        Comprehensive query validation.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check length
        valid, msg = self.validate_query_length(query)
        if not valid:
            return False, msg
        
        # Check forbidden patterns
        safe, msg, _ = self.check_forbidden_patterns(query)
        if not safe:
            return False, msg
        
        return True, ""
    
    def sanitize_retrieved_text(self, text: str) -> str:
        """
        Sanitize retrieved guideline text before injection.
        Removes potentially malicious content while preserving medical information.
        
        Args:
            text: Raw retrieved text
            
        Returns:
            Sanitized text safe for prompt injection
        """
        # Remove common injection markers
        sanitized = text
        
        # Remove markdown code blocks that might contain instructions
        sanitized = re.sub(r'```[\s\S]*?```', '[CODE BLOCK REMOVED]', sanitized)
        
        # Remove HTML-like tags
        sanitized = re.sub(r'<[^>]+>', '', sanitized)
        
        # Escape or remove template syntax
        sanitized = sanitized.replace('{{', '').replace('}}', '')
        
        # Remove any remaining suspicious patterns
        for pattern in self.compiled_patterns:
            sanitized = pattern.sub('[REMOVED]', sanitized)
        
        return sanitized


class RateLimiter:
    """
    Simple rate limiter to prevent abuse.
    Tracks requests per IP with sliding window.
    """
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests allowed per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)  # IP -> list of timestamps
    
    def is_allowed(self, identifier: str) -> Tuple[bool, int]:
        """
        Check if request is allowed for given identifier.
        
        Args:
            identifier: IP address or other unique identifier
            
        Returns:
            Tuple of (is_allowed, requests_remaining)
        """
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self.requests[identifier] = [
            ts for ts in self.requests[identifier] 
            if ts > window_start
        ]
        
        # Check limit
        current_count = len(self.requests[identifier])
        if current_count >= self.max_requests:
            return False, 0
        
        # Record this request
        self.requests[identifier].append(now)
        
        return True, self.max_requests - current_count - 1
    
    def reset(self, identifier: str):
        """Reset rate limit for identifier."""
        if identifier in self.requests:
            del self.requests[identifier]


class AuditLogger:
    """
    Audit logging for RAG operations.
    Logs all queries, retrievals, and security events.
    """
    
    def __init__(self, log_file: str = "rag_audit.log"):
        """
        Initialize audit logger.
        
        Args:
            log_file: Path to audit log file
        """
        self.log_file = Path(log_file)
        self.logger = logging.getLogger("rag_audit")
        
        # Setup file handler if not already configured
        if not self.logger.handlers:
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log_query(self, query: str, ip_address: str, success: bool, 
                  num_results: int = 0, error_msg: str = ""):
        """Log a retrieval query."""
        redacted_query = self._redact_query(query)
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(
            f"QUERY [{status}] - IP: {ip_address} - "
            f"Query: '{redacted_query}' - Results: {num_results}"
            f"{f' - Error: {error_msg}' if error_msg else ''}"
        )
    
    def log_security_event(self, event_type: str, ip_address: str, 
                          details: str, blocked: bool = True):
        """Log a security-related event."""
        action = "BLOCKED" if blocked else "WARNING"
        self.logger.warning(
            f"SECURITY [{action}] - Type: {event_type} - "
            f"IP: {ip_address} - Details: {details}"
        )
    
    def log_retrieval(self, query: str, chunks: List[RetrievedChunk], 
                     ip_address: str):
        """Log successful retrieval with chunk details."""
        redacted_query = self._redact_query(query)
        sources = [f"{c.organization}/{c.topic}" for c in chunks]
        self.logger.info(
            f"RETRIEVAL - IP: {ip_address} - Query: '{redacted_query}' - "
            f"Sources: {sources}"
        )

    def _redact_query(self, query: str) -> str:
        """Redact likely PHI by masking digits and truncating length."""
        masked = re.sub(r"\d", "X", query)
        masked = re.sub(r"\s+", " ", masked).strip()
        if len(masked) > 80:
            return masked[:77] + "..."
        return masked


class GuidelineRetriever:
    """
    Main RAG retriever class for clinical guidelines.
    
    Provides secure, rate-limited vector search with comprehensive audit logging.
    """
    
    # Default chunking parameters (Guide-RAG paper: 1200 chars, 50% overlap, top-25)
    # Scaled down for our corpus size: TOP_K=12 (vs paper's 25), OVERLAP=42% (vs 50%)
    CHUNK_SIZE = 1200
    CHUNK_OVERLAP = 500  # 42% overlap for better context continuity
    TOP_K_DEFAULT = 12   # Increased from 5 for better comprehensiveness (Guide-RAG paper)
    
    # Embedding model (lightweight, CPU-only)
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    
    def __init__(self, 
                 guidelines_dir: str = "guidelines",
                 cache_dir: str = ".chroma_cache",
                 max_query_length: int = 500,
                 rate_limit_requests: int = 10,
                 rate_limit_window: int = 60,
                 audit_log_file: str = "rag_audit.log"):
        """
        Initialize the guideline retriever.
        
        Args:
            guidelines_dir: Directory containing markdown guideline files
            cache_dir: Directory for ChromaDB persistence
            max_query_length: Maximum allowed query length
            rate_limit_requests: Max requests per rate limit window
            rate_limit_window: Rate limit window in seconds
            audit_log_file: Path to audit log file
        """
        self.guidelines_dir = Path(guidelines_dir)
        self.cache_dir = Path(cache_dir)
        self.top_k = self.TOP_K_DEFAULT
        
        # Security components
        self.security = SecurityValidator()
        self.security.MAX_QUERY_LENGTH = max_query_length
        self.rate_limiter = RateLimiter(rate_limit_requests, rate_limit_window)
        self.audit_logger = AuditLogger(audit_log_file)
        
        # Initialize ChromaDB components
        self.embedding_function = None  # Set during initialize()
        self.chroma_client = None
        self.collection = None
        self._initialized = False
        
        # Statistics
        self.indexing_stats = {
            "num_files": 0,
            "num_chunks": 0,
            "last_indexed": None
        }
        
        logger.info("GuidelineRetriever initialized (not yet indexed)")
    
    def initialize(self, force_reindex: bool = False) -> bool:
        """
        Initialize the retriever by loading/creating the vector index.
        
        Args:
            force_reindex: Force reindexing even if cache exists
            
        Returns:
            True if initialization successful
        """
        if not CHROMADB_AVAILABLE:
            logger.error("ChromaDB not available. Install with: pip install chromadb")
            return False
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.error("sentence-transformers not available. Install with: pip install sentence-transformers")
            return False
        
        try:
            # Create embedding function for ChromaDB (shared between indexing and querying)
            # This ensures the same model is used for both, preventing silent mismatches
            logger.info(f"Loading embedding model: {self.EMBEDDING_MODEL}")
            self.embedding_function = SentenceTransformerEmbeddingFunction(
                model_name=self.EMBEDDING_MODEL
            )
            
            # Initialize ChromaDB with persistent client (new API)
            self.chroma_client = chromadb.PersistentClient(path=str(self.cache_dir))
            
            # Check if collection exists and is valid
            # Note: PersistentClient creates the cache_dir immediately, so we can't rely on
            # directory existence alone. We need to try getting the collection and catch
            # ValueError if it doesn't exist.
            cache_exists = self.cache_dir.exists() and any(self.cache_dir.iterdir())
            
            if cache_exists and not force_reindex:
                try:
                    logger.info("Loading existing vector index...")
                    self.collection = self.chroma_client.get_collection(
                        name="guidelines",
                        embedding_function=self.embedding_function
                    )
                    self._load_stats_from_cache()
                except (ValueError, Exception) as e:
                    # Collection doesn't exist in cache (e.g., cache dir recreated by PersistentClient)
                    logger.info(f"Collection not found in cache, creating new index...")
                    self._create_index()
            else:
                logger.info("Creating new vector index...")
                self._create_index()
            
            self._initialized = True
            logger.info(f"Retriever ready: {self.indexing_stats['num_chunks']} chunks indexed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize retriever: {e}")
            return False
    
    def _create_index(self):
        """Create vector index from guideline files."""
        # Create or reset collection
        try:
            self.chroma_client.delete_collection(name="guidelines")
        except:
            pass
        
        self.collection = self.chroma_client.create_collection(
            name="guidelines",
            embedding_function=self.embedding_function
        )
        
        # Load and chunk guidelines
        documents = []
        metadatas = []
        ids = []
        
        if not self.guidelines_dir.exists():
            logger.warning(f"Guidelines directory not found: {self.guidelines_dir}")
            return
        
        file_count = 0
        chunk_count = 0
        
        # Use rglob to recursively find all .md files in subdirectories
        for md_file in self.guidelines_dir.rglob("*.md"):
            file_count += 1
            logger.info(f"Processing: {md_file.name}")
            
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse frontmatter and content
                metadata, body = self._parse_markdown(content)
                
                # Chunk the content
                chunks = self._chunk_text(body)
                
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{md_file.stem}_chunk_{i}"
                    documents.append(chunk)
                    metadatas.append({
                        "title": metadata.get("title", md_file.stem),
                        "organization": metadata.get("organization", "Unknown"),
                        "topic": metadata.get("topic", "general"),
                        "source_url": metadata.get("source_url", ""),
                        "year": metadata.get("year", ""),
                        "chunk_index": i,
                        "file": md_file.name
                    })
                    ids.append(chunk_id)
                    chunk_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing {md_file}: {e}")
        
        # Add to collection in batches
        if documents:
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                end = min(i + batch_size, len(documents))
                self.collection.add(
                    documents=documents[i:end],
                    metadatas=metadatas[i:end],
                    ids=ids[i:end]
                )
        
        # Update stats
        self.indexing_stats = {
            "num_files": file_count,
            "num_chunks": chunk_count,
            "last_indexed": datetime.now().isoformat()
        }
        
        logger.info(f"Indexed {file_count} files into {chunk_count} chunks")
    
    def _parse_markdown(self, content: str) -> Tuple[Dict[str, Any], str]:
        """Parse YAML frontmatter and body from markdown."""
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    metadata = yaml.safe_load(parts[1])
                    body = parts[2].strip()
                    return metadata or {}, body
                except:
                    pass
        return {}, content
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.CHUNK_SIZE
            chunk = text[start:end]
            
            # Try to break at a sentence or paragraph
            if end < len(text):
                # Look for sentence break
                for delim in ['. ', '? ', '! ', '\n\n']:
                    pos = chunk.rfind(delim)
                    if pos > self.CHUNK_SIZE * 0.5:  # At least half the chunk
                        chunk = chunk[:pos+2]
                        break
            
            chunks.append(chunk.strip())
            start += self.CHUNK_SIZE - self.CHUNK_OVERLAP
        
        return chunks
    
    def _load_stats_from_cache(self):
        """Load indexing stats from existing collection."""
        try:
            count = self.collection.count()
            self.indexing_stats = {
                "num_files": "unknown",  # Can't determine from cache alone
                "num_chunks": count,
                "last_indexed": "from_cache"
            }
        except:
            pass
    
    def retrieve(self, query: str, ip_address: str = "unknown", 
                top_k: Optional[int] = None) -> Tuple[List[RetrievedChunk], str]:
        """
        Retrieve relevant guideline chunks for a query.
        
        Args:
            query: Search query
            ip_address: Client IP for rate limiting and audit
            top_k: Number of results (default: 5)
            
        Returns:
            Tuple of (list of RetrievedChunk, error_message)
            If error_message is not empty, retrieval failed
        """
        if not self._initialized:
            return [], "Retriever not initialized"
        
        top_k = top_k or self.top_k
        
        # Security: Rate limiting
        allowed, remaining = self.rate_limiter.is_allowed(ip_address)
        if not allowed:
            self.audit_logger.log_security_event(
                "RATE_LIMIT_EXCEEDED", ip_address, 
                f"Query: '{query[:50]}...'"
            )
            return [], f"Rate limit exceeded. Try again later."
        
        # Security: Validate query
        valid, error_msg = self.security.validate_query(query)
        if not valid:
            self.audit_logger.log_security_event(
                "VALIDATION_FAILED", ip_address, error_msg
            )
            return [], error_msg
        
        try:
            # Perform vector search
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )
            
            # Build result objects with sanitization
            chunks = []
            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i]
                content = results['documents'][0][i]
                distance = results['distances'][0][i]
                
                # Security: Sanitize retrieved content
                safe_content = self.security.sanitize_retrieved_text(content)
                
                chunk = RetrievedChunk(
                    content=safe_content,
                    title=metadata.get("title", "Unknown"),
                    organization=metadata.get("organization", "Unknown"),
                    topic=metadata.get("topic", "general"),
                    source_url=metadata.get("source_url", ""),
                    chunk_id=results['ids'][0][i],
                    distance=distance
                )
                chunks.append(chunk)
            
            # Audit log
            self.audit_logger.log_retrieval(query, chunks, ip_address)
            self.audit_logger.log_query(query, ip_address, True, len(chunks))
            
            return chunks, ""
            
        except Exception as e:
            error_msg = f"Retrieval error: {str(e)}"
            self.audit_logger.log_query(query, ip_address, False, error_msg=error_msg)
            return [], error_msg
    
    def get_status(self) -> Dict[str, Any]:
        """Get current retriever status and statistics."""
        return {
            "initialized": self._initialized,
            "indexing_stats": self.indexing_stats,
            "embedding_model": self.EMBEDDING_MODEL,
            "chunk_size": self.CHUNK_SIZE,
            "chunk_overlap": self.CHUNK_OVERLAP,
            "top_k_default": self.TOP_K_DEFAULT,
            "security": {
                "max_query_length": self.security.MAX_QUERY_LENGTH,
                "forbidden_patterns_count": len(self.security.FORBIDDEN_PATTERNS),
                "rate_limit_requests": self.rate_limiter.max_requests,
                "rate_limit_window": self.rate_limiter.window_seconds
            }
        }
    
    def format_retrieved_context(self, chunks: List[RetrievedChunk]) -> str:
        """
        Format retrieved chunks into a safe context string for prompt injection.
        
        Args:
            chunks: List of retrieved chunks
            
        Returns:
            Formatted context string
        """
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            part = f"""
[Guideline {i}]
Source: {chunk.organization} - {chunk.title}
Topic: {chunk.topic}
URL: {chunk.source_url}

{chunk.content}
"""
            context_parts.append(part)
        
        full_context = "\n---\n".join(context_parts)
        
        # Wrap in clear markers
        return f"""
[RETRIEVED CLINICAL GUIDELINES - START]
{full_context}
[RETRIEVED CLINICAL GUIDELINES - END]

Use the above evidence-based guidelines to inform your response. Cite specific recommendations where applicable.
"""

    def close(self):
        """Release ChromaDB client resources (for proper cleanup on Windows)."""
        if self.chroma_client is not None:
            try:
                # Clear references to allow garbage collection
                self.collection = None
                self.chroma_client = None
                self._initialized = False
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")


# Singleton instance for application use
_retriever_instance: Optional[GuidelineRetriever] = None


def get_retriever(guidelines_dir: str = "guidelines", 
                 **kwargs) -> GuidelineRetriever:
    """
    Get or create singleton retriever instance.
    
    Args:
        guidelines_dir: Directory containing guideline files
        **kwargs: Additional arguments for GuidelineRetriever
        
    Returns:
        GuidelineRetriever instance
    """
    global _retriever_instance
    
    if _retriever_instance is None:
        _retriever_instance = GuidelineRetriever(guidelines_dir, **kwargs)
    
    return _retriever_instance


if __name__ == "__main__":
    # Simple test
    retriever = GuidelineRetriever()
    if retriever.initialize():
        print("Retriever initialized successfully!")
        print(f"Stats: {retriever.get_status()}")
        
        # Test query
        chunks, error = retriever.retrieve(
            "treatment for severe pneumonia", 
            ip_address="test"
        )
        if error:
            print(f"Error: {error}")
        else:
            print(f"Retrieved {len(chunks)} chunks")
            for chunk in chunks:
                print(f"\n--- {chunk.title} ---")
                print(chunk.content[:200] + "...")
