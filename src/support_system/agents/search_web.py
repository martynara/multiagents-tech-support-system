from typing import Dict, Any, List
from langchain_google_community import GoogleSearchAPIWrapper
import asyncio
import logging

from ..state import SupportState, add_web_results
from ..config import settings

logger = logging.getLogger(__name__)

class WebSearchAgent:
    
    def __init__(self):
        self.search_wrapper = GoogleSearchAPIWrapper(
            google_cse_id=settings.google_cse_id,
            google_api_key=settings.google_api_key,
            k=settings.max_web_results
        )
    
    async def search(self, state: SupportState) -> Dict[str, Any]:
        query = state.get("query", "")
        
        if not query:
            logger.warning("No query provided for web search")
            return state
        
        try:
            search_query = self._construct_search_query(query)
            logger.info(f"Web searching for: {search_query}")
            
            max_results = settings.max_web_results
            logger.info(f"Limiting web search to {max_results} result(s)")
            
            try:
                results = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: self.search_wrapper.results(search_query, num_results=max_results)
                    ),
                    timeout=15.0
                )
                logger.info(f"Web search completed, found {len(results)} results")
            except asyncio.TimeoutError:
                logger.warning("Web search timed out after 15 seconds")
                return state
            except Exception as search_error:
                logger.warning(f"Web search failed: {search_error}")
                return state
            
            web_results = []
            for result in results[:settings.max_web_results]:
                web_results.append({
                    "content": result.get("snippet", ""),
                    "metadata": {
                        "title": result.get("title", ""),
                        "url": result.get("link", ""),
                        "source": "web"
                    },
                    "score": 0.8,
                    "source": "web"
                })
            
            search_metadata = {"web_search_query": search_query}
            
            logger.info(f"Returning {len(web_results)} web search results")
            
            return add_web_results(state, web_results, search_metadata)
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return state
    
    def _construct_search_query(self, query: str) -> str:
        query_lower = query.lower()
        
        if any(term in query_lower for term in ["vertiv", "avocent", "liebert", "geist", "emerson"]):
            return f"{query} official documentation guide"
        
        elif query_lower.startswith(("how to", "how do i", "how can i")):
            return f"{query} tutorial guide"
        
        elif any(term in query_lower for term in ["configure", "setup", "install", "deploy"]):
            return f"{query} documentation"
        
        return query

    def __call__(self, state: SupportState) -> Dict[str, Any]:
        import asyncio
        
        if asyncio.iscoroutinefunction(self.search):
            return asyncio.create_task(self.search(state))
        else:
            return asyncio.run(self.search(state))

def create_web_search_node():
    agent = WebSearchAgent()
    
    def web_search_node(state: SupportState) -> Dict[str, Any]:
        logger.info("Web search node triggered")
        
        import concurrent.futures
        import threading
        
        def run_async_in_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.search(state))
                    return result
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error in async thread: {e}")
                return state
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                result = future.result(timeout=20)
            
            logger.info("Web search node completed successfully")
            return result
            
        except concurrent.futures.TimeoutError:
            logger.error("Web search node timed out after 20 seconds")
            return state
        except Exception as e:
            logger.error(f"Web search node failed: {e}")
            return state
    
    return web_search_node