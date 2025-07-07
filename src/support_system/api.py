from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .main import SupportSystem

class QuestionRequest(BaseModel):
    question: str
    thread_id: str = "default"

class QuestionResponse(BaseModel):
    answer: str
    thread_id: str
    sources: Optional[List[Dict[str, str]]] = None

class StreamUpdate(BaseModel):
    node: str
    details: Dict[str, Any]

support_system = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global support_system
    
    print("Starting Multi-Agent Support System API...")
    try:
        support_system = SupportSystem()
        print("Support system initialized successfully")
        
        app.state.support_system = support_system
        
    except Exception as e:
        print(f"Failed to initialize support system: {e}")
        raise
    
    yield
    
    print("Shutting down Multi-Agent Support System API...")
    if support_system:
        support_system.close()
        print("Support system closed successfully")

app = FastAPI(
    title="Technical Support API",
    description="Multi-Agent Technical Support System API",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections: Dict[str, WebSocket] = {}

def extract_sources_from_response(response_text: str) -> tuple[str, List[Dict[str, str]]]:
    sources = []
    answer = response_text
    
    if "**Sources:**" in response_text:
        main_content, sources_text = response_text.split("**Sources:**")
        sources_list = sources_text.strip().split(", ")
        
        for source in sources_list:
            parts = source.split(": ", 1)
            if len(parts) == 2:
                source_type, source_name = parts
                sources.append({"type": source_type, "name": source_name})
        
        answer = main_content.strip()
    
    return answer, sources

@app.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest) -> QuestionResponse:
    try:
        if not support_system:
            raise HTTPException(status_code=503, detail="Support system not initialized")
        
        answer = await support_system.ask(request.question, request.thread_id)
        
        clean_answer, sources = extract_sources_from_response(answer)
        
        return QuestionResponse(
            answer=clean_answer,
            thread_id=request.thread_id,
            sources=sources
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    await websocket.accept()
    active_connections[thread_id] = websocket
    
    try:
        while True:
            data = await websocket.receive_json()
            question = data.get("question")
            
            if not question:
                await websocket.send_json({"error": "No question provided"})
                continue
            
            try:
                if not support_system:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Support system not initialized"
                    })
                    continue
                
                await websocket.send_json({
                    "type": "status",
                    "message": "Processing your question..."
                })
                
                async for chunk in support_system.stream_ask(question, thread_id):
                    if "error" in chunk:
                        await websocket.send_json({
                            "type": "error",
                            "message": chunk["error"]["message"]
                        })
                        break
                    
                    for node_name, data in chunk.items():
                        update = {
                            "type": "update",
                            "node": node_name,
                            "data": {}
                        }
                        
                        if node_name == "coordinator":
                            update["data"]["message"] = "Planning next action"
                            if hasattr(data, 'messages') and data.messages:
                                update["data"]["current_step"] = len(data.messages)
                            
                        elif node_name == "search_internal":
                            if hasattr(data, 'search_results'):
                                internal_results = [r for r in data.search_results if r.get('source') == 'internal']
                                update["data"]["found"] = len(internal_results)
                                if internal_results:
                                    update["data"]["sources"] = [
                                        r.get("metadata", {}).get("category", "Documentation")
                                        for r in internal_results[:3]
                                    ]
                            
                        elif node_name == "search_web":
                            if hasattr(data, 'search_results'):
                                web_results = [r for r in data.search_results if r.get('source') == 'web']
                                update["data"]["found"] = len(web_results)
                                if web_results:
                                    update["data"]["sources"] = [
                                        r.get("metadata", {}).get("title", "Web Result")
                                        for r in web_results[:2]
                                    ]
                            
                        elif node_name == "synthesize":
                            if hasattr(data, 'final_response') and data.final_response:
                                answer, sources = extract_sources_from_response(data.final_response)
                                
                                update["type"] = "final"
                                update["data"]["answer"] = answer
                                update["data"]["sources"] = sources
                        
                        await websocket.send_json(update)
                
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error processing question: {str(e)}"
                })
    
    except WebSocketDisconnect:
        if thread_id in active_connections:
            del active_connections[thread_id]

@app.get("/")
async def root():
    return {
        "message": "Multi-Agent Technical Support System API",
        "version": "0.1.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    try:
        if support_system and support_system.graph:
            return {
                "status": "healthy",
                "support_system": "active",
                "database": "connected"
            }
        else:
            return {
                "status": "starting",
                "support_system": "initializing"
            }
    except Exception as e:
        return {
            "status": "unhealthy", 
            "error": str(e)
        }

@app.get("/conversations/{thread_id}")
async def get_conversation_history(thread_id: str):
    try:
        if not support_system or not support_system.graph_manager or not support_system.graph_manager.checkpointer:
            raise HTTPException(status_code=503, detail="Support system not initialized")
        
        config = {"configurable": {"thread_id": thread_id}}
        
        checkpoints = list(support_system.graph_manager.checkpointer.list(config))
        
        return {
            "thread_id": thread_id,
            "checkpoints": len(checkpoints),
            "history": checkpoints[-10:]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation: {str(e)}")

def start_api():
    import uvicorn
    uvicorn.run("support_system.api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    start_api()