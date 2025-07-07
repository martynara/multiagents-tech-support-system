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
            return future.result(timeout=60)  # 60 second timeout
        except concurrent.futures.TimeoutError:
            return "⏰ Request timed out. Please try again with a shorter question."
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
        
        # Display sources if available
        if message["role"] == "assistant" and "sources" in message:
            # Count total sources
            internal_count = len(message["sources"].get("internal", []))
            web_count = len(message["sources"].get("web", []))
            total_sources = internal_count + web_count
            
            # Only show expander if there are sources
            if total_sources > 0:
                with st.expander(f"🔍 View Source Chunks ({total_sources})", expanded=False):
                    # Internal sources
                    if message["sources"].get("internal"):
                        st.subheader(f"📚 Internal Documentation Sources ({internal_count})")
                        for i, source in enumerate(message["sources"]["internal"]):
                            with st.container():
                                # Access document details from metadata
                                metadata = source.get("metadata", {})
                                source_name = "Unknown"
                                if "document_title" in metadata:
                                    source_name = metadata["document_title"]
                                elif "source" in metadata:
                                    source_name = metadata["source"]
                                elif "filename" in metadata:
                                    source_name = metadata["filename"]
                                
                                # Add page information if available
                                page_info = ""
                                if "page_number" in metadata:
                                    page_info = f" (Page {metadata['page_number']})"
                                
                                st.markdown(f"**Source {i+1}:** {source_name}{page_info}")
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
            status.write("🔍 Searching through documentation...")
            status.write("🧠 Analyzing relevant information...")
            status.write("📝 Generating response...")
            
            # Get response from support system safely
            response_data = run_async_safely(ask_question(prompt))
            
            # Extract answer and sources
            if isinstance(response_data, tuple) and len(response_data) == 2:
                answer, sources = response_data
            else:
                answer = response_data
                sources = {}
            
            # Debug info about sources
            internal_count = len(sources.get("internal", []))
            web_count = len(sources.get("web", []))
            if internal_count > 0 or web_count > 0:
                status.write(f"Found {internal_count} internal and {web_count} web sources")
            
            status.write("✅ Done!")
            status.update(label="Response ready!", state="complete")
        
        # Display the response
        st.markdown(answer)
        
        # Add source summary information directly after the response
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
                    source_name = metadata.get("document_title", metadata.get("source", metadata.get("filename", "Unknown")))
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
            
            st.markdown("*Expand the 'View Source Chunks' section above for detailed content*")
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
    
    # Statistics
    st.subheader("📊 Chat Statistics")
    total_messages = len(st.session_state.messages)
    user_messages = len([m for m in st.session_state.messages if m["role"] == "user"])
    assistant_messages = len([m for m in st.session_state.messages if m["role"] == "assistant"])
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total", total_messages)
        st.metric("User", user_messages)
    with col2:
        st.metric("Assistant", assistant_messages)
    
    st.divider()
    
    # Debug info - Source counts in latest message
    if st.session_state.messages and len(st.session_state.messages) > 1:
        last_message = st.session_state.messages[-1]
        if last_message["role"] == "assistant" and "sources" in last_message:
            internal_count = len(last_message["sources"].get("internal", []))
            web_count = len(last_message["sources"].get("web", []))
            if internal_count > 0 or web_count > 0:
                st.subheader("🔍 Source Information")
                sources_col1, sources_col2 = st.columns(2)
                with sources_col1:
                    st.metric("Internal Sources", internal_count)
                with sources_col2:
                    st.metric("Web Sources", web_count)
    
    st.divider()
    
    # About section
    st.subheader("ℹ️ About")
    st.markdown("""
    **Support Assistant v2.0**
    
    This intelligent assistant is powered by:
    - 🦜 **LangGraph** - Agent orchestration
    - 🔍 **Elasticsearch** - Document search
    - 🧠 **OpenAI** - Language processing
    - ⚡ **Streamlit** - User interface
    
    **Features:**
    - Natural language understanding
    - Documentation search
    - Context-aware responses
    - Chat history management
    """)
    
    # Tips section
    with st.expander("💡 Tips for Better Results"):
        st.markdown("""
        - **Be specific**: Include relevant details in your questions
        - **Use context**: Reference specific features or components
        - **Ask follow-ups**: Build on previous answers for deeper insights
        - **Try examples**: Ask for code examples or step-by-step guides
        """)
    
    # System status
    st.divider()
    st.subheader("🔧 System Status")
    
    # Simple health check
    try:
        if "ask_question" in globals():
            st.success("🟢 Assistant Online")
        else:
            st.error("🔴 Assistant Offline")
    except Exception:
        st.warning("🟡 Status Unknown")

# Footer with helpful information
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        💡 <strong>Pro Tip:</strong> Try asking about specific features, error messages, or implementation guides for the best results!
    </div>
    """, 
    unsafe_allow_html=True
)