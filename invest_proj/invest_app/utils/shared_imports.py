# utils/shared_imports.py

# Python standard libraries
import os
import json
import uuid
import time
import random
import base64
import hmac
import hashlib
import mimetypes
from io import BytesIO
from datetime import datetime, timedelta

# Third-party packages
import requests
import pytz
import razorpay
import boto3
import mimetypes

# Django core
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.timezone import now
from django.db import IntegrityError
from django.db.models import Q, Sum, Max, Value
from django.db.models.functions import Concat
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.core.cache import cache

from email.utils import parsedate
from django.core.cache import cache
from django.core.paginator import Paginator
from django.apps import apps
from django.db.models import Q

from django.contrib.auth.decorators import user_passes_test
from django.utils.timezone import now as timezone_now
