from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
import logging

from ..state import SupportState
from ..config import settings

logger = logging.getLogger(__name__)

class CoordinatorAgent:
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0.1,
            api_key=settings.openai_api_key
        )
    
    def update_state(self, state: SupportState) -> Dict[str, Any]:
        """Simple state update - increment iteration and ensure query is set."""
        iteration = state.get("iteration", 0)
        query = state.get("query", "")
        
        if not query:
            for msg in reversed(state["messages"]):
                if isinstance(msg, HumanMessage):
                    query = msg.content
                    break
        
        logger.info(f"Coordinator updating state - Iteration: {iteration} → {iteration + 1}")
        
        # Only increment iteration, don't make routing decisions here
        return {"iteration": iteration + 1, "query": query}
    
    def _should_search_web(self, query: str, internal_results: List[Dict[str, Any]]) -> bool:
        """Simple logic: check if internal results are insufficient."""
        query_lower = query.lower()
        
        # Always try internal first - only use web if internal fails
        # This is the key principle: internal docs are authoritative for Vertiv
        
        # If no internal results found, try web
        if not internal_results:
            logger.info("No internal results found, recommending web search")
            return True
        
        # If very few internal results (less than 2), try web as backup
        if len(internal_results) < 2:
            logger.info(f"Only {len(internal_results)} internal results found, recommending web search")
            return True
        
        # Check if internal results are low quality (low relevance scores)
        scores = [result.get("score", 0) for result in internal_results]
        avg_score = sum(scores) / len(scores)
        logger.info(f"Internal results average score: {avg_score:.3f}")
        
        if avg_score < 0.5:  # Very low threshold - only for truly irrelevant results
            logger.info(f"Low average score ({avg_score:.3f}), recommending web search")
            return True
        
        # Check if internal results have very little content
        total_content_length = sum(len(doc.get("content", "")) for doc in internal_results)
        logger.info(f"Total content length from internal results: {total_content_length}")
        
        if total_content_length < 200:  # Very short responses suggest poor matches
            logger.info(f"Low content length ({total_content_length}), recommending web search")
            return True
        
        logger.info("Internal results are sufficient, no web search needed")
        return False
    
    def route_next(self, state: SupportState) -> str:
        """Simple routing logic based on iteration and results quality."""
        iteration = state.get("iteration", 0)
        has_internal = bool(state.get("internal_results"))
        has_web = bool(state.get("web_results"))
        query = state.get("query", "")
        
        logger.info(f"Routing decision - Iteration: {iteration}")
        logger.info(f"State: internal={has_internal}, web={has_web}")
        
        # Maximum iterations reached - synthesize what we have
        if iteration >= settings.max_iterations:
            logger.info("Max iterations reached, routing to synthesize")
            return "synthesize"
        
        # First iteration: ALWAYS search internal docs first
        # This is the core principle - internal docs are the primary source
        if iteration == 0:
            logger.info("First iteration, routing to search_internal")
            return "search_internal"
        
        # Second iteration: only search web if internal results are insufficient
        if iteration == 1 and not has_web:
            if self._should_search_web(query, state.get("internal_results", [])):
                logger.info("Second iteration, routing to search_web due to insufficient internal results")
                return "search_web"
            else:
                logger.info("Second iteration, internal results sufficient, routing to synthesize")
                return "synthesize"
        
        # Default: synthesize with available results
        logger.info("Default case, routing to synthesize")
        return "synthesize"
    
    def _is_clearly_non_technical(self, query: str) -> bool:
        """
        Only catch obviously non-technical queries.
        This is much simpler than the previous approach.
        """
        query_lower = query.lower()
        
        # Only the most obvious non-technical patterns
        obvious_patterns = [
            "who is the president",
            "what is the capital of",
            "when was born",
            "what is the weather",
            "stock price",
            "sports score"
        ]
        
        return any(pattern in query_lower for pattern in obvious_patterns)