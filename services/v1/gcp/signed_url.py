# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import logging
import json
import uuid
from datetime import timedelta
from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


def get_gcs_client_with_credentials():
    """
    Create and return a Google Cloud Storage client with signing credentials.
    Returns tuple of (client, credentials) for signed URL generation.
    """
    credentials_json = os.environ.get('GCP_SA_CREDENTIALS')
    if not credentials_json:
        raise ValueError("GCP_SA_CREDENTIALS environment variable is not set")

    try:
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/devstorage.full_control']
        )
        client = storage.Client(credentials=credentials)
        return client, credentials
    except json.JSONDecodeError:
        raise ValueError("GCP_SA_CREDENTIALS is not valid JSON")
    except Exception as e:
        raise ValueError(f"Failed to create GCS client: {str(e)}")


def generate_signed_upload_url(
    filename: str,
    content_type: str = "video/mp4",
    expiration_minutes: int = 15,
    bucket_name: str = None,
    folder: str = None
) -> dict:
    """
    Generate a signed URL for uploading a file directly to GCS.

    Args:
        filename: Name of the file to upload
        content_type: MIME type of the file (default: video/mp4)
        expiration_minutes: How long the URL is valid (default: 15 minutes)
        bucket_name: GCS bucket name (default: from GCP_BUCKET_NAME env var)
        folder: Optional folder/prefix for the file path

    Returns:
        dict with upload_url, public_url, filename, bucket, expires_in_minutes
    """
    try:
        # Get bucket name from env if not provided
        if not bucket_name:
            bucket_name = os.environ.get('GCP_BUCKET_NAME')
            if not bucket_name:
                raise ValueError("GCP_BUCKET_NAME environment variable is not set")

        # Get client and credentials
        client, credentials = get_gcs_client_with_credentials()
        bucket = client.bucket(bucket_name)

        # Build the blob path
        if folder:
            blob_path = f"{folder.strip('/')}/{filename}"
        else:
            blob_path = filename

        blob = bucket.blob(blob_path)

        # Generate signed URL for PUT (upload)
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="PUT",
            content_type=content_type,
            credentials=credentials
        )

        # Build the public URL (where the file will be accessible after upload)
        public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_path}"

        logger.info(f"Generated signed upload URL for {blob_path} in bucket {bucket_name}")

        return {
            "upload_url": upload_url,
            "public_url": public_url,
            "filename": filename,
            "blob_path": blob_path,
            "bucket": bucket_name,
            "content_type": content_type,
            "expires_in_minutes": expiration_minutes,
            "method": "PUT",
            "headers_required": {
                "Content-Type": content_type
            }
        }

    except Exception as e:
        logger.error(f"Error generating signed upload URL: {e}")
        raise


def generate_signed_download_url(
    blob_path: str,
    expiration_minutes: int = 60,
    bucket_name: str = None
) -> dict:
    """
    Generate a signed URL for downloading a file from GCS.

    Args:
        blob_path: Path to the blob in the bucket
        expiration_minutes: How long the URL is valid (default: 60 minutes)
        bucket_name: GCS bucket name (default: from GCP_BUCKET_NAME env var)

    Returns:
        dict with download_url, blob_path, bucket, expires_in_minutes
    """
    try:
        if not bucket_name:
            bucket_name = os.environ.get('GCP_BUCKET_NAME')
            if not bucket_name:
                raise ValueError("GCP_BUCKET_NAME environment variable is not set")

        client, credentials = get_gcs_client_with_credentials()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)

        # Check if blob exists
        if not blob.exists():
            raise ValueError(f"Blob {blob_path} does not exist in bucket {bucket_name}")

        # Generate signed URL for GET (download)
        download_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
            credentials=credentials
        )

        logger.info(f"Generated signed download URL for {blob_path} in bucket {bucket_name}")

        return {
            "download_url": download_url,
            "blob_path": blob_path,
            "bucket": bucket_name,
            "expires_in_minutes": expiration_minutes
        }

    except Exception as e:
        logger.error(f"Error generating signed download URL: {e}")
        raise
