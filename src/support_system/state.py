from typing import List, Dict, Any, Optional, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

class SupportState(TypedDict):
    query: str
    messages: List[BaseMessage]
    search_results: List[Dict[str, Any]]
    internal_results: List[Dict[str, Any]]
    web_results: List[Dict[str, Any]]
    final_response: Optional[str]
    iteration: int
    next_action: Optional[str]
    metadata: Dict[str, Any]

def create_initial_state(query: str, messages: List[BaseMessage] = None) -> SupportState:
    if messages is None:
        messages = [HumanMessage(content=query)]
    
    return SupportState(
        query=query,
        messages=messages,
        search_results=[],
        internal_results=[],
        web_results=[],
        final_response=None,
        iteration=0,
        next_action=None,
        metadata={
            "start_time": None,
            "sources_found": 0,
            "search_queries": []
        }
    )

def add_message(state: SupportState, message: BaseMessage) -> SupportState:
    return {
        **state,
        "messages": state["messages"] + [message]
    }

def add_internal_results(state: SupportState, results: List[Dict[str, Any]]) -> SupportState:
    return {
        **state,
        "internal_results": state["internal_results"] + results,
        "metadata": {
            **state["metadata"],
            "sources_found": state["metadata"]["sources_found"] + len(results)
        }
    }

def add_web_results(state: SupportState, results: List[Dict[str, Any]], metadata: Dict[str, Any] = None) -> SupportState:
    updated_metadata = state.get("metadata", {}).copy()
    
    updated_metadata["sources_found"] = updated_metadata.get("sources_found", 0) + len(results)
    
    if metadata:
        updated_metadata.update(metadata)
    
    return {
        **state,
        "web_results": state["web_results"] + results,
        "metadata": updated_metadata
    }

def add_search_results(state: SupportState, results: List[Dict[str, Any]], source_type: str) -> SupportState:
    updated_state = state.copy()
    if "search_results" not in updated_state:
        updated_state["search_results"] = []
    
    if source_type == "internal":
        updated_state = add_internal_results(updated_state, results)
        updated_state["search_results"] = updated_state["search_results"] + results
    elif source_type == "web":
        updated_state = add_web_results(updated_state, results)
        updated_state["search_results"] = updated_state["search_results"] + results
    
    return updated_state

def set_final_response(state: SupportState, response: str) -> SupportState:
    return {
        **state,
        "final_response": response,
        "messages": state["messages"] + [AIMessage(content=response)]
    }

def increment_iteration(state: SupportState) -> SupportState:
    return {
        **state,
        "iteration": state["iteration"] + 1
    }

def set_next_action(state: SupportState, action: str) -> SupportState:
    return {
        **state,
        "next_action": action
    }