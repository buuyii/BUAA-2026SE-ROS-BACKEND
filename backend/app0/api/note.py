# 标注航点类型，放货点 or 取货点
# 标注放货类型

import json
from django.http import HttpRequest
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app0.models.WayPoint import WayPoint
from app0.util import response_wrapper, success_api_response, failed_api_response, ErrorCode, parse_data

@csrf_exempt
@response_wrapper
@require_http_methods(["PATCH"])
def update_waypoint(request: HttpRequest, waypoint_id):
    """
    PATCH /api/navigation/point/<waypoint_id>/
    修改航点的 type 和 cargo_type
    """
    try:
        waypoint = WayPoint.objects.get(waypoint_id=waypoint_id)
    except WayPoint.DoesNotExist:
        return failed_api_response(ErrorCode.NOT_FOUND_ERROR, "航点不存在")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "Invalid JSON")

    new_type = data.get('waypoint_type')
    new_cargo = data.get('cargo_type')

    if new_type is not None:
        valid_types = dict(WayPoint.STATICS_TYPES).keys()
        if new_type not in valid_types:
            return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, f'Invalid waypoint_type, must be one of {list(valid_types)}')
        waypoint.waypoint_type = new_type

    if new_type == WayPoint.DROPOFF:
        if new_cargo is None:
            return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, '放货点必须指定 cargo_type')
        valid_cargos = dict(WayPoint.CARGO_CHOICES).keys()
        if new_cargo not in valid_cargos:
            return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, f'Invalid cargo_type, must be one of {list(valid_cargos)}')
        waypoint.cargo_type = new_cargo
    elif new_type == WayPoint.PICKUP:
        waypoint.cargo_type = None
    else:
        if new_cargo is not None:
            if waypoint.waypoint_type == WayPoint.PICKUP:
                return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, '取货点不能设置 cargo_type')
            valid_cargos = dict(WayPoint.CARGO_CHOICES).keys()
            if new_cargo not in valid_cargos:
                return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, 'Invalid cargo_type')
            waypoint.cargo_type = new_cargo

    try:
        waypoint.full_clean()
    except ValidationError as e:
        return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, str(e.message_dict))

    waypoint.save()
    return success_api_response({
        'waypoint_id': waypoint.waypoint_id,
        'waypoint_type': waypoint.waypoint_type,
        'cargo_type': waypoint.cargo_type,
        'waypoint_name': waypoint.waypoint_name,
        'px': waypoint.px, 'py': waypoint.py, 'pz': waypoint.pz,
        'orientation': waypoint.orientation,
    })