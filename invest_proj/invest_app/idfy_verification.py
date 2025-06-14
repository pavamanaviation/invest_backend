
import requests
from django.conf import settings

def send_pan_verification_request(pan_number, task_id):
    url = settings.IDFY_PAN_VERIFY_URL
    headers = {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_TEST_ACCOUNT_ID,
        "api-key": settings.IDFY_TEST_API_KEY,
    }

    payload = {
        "task_id": task_id,
        "group_id": settings.IDFY_TEST_GROUP_ID,
        "data": {
            "id_number": pan_number,
            "consent": "Y" # Assuming consent is required, set to 'Y'
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def get_pan_verification_result(request_id):
    url = settings.IDFY_RESULT_URL.format(request_id=request_id)
    headers = {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_TEST_ACCOUNT_ID,
        "api-key": settings.IDFY_TEST_API_KEY,
    }

    try:
        response = requests.get(url, headers=headers)
        return response.json()
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
from django.conf import settings
from django.conf import settings
import uuid
import requests

def verify_bank_account_sync(account_number, ifsc):
    IDFY_BANK_VERIFY_URL = "https://eve.idfy.com/v3/tasks/sync/verify_with_source/ind_bav"
    IDFY_TEST_API_KEY = settings.IDFY_TEST_API_KEY

    task_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())

    headers = {
        "Content-Type": "application/json",
        "apikey": IDFY_TEST_API_KEY
    }

    payload = {
        "task_id": task_id,
        "group_id": group_id,
        "data": {
            "account_number": account_number,
            "ifsc": ifsc
        }
    }

    # TEMP: Print headers to debug
    print(" Sending request to IDfy with headers:", headers)

    response = requests.post(IDFY_BANK_VERIFY_URL, headers=headers, json=payload)

    return task_id, response.json()
