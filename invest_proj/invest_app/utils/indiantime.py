import pytz

def format_datetime_ist(dt):
    if dt is None:
        return None
    ist = pytz.timezone("Asia/Kolkata")
    return dt.astimezone(ist).strftime("%Y-%m-%d %H:%M:%S")
