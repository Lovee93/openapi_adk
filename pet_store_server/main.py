from fastapi import FastAPI, HTTPException, Header, Security
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

app = FastAPI(
    title="Enhanced Petstore API",
    description="A simple API that demonstrates CRUD operations on pets.",
    version="1.0.1"
)

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
    photoUrls: Optional[List[str]] = []
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


# --- Endpoints ---

@app.post("/pet", response_model=Pet, summary="Add a new pet to the store")
def add_pet(pet: Pet, api_key: Optional[str] = Header(None)):
    """
    Creates a new pet with the given details. 
    """
    if pet.id in pets_db:
         raise HTTPException(status_code=400, detail="Pet with this ID already exists")
    
    pets_db[pet.id] = pet
    return pet

@app.put("/pet", response_model=Pet, summary="Update an existing pet")
def update_pet(pet: Pet):
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
