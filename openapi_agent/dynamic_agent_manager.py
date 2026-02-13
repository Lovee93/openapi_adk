import logging
import os
import uuid
import json
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

from google.adk.agents import LlmAgent
from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import OpenAPIToolset
from openapi_agent.spec_utils import parse_security_scheme

from google.adk.runners import InMemoryRunner

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure environment from env variables with defaults
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE") # Set to FALSE if you want to use Gemini API key instead
# os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY", "your-api-key") # Set to your Google API key if you want to use Gemini API key instead
os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")
os.environ["GOOGLE_CLOUD_LOCATION"] = os.getenv("GOOGLE_CLOUD_LOCATION", "your-location")

from google.genai import types

class DynamicAgentManager:
    def __init__(self):
        # In-memory storage for active agents: { session_id: LlmAgent }
        self.active_agents: Dict[str, LlmAgent] = {}
        # In-memory storage for runners: { session_id: InMemoryRunner }
        self.active_runners: Dict[str, InMemoryRunner] = {}
        # In-memory storage for specs: { session_id: spec_json_string }
        # In production, use Redis or a Database.
        self.specs: Dict[str, str] = {}
        # Store state deltas to pass back to runner on next call
        self.latest_state_delta: Dict[str, Dict[str, Any]] = {}
        # Store pending function responses (like auth codes)
        self.pending_responses: Dict[str, types.Part] = {}
        
    def save_spec(self, session_id: str, spec_content: str) -> bool:
        """
        Saves the uploaded spec for the session.
        Validates that it is parseable JSON.
        """
        try:
            # Basic validation
            json.loads(spec_content)
            self.specs[session_id] = spec_content
            return True
        except json.JSONDecodeError:
            return False

    def get_agent(self, session_id: str) -> Optional[LlmAgent]:
        """Returns the active agent for the session, or None."""
        return self.active_agents.get(session_id)

    def get_runner(self, session_id: str) -> Optional[InMemoryRunner]:
        """Returns the active runner for the session, or None."""
        return self.active_runners.get(session_id)

    async def create_agent(self, session_id: str, credentials: Dict[str, Any]) -> LlmAgent:
        """
        Initializes a new LlmAgent specific to the session's spec and credentials.
        Also initializes a Runner for this agent session.
        """
        spec_content = self.specs.get(session_id)
        if not spec_content:
            raise ValueError("No spec found for this session. Please upload first.")

        # 1. Parse Auth
        auth_scheme, auth_credential = parse_security_scheme(spec_content, user_credentials=credentials)

        # 2. Create Toolset
        # We assume the user wants to use the spec they just uploaded
        toolset = OpenAPIToolset(
            spec_str=spec_content,
            spec_str_type="json",
            auth_scheme=auth_scheme,
            auth_credential=auth_credential
        )

        # 3. Create Agent
        # We give it a unique name to avoid conflicts if logging systems index by name
        agent_name = f"sandbox_agent_{session_id[:8]}"
        
        agent = LlmAgent(
            model='gemini-2.5-pro',
            name=agent_name,
            instruction="""You are a helpful API Assistant.
            Your goal is to help the user interact with the provided API Specification.
            1. Explain what endpoints are available.
            2. Call tools on behalf of the user when requested.
            3. If a tool fails (e.g. 401 Auth), explain clearly what happened.
            4. Do not hallucinate endpoints not in the toolset.
            5. If the user wants to see sample code for any endpoint, provide it in the response be it any language or curl.
            """,
            tools=[toolset],
            # We can add the callbacks here if needed
        )
        
        self.active_agents[session_id] = agent
        
        # 4. Create Runner
        # Initialize a dedicated Runner for this session to maintain context
        runner = InMemoryRunner(agent=agent, app_name="openapi_adk")
        await runner.session_service.create_session(app_name="openapi_adk", user_id="sandbox_user", session_id=session_id)
        self.active_runners[session_id] = runner
        
        return agent

    def update_latest_delta(self, session_id: str, delta: Dict[str, Any]):
        """Updates the latest state delta for the session."""
        if session_id not in self.latest_state_delta:
            self.latest_state_delta[session_id] = {}
        self.latest_state_delta[session_id].update(delta)

    def get_latest_delta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns the accumulated state delta for the session."""
        return self.latest_state_delta.get(session_id)

    async def inject_auth_response(self, session_id: str, code: str, state_val: str):
        """
        Manually updates the session state AND prepares a function response.
        """
        runner = self.get_runner(session_id)
        if not runner:
            return

        delta = self.get_latest_delta(session_id) or {}
        pending_key = delta.get("_pending_auth_key")
        call_id = delta.get("_pending_auth_call_id")
        orig_config = delta.get("_pending_auth_config")
        
        if pending_key and call_id and orig_config:
            # 1. Direct State Injection (Backup)
            credential_data = {
                "auth_type": "oauth2",
                "oauth2": {
                    "authCode": code,
                    "state": state_val
                }
            }
            try:
                service = runner.session_service
                app_name = "openapi_adk"
                user_id = "sandbox_user"
                
                # Try getting the session object directly from the service storage
                if app_name in service.sessions and \
                   user_id in service.sessions[app_name] and \
                   session_id in service.sessions[app_name][user_id]:
                    
                    session_obj = service.sessions[app_name][user_id][session_id]
                    state_key = f"temp:{pending_key}"
                    session_obj.state[state_key] = credential_data
                    logger.info(f"Directly injected into session state: {state_key}")
                else:
                    logger.error(f"Failed to find session {session_id} for injection. Apps: {list(service.sessions.keys())}")
            except Exception as e:
                logger.error(f"State injection failed: {e}")


            # 2. Prepare functionResponse (Primary)
            # Mimic test_agent_auth.py: modify the config and send it back
            updated_config = copy.deepcopy(orig_config)
            if "exchangedAuthCredential" not in updated_config:
                updated_config["exchangedAuthCredential"] = {}
            if "oauth2" not in updated_config["exchangedAuthCredential"]:
                updated_config["exchangedAuthCredential"]["oauth2"] = {}
            
            # Inject the code and state
            updated_config["exchangedAuthCredential"]["oauth2"]["authCode"] = code
            updated_config["exchangedAuthCredential"]["oauth2"]["state"] = state_val

            
            # Create the function response part
            response_part = types.Part(
                function_response=types.FunctionResponse(
                    name="adk_request_credential",
                    id=call_id,
                    response=updated_config
                )
            )
            self.pending_responses[session_id] = response_part
            logger.info(f"Prepared functionResponse for call {call_id}")
            
            # Clear pending metadata
            del delta["_pending_auth_key"]
            del delta["_pending_auth_call_id"]
            del delta["_pending_auth_config"]
        else:
            logger.warning("Missing metadata for auth injection.")

    def consume_pending_response(self, session_id: str) -> Optional[types.Part]:
        """Returns and clears any pending response part for the session."""
        return self.pending_responses.pop(session_id, None)

import copy

# Global instance
manager = DynamicAgentManager()
