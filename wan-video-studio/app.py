import base64
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time

import httpx
from dotenv import load_dotenv
from flask import Flask, abort, render_template, request, send_file
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

ZHIPU_BASE = 'https://open.bigmodel.cn/api/paas/v4'
DEFAULT_IMAGE_MODEL = 'glm-image'
DEFAULT_IMAGE_SIZE = '1024x1024'
DEFAULT_VIDEO_MODEL = 'Seedance_2.5'
DEFAULT_VISION_MODEL = 'glm-5.3-flash'
MAX_PHOTO = 10 * 1024 * 1024
MAX_DESCRIPTION = 200
PORTRAIT_SIZE = 720  # 形象统一缩到 720×720：舞台预览和 Seedance 首帧共用
VIDEO_WAIT = 1500
STATE_KEEP = 30 * 86400
FORMATS = ['JPEG', 'PNG', 'WEBP', 'BMP']

ACTIONS = {
    'idle': ('待机', '自然慢眨一下', '保持原姿势和视线。若首帧睁眼，只缓慢眨眼一次；若本来闭眼，只表现轻微呼吸。'),
    'happy': ('开心', '轻快抬头', '轻快地将下巴抬高一点，像看到了熟悉的人。嘴巴自然闭合，身体不移动。'),
    'sad': ('低落', '轻轻垂下视线', '只将目光慢慢垂向前方地面，头部和身体保持原位，不流泪。'),
    'sick': ('不适', '安静地半眯眼', '眼睑缓缓垂下一点，像安静休息。保持姿势，不表现伤口、喘气或抽搐。'),
    'crouch': ('伏卧', '胸口轻轻放低', '若可见躯干和前爪，沿原姿势轻屈前肢，让胸口下沉一次；若已伏卧或画面是特写，只轻轻降低头部，不补画画外身体。'),
    'look_left': ('左看', '朝画面左侧看一眼', '目光与头部一起轻转向画面左侧（观众的左手边），幅度很小，身体不转动。'),
    'look_right': ('右看', '朝画面右侧看一眼', '目光与头部一起轻转向画面右侧（观众的右手边），幅度很小，身体不转动。'),
}
IDENTITY = (
    '以上传图为首帧，保持同一只宠物的物种、毛色、花纹、眼睛颜色及耳形。'
    '整体为卡通 2.5D 画风：圆润简化的形体、干净平涂与 2 层柔和分层阴影、成组蓬松绒毛块（不出现写实毛发丝），背景保持纯色 #FEECD4。'
    '保持首帧的构图、背景和主体位置，固定机位，不重构画外部位。开头短暂停住，中间只做一次小动作，结尾自然停稳。'
)
NEGATIVE = '换宠物，毛色或花纹漂移，五官变形，四肢增生，夸张拟人表情，写实毛发，塑料质感，粗黑描边，硬光，背景跳变，镜头移动或变焦，切镜头，画面闪烁。'
# 生图提示词：glm-image 只收文本，先用 glm-5.3-flash 识别照片特征，再拼成完整提示词。
PORTRAIT_REFERENCE = (
    '以识别到的这只宠物为原型，保留它的物种、毛色、花纹、耳形、眼睛颜色与体型比例，重绘成一张完整的全身角色立绘：'
    '从头顶、耳朵到最后一只脚掌和尾巴尖，全部完整落在画面内，任何部位都不被画框裁切；'
    '照片若只拍到半身或局部，请按同一只宠物的毛色与体型合理补全后腿、脚掌和尾巴，不要沿用照片的裁切构图。'
)
PORTRAIT_BODY = (
    '画风：卡通 2.5D，带明显 3D 动画电影质感 —— 圆润立体的形体有清晰体积感与厚度，柔和的全局光照，暗部带轻微环境光遮蔽，边缘一道细软的轮廓光让主体从背景中浮出来；'
    '头略大、眼睛大而圆、口鼻小巧、四肢短圆；毛发概括成几组清晰的蓬松绒毛块，末端少量短毛尖，不画单根写实毛发丝；'
    '整体像高品质 3D 动画电影的角色设定渲染：材质干净、略带哑光绒感，保持卡通比例与简化细节；不要写实摄影感、不要毛绒玩偶实拍感、不要纯 2D 平涂插画。'
    '构图：正方形 1:1，全身完整入画，头顶、耳朵、四只脚掌与尾尖全部可见且不贴边；'
    '宠物为纵向站姿或坐姿（四脚着地、身体朝上延伸），不要横向趴卧、不要压扁身体；'
    '主体居中，高度约占画面 72%，四周留白均衡（上下各约 12%、左右各约 14%）；'
    '平视四分之三侧身，安静看向镜头，姿态自然放松。'
    '背景：纯色 #FEECD4（RGB 254, 236, 212），是明亮偏浅的奶油底色，比常见米色更亮更淡；'
    '完全平涂，无渐变、无暗角、无光斑、无地面线、无道具、无文字；主体脚下只留极淡的柔和接触阴影。'
    '光色：左上方柔和漫射主光，暖调浅阴影，整体明亮干净，主色不超过 4 种。'
)
PORTRAIT_NEGATIVE = '写实毛发，写实渲染，纯 2D 平涂，扁平贴纸感，无体积感，线稿风，毛绒玩偶摄影感，单根毛发丝，渐变背景，背景偏暗，暗角，复杂背景，地面反光，道具，文字，水印，多肢，断肢，尾巴或脚被裁切，横向趴卧，身体被压扁，半身像，胸部以上特写，只画头部和前胸，沿用参考图的裁切构图，四肢出框，尾巴出框，主体贴边，五官畸形，粗黑描边，硬光，镜头畸变，鱼眼，过曝。'
VISION_PROMPT = (
    '观察这张宠物照片，用一段中文客观描述它的外形特征，供画师按描述重绘。必须覆盖：'
    '物种与品种倾向；毛色与花纹分布（哪里是什么颜色）；耳朵形状与朝向；眼睛颜色；'
    '体型与姿态（站/坐/趴，朝向）；胡须、爪色、尾形等明显特征。只描述可见特征，不猜测情绪，不超过 150 字。'
)

# ═══════════════════════════════════════════════════════════════════════
# 提示词配置区（页面上不再填写提示词）：改这里，保存后重启工作台即生效
# ═══════════════════════════════════════════════════════════════════════
# 主人补充描述：描述这只宠物独有的外形特征，会拼进生图提示词；留空则跳过。
# 例如：'耳朵尖有一撮白毛，浅蓝色眼睛，尾巴很蓬松'
PET_EXTRA_DESCRIPTION = ''

# 对比提示词：填写后每次生成形象时，网页会额外用它重绘一版形象做并排对比；
# 只影响网页展示，不参与视频生成；留空则不做对比图（省一次生图费用）。
# 例如：'Q 版盲盒手办风，保留原毛色与花纹' / '改成像素风格，保留橘白毛色'
COMPARE_PROMPT = 'Q 版盲盒手办风，保留原毛色与花纹'
# ═══════════════════════════════════════════════════════════════════════


class JobError(RuntimeError):
    """生成任务失败，消息会原样展示给页面。"""


def create_app(state_dir=None, worker=None):
    app = Flask(__name__)
    app.json.ensure_ascii = False
    host = os.getenv('WAN_STUDIO_HOST', '').strip()
    password = os.getenv('WAN_STUDIO_PASSWORD', '')
    if host and (not re.fullmatch(r'[a-zA-Z0-9.-]+', host) or not password):
        raise ValueError('WAN_STUDIO_HOST 必须是域名（不含协议或端口），且必须设置 WAN_STUDIO_PASSWORD。')

    api_key = os.getenv('ZHIPU_API_KEY', '').strip()
    vision_model = os.getenv('ZHIPU_VISION_MODEL', '').strip() or DEFAULT_VISION_MODEL
    image_model = os.getenv('ZHIPU_IMAGE_MODEL', '').strip() or DEFAULT_IMAGE_MODEL
    image_size = os.getenv('ZHIPU_IMAGE_SIZE', '').strip() or DEFAULT_IMAGE_SIZE
    video_model = os.getenv('JIMENG_VIDEO_MODEL', '').strip() or DEFAULT_VIDEO_MODEL
    cli = os.getenv('JIMENG_CLI', '').strip() or 'jimeng-novel'
    cli_path = shutil.which(cli) or (cli if os.path.isfile(cli) else '')
    project_id = os.getenv('JIMENG_PROJECT_ID', '').strip()
    image_ready = bool(api_key)
    video_ready = bool(cli_path)

    app.config.update(TRUSTED_HOSTS=['127.0.0.1', 'localhost', '[::1]'] + ([host] if host else []),
                      MAX_CONTENT_LENGTH=MAX_PHOTO + 64 * 1024, MAX_FORM_PARTS=4)
    state_dir = state_dir or os.getenv('WAN_STUDIO_STATE_DIR', '').strip() or os.path.join(app.root_path, 'state')
    photos = os.path.join(state_dir, 'photos')
    images = os.path.join(state_dir, 'images')
    videos = os.path.join(state_dir, 'videos')
    jobs = os.path.join(state_dir, 'jobs')
    for folder in (photos, images, videos, jobs):
        os.makedirs(folder, exist_ok=True)
    cleanup(state_dir)
    for job_id in os.listdir(jobs):
        job = read_job(os.path.join(jobs, job_id, 'job.json'))
        if job and job.get('status') in ('queued', 'running'):
            job.update(status='failed', stage='已中断', error='工作台重启，任务已中断；请重新生成。')
            write_job(os.path.join(jobs, job_id, 'job.json'), job)

    @app.before_request
    def authenticate():
        if password:
            import hmac
            auth = request.authorization
            if (not auth or auth.type != 'basic' or auth.username != 'studio'
                    or not hmac.compare_digest((auth.password or '').encode(), password.encode())):
                return '此工作台需要登录。', 401, {'WWW-Authenticate': 'Basic realm="Wan Video Studio", charset="UTF-8"'}

    @app.after_request
    def protect(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.endpoint in ('video_file', 'image_file', 'photo_file'):
            response.headers['Cache-Control'] = 'private, max-age=3600'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
            "script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.errorhandler(HTTPException)
    def error(exc):
        detail = {413: '照片过大，请压缩后重试。', 404: '文件不存在或已过期。'}.get(exc.code, exc.description)
        return {'detail': detail}, exc.code

    def guard():
        if request.headers.get('X-Studio-Request') != '1' or request.headers.get('Sec-Fetch-Site') == 'cross-site':
            abort(403, '请从工作台页面提交任务。')

    def zhipu_headers():
        return {'Authorization': f'Bearer {api_key}'}

    def vision_describe(photo_bytes):
        """glm-5.3-flash 读照片，输出外形特征描述，供 glm-image 重绘参考。"""
        small = downscale(photo_bytes, 768, 'JPEG')
        data_url = 'data:image/jpeg;base64,' + base64.b64encode(small).decode()
        try:
            response = httpx.request('POST', f'{ZHIPU_BASE}/chat/completions', headers=zhipu_headers(),
                                     json={'model': vision_model, 'temperature': 0.2, 'max_tokens': 2048,
                                           'messages': [{'role': 'user', 'content': [
                                               {'type': 'image_url', 'image_url': {'url': data_url}},
                                               {'type': 'text', 'text': VISION_PROMPT},
                                           ]}]},
                                     timeout=120)
        except httpx.RequestError:
            abort(504, '照片识别请求超时或网络中断，请稍后重试。')
        data = parse_json(response)
        choices = data.get('choices') if isinstance(data, dict) else None
        content = ''
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get('message')
            if isinstance(message, dict):
                content = str(message.get('content') or '').strip()
        if not content:
            abort(502, upstream_message(data, response.status_code, f'照片识别失败（{vision_model}）'))
        return content[:300]

    def zhipu_image(prompt):
        try:
            response = httpx.request('POST', f'{ZHIPU_BASE}/images/generations', headers=zhipu_headers(),
                                     json={'model': image_model, 'prompt': prompt, 'size': image_size},
                                     timeout=180)
        except httpx.RequestError:
            abort(504, '生图请求超时或网络中断，可稍后重试；不要连续重复提交。')
        data = parse_json(response)
        items = data.get('data') if isinstance(data, dict) else None
        if isinstance(items, list) and items and isinstance(items[0], dict):
            url = https_url(items[0].get('url'))
            b64 = items[0].get('b64_json')
            if url:
                try:
                    image = httpx.request('GET', url, timeout=120)
                except httpx.RequestError:
                    abort(502, '生成的图片下载失败，请稍后重新生成。')
                if (not image.is_success or not image.headers.get('Content-Type', '').startswith('image/')
                        or len(image.content) > MAX_PHOTO):
                    abort(502, '生图服务返回的图片无效或过大，请重新生成。')
                return image.content
            if b64:
                try:
                    return base64.b64decode(b64)
                except (ValueError, TypeError):
                    abort(502, '生图服务返回的图片无法解析，请重新生成。')
        abort(502, upstream_message(data, response.status_code, '智谱生图失败'))

    @app.get('/')
    def index():
        return render_template('index.html', image_model=image_model, vision_model=vision_model,
                               video_model=video_model, actions=ACTIONS, identity=IDENTITY, negative=NEGATIVE,
                               portrait_prompt=PORTRAIT_REFERENCE + PORTRAIT_BODY, portrait_negative=PORTRAIT_NEGATIVE,
                               durations=(4, 5, 6), image_ready=image_ready, video_ready=video_ready)

    @app.post('/api/portrait')
    def generate_portrait():
        guard()
        if not image_ready:
            abort(503, '请在 .env 中设置 ZHIPU_API_KEY 后重启工作台。')
        upload = request.files.get('image')
        if not upload or not upload.filename:
            abort(400, '请先上传一张宠物照片。')
        raw = upload.read()
        if len(raw) > MAX_PHOTO:
            abort(413, '照片超过 10 MB，请换一张小一些的。')
        photo = normalize_photo(raw)
        description = (PET_EXTRA_DESCRIPTION or '').strip()[:MAX_DESCRIPTION]
        features = vision_describe(photo)
        prompt = '；'.join(part for part in (PORTRAIT_REFERENCE, '照片特征：' + features,
                                            f'主人补充：{description}' if description else '', PORTRAIT_BODY) if part)
        photo_id = secrets.token_hex(12)
        with open(os.path.join(photos, photo_id + '.png'), 'wb') as saved:
            saved.write(photo)
        portrait = validate_image(zhipu_image(prompt))
        portrait = downscale(portrait, PORTRAIT_SIZE, 'PNG')
        image_id = secrets.token_hex(12)
        with open(os.path.join(images, image_id + '.png'), 'wb') as saved:
            saved.write(portrait)
        data_url = 'data:image/png;base64,' + base64.b64encode(portrait).decode()
        result = {'image_id': image_id, 'image': data_url,
                  'download_url': f'/api/images/{image_id}/image?download=1'}
        # 对比提示词来自顶部配置区：只重绘一版形象在网页上并排展示，视频首帧仍用原形象。
        compare_prompt = (COMPARE_PROMPT or '').strip()[:1000]
        if compare_prompt:
            style = ('；'.join(filter(None, (
                PORTRAIT_REFERENCE, '照片特征：' + features,
                '画风与效果要求（以下要求优先，覆盖默认画风）：' + compare_prompt,
                '构图硬性要求：正方形 1:1 全身立绘，主体完整不裁切，纯色 #FEECD4 背景。'))))
            compare = validate_image(zhipu_image(style))
            compare = downscale(compare, PORTRAIT_SIZE, 'PNG')
            compare_id = secrets.token_hex(12)
            with open(os.path.join(images, compare_id + '.png'), 'wb') as saved:
                saved.write(compare)
            result['compare'] = {'image_id': compare_id,
                                 'image': 'data:image/png;base64,' + base64.b64encode(compare).decode(),
                                 'download_url': f'/api/images/{compare_id}/image?download=1'}
        return result

    @app.get('/api/images/<image_id>/image')
    def image_file(image_id):
        if not re.fullmatch(r'[0-9a-f]{24}', image_id):
            abort(404)
        path = os.path.join(images, image_id + '.png')
        if not os.path.isfile(path):
            abort(404)
        return send_file(path, mimetype='image/png', as_attachment=request.args.get('download') == '1',
                         download_name='绒星-形象.png', conditional=True, max_age=0)

    @app.get('/api/photos/<photo_id>/image')
    def photo_file(photo_id):
        if not re.fullmatch(r'[0-9a-f]{24}', photo_id):
            abort(404)
        path = os.path.join(photos, photo_id + '.png')
        if not os.path.isfile(path):
            abort(404)
        return send_file(path, mimetype='image/png', conditional=True, max_age=0)

    @app.post('/api/videos')
    def submit_video():
        guard()
        if not video_ready:
            abort(503, '未找到 jimeng-novel CLI，请先安装并登录即梦后再重启工作台。')
        payload = request.get_json(silent=True) or {}
        image_id = payload.get('image_id') or ''
        if not re.fullmatch(r'[0-9a-f]{24}', image_id) or not os.path.isfile(os.path.join(images, image_id + '.png')):
            abort(404, '请先生成并确认宠物形象。')
        action = payload.get('action') or ''
        if action not in ACTIONS:
            abort(400, '请选择一个动作。')
        title, motion, description = ACTIONS[action]
        try:
            duration = int(payload.get('duration') or 5)
        except (TypeError, ValueError):
            abort(400, '视频时长必须是整数秒。')
        if not 4 <= duration <= 10:
            abort(400, '视频时长需在 4–10 秒之间。')

        prompt = f'{IDENTITY} 动作要求：{title}——{motion}。{description} 反面要求：{NEGATIVE}'
        job_id = secrets.token_hex(8)
        job_dir = os.path.join(jobs, job_id)
        os.makedirs(job_dir, exist_ok=True)
        shutil.copyfile(os.path.join(images, image_id + '.png'), os.path.join(job_dir, 'first.png'))
        with open(os.path.join(job_dir, 'prompt.txt'), 'w', encoding='utf-8') as saved:
            saved.write(prompt)
        job = {'id': job_id, 'status': 'queued', 'stage': '排队中', 'action': title, 'image_id': image_id,
               'duration': duration, 'ratio': '1:1', 'resolution': '720p', 'created_at': time.time(),
               'error': None, 'credits': None,
               'state_dir': state_dir, 'job_dir': job_dir, 'cli': cli_path or cli, 'video_model': video_model,
               'project_id': project_id,
               # jimeng CLI 在仓库根目录执行（在任务目录里执行会导致提交无法被服务端受理）
               'cwd': os.path.dirname(os.path.dirname(state_dir))}
        write_job(os.path.join(job_dir, 'job.json'), job)
        start_job(app, job, worker or run_video_job)
        return {'job_id': job_id}, 202

    @app.get('/api/videos/<job_id>')
    def video_status(job_id):
        job = read_job(os.path.join(jobs, job_id, 'job.json')) if re.fullmatch(r'[0-9a-f]{16}', job_id) else None
        if not job:
            abort(404)
        done = job.get('status') == 'succeeded'
        return {'status': job.get('status'), 'stage': job.get('stage'), 'error': job.get('error'),
                'action': job.get('action'), 'credits': job.get('credits'),
                'elapsed': round(time.time() - job.get('created_at', time.time())),
                'video_url': f'/api/videos/{job_id}/video' if done else None,
                'download_url': f'/api/videos/{job_id}/video?download=1' if done else None}

    @app.get('/api/videos/<job_id>/video')
    def video_file(job_id):
        if not re.fullmatch(r'[0-9a-f]{16}', job_id):
            abort(404)
        path = os.path.join(videos, job_id + '.mp4')
        if not os.path.isfile(path):
            abort(404)
        return send_file(path, mimetype='video/mp4', as_attachment=request.args.get('download') == '1',
                         download_name=f'绒星-动作-{job_id[:8]}.mp4', conditional=True, max_age=0)

    def start_job(application, job, runner):
        job_dir = job['job_dir']
        job_file = os.path.join(job_dir, 'job.json')

        def update(**fields):
            current = read_job(job_file) or dict(job)
            current.update(fields)
            write_job(job_file, current)

        def target():
            update(status='running', stage='准备提交')
            try:
                result = runner(job, update)
            except JobError as exc:
                update(status='failed', stage='已失败', error=str(exc))
            except Exception:  # noqa: BLE001 - 后台任务兜底，避免线程静默退出
                application.logger.exception('jimeng job %s failed', job['id'])
                update(status='failed', stage='已失败', error='生成视频失败，请查看工作台日志后重试。')
            else:
                current = read_job(job_file) or dict(job)
                current.update(status='succeeded', stage='已完成', error=None,
                               credits=result.get('credits'), video=result.get('video'))
                write_job(job_file, current)

        threading.Thread(target=target, daemon=True, name=f'jimeng-{job["id"]}').start()

    return app


CANVAS_LOCK = threading.Lock()


def run_video_job(job, update):
    """用 jimeng-novel 把形象图交给 Seedance 生成视频，成功返回本地路径。"""
    job_dir = job['job_dir']
    project = job.get('project_id') or ensure_canvas(job, job['cli'], job['state_dir'], CANVAS_LOCK)
    key = f'job/{job["id"]}'
    update(stage='提交任务')
    run_cli(job, ['node', 'create', '--project-id', project, '--key', key, '--type', 'video',
                  '--model', job['video_model'], '--prompt-file', os.path.join(job_dir, 'prompt.txt'),
                  '--first-frame', 'file:' + os.path.join(job_dir, 'first.png'),
                  '--param', f'duration={job["duration"]}', '--param', f'ratio={job["ratio"]}',
                  '--param', f'resolution={job["resolution"]}', '-j'], timeout=180)
    data = submit_task(job, project, key, update)
    status, item = node_state(data)
    deadline = time.time() + VIDEO_WAIT
    update(stage='生成中')
    while status != 'succeeded' and time.time() < deadline:
        data = run_cli(job, ['node', 'result', '--project-id', project, '--key', key, '--wait', '120',
                             '--out', job_dir + os.sep, '-j'], timeout=180)
        status, item = node_state(data)
        if status == 'failed':
            raise JobError(node_error(item) or '视频生成失败，请调整动作后重试。')
        update(stage='生成中')
    if status != 'succeeded':
        raise JobError('视频生成超时；可稍后在即梦画布查看该任务是否完成。')
    video = find_video(job_dir)
    if not video:
        raise JobError('任务已完成，但没有下载到视频文件。')
    os.makedirs(os.path.join(job['state_dir'], 'videos'), exist_ok=True)
    target = os.path.join(job['state_dir'], 'videos', job['id'] + '.mp4')
    os.replace(video, target)
    return {'video': target, 'credits': credits(item)}


def submit_task(job, project, key, update):
    """提交视频任务。提交结果未知（网络中断或服务端未受理）时先重置节点再试一次：
    未受理的任务不会计费，重试不会重复扣费；已受理则直接沿用运行中的任务。"""
    last = None
    for attempt in (1, 2):
        uncertain = False
        try:
            data = run_cli(job, ['node', 'run', '--project-id', project, '--key', key, '--wait', '60',
                                 '--out', job['job_dir'] + os.sep, '-j'], timeout=180)
        except JobError as exc:
            last = exc
            uncertain = any(tag in str(exc) for tag in ('不确定', 'unknown', 'TASK_NOT_FOUND'))
        else:
            status, item = node_state(data)
            if status in ('queued', 'running', 'succeeded'):
                return data
            error = node_error(item) or cli_error(data) or '即梦拒绝了视频任务，请检查提示词后重试。'
            last = JobError(error)
            uncertain = 'TASK_NOT_FOUND' in error or '不存在' in error
        if attempt == 1 and uncertain:
            try:
                run_cli(job, ['node', 'reset', '--project-id', project, '--key', key, '-j'], timeout=120)
            except JobError:
                pass
            update(stage='重新提交')
            continue
        raise last
    raise last


def ensure_canvas(job, cli, state_dir, lock):
    path = os.path.join(state_dir, 'canvas.json')
    with lock:
        saved = read_job(path)
        if saved and saved.get('project_id'):
            return saved['project_id']
        data = run_cli(job, ['canvas', 'create', '--name', '绒星-图片视频工作台', '-j'], timeout=120)
        project = (data.get('data') or {}).get('projectId') if isinstance(data.get('data'), dict) else None
        if not project:
            raise JobError('无法创建即梦画布，请先在终端执行 jimeng-novel login 后重试。')
        write_job(path, {'project_id': project})
        return project


def run_cli(job, args, timeout):
    command = [job['cli']] + args
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout,
                              cwd=job.get('cwd') or job['job_dir'], text=True,
                              encoding='utf-8', errors='replace')
    except FileNotFoundError:
        raise JobError('找不到 jimeng-novel CLI，请安装并确认它在 PATH 中。')
    except subprocess.TimeoutExpired:
        raise JobError('即梦 CLI 调用超时；任务可能仍在生成，请先到即梦画布核对，不要重复提交。')
    except OSError:
        raise JobError('无法启动 jimeng-novel CLI，请检查本机安装。')
    data = parse_cli(proc.stdout)
    if proc.returncode != 0 or (isinstance(data, dict) and data.get('status') == 'error'):
        raise JobError(cli_error(data) or (proc.stderr or proc.stdout or '').strip()[-300:] or '即梦 CLI 执行失败。')
    return data


def parse_cli(raw):
    text = (raw or '').strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {'status': 'error', 'error': {'message': text[-300:]}}


def cli_error(data):
    if not isinstance(data, dict):
        return ''
    error = data.get('error')
    if isinstance(error, dict):
        message = error.get('message') or error.get('code') or ''
        hint = error.get('hint') or ''
        return (str(message) + ('；' + str(hint) if hint else '')).strip()
    if isinstance(error, str):
        return error
    return str(data.get('message') or '')


def node_state(data):
    if not isinstance(data, dict):
        return '', {}
    body = data.get('data')
    items = body.get('items') if isinstance(body, dict) and isinstance(body.get('items'), list) else None
    candidates = items if items else ([body] if isinstance(body, dict) else [])
    for item in candidates:
        if isinstance(item, dict) and item.get('status'):
            return str(item['status']).lower(), item
    return '', {}


def node_error(item):
    if not isinstance(item, dict):
        return ''
    error = item.get('error')
    if isinstance(error, dict):
        return str(error.get('message') or error.get('code') or '')
    return str(error or item.get('message') or '')


def credits(item):
    value = item.get('credits') if isinstance(item, dict) else None
    if isinstance(value, dict):
        return value.get('deducted') or value.get('total') or 0
    if isinstance(value, (int, float)):
        return value
    return 0


def find_video(job_dir):
    newest = None
    for root, _, files in os.walk(job_dir):
        for name in files:
            if name.lower().endswith('.mp4'):
                path = os.path.join(root, name)
                if newest is None or os.path.getmtime(path) > os.path.getmtime(newest):
                    newest = path
    return newest


def parse_json(response):
    try:
        return response.json()
    except ValueError:
        return None


def upstream_message(data, status, fallback):
    message = code = ''
    if isinstance(data, dict):
        error = data.get('error')
        if isinstance(error, dict):
            message = error.get('message') or ''
            code = error.get('code') or ''
        elif isinstance(error, str):
            message = error
        message = message or data.get('message') or data.get('msg') or ''
        code = code or data.get('code') or ''
    detail = '：'.join(part for part in (str(code), str(message)) if part)
    return f'{fallback}（{detail or status}）'


def normalize_photo(raw):
    """校验上传照片并统一转成 PNG；透明图铺奶油底色，与舞台一致。"""
    cream = (254, 236, 212)
    try:
        with Image.open(io.BytesIO(raw), formats=FORMATS) as image:
            image.load()
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGBA')
                background = Image.new('RGB', image.size, cream)
                background.paste(image, mask=image.split()[-1])
                image = background
            else:
                image = image.convert('RGB')
            output = io.BytesIO()
            image.save(output, 'PNG')
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        abort(400, '请上传 JPG、PNG、WebP 或 BMP 格式的照片。')


def validate_image(photo):
    try:
        with Image.open(io.BytesIO(photo), formats=FORMATS) as image:
            width, height = image.size
            if not (240 <= min(width, height) and max(width, height) <= 4096):
                raise ValueError('size')
            if max(width, height) > 8 * min(width, height):
                raise ValueError('ratio')
            image.load()
            output = io.BytesIO()
            image.convert('RGB').save(output, 'PNG')
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        abort(502, '生图服务返回的图片无法作为视频首帧使用，请重新生成。')


def downscale(photo, box, fmt):
    with Image.open(io.BytesIO(photo)) as image:
        image = image.convert('RGB')
        image.thumbnail((box, box), Image.LANCZOS)
        output = io.BytesIO()
        image.save(output, fmt, quality=90 if fmt == 'JPEG' else None)
        return output.getvalue()


def https_url(value):
    try:
        from urllib.parse import urlsplit
        parsed = urlsplit(value) if isinstance(value, str) else None
        if parsed and parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return ''


def read_job(path):
    try:
        with open(path, encoding='utf-8') as saved:
            data = json.load(saved)
            return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_job(path, job):
    temp = path + '.tmp'
    with open(temp, 'w', encoding='utf-8') as saved:
        json.dump(job, saved, ensure_ascii=False)
    os.replace(temp, path)


def cleanup(state_dir):
    cutoff = time.time() - STATE_KEEP
    for folder in ('photos', 'images', 'videos', 'jobs'):
        root = os.path.join(state_dir, folder)
        for name in os.listdir(root):
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
            except OSError:
                pass


if __name__ == '__main__':
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
    create_app().run(host='127.0.0.1', port=5050)
