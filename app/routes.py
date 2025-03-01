# routes.py
# API endpoints

import os
import io
import csv
import re
import uuid
import time
import requests
from io import BytesIO
from datetime import datetime
from PIL import Image
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ProcessingRequest, Product

router = APIRouter()

# Directory to store output CSV files
OUTPUT_DIR = "output"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Directory to store processed images
PROCESSED_DIR = "processed_images"
if not os.path.exists(PROCESSED_DIR):
    os.makedirs(PROCESSED_DIR)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def normalize(text: str) -> str:
    """Remove non-alphanumeric characters and convert to lowercase."""
    return re.sub(r'\W+', '', text).lower()

def generate_output_csv(request_id: str, db: Session):
    """
    Generate an output CSV file for a given request.
    Columns: S. No, Product Name, Input Image Urls, Output Image Urls.
    """
    products = db.query(Product).filter(Product.request_id == request_id).all()
    output_file = os.path.join(OUTPUT_DIR, f"{request_id}_output.csv")
    with open(output_file, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["S. No", "Product Name", "Input Image Urls", "Output Image Urls"])
        for product in products:
            writer.writerow([
                product.serial_number,
                product.product_name,
                product.input_image_urls,
                product.output_image_urls or ""
            ])
    return output_file

def process_images(request_id: str):
    """
    1. Download each image URL and compress it to 50% quality.
    2. Save the compressed file locally under processed_images.
    3. Update the product record with the new local URL.
    4. Mark the request as completed and set completed_at.
    5. If callback_url is provided, POST to that URL with status info.
    """
    db = SessionLocal()
    try:
        products = db.query(Product).filter(Product.request_id == request_id).all()
        for product in products:
            new_urls = []
            input_urls = product.input_image_urls.split(',')
            for url in input_urls:
                url = url.strip()
                if not url:
                    continue
                try:
                    response = requests.get(url, stream=True, timeout=10)
                    if response.status_code == 200:
                        img = Image.open(BytesIO(response.content))
                        # Create a unique filename
                        new_filename = f"{uuid.uuid4()}.jpg"
                        new_path = os.path.join(PROCESSED_DIR, new_filename)
                        # Compress to 50% quality
                        img.convert("RGB").save(new_path, format="JPEG", quality=50)
                        # Construct local URL
                        local_url = f"/processed_images/{new_filename}"
                        new_urls.append(local_url)
                    else:
                        print(f"Failed to download image from {url}, status code: {response.status_code}")
                except Exception as e:
                    print(f"Error downloading or processing image {url}: {e}")
            
            product.output_image_urls = ','.join(new_urls)
            product.status = "processed"
            db.add(product)
            # Optional short delay
            time.sleep(0.5)
        
        # Update the request status and completed_at
        processing_request = db.query(ProcessingRequest).filter(ProcessingRequest.request_id == request_id).first()
        if processing_request:
            processing_request.status = "completed"
            processing_request.completed_at = datetime.utcnow()
            db.add(processing_request)
        db.commit()

        # Trigger the webhook if callback_url is provided
        if processing_request and processing_request.callback_url:
            try:
                payload = {
                    "request_id": request_id,
                    "status": "completed"
                }
                resp = requests.post(processing_request.callback_url, json=payload, timeout=5)
                if resp.status_code < 200 or resp.status_code >= 300:
                    print(f"Webhook call failed, status: {resp.status_code}")
            except Exception as e:
                print(f"Error calling webhook for request {request_id}: {e}")

    except Exception as e:
        db.rollback()
        print(f"Error processing images for request {request_id}: {e}")
    finally:
        db.close()

@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    webhook_url: str = None,  # optional
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # Validate file type
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Invalid file type. Only CSV files are accepted.")
    
    content = await file.read()
    decoded_content = content.decode("utf-8")
    csv_reader = csv.reader(io.StringIO(decoded_content))
    
    header = next(csv_reader, None)
    if header is None:
        raise HTTPException(status_code=400, detail="CSV file is empty.")
    
    expected_header = ["sno", "productname", "inputimageurls"]
    csv_header = [normalize(col) for col in header]
    if csv_header != expected_header:
        raise HTTPException(
            status_code=400,
            detail="Invalid CSV header format. Expected header: S. No, Product Name, Input Image Urls"
        )
    
    request_id = str(uuid.uuid4())
    new_request = ProcessingRequest(
        request_id=request_id,
        status="pending",
        callback_url=webhook_url
    )
    db.add(new_request)
    
    for row in csv_reader:
        if len(row) != 3:
            raise HTTPException(status_code=400, detail="CSV row does not have exactly 3 columns.")
        serial_number, product_name, input_image_urls = row
        product = Product(
            request_id=request_id,
            serial_number=serial_number.strip(),
            product_name=product_name.strip(),
            input_image_urls=input_image_urls.strip(),
            status="pending"
        )
        db.add(product)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error saving request and product data.")
    
    # Schedule background processing
    background_tasks.add_task(process_images, request_id)
    
    return {"request_id": request_id, "message": "CSV file uploaded and processing started."}

@router.get("/status/{request_id}")
async def get_status(request_id: str, db: Session = Depends(get_db)):
    processing_request = db.query(ProcessingRequest).filter(ProcessingRequest.request_id == request_id).first()
    if not processing_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    products = db.query(Product).filter(Product.request_id == request_id).all()
    products_data = [
        {
            "serial_number": product.serial_number,
            "product_name": product.product_name,
            "input_image_urls": product.input_image_urls,
            "output_image_urls": product.output_image_urls,
            "status": product.status
        }
        for product in products
    ]
    
    response = {
        "request_id": processing_request.request_id,
        "status": processing_request.status,
        "created_at": str(processing_request.created_at),
        "completed_at": str(processing_request.completed_at) if processing_request.completed_at else None,
        "callback_url": processing_request.callback_url,
        "products": products_data
    }
    
    if processing_request.status == "completed":
        output_file = os.path.join(OUTPUT_DIR, f"{request_id}_output.csv")
        if not os.path.exists(output_file):
            generate_output_csv(request_id, db)
        response["output_csv_link"] = f"/download/{request_id}"
    
    return response

@router.get("/download/{request_id}")
async def download_output_csv(request_id: str):
    output_file = os.path.join(OUTPUT_DIR, f"{request_id}_output.csv")
    if not os.path.exists(output_file):
        raise HTTPException(status_code=404, detail="Output CSV not found.")
    return FileResponse(output_file, media_type="text/csv", filename=f"{request_id}_output.csv")