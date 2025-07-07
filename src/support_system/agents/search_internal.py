from typing import Dict, Any, List
from langchain_elasticsearch import ElasticsearchStore
from langchain_openai import OpenAIEmbeddings
import logging
import elasticsearch
import json
import asyncio
import time
from elasticsearch import Elasticsearch

from ..state import SupportState, add_internal_results
from ..config import settings

logger = logging.getLogger(__name__)

class InternalSearchAgent:
    
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)
        self.vectorstore = None
        self.es_available = False
        self.es_client = None
        
        try:
            self.vectorstore = ElasticsearchStore(
                es_url=settings.elasticsearch_url,
                index_name=settings.elasticsearch_index,
                embedding=self.embeddings,
                es_api_key=settings.elasticsearch_api_key,
            )
            
            self.es_client = Elasticsearch(
                settings.elasticsearch_url,
                api_key=settings.elasticsearch_api_key,
            )
            
            self.es_available = True
            logger.info("Successfully connected to Elasticsearch")
        except elasticsearch.AuthenticationException as e:
            logger.warning(f"Authentication error connecting to Elasticsearch: {e}")
            logger.warning("Make sure ELASTICSEARCH_API_KEY is properly set in your .env file")
        except Exception as e:
            logger.warning(f"Failed to connect to Elasticsearch: {e}")
    
    async def search(self, state: SupportState) -> Dict[str, Any]:
        query = state.get("query", "")
        start_time = time.time()
        
        if not query or not self.es_available or not self.es_client:
            logger.warning("Cannot perform internal search: Elasticsearch not available or no query provided")
            return {"internal_results": []}
        
        try:
            logger.info(f"🔍 Starting internal search for: '{query}'")
            
            # EMBEDDINGS ONLY: Generate embeddings for vector search
            # No text search fallback as requested by user
            logger.info("📡 Generating embeddings via OpenAI API...")
            embedding_start = time.time()
            
            try:
                embedding_response = await asyncio.wait_for(
                    self.embeddings.aembed_query(query),
                    timeout=10.0  # 10 second timeout for embeddings
                )
                embedding_time = time.time() - embedding_start
                logger.info(f"✅ Embeddings generated in {embedding_time:.2f}s")
            except asyncio.TimeoutError:
                embedding_time = time.time() - embedding_start
                logger.error(f"⏰ Embedding generation timed out after {embedding_time:.2f}s")
                return {"internal_results": []}
            except Exception as embed_error:
                embedding_time = time.time() - embedding_start
                logger.error(f"❌ Embedding generation failed after {embedding_time:.2f}s: {embed_error}")
                return {"internal_results": []}
            
            # Execute KNN vector search ONLY
            search_start = time.time()
            logger.info("🎯 Executing KNN vector search...")
            
            try:
                search_response = self.es_client.search(
                    index=settings.elasticsearch_index,
                    knn={
                        "field": "content_embedding",
                        "query_vector": embedding_response,
                        "k": settings.max_docs,
                        "num_candidates": 50  # Reduced for speed
                    },
                    size=settings.max_docs,
                    timeout="8s"  # 8 second timeout
                )
                search_time = time.time() - search_start
                logger.info(f"✅ KNN search completed in {search_time:.2f}s")
            except Exception as knn_error:
                search_time = time.time() - search_start
                logger.error(f"❌ KNN search failed after {search_time:.2f}s: {str(knn_error)}")
                return {"internal_results": []}
            
            # Process results
            processing_start = time.time()
            
            # Extract search results
            if hasattr(search_response, 'body'):
                search_dict = search_response.body
            elif hasattr(search_response, 'raw'):
                search_dict = search_response.raw
            else:
                search_dict = search_response
            
            # Debug the response structure
            logger.debug(f"Search response keys: {list(search_dict.keys())}")
            
            # Check if we have hits
            if "hits" not in search_dict or "hits" not in search_dict["hits"]:
                logger.warning("No hits found in Elasticsearch response")
                logger.debug(f"Search response structure: {json.dumps(search_dict)[:200]}...")
                return {"internal_results": []}
            
            hit_count = len(search_dict["hits"]["hits"])
            logger.info(f"📊 Found {hit_count} documents from Elasticsearch")
            
            if hit_count == 0:
                logger.warning("No results found in Elasticsearch")
                return {"internal_results": []}
            
            results = []
            for hit in search_dict["hits"]["hits"]:
                source = hit["_source"]
                
                # Extract content and metadata based on known fields
                content = source.get("content", "No content available")
                
                # Create structured metadata using known fields
                metadata = {
                    "document_title": source.get("document_title", "Unknown Document"),
                    "source": source.get("source", "internal"),
                    "filename": source.get("filename", ""),
                    "file_path": source.get("file_path", ""),
                    "page_number": source.get("page_number", None),
                    "chunk_id": source.get("chunk_id", ""),
                    "chunk_seq_id": source.get("chunk_seq_id", "")
                }
                
                # Determine the best source name for display
                source_name = metadata["filename"]
                if not source_name:
                    source_name = metadata["document_title"]
                    if not source_name or source_name == "Unknown Document" or source_name == "Untitled Document":
                        source_name = metadata["source"]
                
                result = {
                    "content": content,
                    "metadata": metadata,
                    "score": hit.get("_score", 0),
                    "source": source_name
                }
                
                if len(results) < 2:
                    logger.info(f"📄 Document {len(results)}: source={source_name}, score={hit.get('_score', 0):.3f}")
                    logger.debug(f"Content preview: {content[:100]}...")
                
                results.append(result)
            
            processing_time = time.time() - processing_start
            total_time = time.time() - start_time
            
            logger.info(f"⚡ Processing completed in {processing_time:.2f}s")
            logger.info(f"🏁 Total internal search time: {total_time:.2f}s")
            logger.info(f"📦 Returning {len(results)} relevant results from Elasticsearch")
            
            # FIXED: Use proper state update function instead of raw dict
            return add_internal_results(state, results)
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"❌ Internal search error after {total_time:.2f}s: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"internal_results": []}

def create_internal_search_node():
    """Create a LangGraph-compatible node function for internal search."""
    agent = InternalSearchAgent()
    
    def internal_search_node(state: SupportState) -> Dict[str, Any]:
        """Sync wrapper for async internal search - LangGraph compatible."""
        logger.info("🏃 Internal search node triggered")
        
        # Fixed async-to-sync wrapper using threading
        import concurrent.futures
        import threading
        
        def run_async_in_thread():
            """Run async function in a new thread with its own event loop."""
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.search(state))
                    return result
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error in async thread: {e}")
                return {"internal_results": []}
        
        try:
            # Run the async function in a thread with timeout
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                result = future.result(timeout=30)  # 30 second timeout
            
            logger.info("✅ Internal search node completed successfully")
            return result
            
        except concurrent.futures.TimeoutError:
            logger.error("❌ Internal search node timed out after 30 seconds")
            return {"internal_results": []}
        except Exception as e:
            logger.error(f"❌ Internal search node failed: {e}")
            return {"internal_results": []}
    
    return internal_search_node