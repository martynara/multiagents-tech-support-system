from typing import Dict, Any, List
from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
import logging
import asyncio

from ..state import SupportState
from ..config import settings

logger = logging.getLogger(__name__)

class SynthesizerAgent:
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.3,
            api_key=settings.openai_api_key,
            max_tokens=500
        )
    
    async def synthesize(self, state: SupportState) -> Dict[str, Any]:
        query = state.get("query", "")
        internal_results = state.get("internal_results", [])
        web_results = state.get("web_results", [])
        
        logger.info(f"Synthesizing response from {len(internal_results)} internal + {len(web_results)} web sources")
        
        context_parts = []
        sources = []
        
        if internal_results:
            context_parts.append("=== DOCUMENTATION ===")
            for i, result in enumerate(internal_results[:2], 1):
                category = result.get("metadata", {}).get("category", "Documentation")
                context_parts.append(f"Source {i} ({category}):")
                content = result.get("content", "")
                context_parts.append(content[:400] + "..." if len(content) > 400 else content)
                context_parts.append("")
                sources.append(f" Vertiv {category}")
        
        if web_results:
            context_parts.append("=== WEB RESOURCES ===")
            result = web_results[0]
            title = result.get("metadata", {}).get("title", "Web Result")
            context_parts.append(f"Web: {title}")
            content = result.get("content", "")
            context_parts.append(content[:200] + "..." if len(content) > 200 else content)
            sources.append(f"Web: {title}")
        
        context = "\n".join(context_parts) if context_parts else "No specific information found."
        
        prompt = f"""Answer this technical question clearly and helpfully:

Question: {query}

Context:
{context}

Provide a direct, actionable answer. Use markdown formatting. Be concise but complete."""
        
        try:
            logger.info("Generating final response with OpenAI...")
            response = await self.llm.ainvoke([SystemMessage(content=prompt)])
            
            response_content = response.content
            if sources:
                unique_sources = list(set(sources))
                response_content += f"\n\n**Sources:** {', '.join(unique_sources)}"
            
            logger.info("Synthesis completed successfully")
            
            return {
                "messages": [AIMessage(content=response_content)],
                "internal_results": internal_results,
                "web_results": web_results,
                "final_response": response_content
            }
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            error_response = f"I encountered an error while processing your request: {str(e)}"
            return {
                "messages": [AIMessage(content=error_response)],
                "internal_results": internal_results,
                "web_results": web_results
            }

def create_synthesizer_node():
    agent = SynthesizerAgent()
    
    def synthesizer_node(state: SupportState) -> Dict[str, Any]:
        logger.info("Synthesizer node triggered")
        
        import concurrent.futures
        import threading
        
        def run_async_in_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.synthesize(state))
                    return result
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error in async thread: {e}")
                error_response = f"I encountered an error while processing your request: {str(e)}"
                return {
                    "messages": [AIMessage(content=error_response)],
                    "internal_results": state.get("internal_results", []),
                    "web_results": state.get("web_results", []),
                    "final_response": error_response
                }
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                result = future.result(timeout=30)
            
            logger.info("Synthesizer node completed successfully")
            return result
            
        except concurrent.futures.TimeoutError:
            logger.error("Synthesizer node timed out after 30 seconds")
            error_response = "The response generation timed out. Please try again."
            return {
                "messages": [AIMessage(content=error_response)],
                "internal_results": state.get("internal_results", []),
                "web_results": state.get("web_results", []),
                "final_response": error_response
            }
        except Exception as e:
            logger.error(f"Synthesizer node failed: {e}")
            error_response = f"I encountered an error while processing your request: {str(e)}"
            return {
                "messages": [AIMessage(content=error_response)],
                "internal_results": state.get("internal_results", []),
                "web_results": state.get("web_results", []),
                "final_response": error_response
            }
    
    return synthesizer_node