from django.http import FileResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from pathlib import Path

from app0.models.Map import Map
from app0.util import response_wrapper, success_api_response, failed_api_response, ErrorCode, parse_data
from app0.api.ros import _map_to_dict


@response_wrapper
@require_http_methods(["GET"])
def map_image(request, map_id):
    try:
        m = Map.objects.get(map_id=map_id)
    except Map.DoesNotExist:
        return failed_api_response(ErrorCode.NOT_FOUND_ERROR, "地图不存在")
    p = Path(m.map_file_path)
    if not p.is_file():
        return failed_api_response(ErrorCode.NOT_FOUND_ERROR, "地图图片文件缺失")
    return FileResponse(open(p, "rb"), content_type="image/png")


@csrf_exempt
@response_wrapper
@require_http_methods(["DELETE"])
def map_delete(request, map_id):
    try:
        m = Map.objects.get(map_id=map_id)
    except Map.DoesNotExist:
        return failed_api_response(ErrorCode.NOT_FOUND_ERROR, "地图不存在")
    for f in (m.map_file_path, m.annotation_file_path):
        try:
            Path(f).unlink(missing_ok=True)
        except Exception:
            pass
    m.delete()
    return success_api_response()


@csrf_exempt
@response_wrapper
@require_http_methods(["PATCH"])
def map_rename(request, map_id):
    try:
        m = Map.objects.get(map_id=map_id)
    except Map.DoesNotExist:
        return failed_api_response(ErrorCode.NOT_FOUND_ERROR, "地图不存在")
    data = parse_data(request) or {}
    name = str(data.get("map_name", "")).strip()
    if not name:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "地图名称不能为空")
    if Map.objects.filter(map_name=name).exclude(map_id=map_id).exists():
        return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, "地图名称重复")
    m.map_name = name
    m.save()
    return success_api_response(_map_to_dict(m))
