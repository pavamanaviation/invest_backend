import base64
import uuid
import httpx
import json

ACCOUNT_ID = "e351a415009f/ebd20862-8dc6-421e-bd1c-0480a19485dc"
API_KEY = "082618e6-1a00-4d5d-aefb-12f466fa4494"

file_path = "C:/Users/admin/Downloads/pan.jpeg"

with open(file_path, "rb") as f:
    encoded = base64.b64encode(f.read()).decode("utf-8")

payload = {
    "task_id": str(uuid.uuid4()),
    "data": {
        "file": encoded,
        "document_type": "pan"
    }
}

headers = {
    "Content-Type": "application/json",
    "account-id": ACCOUNT_ID,
    "api-key": API_KEY
}

url = "https://eve.idfy.com/v3/tasks/async/verify_with_source/ocr_pan"

async def main():
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        print("Status Code:", resp.status_code)
        print("Response:", resp.text)

import asyncio
asyncio.run(main())
