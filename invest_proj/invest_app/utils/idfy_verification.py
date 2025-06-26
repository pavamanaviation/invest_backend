

from invest_app.utils.shared_imports import *


# def send_pan_verification_request(pan_number,full_name,dob, task_id):
#     url = settings.IDFY_PAN_VERIFY_URL
#     headers = {
#         "Content-Type": "application/json",
#         "account-id": settings.IDFY_TEST_ACCOUNT_ID,
#         "api-key": settings.IDFY_TEST_API_KEY,
#     }

#     payload = {
#         "task_id": task_id,
#         "group_id": settings.IDFY_TEST_GROUP_ID,
#         "data": {
#             "id_number": pan_number,
#             "full_name":full_name,
#             "dob": dob,  # Format: YYYY-MM-DD
#             # "consent": "Y"
#         }
#     }

#     try:
#         response = requests.post(url, headers=headers, json=payload)
#         return response.json()
#     except Exception as e:
#         return {"error": str(e)}
# pan_utils.py

def send_pan_verification_request(pan_number, full_name, dob, task_id=None):
    url = settings.IDFY_PAN_VERIFY_URL
    headers = {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_TEST_ACCOUNT_ID,
        "api-key": settings.IDFY_TEST_API_KEY,
    }

    if not task_id:
        task_id = str(uuid.uuid4())

    payload = {
        "task_id": task_id,
        "group_id": settings.IDFY_TEST_GROUP_ID,
        "data": {
            "id_number": pan_number,
            "full_name": full_name,
            "dob": dob
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def send_idfy_pan_ocr(file_bytes):
    url = "https://eve.idfy.com/v3/tasks/async/verify_with_source/ocr_pan"
    headers = {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_TEST_ACCOUNT_ID,
        "api-key": settings.IDFY_TEST_API_KEY
    }

    task_id = str(uuid.uuid4())
    encoded_file = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "task_id": task_id,
        "data": {
            "file": encoded_file,
            "document_type": "pan"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        return {
            "status_code": response.status_code,
            "task_id": task_id,
            "response": response.json()
        }
    except Exception as e:
        return {
            "status_code": 500,
            "error": str(e)
        }


def get_pan_verification_result(request_id):
    url = f"https://eve.idfy.com/v3/tasks?request_id={request_id}"
    headers = {
        'Content-Type': 'application/json',
        'api-key': settings.IDFY_TEST_API_KEY,
        'account-id': settings.IDFY_TEST_ACCOUNT_ID,
    }

    try:
        response = requests.get(url, headers=headers)
        data = response.json()

        # IDfy might sometimes return a list. Convert to dict safely
        if isinstance(data, list) and len(data) > 0:
            return data[0]  # Take the first result
        return data
    except Exception as e:
        return {"error": str(e)}

import requests
import uuid
from django.conf import settings
def verify_aadhar_sync(aadhar_number, task_id):
    url = "https://eve.idfy.com/v3/tasks/sync/verify_with_source/aadhaar_lite"
    headers = {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_TEST_ACCOUNT_ID,
        "api-key": settings.IDFY_TEST_API_KEY,
    }
    payload = {
        "task_id": task_id,
        "group_id": settings.IDFY_TEST_GROUP_ID,
        "data": {
            "aadhaar_number": aadhar_number
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    return response.json()
    
def verify_bank_account_sync(account_number, ifsc):
    IDFY_BANK_VERIFY_URL = settings.IDFY_BANK_VERIFY_URL
    IDFY_TEST_API_KEY= settings.IDFY_TEST_API_KEY
    IDFY_TEST_ACCOUNT_ID = settings.IDFY_TEST_ACCOUNT_ID

    task_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())

    headers = {
        "Content-Type": "application/json",
        "api-key": IDFY_TEST_API_KEY,
        "account-id": IDFY_TEST_ACCOUNT_ID
    }

    payload = {
        "task_id": task_id,
        "group_id": group_id,
        "data": {
            "bank_ifsc_code": ifsc,
            "bank_account_no": account_number,
            "nf_verification": False
        }
    }

    response = requests.post(IDFY_BANK_VERIFY_URL, headers=headers, json=payload)
    return task_id, response.json()

