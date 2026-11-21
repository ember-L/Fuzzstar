import asyncio

from app.services.media import PhotoStorage
from app.models import MediaUpload, Task

ACTIONS = ('idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right')
MIN_READY = 5
BASE_PROMPT = '将这张猫照片转为绒星风格的卡通分身底图，保持毛色与体态特征，纯色背景，正面全身。'
ACTION_PROMPTS = {
    'idle': 'idle 待机：轻微呼吸起伏与眨眼，循环自然。',
    'happy': 'happy 开心：摇尾蹭头，轻快小跳。',
    'sad': 'sad 难过：低头垂耳，缓慢蜷缩。',
    'sick': 'sick 不适：精神萎靡，趴卧少动。',
    'crouch': 'crouch 蹲伏：压低身体蓄势，警觉张望。',
    'look_left': 'look_left 左看：头部转向左侧再回正。',
    'look_right': 'look_right 右看：头部转向右侧再回正。',
}


class S3Assets:
    """Versioned avatar assets in the same private bucket as photos."""

    def __init__(self, client, bucket):
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls):
        storage = PhotoStorage.from_env()
        return cls(storage.client, storage.bucket) if storage is not None else None

    async def read_photo(self, media: MediaUpload) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket,
                                      Key=media.object_key, VersionId=media.version_id)
        return obj['Body'].read()

    async def read_object(self, key: str, version_id: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket,
                                      Key=key, VersionId=version_id)
        return obj['Body'].read()

    async def write(self, key: str, data: bytes, content_type: str) -> str:
        response = await asyncio.to_thread(self.client.put_object, Bucket=self.bucket,
                                           Key=key, Body=data, ContentType=content_type)
        version = response.get('VersionId')
        if not version:
            raise RuntimeError('avatar bucket must be versioned')
        return version

    async def presign_url(self, key: str, version_id: str) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url, 'get_object',
            Params={'Bucket': self.bucket, 'Key': key, 'VersionId': version_id}, ExpiresIn=3600)


async def generate_avatar(task: Task, media: MediaUpload, *, assets, image_provider, video_provider) -> dict:
    if media.version_id is None:
        raise ValueError('avatar source photo must be verified')
    photo = await assets.read_photo(media)
    base = await image_provider.edit(photo, BASE_PROMPT)
    base_key = f'avatars/{task.pet_id}/{task.id}/base.png'
    base_version = await assets.write(base_key, base.data, base.content_type)
    base_url = await assets.presign_url(base_key, base_version)
    clips = {}
    for action in ACTIONS:
        key = f'avatars/{task.pet_id}/{task.id}/{action}.mp4'
        try:
            clip = await video_provider.image_to_video(base.data, ACTION_PROMPTS[action], image_url=base_url)
            version = await assets.write(key, clip.data, clip.content_type)
            clips[action] = {'status': 'ready', 'key': key, 'version_id': version}
        except Exception:
            # F03-3: one failed clip must not block the remaining actions.
            clips[action] = {'status': 'failed'}
    ready_count = sum(clip['status'] == 'ready' for clip in clips.values())
    return {'base_image': {'key': base_key, 'version_id': base_version},
            'clips': clips, 'ready_count': ready_count, 'usable': ready_count >= MIN_READY}
