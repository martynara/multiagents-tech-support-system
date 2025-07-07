from contextlib import contextmanager
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import InMemorySaver
import logging
import asyncio

from .state import SupportState
from .agents.coordinator import CoordinatorAgent
from .agents.search_internal import InternalSearchAgent, create_internal_search_node
from .agents.search_web import WebSearchAgent, create_web_search_node
from .agents.synthesizer import SynthesizerAgent, create_synthesizer_node
from .config import settings

logger = logging.getLogger(__name__)

_agent_cache = {
    'coordinator': None,
    'internal_search': None,
    'web_search': None, 
    'synthesizer': None,
    'internal_search_node': None,
    'web_search_node': None,
    'synthesizer_node': None
}

def _get_or_create_agents():
    global _agent_cache
    
    if _agent_cache['coordinator'] is None:
        _agent_cache['coordinator'] = CoordinatorAgent()
        logger.debug("Created new coordinator agent")
    
    if _agent_cache['internal_search'] is None:
        try:
            _agent_cache['internal_search'] = InternalSearchAgent()
            _agent_cache['internal_search_node'] = create_internal_search_node()
            logger.info("Internal search agent initialized successfully (cached)")
        except Exception as e:
            logger.warning(f"Failed to initialize internal search agent: {e}")
            def mock_internal_search_node(state):
                logger.warning("Using mock internal search (initialization failed)")
                return {"internal_results": []}
            _agent_cache['internal_search_node'] = mock_internal_search_node
    
    if _agent_cache['web_search'] is None:
        try:
            _agent_cache['web_search'] = WebSearchAgent()
            _agent_cache['web_search_node'] = create_web_search_node()
            logger.info("Web search agent initialized successfully (cached)")
        except Exception as e:
            logger.warning(f"Failed to initialize web search agent: {e}")
            def mock_web_search_node(state):
                logger.warning("Using mock web search (initialization failed)")
                return {"web_results": []}
            _agent_cache['web_search_node'] = mock_web_search_node
    
    if _agent_cache['synthesizer'] is None:
        _agent_cache['synthesizer'] = SynthesizerAgent()
        _agent_cache['synthesizer_node'] = create_synthesizer_node()
        logger.debug("Synthesizer agent initialized successfully (cached)")
    
    return _agent_cache

def create_workflow():
    agents = _get_or_create_agents()
    
    workflow = StateGraph(SupportState)
    
    workflow.add_node("coordinator", agents['coordinator'].update_state)
    workflow.add_node("search_internal", agents['internal_search_node'])
    workflow.add_node("search_web", agents['web_search_node'])
    workflow.add_node("synthesize", agents['synthesizer_node'])
    
    workflow.add_conditional_edges(
        START,
        agents['coordinator'].route_next,
        {
            "search_internal": "search_internal",
            "search_web": "search_web",
            "synthesize": "synthesize"
        }
    )
    
    workflow.add_edge("search_internal", "coordinator")
    workflow.add_edge("search_web", "coordinator")
    
    workflow.add_conditional_edges(
        "coordinator",
        agents['coordinator'].route_next,
        {
            "search_internal": "search_internal",
            "search_web": "search_web",
            "synthesize": "synthesize"
        }
    )
    
    workflow.add_edge("synthesize", END)
    
    return workflow

def clear_agent_cache():
    global _agent_cache
    _agent_cache = {
        'coordinator': None,
        'internal_search': None,
        'web_search': None, 
        'synthesizer': None,
        'internal_search_node': None,
        'web_search_node': None,
        'synthesizer_node': None
    }
    logger.info("Agent cache cleared")

def _test_postgres_connection(database_url: str, timeout: float = 2.0) -> bool:
    try:
        import psycopg2
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Connection timeout")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(timeout))
        
        try:
            conn = psycopg2.connect(database_url)
            conn.close()
            signal.alarm(0)
            return True
        except:
            signal.alarm(0)
            return False
            
    except ImportError:
        return False
    except Exception:
        return False


class GraphManager:
    def __init__(self):
        self.checkpointer_cm = None
        self.checkpointer = None
        self.graph = None
        self.force_memory = False
        self._setup_called = False
    
    def initialize(self):
        workflow = create_workflow()
        
        if self.force_memory:
            logger.info("Using in-memory checkpointer (forced)")
            self.checkpointer = InMemorySaver()
            self.graph = workflow.compile(checkpointer=self.checkpointer)
            return self.graph
        
        postgres_available = _test_postgres_connection(settings.database_url, timeout=1.0)
        
        if not postgres_available:
            logger.warning("PostgreSQL not available (fast check), using in-memory storage")
            self.checkpointer = InMemorySaver()
            self.graph = workflow.compile(checkpointer=self.checkpointer)
            return self.graph
        
        try:
            self.checkpointer_cm = PostgresSaver.from_conn_string(settings.database_url)
            self.checkpointer = self.checkpointer_cm.__enter__()
            
            if not self._setup_called:
                self.checkpointer.setup()
                self._setup_called = True
            
            self.graph = workflow.compile(checkpointer=self.checkpointer)
            logger.info("Graph initialized with PostgreSQL checkpointer")
        except Exception as e:
            logger.warning(f"Failed to initialize graph with PostgreSQL checkpointer: {e}")
            logger.info("Falling back to in-memory storage")
            self.checkpointer = InMemorySaver()
            self.graph = workflow.compile(checkpointer=self.checkpointer)
        
        return self.graph
    
    def close(self):
        if self.checkpointer_cm:
            try:
                self.checkpointer_cm.__exit__(None, None, None)
                logger.info("PostgreSQL checkpointer closed successfully")
            except Exception as e:
                logger.warning(f"Error closing checkpointer: {e}")
            finally:
                self.checkpointer_cm = None
                self.checkpointer = None
        
        self.graph = None
        self._setup_called = False
    
    def __enter__(self):
        return self.initialize()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncGraphManager:
    def __init__(self):
        self.checkpointer_cm = None
        self.checkpointer = None
        self.graph = None
        self._setup_called = False
        self.force_memory = False
    
    async def initialize(self):
        workflow = create_workflow()
        
        if self.force_memory:
            logger.info("Using in-memory checkpointer for async (forced)")
            self.checkpointer = InMemorySaver()
            self.graph = workflow.compile(checkpointer=self.checkpointer)
            return self.graph
        
        postgres_available = _test_postgres_connection(settings.database_url, timeout=1.0)
        
        if not postgres_available:
            logger.warning("PostgreSQL not available (fast check), using in-memory storage")
            self.checkpointer = InMemorySaver()
            self.graph = workflow.compile(checkpointer=self.checkpointer)
            return self.graph
        
        try:
            self.checkpointer_cm = AsyncPostgresSaver.from_conn_string(settings.database_url)
            
            try:
                self.checkpointer = await asyncio.wait_for(
                    self.checkpointer_cm.__aenter__(), 
                    timeout=3.0
                )
            except asyncio.TimeoutError:
                logger.warning("Async PostgreSQL connection timed out, falling back to in-memory")
                self.checkpointer = InMemorySaver()
                self.graph = workflow.compile(checkpointer=self.checkpointer)
                return self.graph
            
            if not self._setup_called:
                await asyncio.wait_for(self.checkpointer.setup(), timeout=3.0)
                self._setup_called = True
            
            self.graph = workflow.compile(checkpointer=self.checkpointer)
            logger.info("Async graph initialized with PostgreSQL checkpointer")
        except Exception as e:
            logger.warning(f"Failed to initialize async graph with PostgreSQL checkpointer: {e}")
            logger.info("Falling back to in-memory storage for async graph")
            self.checkpointer = InMemorySaver()
            self.graph = workflow.compile(checkpointer=self.checkpointer)
        
        return self.graph
    
    async def close(self):
        if self.checkpointer_cm:
            try:
                await asyncio.wait_for(
                    self.checkpointer_cm.__aexit__(None, None, None),
                    timeout=2.0
                )
                logger.info("Async PostgreSQL checkpointer closed successfully")
            except Exception as e:
                logger.warning(f"Error closing async checkpointer: {e}")
            finally:
                self.checkpointer_cm = None
                self.checkpointer = None
        
        self.graph = None
        self._setup_called = False
    
    async def __aenter__(self):
        return await self.initialize()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class UniversalGraphManager:
    def __init__(self):
        self.sync_manager = None
        self.async_manager = None
        self._current_graph = None
        self._is_async = False
    
    def get_sync_graph(self):
        if self.sync_manager is None:
            self.sync_manager = GraphManager()
        return self.sync_manager.initialize()
    
    async def get_async_graph(self):
        if self.async_manager is None:
            self.async_manager = AsyncGraphManager()
        return await self.async_manager.initialize()
    
    def close(self):
        if self.sync_manager:
            self.sync_manager.close()
            self.sync_manager = None
        
    async def aclose(self):
        if self.async_manager:
            await self.async_manager.close()
            self.async_manager = None
        self.close()
    
    def __enter__(self):
        self._current_graph = self.get_sync_graph()
        self._is_async = False
        return self._current_graph
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    async def __aenter__(self):
        self._current_graph = await self.get_async_graph()
        self._is_async = True
        return self._current_graph
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()