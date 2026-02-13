
import logging
import uuid
from typing import Dict, Any, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import our Dynamic Manager
from openapi_agent.dynamic_agent_manager import manager
from openapi_agent.spec_utils import get_auth_requirements



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---
class InitRequest(BaseModel):
    session_id: str
    credentials: Dict[str, Any]

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    auth_url: Any = None
    
class AnalyzeRequest(BaseModel):
    spec_content: str
    
# --- Endpoints ---

@app.post("/api/analyze")
async def analyze_spec(request: AnalyzeRequest):
    """
    Analyzes the raw spec string and returns auth requirements.
    This replaces the mock api.analyzeSpec call.
    """
    try:
        reqs = get_auth_requirements(request.spec_content)
        # Create a temp session ID just to associate this upload
        session_id = str(uuid.uuid4())
        manager.save_spec(session_id, request.spec_content)
        return {"session_id": session_id, "requirements": reqs}
    except Exception as e:
        logger.error(f"Error analyzing spec: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/init_agent")
async def init_agent_endpoint(request: InitRequest):
    """
    Initializes the agent for the given session with credentials.
    """
    try:
        agent = await manager.create_agent(request.session_id, request.credentials)
        if not agent:
             raise HTTPException(status_code=500, detail="Failed to create agent")
        return {"status": "success", "agent_name": agent.name}
    except Exception as e:
        logger.error(f"Error initializing agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Sends a message to the agent and returns a response.
    Uses the ADK Runner to execute the turn.
    """
    agent = manager.get_agent(request.session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found. Init first.")

    try:
        # Create a ephemeral runner just for this execution context?
        # Or reuse? The Runner usually manages conversation history/session.
        # But here we are building a custom session manager.
        # LlmAgent usually needs a 'Session' object passed to it or managed by runner.
        
        # Simplified execution for MVP:
        # We assume stateless execution or that agent handles history internally if passed the right runner context.
        # ADK's 'Runner' typically runs a loop. We might need 'runner.run_step' logic.
        
        # NOTE: Looking at ADK internals, Runner.run_async usually takes a 'new_message'.
        # We need to construct the ADK message structure.
        
        from google.genai.types import Content, Part
        
        # Check for pending function responses (e.g. from OAuth callback)
        pending_part = manager.consume_pending_response(request.session_id)
        
        parts = []
        if pending_part:
            parts.append(pending_part)
            logger.info(f"Appending pending auth response to message for session {request.session_id}")
            
        parts.append(Part(text=request.message))
        adk_message = Content(role="user", parts=parts)
        
        # Retrieve existing runner for this session to maintain history
        runner = manager.get_runner(request.session_id)
        if not runner:
             raise HTTPException(status_code=404, detail="Runner session lost. Please re-init.")
        
        # Use accumulated state delta from previous turns / callbacks
        state_delta = manager.get_latest_delta(request.session_id)
        
        text_response = ""
        auth_url = None
        try:
            async for event in runner.run_async(
                new_message=adk_message,
                session_id=request.session_id,
                user_id="sandbox_user",
                state_delta=state_delta
            ):
                # Capture state delta from agent for persistence
                if event.actions and event.actions.state_delta:
                    manager.update_latest_delta(request.session_id, event.actions.state_delta)
                print("state_delta", state_delta)
                # Check for requested authentication (OAuth2 flow)
                if event.actions and event.actions.requested_auth_configs:
                    for call_id, config in event.actions.requested_auth_configs.items():
                        if config.exchanged_auth_credential and config.exchanged_auth_credential.oauth2:
                            if config.exchanged_auth_credential.oauth2.auth_uri:
                                auth_url = config.exchanged_auth_credential.oauth2.auth_uri
                                logger.info(f"Detected Auth URI request: {auth_url}")
                                
                                # Store metadata needed to identify the request
                                manager.update_latest_delta(request.session_id, {
                                    "_pending_auth_key": config.credential_key,
                                    "_orig_tool_call_id": call_id,
                                    "_pending_auth_config": config.model_dump(exclude_none=True, by_alias=True)
                                })
                # print("inspecting event", event)
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_call:
                            logger.info(f"Function call: {part.function_call.name} (ID: {part.function_call.id})")
                            if part.function_call.name == "adk_request_credential":
                                # This is the internal ADK call we MUST respond to
                                auth_call_id = part.function_call.id
                                # Optionally verify it matches our pending tool call
                                args = part.function_call.args or {}
                                orig_id = args.get("functionCallId")
                                logger.info(f"Captured adk_request_credential ID: {auth_call_id} for original call: {orig_id}")
                                manager.update_latest_delta(request.session_id, {"_pending_auth_call_id": auth_call_id})
                        if part.function_response:
                            logger.info(f"Function response: {part.function_response.name}")
                        if part.text:
                            text_response += part.text
        except Exception as run_error:
            # Check for specific authentication errors or agent errors
             logger.error(f"Runner execution error: {run_error}")
             raise run_error
             
        # Extract text response - handled in loop
                    
        return {"response": text_response, "auth_url": auth_url}

    except Exception as e:
        logger.error(f"Error during chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth_callback")
async def auth_callback(session_id: str, code: str, state: str = None):
    """
    Endpoint for the callback page to hit (optional) or just use for logic reference.
    Actually the manager method is enough if hit by our own logic.
    """
    await manager.inject_auth_response(session_id, code, state)
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
