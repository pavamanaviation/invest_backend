import requests
import json
from django.conf import settings

def send_bulk_sms(mobile_number,otp):
    url = settings.MSG91_SMS_URL
    
    payload = {
        "flow_id": settings.MSG91_FLOW_ID_RESETPASSWORD,
        "sender":settings.MSG91_SENDER_ID,
        # "mobiles": mobile_number,
        "mobiles": ",".join(mobile_number),  # results in "919876543210"

        "OTP": otp
    }

    headers = {
        'accept': "application/json",
        'authkey': settings.MSG91_AUTH_KEY,
        'content-type': "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    return response.json()