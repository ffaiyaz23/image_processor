# main.py
# FastAPI app entry point

from fastapi import FastAPI
from app.routes import router as api_router
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Image Processor API")

app.include_router(api_router)

# Mount the processed_images directory to serve processed images
app.mount("/processed_images", StaticFiles(directory="processed_images"), name="processed_images")

@app.get("/")
async def root():
    return {"message": "Welcome to the Image Processor API"}