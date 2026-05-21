import boto3
from botocore.exceptions import ClientError, BotoCoreError
from typing import BinaryIO, Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)

# Global S3 client (initialized lazily)
_s3_client = None


def get_s3_client():
    """Get or create S3 client with proper credentials"""
    global _s3_client
    
    if _s3_client is None:
        client_kwargs = {
            "region_name": settings.aws_s3_region,
        }
        
        # Use explicit credentials if provided, otherwise rely on IAM role/environment variables
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        
        _s3_client = boto3.client("s3", **client_kwargs)
        logger.info(f"S3 client initialized for region: {settings.aws_s3_region}")
    
    return _s3_client


def upload_file_to_s3(
    file_obj: BinaryIO,
    case_id: int,
    image_id: int,
    filename: str,
    content_type: str
) -> str:
    """
    Upload a file to S3 and return the S3 key.
    
    Args:
        file_obj: File-like object to upload
        case_id: Case ID for organizing files
        image_id: Image ID for uniqueness
        filename: Original filename
        content_type: MIME content type
    
    Returns:
        S3 key (path) of the uploaded file
    
    Raises:
        ClientError: If S3 upload fails
        ValueError: If bucket name is not configured
    """
    if not settings.aws_s3_bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME is not configured")
    
    # Generate S3 key: cases/{case_id}/{image_id}_{filename}
    # Sanitize filename to avoid issues with special characters
    safe_filename = filename.replace(" ", "_")
    s3_key = f"cases/{case_id}/{image_id}_{safe_filename}"
    
    try:
        s3_client = get_s3_client()
        
        # Upload file with metadata
        s3_client.upload_fileobj(
            file_obj,
            settings.aws_s3_bucket_name,
            s3_key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {
                    "case_id": str(case_id),
                    "image_id": str(image_id),
                    "original_filename": filename
                }
            }
        )
        
        logger.info(f"Successfully uploaded file to S3: {s3_key}")
        return s3_key
        
    except ClientError as e:
        logger.error(f"Failed to upload file to S3: {e}")
        raise
    except BotoCoreError as e:
        logger.error(f"AWS error during S3 upload: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during S3 upload: {e}")
        raise


def generate_presigned_url(s3_key: str, expiration: int = 3600) -> Optional[str]:
    """
    Generate a presigned URL for accessing an S3 object.
    
    Args:
        s3_key: S3 key (path) of the object
        expiration: URL expiration time in seconds (default: 1 hour)
    
    Returns:
        Presigned URL string, or None if generation fails
    """
    if not settings.aws_s3_bucket_name:
        logger.warning("AWS_S3_BUCKET_NAME is not configured, cannot generate presigned URL")
        return None
    
    try:
        s3_client = get_s3_client()
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.aws_s3_bucket_name, "Key": s3_key},
            ExpiresIn=expiration
        )
        return url
    except ClientError as e:
        logger.error(f"Failed to generate presigned URL for {s3_key}: {e}")
        return None


def download_file_from_s3(s3_key: str) -> bytes:
    """
    Download an S3 object into memory.

    Raises:
        ValueError: If bucket name is not configured
        ClientError/BotoCoreError: If S3 download fails
    """
    if not settings.aws_s3_bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME is not configured")

    try:
        s3_client = get_s3_client()
        response = s3_client.get_object(
            Bucket=settings.aws_s3_bucket_name,
            Key=s3_key,
        )
        return response["Body"].read()
    except ClientError as e:
        logger.error(f"Failed to download file from S3 {s3_key}: {e}")
        raise
    except BotoCoreError as e:
        logger.error(f"AWS error during S3 download {s3_key}: {e}")
        raise


def delete_file_from_s3(s3_key: str) -> bool:
    """
    Delete a file from S3.
    
    Args:
        s3_key: S3 key (path) of the object to delete
    
    Returns:
        True if deletion succeeded, False otherwise
    """
    if not settings.aws_s3_bucket_name:
        logger.warning("AWS_S3_BUCKET_NAME is not configured, cannot delete from S3")
        return False
    
    try:
        s3_client = get_s3_client()
        s3_client.delete_object(
            Bucket=settings.aws_s3_bucket_name,
            Key=s3_key
        )
        logger.info(f"Successfully deleted file from S3: {s3_key}")
        return True
    except ClientError as e:
        logger.error(f"Failed to delete file from S3 {s3_key}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during S3 deletion: {e}")
        return False


def get_s3_url(s3_key: str) -> str:
    """
    Get the public S3 URL for an object (if bucket is public) or presigned URL.
    
    Args:
        s3_key: S3 key (path) of the object
    
    Returns:
        S3 URL string
    """
    if not settings.aws_s3_bucket_name:
        return ""
    
    # Return standard S3 URL format
    return f"https://{settings.aws_s3_bucket_name}.s3.{settings.aws_s3_region}.amazonaws.com/{s3_key}"

