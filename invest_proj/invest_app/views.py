from django.shortcuts import render

# Create your views here.
from django.http import JsonResponse
from django.utils import timezone
import pytz

def check_indian_time(request):
    india_tz = pytz.timezone('Asia/Kolkata')
    india_time = timezone.now().astimezone(india_tz)
    # Format the time as a string
    india_time_str = india_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')
    
    return JsonResponse({"current_indian_time": india_time_str})
