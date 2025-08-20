from invest_app.utils.shared_imports import *

def get_idfy_headers():
    return {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_ACCOUNT_ID,
        "api-key": settings.IDFY_API_KEY
    }

def submit_idfy_pan_ocr(document_url, task_id=None):
    if not task_id:
        task_id = str(uuid.uuid4())

    payload = {
        "task_id": task_id,
        "group_id": settings.IDFY_GROUP_ID,
        "data": {
            "document1": document_url
        }
    }

    response = requests.post(
        f"{settings.IDFY_BASE_URL}/tasks/async/extract/ind_pan",
        headers=get_idfy_headers(),
        json=payload
    )

    return response.status_code, response.json(), task_id

def check_idfy_task_status(task_id):
    response = requests.get(
        f"{settings.IDFY_BASE_URL}/tasks/async/tasks/{task_id}",
        headers=get_idfy_headers()
    )
    return response.status_code, response.json()

def check_idfy_status_by_request_id(request_id):
    response = requests.get(
        f"{settings.IDFY_BASE_URL}/tasks",
        headers=get_idfy_headers(),
        params={"request_id": request_id}
    )
    return response.status_code, response.json()



def submit_idfy_pan_verification(name, dob, pan_number):
    url = "https://eve.idfy.com/v3/tasks/async/verify_with_source/ind_pan"

    headers = {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_ACCOUNT_ID,
        "api-key": settings.IDFY_API_KEY,

    }

    task_id = str(uuid.uuid4())
    payload = {
        "task_id": task_id,
        # "group_id": "8e16424a-58fc-4ba4-ab20-5bc8e7c3c41e",
        "group_id": settings.IDFY_GROUP_ID,
        "data": {
            "id_number": pan_number,
            "full_name": name,
            "dob": dob
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    try:
        response_data = response.json()
    except Exception:
        response_data = {"error": "Invalid JSON response", "raw": response.text}

    return response.status_code, response_data, task_id, response_data.get("request_id")

# --------------------

def submit_idfy_aadhar_ocr(file_url):
    headers = {
        "Content-Type": "application/json",
        "api-key": settings.IDFY_API_KEY,
        "account-id": settings.IDFY_ACCOUNT_ID
    }
    payload = {
        "task_id": str(uuid.uuid4()),
        "group_id": settings.IDFY_GROUP_ID,
        "data": {
            "document1": file_url,
            "consent": "yes"
        }
    }
    response = requests.post(
        f"{settings.IDFY_BASE_URL}/tasks/async/extract/ind_aadhaar",
        headers=headers,
        json=payload
    )
    return response.status_code, response.json(), payload["task_id"]


def check_idfy_status_by_request_id(request_id):
    headers = {
        "api-key": settings.IDFY_API_KEY,
        "account-id": settings.IDFY_ACCOUNT_ID
    }

    response = requests.get(
        f"{settings.IDFY_BASE_URL}/tasks?request_id={request_id}",
        headers=headers
    )
    return response.status_code, response.json()


# ------------------------
def verify_aadhar_sync(aadhaar_number, task_id):
    import requests

    url = "https://eve.idfy.com/v3/tasks/sync/verify_with_source/aadhaar_lite"
    headers = {
        "Content-Type": "application/json",
        "account-id": settings.IDFY_TEST_ACCOUNT_ID,  # Replace with actual account ID
        "api-key": settings.IDFY_TEST_API_KEY         # Replace with actual API key
    }
    payload = {
        "task_id": task_id,
        "group_id": settings.IDFY_TEST_GROUP_ID,       # Replace with valid group ID
        "data": {
            "aadhaar_number": aadhaar_number           # ✅ Use correct spelling
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        status_code = response.status_code
        try:
            response_json = response.json()
        except Exception:
            response_json = {"error": "Invalid JSON", "raw": response.text}

        return {
            "status_code": status_code,
            "status": response_json.get("status", ""),
            "result": response_json
        }

    except requests.RequestException as e:
        return {
            "status_code": None,
            "status": "failed",
            "error": str(e)
        }

# def verify_aadhar_sync(aadhar_number, task_id):
#     url = "https://eve.idfy.com/v3/tasks/sync/verify_with_source/aadhar_lite"
#     headers = {
#         "Content-Type": "application/json",
#         "account-id": settings.IDFY_TEST_ACCOUNT_ID,
#         "api-key": settings.IDFY_TEST_API_KEY,
#     }
#     payload = {
#         "task_id": task_id,
#         "group_id": settings.IDFY_TEST_GROUP_ID,
#         "data": {
#             "aadhar_number": aadhar_number
#         }
#     }

#     response = requests.post(url, headers=headers, json=payload)
#     return response.json()
    
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

