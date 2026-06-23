import uuid
from pathlib import Path

from app0.util import response_wrapper, success_api_response, failed_api_response, ErrorCode

import subprocess
from django.core.validators import validate_slug
from django.core.exceptions import ValidationError
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

UPLOAD_DIR = Path("~").expanduser() / "ros_server" / "uploaded_files"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@response_wrapper
@csrf_exempt
@require_POST
def upload_file(request):
    """接收 multipart/form-data 的文件上传请求。"""
    upload = request.FILES.get('file')
    if upload is None:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "未找到上传文件，请使用 field 名称 file")

    original_filename = upload.name
    saved_filename = f"{uuid.uuid4().hex}_{original_filename}"
    dest_path = UPLOAD_DIR / saved_filename

    try:
        with open(dest_path, 'wb+') as dest_file:
            for chunk in upload.chunks():
                dest_file.write(chunk)
    except Exception as exc:
        return failed_api_response(ErrorCode.FILE_WRITE_ERROR, "文件数据块写入过程中发生异常: {}".format(str(exc)))

    return success_api_response(
        {
            'original_filename': original_filename,
            'saved_filename': saved_filename,
            'saved_path': str(dest_path),
        }
    )


