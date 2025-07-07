import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

async def test_async_operations():
    from .graph import AsyncGraphManager
    from .state import create_initial_state
    
    async with AsyncGraphManager() as graph:
        graph_manager = AsyncGraphManager()
        graph_manager.force_memory = True
        graph = await graph_manager.initialize()
        
        initial_state = create_initial_state("Test async question")
        config = {"configurable": {"thread_id": "test_async"}}
        
        try:
            result = await graph.ainvoke(initial_state, config=config)
            await graph_manager.close()
            return result
        except Exception as e:
            await graph_manager.close()
            raise e


def test_sync_operations():
    from .graph import GraphManager
    from .state import create_initial_state
    
    with GraphManager() as graph:
        graph_manager = GraphManager()
        graph_manager.force_memory = True
        graph = graph_manager.initialize()
        
        initial_state = create_initial_state("Test sync question")
        config = {"configurable": {"thread_id": "test_sync"}}
        
        try:
            result = graph.invoke(initial_state, config=config)
            graph_manager.close()
            return result
        except Exception as e:
            graph_manager.close()
            raise e


def test_universal_operations():
    from .graph import UniversalGraphManager
    from .state import create_initial_state
    
    with UniversalGraphManager() as graph:
        initial_state = create_initial_state("Test sync question")
        config = {"configurable": {"thread_id": "test_universal_sync"}}
        sync_result = graph.invoke(initial_state, config=config)
    
    return sync_result


async def test_universal_async_operations():
    from .graph import UniversalGraphManager
    from .state import create_initial_state
    
    async with UniversalGraphManager() as graph:
        initial_state = create_initial_state("Test async question")
        config = {"configurable": {"thread_id": "test_universal_async"}}
        async_result = await graph.ainvoke(initial_state, config=config)
    
    return async_result


from langchain_core.messages import HumanMessage
from .graph import UniversalGraphManager, GraphManager, AsyncGraphManager
from .state import SupportState, create_initial_state
from .config import settings

logger = logging.getLogger(__name__)


class SupportSystem:
    
    def __init__(self, use_memory=False, use_sqlite=None):
        if use_sqlite is not None:
            logger.warning("Parameter 'use_sqlite' is deprecated, use 'use_memory' instead")
            use_memory = use_sqlite
            
        self.graph_manager = None
        self.graph = None
        self.use_memory = use_memory
        self._initialize()
    
    def _initialize(self):
        try:
            self.graph_manager = UniversalGraphManager()
            print("SupportSystem initialized successfully")
        except Exception as e:
            print(f"Failed to initialize SupportSystem: {e}")
            raise
    
    def close(self):
        if self.graph_manager:
            self.graph_manager.close()
            self.graph_manager = None
            self.graph = None
    
    async def aclose(self):
        if self.graph_manager:
            await self.graph_manager.aclose()
            self.graph_manager = None
            self.graph = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()
    
    def ask_sync(self, question: str, thread_id: str = "default") -> str:
        if not self.graph_manager:
            raise Exception("SupportSystem not properly initialized")
        
        initial_state = create_initial_state(question)
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            with self.graph_manager as graph:
                final_state = graph.invoke(initial_state, config=config)
                return self._extract_response(final_state)
                
        except Exception as e:
            logger.error(f"Error in ask_sync: {e}")
            return f"An error occurred: {str(e)}"
    
    async def ask(self, question: str, thread_id: str = "default") -> str:
        if not self.graph_manager:
            raise Exception("SupportSystem not properly initialized")
        
        initial_state = create_initial_state(question)
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            async with self.graph_manager as graph:
                final_state = await graph.ainvoke(initial_state, config=config)
                return self._extract_response(final_state)
                
        except Exception as e:
            logger.error(f"Error in ask: {e}")
            return f"An error occurred: {str(e)}"
    
    def _extract_response(self, final_state):
        messages = final_state.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, 'content'):
                return last_message.content
        
        final_response = final_state.get("final_response")
        if final_response:
            return final_response
        
        return "I couldn't generate a response. Please try again."
    
    async def stream_ask(self, question: str, thread_id: str = "default"):
        if not self.graph_manager:
            raise Exception("SupportSystem not properly initialized")
        
        initial_state = create_initial_state(question)
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            async with self.graph_manager as graph:
                async for chunk in graph.astream(initial_state, config=config):
                    yield chunk
        except Exception as e:
            logger.error(f"Error in stream_ask: {e}")
            yield {"error": {"message": str(e)}}


class SupportSystemContextManager:
    
    def __init__(self, use_memory=False, use_sqlite=None):
        if use_sqlite is not None:
            logger.warning("Parameter 'use_sqlite' is deprecated, use 'use_memory' instead")
            use_memory = use_sqlite
            
        self.graph_manager = None
        self.use_memory = use_memory
    
    def __enter__(self):
        self.graph_manager = UniversalGraphManager()
        if self.use_memory:
            if hasattr(self.graph_manager, 'sync_manager'):
                self.graph_manager.sync_manager = GraphManager()
                self.graph_manager.sync_manager.force_memory = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.graph_manager:
            self.graph_manager.close()
    
    async def __aenter__(self):
        self.graph_manager = UniversalGraphManager()
        if self.use_memory:
            if hasattr(self.graph_manager, 'async_manager'):
                self.graph_manager.async_manager = AsyncGraphManager()
                self.graph_manager.async_manager.force_memory = True
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.graph_manager:
            await self.graph_manager.aclose()
    
    def ask_sync(self, question: str, thread_id: str = "default") -> str:
        initial_state = create_initial_state(question)
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            with self.graph_manager as graph:
                final_state = graph.invoke(initial_state, config=config)
                return self._extract_response(final_state)
        except Exception as e:
            logger.error(f"Error in ask_sync: {e}")
            return f"An error occurred: {str(e)}"
    
    async def ask(self, question: str, thread_id: str = "default") -> tuple:
        initial_state = create_initial_state(question)
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            async with self.graph_manager as graph:
                final_state = await graph.ainvoke(initial_state, config=config)
                answer = self._extract_response(final_state)
                
                internal_results = final_state.get("internal_results", [])
                web_results = final_state.get("web_results", [])
                
                logger.debug(f"Raw internal_results type: {type(internal_results)}")
                logger.debug(f"Raw web_results type: {type(web_results)}")
                
                sources = {
                    "internal": internal_results if isinstance(internal_results, list) else [],
                    "web": web_results if isinstance(web_results, list) else []
                }
                
                return answer, sources
        except Exception as e:
            logger.error(f"Error in ask: {e}")
            return f"An error occurred: {str(e)}", {}
    
    def _extract_response(self, final_state):
        messages = final_state.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, 'content'):
                return last_message.content
        
        final_response = final_state.get("final_response")
        if final_response:
            return final_response
        
        return "I couldn't generate a response. Please try again."


def ask_question_sync(question: str, thread_id: str = "default", use_memory: bool = False, use_sqlite: bool = None) -> str:
    if use_sqlite is not None:
        logger.warning("Parameter 'use_sqlite' is deprecated, use 'use_memory' instead")
        use_memory = use_sqlite
    
    with SupportSystemContextManager(use_memory=use_memory) as support:
        return support.ask_sync(question, thread_id)


async def ask_question(question: str, thread_id: str = "default", use_memory: bool = False, use_sqlite: bool = None) -> tuple:
    if use_sqlite is not None:
        logger.warning("Parameter 'use_sqlite' is deprecated, use 'use_memory' instead")
        use_memory = use_sqlite
    
    async with SupportSystemContextManager(use_memory=use_memory) as support:
        initial_state = create_initial_state(question)
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            async with support.graph_manager as graph:
                final_state = await graph.ainvoke(initial_state, config=config)
                answer = support._extract_response(final_state)
                
                internal_results = final_state.get("internal_results", [])
                web_results = final_state.get("web_results", [])
                
                logger.debug(f"Raw internal_results type: {type(internal_results)}")
                logger.debug(f"Raw web_results type: {type(web_results)}")
                
                sources = {
                    "internal": internal_results if isinstance(internal_results, list) else [],
                    "web": web_results if isinstance(web_results, list) else []
                }
                
                return answer, sources
                
        except Exception as e:
            logger.error(f"Error in ask_question: {e}")
            return f"An error occurred: {str(e)}", {}


def create_support_system(use_memory: bool = False, use_sqlite: bool = None) -> SupportSystem:
    if use_sqlite is not None:
        logger.warning("Parameter 'use_sqlite' is deprecated, use 'use_memory' instead")
        use_memory = use_sqlite
    
    return SupportSystem(use_memory=use_memory)


async def example_usage():
    print("Example 1: Long-lived SupportSystem (Sync)")
    
    support = SupportSystem()
    try:
        answer = support.ask_sync("How do I deploy FastAPI?", "example_thread")
        print(f"Sync Answer: {answer}")
    finally:
        support.close()
    
    print("\nExample 2: Long-lived SupportSystem (Async)")
    
    async with SupportSystem() as support:
        answer = await support.ask("How do I deploy FastAPI?", "example_thread")
        print(f"Async Answer: {answer}")
    
    print("\nExample 3: Context manager (Sync)")
    
    with SupportSystemContextManager() as support:
        answer = support.ask_sync("What is Docker?", "example_thread_2")
        print(f"Sync CM Answer: {answer}")
    
    print("\nExample 4: Context manager (Async)")
    
    async with SupportSystemContextManager() as support:
        answer = await support.ask("What is Docker?", "example_thread_2")
        print(f"Async CM Answer: {answer}")
    
    print("\nExample 5: Quick functions")
    
    sync_answer = ask_question_sync("How to use git?", "example_thread_3")
    print(f"Quick Sync Answer: {sync_answer}")
    
    async_answer = await ask_question("How to use git?", "example_thread_4")
    print(f"Quick Async Answer: {async_answer}")
    
    print("\nExample 6: Testing with in-memory")
    
    test_answer = ask_question_sync("Test question", "test_thread", use_memory=True)
    print(f"Test Answer: {test_answer}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())