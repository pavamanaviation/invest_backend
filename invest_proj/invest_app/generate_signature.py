import hmac
import hashlib

# Replace with your Razorpay Webhook Secret
webhook_secret = b"your_webhook_secret_here"

# Use raw body string as it is (from Postman Body - Raw - JSON)
raw_payload = b'''
{
  "event": "payment.captured",
  "payload": {
    "payment": {
      "entity": {
        "order_id": "order_Oj0HtuAf6YihN",
        "id": "pay_Oj0IwwhF9mQnkr"
      }
    }
  }
}
'''

# Calculate HMAC SHA256 signature
signature = hmac.new(webhook_secret, raw_payload, hashlib.sha256).hexdigest()
print("X-Razorpay-Signature:", signature)
