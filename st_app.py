import streamlit as st
import asyncio
import concurrent.futures
import platform
from src.support_system.main import ask_question

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

st.set_page_config(
    page_title="Support Assistant", 
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🤖 Support Assistant")
st.markdown("Ask questions about technical documentation and get intelligent answers.")

def run_async_safely(coro):
    """Safely run async coroutine in Streamlit without blocking the main thread."""
    def run_in_thread():
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        try:
            return future.result(timeout=30)  # Reduced to 30 second timeout
        except concurrent.futures.TimeoutError:
            return "⏰ Request timed out after 30 seconds. This might be due to:\n- Slow web search\n- Network issues\n- Internal search problems\n\nTry a simpler question first."
        except Exception as e:
            return f"❌ An error occurred: {str(e)}"

# Initialize chat history with welcome message
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant", 
            "content": "👋 Hello! I'm your support assistant. I can help answer questions about your technical documentation. What would you like to know?"
        }
    ]

# Display chat messages from history
for message in st.session_state.messages:
    avatar = "🤖" if message["role"] == "assistant" else "👤"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        
        # Display sources section (always show for assistant messages)
        if message["role"] == "assistant":
            # Check if sources exist, if not create empty structure
            if "sources" not in message:
                message["sources"] = {"internal": [], "web": []}
            
            # Count total sources
            internal_count = len(message["sources"].get("internal", []))
            web_count = len(message["sources"].get("web", []))
            total_sources = internal_count + web_count
            
            # Always show expander, with different labels based on content
            expander_label = f"🔍 View Source Chunks ({total_sources})" if total_sources > 0 else "🔍 View Source Chunks (No sources found)"
            
            with st.expander(expander_label, expanded=False):
                if total_sources > 0:
                    # Internal sources
                    if message["sources"].get("internal"):
                        st.subheader(f"📚 Internal Documentation Sources ({internal_count})")
                        for i, source in enumerate(message["sources"]["internal"]):
                            with st.container():
                                # Access document details from metadata
                                metadata = source.get("metadata", {})
                                
                                # Get source title using field hierarchy
                                source_name = metadata.get("filename", "")
                                if not source_name:
                                    source_name = metadata.get("document_title", "Unknown Document")
                                    if source_name == "Untitled Document":
                                        source_name = metadata.get("source", "Unknown Document")
                                
                                # Add page information if available
                                page_info = ""
                                if metadata.get("page_number"):
                                    page_info = f" (Page {metadata['page_number']})"
                                
                                # Add file info if available
                                file_info = ""
                                if metadata.get("filename"):
                                    file_info = f" - File: {metadata['filename']}"
                                
                                # Include chunk ID info for debug purposes if needed
                                chunk_info = ""
                                if st.session_state.get("debug_mode", False) and metadata.get("chunk_id"):
                                    chunk_info = f" [Chunk: {metadata['chunk_id']}]"
                                
                                st.markdown(f"**Source {i+1}:** {source_name}{page_info}{file_info}{chunk_info}")
                                st.markdown(f"```\n{source.get('content', 'No content available')[:300]}...\n```")
                                st.markdown("---")
                    
                    # Web sources
                    if message["sources"].get("web"):
                        st.subheader(f"🌐 Web Sources ({web_count})")
                        for i, source in enumerate(message["sources"]["web"]):
                            with st.container():
                                metadata = source.get("metadata", {})
                                title = metadata.get("title", "Unknown Title")
                                url = metadata.get("url", "#")
                                
                                # Display source with clickable URL
                                st.markdown(f"**Source {i+1}:** [{title}]({url})")
                                
                                # Display content snippet
                                content = source.get("content", "No content available")
                                if content:
                                    st.markdown(f"```\n{content[:300]}...\n```")
                                else:
                                    st.markdown("*No preview available*")
                                
                                st.markdown("---")
                else:
                    # Show message when no sources were found
                    st.info("🔍 **No source chunks were retrieved for this response.**")
                    st.markdown("This could mean:")
                    st.markdown("- The question was answered from general knowledge")
                    st.markdown("- No relevant documentation was found")
                    st.markdown("- The search didn't return matching results")
                    st.markdown("- There was an issue with the search process")

# Chat input
if prompt := st.chat_input("Ask me anything about the documentation..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
    
    # Generate and display assistant response
    with st.chat_message("assistant", avatar="🤖"):
        # Show different loading messages for better UX
        with st.status("Processing your question...", expanded=True) as status:
            
            # Get response from support system safely
            response_data = run_async_safely(ask_question(prompt))
            
            # Extract answer and sources
            if isinstance(response_data, tuple) and len(response_data) == 2:
                answer, sources = response_data
                # Ensure sources has the right structure
                if not isinstance(sources, dict):
                    sources = {}
                # Make sure internal and web keys exist
                if "internal" not in sources:
                    sources["internal"] = []
                if "web" not in sources:
                    sources["web"] = []
            else:
                answer = response_data
                sources = {"internal": [], "web": []}
            
            # Debug info about sources
            internal_count = len(sources.get("internal", []))
            web_count = len(sources.get("web", []))
            if internal_count > 0 or web_count > 0:
                status.write(f"Found {internal_count} internal and {web_count} web sources")
            
            status.write("✅ Done!")
            status.update(label="Response ready!", state="complete")
        
        # Display the response
        st.markdown(answer)
        
        # Display the View Source Chunks expander for the current response
        internal_count = len(sources.get("internal", []))
        web_count = len(sources.get("web", []))
        total_sources = internal_count + web_count
        
        # Always show expander for current response
        expander_label = f"🔍 View Source Chunks ({total_sources})" if total_sources > 0 else "🔍 View Source Chunks (No sources found)"
        
        with st.expander(expander_label, expanded=False):
            if total_sources > 0:
                # Internal sources
                if sources.get("internal"):
                    st.subheader(f"📚 Internal Documentation Sources ({internal_count})")
                    for i, source in enumerate(sources["internal"]):
                        with st.container():
                            # Access document details from metadata
                            metadata = source.get("metadata", {})
                            
                            # Get source title using field hierarchy
                            source_name = metadata.get("filename", "")
                            if not source_name:
                                source_name = metadata.get("document_title", "Unknown Document")
                                if source_name == "Untitled Document":
                                    source_name = metadata.get("source", "Unknown Document")
                            
                            # Add page information if available
                            page_info = ""
                            if metadata.get("page_number"):
                                page_info = f" (Page {metadata['page_number']})"
                            
                            # Add file info if available
                            file_info = ""
                            if metadata.get("filename"):
                                file_info = f" - File: {metadata['filename']}"
                            
                            # Include chunk ID info for debug purposes if needed
                            chunk_info = ""
                            if st.session_state.get("debug_mode", False) and metadata.get("chunk_id"):
                                chunk_info = f" [Chunk: {metadata['chunk_id']}]"
                            
                            st.markdown(f"**Source {i+1}:** {source_name}{page_info}{file_info}{chunk_info}")
                            st.markdown(f"```\n{source.get('content', 'No content available')[:300]}...\n```")
                            st.markdown("---")
                
                # Web sources
                if sources.get("web"):
                    st.subheader(f"🌐 Web Sources ({web_count})")
                    for i, source in enumerate(sources["web"]):
                        with st.container():
                            metadata = source.get("metadata", {})
                            title = metadata.get("title", "Unknown Title")
                            url = metadata.get("url", "#")
                            
                            # Display source with clickable URL
                            st.markdown(f"**Source {i+1}:** [{title}]({url})")
                            
                            # Display content snippet
                            content = source.get("content", "No content available")
                            if content:
                                st.markdown(f"```\n{content[:300]}...\n```")
                            else:
                                st.markdown("*No preview available*")
                            
                            st.markdown("---")
            else:
                # Show message when no sources were found
                st.info("🔍 **No source chunks were retrieved for this response.**")
                st.markdown("This could mean:")
                st.markdown("- The question was answered from general knowledge")
                st.markdown("- No relevant documentation was found")
                st.markdown("- The search didn't return matching results")
                st.markdown("- There was an issue with the search process")
        
        # Display source summary information directly after the response
        if sources:
            internal_count = len(sources.get("internal", []))
            web_count = len(sources.get("web", []))
            
            # Create a clear source summary section
            st.markdown("---")
            st.markdown("### 🔍 Source Information")
            
            # Display internal source summary
            if internal_count > 0:
                st.markdown(f"**📚 Internal Documents:** {internal_count} chunks used")
                # List top sources
                internal_sources = []
                for source in sources.get("internal", [])[:3]:  # Show top 3
                    metadata = source.get("metadata", {})
                    # Prioritize filename over document_title
                    source_name = metadata.get("filename", "")
                    if not source_name or source_name.endswith('.json'):
                        # If filename is empty or ends with .json, try document_title
                        source_name = metadata.get("document_title", "")
                        # Clean up "Untitled Document"
                        if not source_name or source_name == "Untitled Document":
                            source_name = metadata.get("source", "Unknown")
                    # Add page number if available
                    if metadata.get("page_number"):
                        source_name += f" (Page {metadata['page_number']})"
                    internal_sources.append(source_name)
                
                if internal_sources:
                    st.markdown("**Top internal sources:** " + ", ".join(internal_sources))
            
            # Display web source summary
            if web_count > 0:
                st.markdown(f"**🌐 Web Search Results:** {web_count} resources found")
                # Show searched query and top results
                web_sources = []
                for source in sources.get("web", [])[:3]:  # Show top 3
                    metadata = source.get("metadata", {})
                    title = metadata.get("title", "Unknown Title")
                    url = metadata.get("url", "#")
                    web_sources.append(f"[{title}]({url})")
                
                if web_sources:
                    st.markdown("**Top web sources:** " + ", ".join(web_sources))
                    
                    # Show the actual search query that was used if available
                    metadata = sources.get("metadata", {})
                    search_query = metadata.get("web_search_query", None)
                    if search_query:
                        st.markdown(f"**Search query:** {search_query}")
                    else:
                        # Fall back to old behavior if metadata not available
                        st.markdown("**Search query:** " + prompt)
            
            st.markdown("*Detailed chunk content is available in the 'View Source Chunks' section above*")
            st.markdown("---")
    
    # Add assistant response to chat history with sources
    st.session_state.messages.append({
        "role": "assistant", 
        "content": answer,
        "sources": sources
    })

# Sidebar with enhanced features
with st.sidebar:
    st.header("🛠️ Assistant Controls")
    
    # Clear conversation button
    if st.button("🗑️ Clear Conversation", type="secondary", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant", 
                "content": "👋 Hello! I'm your support assistant. I can help answer questions about your technical documentation. What would you like to know?"
            }
        ]
        st.rerun()
    
    # Export conversation
    if st.button("📄 Export Chat", type="secondary", use_container_width=True):
        chat_text = "\n\n".join([
            f"**{msg['role'].title()}:** {msg['content']}"
            for msg in st.session_state.messages
        ])
        st.download_button(
            label="💾 Download as Text",
            data=chat_text,
            file_name=f"support_chat_{len(st.session_state.messages)}_messages.txt",
            mime="text/plain",
            use_container_width=True
        )
    
    st.divider()
    
    # Debug mode settings
    st.sidebar.subheader("⚙️ Debug Settings")
    
    # Initialize debug_mode in session state if not present
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = False
    
    # Debug mode toggle
    if st.sidebar.checkbox("Enable Debug Mode", value=st.session_state.debug_mode):
        st.session_state.debug_mode = True
        
        # Display debug information
        st.sidebar.markdown("### Debug Information")
        st.sidebar.info("Debug mode enabled. Additional information will be shown.")
        
        # Add debug controls
        if st.sidebar.button("Test ElasticSearch Connection"):
            with st.sidebar:
                with st.status("Testing ElasticSearch..."):
                    try:
                        from src.support_system.agents.search_internal import InternalSearchAgent
                        from src.support_system.config import settings
                        
                        search_agent = InternalSearchAgent()
                        if search_agent.es_available:
                            st.success("✅ ElasticSearch connection successful")
                            
                            # Safely get connection info
                            try:
                                # Try to get URL from settings first (more reliable)
                                es_url = settings.elasticsearch_url
                                es_index = settings.elasticsearch_index
                                st.write(f"📍 **URL:** {es_url}")
                                st.write(f"📂 **Index:** {es_index}")
                                
                                # Try to get some basic cluster info
                                if hasattr(search_agent, 'es_client') and search_agent.es_client:
                                    cluster_info = search_agent.es_client.info()
                                    st.write(f"🔧 **ES Version:** {cluster_info.get('version', {}).get('number', 'Unknown')}")
                                    st.write(f"📊 **Cluster:** {cluster_info.get('cluster_name', 'Unknown')}")
                                
                            except Exception as detail_error:
                                st.warning(f"⚠️ Connection works but can't get details: {detail_error}")
                                st.write("📍 **URL:** From config settings")
                                st.write(f"📂 **Index:** {getattr(search_agent.vectorstore, 'index_name', 'Unknown')}")
                        else:
                            st.error("❌ ElasticSearch connection failed")
                            st.write("Check your .env file configuration:")
                            st.code("""
ELASTICSEARCH_URL=your_elasticsearch_url
ELASTICSEARCH_API_KEY=your_api_key  
ELASTICSEARCH_INDEX_NAME=your_index_name
                            """)
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                        st.write("Make sure your Elasticsearch configuration is correct in .env file")
    else:
        st.session_state.debug_mode = False
    
