from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import OpenAPIToolset
from google.adk.tools.openapi_tool.auth.auth_helpers import token_to_scheme_credential
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.base_tool import BaseTool
from typing import Optional
from typing import Dict, Any
from openapi_agent.pets_api import pets
from fastapi.openapi.models import OAuth2
from fastapi.openapi.models import OAuthFlowAuthorizationCode
from fastapi.openapi.models import OAuthFlows
from google.adk.auth import AuthCredential
from google.adk.auth import AuthCredentialTypes
from google.adk.auth import OAuth2Auth

openapi_spec_json = pets
auth_scheme, auth_credential = token_to_scheme_credential(
    "apikey", "header", "api_key", "special-key"
)
# auth_scheme = OAuth2(
#     flows=OAuthFlows(
#         authorizationCode=OAuthFlowAuthorizationCode(
#             authorizationUrl="https://petstore3.swagger.io/oauth/authorize",
#             tokenUrl="https://petstore3.swagger.io/oauth/token",
#             scopes={
#                 "write:pets": "modify pets in your account",
#                 "read:pets": "read your pets"
#             },
#         )
#     )
# )
# auth_credential = AuthCredential(
#     auth_type=AuthCredentialTypes.OAUTH2,
#     oauth2=OAuth2Auth(
#         client_id="client", 
#         client_secret="secret"
#     ),
# )
# auth_scheme, auth_credential = token_to_scheme_credential(
#     "oauth2Token", "header", "api", "some token"
# )

toolset = OpenAPIToolset(
    spec_str=openapi_spec_json, 
    spec_str_type="json",
    auth_scheme=auth_scheme,
    auth_credential=auth_credential,
)

def post_tool_callback(
    tool: BaseTool, 
    args: Dict[str, Any], 
    tool_context: ToolContext, 
    tool_response: Dict
) -> Optional[Dict]:
    print(f"Tool called: {tool.name}")
    print(f"Tool response: {tool_response}")
    return None

root_agent = LlmAgent(
    model='gemini-2.5-pro',
    name='open_api_agent',
    instruction="""You are a Pet Store assistant managing pets via an API.
    Tell the user that you can tell them more about how to use the APIs and also call them for you.
    Use the available tools to fulfill user requests.
    For any tools that need user input, always tell the user about both required and non-required fields.
    Only ask the user for required fields, and fake rest of the details needed so that tools do not fail. 
    Help user in understanding what all API endpoints exist, what all can a user do and what endpoints are public and what endpoints are secure.
    You can determine if the endpoint needs authentication (and it's type) from the API specs.
    DO NOT HALLUCINATE on the authentication type, check the specs and security scheme attached to the endpoints.
    Also help generating code examples for the user if they would like to integrate these APIs.
    The code examples should be in the language that user prefers such as Python, Javascript, etc.
    Also, help the user with sample data so that they can create their own requests.
    Share the exact response from the API/tools if the user asks so that helps the user to understand the endpoints.
    """,
    description="Manages a Pet Store using tools generated from an OpenAPI spec.", 
    tools=[
        toolset,
        # google_search
    ],
    after_tool_callback = post_tool_callback
)
