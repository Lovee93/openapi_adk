from fastapi import FastAPI, HTTPException, Security, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2
from fastapi.openapi.models import OAuthFlows, OAuthFlowAuthorizationCode
from starlette.status import HTTP_401_UNAUTHORIZED
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum
import uuid

# Define the OAuth2 Authorization Code scheme matching the spec
# This configuration is critical for generating the correct OpenAPI (Swagger) UI
# The user will click 'Authorize' -> redirect to authorizationUrl -> authenticate -> redirect back with code -> swap code at tokenUrl
oauth2_scheme = OAuth2(
    flows=OAuthFlows(
        authorizationCode=OAuthFlowAuthorizationCode(
            authorizationUrl="http://127.0.0.1:8000/oauth/authorize",
            tokenUrl="http://127.0.0.1:8000/oauth/token",
            scopes={
                "write:pets": "modify pets in your account",
                "read:pets": "read your pets",
            },
        )
    )
)

app = FastAPI(
    title="Enhanced Petstore API",
    description="A simple API that demonstrates CRUD operations on pets with OAuth2 Authorization Code flow.",
    version="1.0.1"
)

# --- Mock OAuth Data ---
auth_codes = {}
valid_tokens = set()

# --- OAuth Endpoints ---

@app.get("/oauth/authorize", response_class=HTMLResponse)
def authorize_page(client_id: str, redirect_uri: str, state: str, scope: str = "", response_type: str = "code"):
    return f"""
    <html>
        <head>
            <title>PetStore Login</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f4f4f9; color: #333; }}
                .container {{ background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }}
                h2 {{ margin-top: 0; color: #6200ea; }}
                label {{ display: block; margin-bottom: 0.5rem; font-weight: 500; }}
                input {{ width: 100%; padding: 0.75rem; margin-bottom: 1rem; border: 1px solid #ddd; border-radius: 4px; font-size: 1rem; box-sizing: border-box; }}
                button {{ width: 100%; padding: 0.75rem; background-color: #6200ea; color: white; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; transition: background 0.2s; }}
                button:hover {{ background-color: #3700b3; }}
                .info {{ font-size: 0.875rem; color: #666; margin-bottom: 1.5rem; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>PetStore Auth</h2>
                <p class="info">Demo Authorization Server. <br>Use <b>user</b> / <b>password</b> to sign in.</p>
                <form action="/oauth/authorize" method="post">
                    <input type="hidden" name="client_id" value="{client_id}">
                    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
                    <input type="hidden" name="state" value="{state}">
                    
                    <label>Username</label>
                    <input type="text" name="username" value="user" required>
                    
                    <label>Password</label>
                    <input type="password" name="password" value="password" required>
                    
                    <button type="submit">Authorize</button>
                </form>
            </div>
        </body>
    </html>
    """

@app.post("/oauth/authorize")
def authorize_submit(
    username: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(...)
):
    if username == "user" and password == "password":
        code = str(uuid.uuid4())
        auth_codes[code] = {"client_id": client_id, "user": username}
        # Standard OAuth2 redirect with code and state
        return RedirectResponse(url=f"{redirect_uri}?code={code}&state={state}", status_code=302)
    return HTMLResponse("Invalid credentials", status_code=401)

@app.post("/oauth/token")
def issue_token(
    grant_type: str = Form(None),
    code: str = Form(None),
    client_id: str = Form(None),
    redirect_uri: str = Form(None),
):
    print(f"Token Request Received: grant_type={grant_type}, code={code}, client_id={client_id}, redirect_uri={redirect_uri}")
    print(f"Current Auth Codes: {auth_codes.keys()}")
    
    if code in auth_codes:
        # Generate a 'secure' token and store it
        token = f"sat_{code}_{uuid.uuid4()}"
        valid_tokens.add(token)
        print(f"Issued Token: {token}")
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 3600
        }
    
    print("Error: Invalid Grant - Code not found")
    return JSONResponse({"error": "invalid_grant"}, status_code=400)


# --- Models ---

class Category(BaseModel):
    id: int
    name: str

class Tag(BaseModel):
    id: int
    name: str

class PetStatus(str, Enum):
    available = "available"
    pending = "pending"
    sold = "sold"

class Pet(BaseModel):
    id: int
    name: str
    category: Optional[Category] = None
    photoUrls: List[str]
    tags: Optional[List[Tag]] = []
    status: PetStatus

# --- In-memory Storage ---

pets_db = {}
# Initialize with some data
pets_db[0] = Pet(
    id=0,
    name="doggie",
    category=Category(id=6, name="Dogs"),
    photoUrls=["https://example.com/photo1.jpg", "https://example.com/photo2.jpg"],
    tags=[Tag(id=1, name="friendly")],
    status=PetStatus.available
)
pets_db[1] = Pet(
    id=1,
    name="cat",
    category=Category(id=5, name="Cats"),
    photoUrls=["https://example.com/photo3.jpg"],
    tags=[Tag(id=2, name="playful")],
    status=PetStatus.pending
)

# --- Auth Dependency ---

def verify_token(token: str = Depends(oauth2_scheme)):
    """
    Validates the bearer token provided in the Authorization header.
    Checks if it is one of the valid tokens issued by our local Mock OAuth logic.
    """
    print(f"Verifying Token: '{token}'")
    # print(f"Valid Tokens in-memory: {valid_tokens}") # Commented out to avoid log spam if list is huge, but useful for debug
    
    # Robustness fix: Strip 'Bearer ' if present (caused failure in previous run)
    if token.startswith("Bearer "):
        token = token.split(" ")[1]
        print(f"Stripped 'Bearer ' prefix. New token: '{token}'")

    if token not in valid_tokens:
        print(f"Token verification failed! Token not found in valid_tokens.")
        # Fail if unauthorized
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please authenticate via the OAuth flow.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    print("Token verified successfully.")
    return token

# --- Endpoints ---

@app.post("/pet", response_model=Pet, summary="Add a new pet to the store")
def add_pet(
    pet: Pet, 
    token: str = Security(verify_token, scopes=["write:pets", "read:pets"])
):
    """
    Creates a new pet with the given details. 
    Requires OAuth2 Authorization Code authentication with write:pets and read:pets scopes.
    """
    if pet.id in pets_db:
         raise HTTPException(status_code=400, detail="Pet with this ID already exists")
    
    pets_db[pet.id] = pet
    return pet

@app.put("/pet", response_model=Pet, summary="Update an existing pet")
def update_pet(
    pet: Pet,
    token: str = Security(verify_token, scopes=["write:pets", "read:pets"])
):
    """
    Updates an existing pet in the store.
    """
    if pet.id not in pets_db:
        raise HTTPException(status_code=404, detail="Pet not found")
    
    pets_db[pet.id] = pet
    return pet

@app.get("/pet/{pet_id}", response_model=Pet, summary="Find pet by ID")
def get_pet_by_id(pet_id: int):
    """
    Returns a single pet by its ID.
    """
    if pet_id not in pets_db:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pets_db[pet_id]

@app.get("/store/inventory", summary="Returns pet inventories by status")
def get_inventory():
    """
    Displays counts of pets in various statuses such as available, pending, or sold.
    """
    inventory = {}
    for pet in pets_db.values():
        status = pet.status.value
        inventory[status] = inventory.get(status, 0) + 1
    return inventory

if __name__ == "__main__":
    import uvicorn
    # Important: Run on port 8000 to match the authorizationUrl in this file
    uvicorn.run(app, host="0.0.0.0", port=8000)
