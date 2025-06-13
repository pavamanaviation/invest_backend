# # import requests

# # IDFY_API_KEY = 'your_idfy_api_key'
# # IDFY_PAN_URL = 'https://api.idfy.com/v3/tasks/async/verify_with_source/individual_pan'

# # def verify_pan_idfy(pan_number, name):
# #     payload = {
# #         "task_id": f"pan-task-{pan_number}",
# #         "group_id": "kyc_group_001",
# #         "data": {
# #             "id_number": pan_number,
# #             "name": name
# #         }
# #     }
    
# #     headers = {
# #         "api-key": IDFY_API_KEY,
# #         "Content-Type": "application/json"
# #     }

# #     response = requests.post(IDFY_PAN_URL, headers=headers, json=payload)
# #     return response.json()
# import uuid
# import requests
# from django.conf import settings
# # IDFY_API_KEY = 'YOUR_SANDBOX_API_KEY'
# # IDFY_CLIENT_ID = 'YOUR_SANDBOX_CLIENT_ID'
# IDFY_URL = settings.IDFY_URL  # Use the URL from settings
# # IDFY_URL = 'https://api.idfy.com/v3/tasks/async/verify_with_source/individual_pan'
# def verify_pan_idfy(pan_number):
#     headers = {
#         "Content-Type": "application/json",
#         "api-key": settings.IDFY_API_KEY,
#         "client-id": settings.IDFY_CLIENT_ID
#     }

#     payload = {
#         "task_id": str(uuid.uuid4()),
#         "group_id": "pan-verification-sandbox",
#         "data": {
#             "pan_number": pan_number
#         }
#     }

#     try:
#         response = requests.post(settings.IDFY_URL, headers=headers, json=payload)

#         # response = requests.post(IDFY_URL, headers=headers, json=payload)
#         print(response.status_code, IDFY_URL)
#         print(response.json())
#         return response.status_code, response.json()
#     except Exception as e:
#         return 500, {"error": str(e)}
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
