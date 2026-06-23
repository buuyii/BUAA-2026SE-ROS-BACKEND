import os
import shutil
from pathlib import Path
from django.http import HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from app0.util import response_wrapper, success_api_response, failed_api_response, ErrorCode, parse_data
from app0.models.Map import Map
from app0.models.WayPoint import WayPoint
import xml.etree.ElementTree as ET

@csrf_exempt
@require_POST
@response_wrapper
def upload_map_from_ros(request: HttpRequest):
    """
    ROS 节点调用此 API 上传地图文件。
    请求必须为 multipart/form-data，包含 pgm_file, yaml_file, map_name。
    """
    # 1. 获取表单数据
    map_name = request.POST.get('map_name')
    pgm_file = request.FILES.get('pgm_file')
    yaml_file = request.FILES.get('yaml_file')
    xml_file = request.FILES.get('xml_file')

    if not map_name:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "缺少 map_name")
    if not pgm_file:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "缺少 pgm_file")
    if not yaml_file:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "缺少 yaml_file")

    # 检查地图名称是否重复
    if Map.objects.filter(map_name=map_name).exists():
        return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, "地图名称已存在")

    # 2. 确定保存目录
    maps_dir = Path("~/ros_server/maps").expanduser()
    maps_dir.mkdir(parents=True, exist_ok=True)

    # 3. 保存 pgm 文件
    pgm_path = maps_dir / f"{map_name}.pgm"
    with open(pgm_path, 'wb+') as dest:
        for chunk in pgm_file.chunks():
            dest.write(chunk)

    # 4. 保存 yaml 文件
    yaml_path = maps_dir / f"{map_name}.yaml"
    with open(yaml_path, 'wb+') as dest:
        for chunk in yaml_file.chunks():
            dest.write(chunk)

    # 5.
    xml_path = maps_dir / f"{map_name}.xml"
    with open(xml_path, 'wb+') as dest:
        for chunk in xml_file.chunks():
            dest.write(chunk)

    # 6. 创建 Map 记录
    m = Map.objects.create(
        map_name=map_name,
        map_file_path=str(pgm_path),
        annotation_file_path=str(yaml_path),
    )
    # 7.
    tree = ET.parse(xml_path)
    root = tree.getroot()
    waypoints_to_create = []
    for wp_elem in root.findall('Waypoint'):
        name_elem = wp_elem.find('Name')
        if name_elem is None or not name_elem.text:
            continue
        waypoint_name = name_elem.text.strip()
        pos_x = float(wp_elem.find('Pos_x').text) if wp_elem.find('Pos_x') is not None else 0.0
        pos_y = float(wp_elem.find('Pos_y').text) if wp_elem.find('Pos_y') is not None else 0.0
        pos_z = float(wp_elem.find('Pos_z').text) if wp_elem.find('Pos_z') is not None else 0.0
        ori = float(wp_elem.find('Ori_z').text) if wp_elem.find('Ori_z') is not None else 0.0
        waypoints_to_create.append(
            WayPoint(
                map=m,
                waypoint_name=waypoint_name,
                waypoint_type=WayPoint.PICKUP,   # 默认取货点
                cargo_type=None,                 # 不设置货物类型
                px=pos_x,
                py=pos_y,
                pz=pos_z,
                orientation=ori,
            )
        )
    if waypoints_to_create:
        WayPoint.objects.bulk_create(waypoints_to_create)

    return success_api_response({
        "map_id": m.map_id,
        "map_name": m.map_name,
        "map_file_path": str(pgm_path),
        "annotation_file_path": str(yaml_path),
    })


