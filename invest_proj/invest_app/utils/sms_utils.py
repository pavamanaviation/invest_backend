from twilio.rest import Client
from django.conf import settings

def send_otp_sms(mobile_nos, message):
    """Send SMS using Twilio to multiple recipients."""
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    
    for mobile_no in mobile_nos:
        sms = client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=mobile_no  # Ensure correct variable usage
        )
        print(f"SMS sent to {mobile_no}: {sms.sid}")  # Debugging purpose
