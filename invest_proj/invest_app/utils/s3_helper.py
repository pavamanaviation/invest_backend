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
            'ResponseContentDisposition': 'inline',  # tells browser to preview
            'ResponseContentType': mime_type
        },
        ExpiresIn=expires_in
    )
def delete_all_kyc_files(customer_id, first_name, last_name, doc_type):
    """
    Deletes all PAN or Aadhaar related S3 files for a specific customer.

    :param customer_id: int
    :param first_name: str
    :param last_name: str
    :param doc_type: str ('aadhar' or 'pan')
    """
    try:
        assert doc_type in ['aadhar', 'pan'], "Invalid doc_type. Must be 'aadhar' or 'pan'."

        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        bucket = settings.AWS_STORAGE_BUCKET_NAME
        prefix = f"customerdoc/{customer_id}_{first_name.lower()}{last_name.lower()}/{doc_type}_"

        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if 'Contents' in response:
            for obj in response['Contents']:
                s3.delete_object(Bucket=bucket, Key=obj['Key'])
                print(f"Deleted: {obj['Key']}")
        else:
            print(f"No {doc_type.upper()} files found to delete.")

    except Exception as e:
        print(f"Error deleting {doc_type.upper()} files: {str(e)}")

def get_next_folder_and_filename():
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )

    base_folder = "drone_uploads/"
    existing_objects = s3.list_objects_v2(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Prefix=base_folder
    ).get("Contents", [])

    folder_nums = []
    for obj in existing_objects:
        parts = obj['Key'].split("/")
        if len(parts) > 1:
            folder = parts[1]
            if folder.startswith("pavaman_drones_") and folder.split("_")[-1].isdigit():
                folder_nums.append(int(folder.split("_")[-1]))

    next_num = max(folder_nums) + 1 if folder_nums else 1
    folder_name = f"pavaman_drones_{next_num:04d}"
    file_name = f"drone_models_{next_num:04d}.xlsx"

    return folder_name, file_name


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
