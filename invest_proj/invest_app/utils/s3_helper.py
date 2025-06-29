from invest_app.utils.shared_imports import *

def upload_to_s3(file_obj, file_key):
    s3 = boto3.client('s3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )
    s3.upload_fileobj(file_obj, settings.AWS_STORAGE_BUCKET_NAME, file_key)
    return file_key


def generate_presigned_url(file_key, expires_in=300):
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )
    # Ensure key is only S3 path like "customerdoc/abc/pan_xyz.jpeg"
    mime_type, _ = mimetypes.guess_type(file_key)
    if not mime_type:
        mime_type = 'application/octet-stream'

    print("🔍 File Key:", file_key)
    print("📎 MIME Type:", mime_type)

    return s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
            'Key': file_key,
            'ResponseContentDisposition': 'inline',  # 👈 tells browser to preview
            'ResponseContentType': mime_type
        },
        ExpiresIn=expires_in
    )
# def generate_presigned_url(file_key, expires_in=300):
#     s3 = boto3.client(
#         's3',
#         aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#         aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#         region_name=settings.AWS_S3_REGION_NAME
#     )
#     mime_type, _ = mimetypes.guess_type(file_key)
#     if not mime_type:
#         mime_type = 'application/octet-stream'

#     print("🔍 File Key:", file_key)
#     print("📎 MIME Type:", mime_type)

#     url = s3.generate_presigned_url(
#         ClientMethod='get_object',
#         Params={
#             'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
#             'Key': file_key,
#             'ResponseContentDisposition': 'inline',
#             'ResponseContentType': mime_type
#         },
#         ExpiresIn=expires_in
#     )

#     print("✅ Pre-signed URL:", url)  # ✅ Add this line to test

#     return url


# def generate_presigned_url(file_key, expires_in=3600): # 1 hr.
#     s3 = boto3.client('s3',
#         aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#         aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#         region_name=settings.AWS_S3_REGION_NAME
#     )
#     return s3.generate_presigned_url(
#         ClientMethod='get_object',
#         Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': file_key},
#         ExpiresIn=expires_in
#     )
