import io
import os
from contextlib import closing
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image
from pillow_heif import register_heif_opener

from app.auth import APIError
from app.models import MediaUpload

MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTO_PIXELS = 25_000_000
UPLOAD_SECONDS = 600
DOWNLOAD_SECONDS = 3600
FORMATS = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/heic': 'HEIF'}
register_heif_opener(thumbnails=False)


def storage_unavailable() -> APIError:
    return APIError(503, 'MEDIA_UNAVAILABLE', '照片存储暂不可用')


class PhotoStorage:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls):
        endpoint, bucket, key, secret = (os.environ.get(f'MEDIA_S3_{name}', '').strip()
                                         for name in ('ENDPOINT', 'BUCKET', 'ACCESS_KEY', 'SECRET_KEY'))
        if not any((endpoint, bucket, key, secret)):
            return None
        parsed = urlsplit(endpoint)
        if not all((bucket, key, secret, parsed.hostname)) or parsed.username is not None or parsed.query or parsed.fragment:
            raise RuntimeError('Configure MEDIA_S3_ENDPOINT, BUCKET, ACCESS_KEY and SECRET_KEY together')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')):
            raise RuntimeError('Media storage requires HTTPS except on localhost')
        client = boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=key, aws_secret_access_key=secret,
                              region_name=os.environ.get('MEDIA_S3_REGION', 'us-east-1'),
                              config=Config(signature_version='s3v4', s3={'addressing_style': 'path'},
                                            connect_timeout=3, read_timeout=10, retries={'total_max_attempts': 1}))
        return cls(client, bucket)

    def presign(self, photo: MediaUpload) -> dict:
        try:
            return self.client.generate_presigned_post(
                Bucket=self.bucket, Key=photo.object_key, Fields={'Content-Type': photo.content_type},
                Conditions=[{'Content-Type': photo.content_type}, ['content-length-range', photo.size_bytes, photo.size_bytes]],
                ExpiresIn=UPLOAD_SECONDS,
            )
        except (BotoCoreError, ClientError) as exc:
            raise storage_unavailable() from exc

    def download_url(self, photo: MediaUpload) -> str:
        try:
            return self.client.generate_presigned_url('get_object', Params={
                'Bucket': self.bucket, 'Key': photo.object_key, 'VersionId': photo.version_id,
                'ResponseContentDisposition': 'attachment',
            }, ExpiresIn=DOWNLOAD_SECONDS)
        except (BotoCoreError, ClientError) as exc:
            raise storage_unavailable() from exc

    def asset_url(self, key: str, version_id: str) -> str:
        try:
            return self.client.generate_presigned_url('get_object', Params={
                'Bucket': self.bucket, 'Key': key, 'VersionId': version_id,
            }, ExpiresIn=DOWNLOAD_SECONDS)
        except (BotoCoreError, ClientError) as exc:
            raise storage_unavailable() from exc

    def verify(self, photo: MediaUpload) -> str:
        ref = {'Bucket': self.bucket, 'Key': photo.object_key}
        try:
            head = self.client.head_object(**ref)
            if head['ContentLength'] != photo.size_bytes or head.get('ContentType') != photo.content_type:
                raise APIError(422, 'MEDIA_INVALID', '照片类型或大小与申请不一致')
            version = head.get('VersionId')
            if not version or version == 'null' or len(version) > 1024:
                raise storage_unavailable()
            with closing(self.client.get_object(**ref, VersionId=version)['Body']) as body:
                data = body.read(photo.size_bytes + 1)
        except ClientError as exc:
            if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
                raise APIError(409, 'MEDIA_NOT_UPLOADED', '尚未收到照片，请先上传') from exc
            raise storage_unavailable() from exc
        except BotoCoreError as exc:
            raise storage_unavailable() from exc
        if len(data) != photo.size_bytes or not valid_photo(data, photo.content_type):
            raise APIError(422, 'MEDIA_INVALID', '照片格式无效或像素超限')
        return version


def valid_photo(data: bytes, content_type: str) -> bool:
    try:
        with Image.open(io.BytesIO(data), formats=[FORMATS[content_type]]) as image:
            if image.width * image.height > MAX_PHOTO_PIXELS or getattr(image, 'n_frames', 1) != 1:
                return False
            if content_type == 'image/heic' and image.custom_mimetype != content_type:
                return False
            image.load()
    except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError):
        return False
    return True
