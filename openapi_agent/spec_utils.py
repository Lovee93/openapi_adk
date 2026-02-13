
import json
import logging
from typing import Tuple, Optional, Any
from fastapi.openapi.models import (
    OAuth2, OAuthFlows, OAuthFlowAuthorizationCode, 
    OAuthFlowImplicit, OAuthFlowClientCredentials, OAuthFlowPassword,
    APIKey, HTTPBase, HTTPBearer
)
from google.adk.tools.openapi_tool.auth.auth_helpers import token_to_scheme_credential
from google.adk.auth import AuthCredential, AuthCredentialTypes, OAuth2Auth

logger = logging.getLogger(__name__)

def get_auth_requirements(spec_str: str) -> dict:
    try:
        spec = json.loads(spec_str)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    components = spec.get("components", {})
    security_schemes = components.get("securitySchemes", {})

    if not security_schemes:
        return {"type": "none", "description": "No authentication required."}

    scheme_name, scheme_def = next(iter(security_schemes.items()))
    scheme_type = scheme_def.get("type")

    requirements = {
        "scheme_name": scheme_name,
        "type": scheme_type,
        "fields": []
    }

    if scheme_type == "oauth2":
      flows = scheme_def.get("flows", {})
      # Normalized check for flow data
      imp = flows.get("implicit")
      ac = flows.get("authorizationCode")
      
      if imp:
        requirements["description"] = "OAuth2 Implicit Authentication"
        requirements["fields"] = [
            {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
            {"name": "redirect_uri", "label": "Redirect URI (Full URL, e.g. http://localhost:5173/callback.html)", "type": "text", "required": True}
        ]
      elif ac:
        requirements["description"] = "OAuth2 Authorization Code Authentication"
        requirements["fields"] = [
            {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
            {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True},
            {"name": "redirect_uri", "label": "Redirect URI (Full URL, e.g. http://localhost:5173/callback.html)", "type": "text", "required": True}
        ]
      else:
        requirements["description"] = "OAuth2 Authentication"
        requirements["fields"] = [
            {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
            {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True},
            {"name": "redirect_uri", "label": "Redirect URI (Full URL)", "type": "text", "required": True}
        ]
        
    elif scheme_type == "apiKey":
        key_name = scheme_def.get("name", "api_key")
        key_in = scheme_def.get("in", "header")
        requirements["description"] = f"API Key ({key_in}: {key_name})"
        requirements["fields"] = [
            {"name": "api_key", "label": f"Value for {key_name}", "type": "password", "required": True}
        ]
    else:
        requirements["description"] = f"Unsupported Scheme: {scheme_type}"
    
    return requirements

def parse_security_scheme(spec_str: str, user_credentials: Optional[dict] = None) -> Tuple[Optional[Any], Optional[AuthCredential]]:
    try:
        spec = json.loads(spec_str)
    except json.JSONDecodeError:
        return None, None

    components = spec.get("components", {})
    security_schemes = components.get("securitySchemes", {})
    if not security_schemes: return None, None

    scheme_name, scheme_def = next(iter(security_schemes.items()))
    scheme_type = scheme_def.get("type")
    credentials = user_credentials or {}

    if scheme_type == "oauth2":
        return _parse_oauth2(scheme_def, credentials)
    elif scheme_type == "apiKey":
        return _parse_api_key(scheme_def, credentials)
    
    return None, None

def _parse_oauth2(scheme_def: dict, credentials: dict) -> Tuple[OAuth2, AuthCredential]:
    flows_def = scheme_def.get("flows", {})
    flows_model = OAuthFlows()
    
    client_id = credentials.get("client_id", "client")
    client_secret = credentials.get("client_secret", "secret")
    redirect_uri = credentials.get("redirect_uri")

    # Ensure redirect_uri has a scheme
    if redirect_uri and not redirect_uri.startswith("http"):
        redirect_uri = "http://" + redirect_uri

    if "implicit" in flows_def:
      f = flows_def["implicit"]
      flows_model.implicit = OAuthFlowImplicit(
          authorizationUrl=f.get("authorizationUrl"),
          scopes=f.get("scopes", {})
      )
      return OAuth2(flows=flows_model), AuthCredential(
          auth_type=AuthCredentialTypes.OAUTH2,
          oauth2=OAuth2Auth(client_id=client_id, redirect_uri=redirect_uri)
      )
    else:
      key = "authorizationCode" if "authorizationCode" in flows_def else next(iter(flows_def.keys()))
      f = flows_def[key]
      
      # Manually build the flow dictionary for Pydantic
      flow_kwargs = {
          "authorizationUrl": f.get("authorizationUrl"),
          "tokenUrl": f.get("tokenUrl"),
          "scopes": f.get("scopes", {})
      }
      
      setattr(flows_model, key, OAuthFlowAuthorizationCode(**flow_kwargs) if key == "authorizationCode" else flow_kwargs)
      
      return OAuth2(flows=flows_model), AuthCredential(
          auth_type=AuthCredentialTypes.OAUTH2,
          oauth2=OAuth2Auth(
              client_id=client_id, 
              client_secret=client_secret,
              redirect_uri=redirect_uri
          )
      )

def _parse_api_key(scheme_def: dict, credentials: dict) -> Tuple[APIKey, AuthCredential]:
    name = scheme_def.get("name", "api-key")
    in_ = scheme_def.get("in", "header")
    val = credentials.get("api_key") or "placeholder"
    return token_to_scheme_credential("apikey", in_, name, val)
