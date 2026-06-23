import os
import time
from enum import unique, Enum

from django.http import HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from roslibpy.core import RosTimeoutError

from app0.models.Map import Map
from app0.models.WayPoint import WayPoint

from app0.ros_util import ROSClient, ctrl_template, require_ros, \
    ros_wrap_point, info_msg_template, navigation_task_template
from app0.util import response_wrapper, success_api_response, failed_api_response, ErrorCode, \
    parse_data



from pathlib import Path
import cv2
import roslibpy
import yaml as _yaml
from app0.models.TaskRecord import TaskRecord
from backend.settings import ROS_HOST, ROS_PORT, DEBUG
import xml.etree.ElementTree as ET

from django.core.management import call_command
import shutil


def _map_to_dict(m):
    origin = [0.0, 0.0, 0.0]
    resolution = 0.05
    try:
        with open(str(m.annotation_file_path)) as f:
            y = _yaml.safe_load(f) or {}
            resolution = float(y.get("resolution", 0.05))
            o = y.get("origin", [0, 0, 0])
            origin = [float(o[0]), float(o[1]), float(o[2]) if len(o) > 2 else 0.0]
    except Exception:
        pass
    return {
        "map_id": m.map_id, "map_name": m.map_name,
        "map_file_path": m.map_file_path, "annotation_file_path": m.annotation_file_path,
        "origin": origin, "resolution": resolution,
        "create_time": m.create_time.isoformat(), "update_time": m.update_time.isoformat()
    }


def _wp_to_dict(w):
    return {
        "waypoint_id": w.waypoint_id, "waypoint_name": w.waypoint_name,
        "waypoint_type": w.waypoint_type, "cargo_type": w.cargo_type,
        "px": w.px, "py": w.py, "pz": w.pz, "orientation": w.orientation,
        "map_id": w.map_id, "create_time": w.create_time.isoformat()
    }
@unique
class CtrlType(Enum):
    STOP_FORCE = 0
    EXIT = 1

    # map
    MAPPING_START = 20
    MAPPING_END = 21
    MAPPING_SAVE_MAP = 23

    # NAV
    NAV_GOTO_POINT = 33
    NAV_STOP = 34

    # GRUB
    TASK_START = 41
    
def check_connect():
    ros_client = ROSClient()
    # 如果没有 client 则创建
    if ros_client.client is None:
        try:
            ros_client.reset(host=ROS_HOST, port=ROS_PORT)
        except RosTimeoutError:
            return False
    # 如果连接失败，2s 内检查10次，roslibpy 会自动尝试重新连接
    count = 10
    while not ros_client.is_connect and count >= 0:
        time.sleep(0.2)
        count -= 1
    # 如果还是没连上，记连接失败
    if not ros_client.is_connect:
        ros_client.failed_count += 1
        # 如果3次都连接失败，则断开
        if ros_client.failed_count >= 3:
            ros_client.exit()
            return False
    ros_client.failed_count = 0
    return True

@response_wrapper
def ros_connect(request: HttpRequest):
    """
    [GET] /api/ros/connect
    """
    ros_client = ROSClient()
    if ros_client.client is None:
        try:
            ros_client.reset(host=ROS_HOST, port=ROS_PORT)
        except RosTimeoutError:
            return failed_api_response(ErrorCode.ROS_CONNECT_FAILED, "ROS连接失败，请检查相关配置是否正确以及网络是否连通")
    return success_api_response({"connect": True})

@require_GET
@response_wrapper
def get_ros_connect_status(request: HttpRequest):
    """
    [GET] /api/ros/connect_status
    """
    return success_api_response({"connect": ROSClient().is_connect})


@require_GET
@response_wrapper
def ros_free(request: HttpRequest):
    """
    [GET] /api/ros/free
    """
    if ROSClient().client is None:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "状态错误，不存在已连接的ROSClient！")
    ROSClient().exit()
    return success_api_response()


"""==========================================  Mapping  ==============================================="""
@require_GET
@response_wrapper
@require_ros
def get_ros_map_list(request: HttpRequest):
    """
    [GET] /api/maps/ros_map_list/
    调用 ROS 服务获取服务器本地已保存的地图名称列表。
    """
    ros_client = ROSClient()
    try:
        map_names = ros_client.get_map_list()
        return success_api_response({"map_names": map_names})
    except Exception as e:
        return failed_api_response(ErrorCode.ROS_CONNECT_FAILED, f"获取地图列表失败: {str(e)}")

@csrf_exempt
@require_POST
@response_wrapper
@require_ros
def mapping_save(request: HttpRequest):
    """
    [POST] /api/mapping/save
    body: JSON {name: string}
    """
    data = parse_data(request)
    if not data or "name" not in data:
        return failed_api_response(ErrorCode.BAD_REQUEST_ERROR, "缺少 name 字段")
    name = str(data["name"]).strip()
    if not name:
        return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, "地图名称不能为空")
    if Map.objects.filter(map_name=name).exists():
        return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, "地图名称重复")
    if not check_connect():
        return failed_api_response(ErrorCode.ROS_CONNECT_FAILED, "ROS未连接，无法保存地图")
    
    ros = ROSClient()
    ros.trigger_save_map(name)

    return success_api_response({"msg": "ROS开始上传地图"})

@csrf_exempt
@response_wrapper
@require_GET
def map_image(request: HttpRequest, map_id: int):
    """
    [GET] /api/maps/<map_id>/image/
    返回地图的PNG图片数据，用于前端<img>渲染。
    由于带宽不太够，这个不能频繁调用，前端要做缓存
    """
    try:
        map_obj = Map.objects.get(map_id=map_id)
    except Map.DoesNotExist:
        return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, "地图不存在")

    img_path = map_obj.map_file_path
    if not img_path or not os.path.exists(img_path):
        return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, "图片资源不存在")

    # 读取图片二进制
    with open(img_path, 'rb') as f:
        image_data = f.read()

    # 返回PNG图片
    return success_api_response({"data": image_data})

"""==========================================  Navigating  ==============================================="""

@require_GET
@response_wrapper
@require_ros
def navigation_to(request: HttpRequest, query_id):
    """
    [GET] /api/navigation/to/<query_id>
    """
    try:
        p = WayPoint.objects.get(waypoint_id=query_id)
    except WayPoint.DoesNotExist:
        return failed_api_response(ErrorCode.NOT_FOUND_ERROR, "航点不存在")

    name = p.waypoint_name
    px = p.px
    py = p.py
    pz = p.pz

    # 导航到 对应位置
    ros_client = ROSClient()
    """
    # 导航任务消息类型
    # type 取值:
    #   "pose"      - 绝对坐标导航 (需填充 pose)
    #   "waypoint"  - 航点导航 (需填充 waypoint_name)
    #   "relative"  - 相对移动 (需填充 dx, dy, dtheta_deg)

    string type

    # 绝对坐标目标 (type="pose" 时使用)
    geometry_msgs/PoseStamped pose

    # 航点名称 (type="waypoint" 时使用)
    string waypoint_name

    # 相对移动参数 (type="relative" 时使用)
    # dx: 前后移动 (正=前进，负=后退)
    # dy: 左右移动 (正=左移，负=右移)
    # dtheta_deg: 旋转角度 (正=左转，负=右转)
    float32 dx
    float32 dy
    float32 dtheta_deg
    """
    
    msg = navigation_task_template()
    msg["type"] = "waypoint_name"
    msg['waypoint_name'] = name
    ros_client.nav_pub.publish(roslibpy.Message(msg))

    return success_api_response({"x" : px, "y" :py, "z":pz})

@require_GET
@response_wrapper
@require_ros
def navigation_stop(request: HttpRequest):
    """
    [GET] /api/navigation/stop
    """
    return failed_api_response(ErrorCode.ROS_CONNECT_FAILED, "ROS控制服务未就绪，导航停止暂不可用")

@require_GET
@response_wrapper
def navigation_map_list(request: HttpRequest):
    """[GET] /api/navigation/map_list"""
    data = {"maps": [_map_to_dict(m) for m in Map.objects.all()]}
    return success_api_response(data)

@require_GET
@response_wrapper
def navigation_point_list(request: HttpRequest, query_id):
    """[GET] /api/navigation/point_list/<query_id>"""
    data = {"points": [_wp_to_dict(w) for w in WayPoint.objects.filter(map_id=query_id)]}
    return success_api_response(data)



"""==========================================  Task  ==============================================="""

@require_GET
@response_wrapper
@require_ros
def task_start(request: HttpRequest):
    """进入完成任务模式"""
    if not check_connect():
        return failed_api_response(ErrorCode.ROS_CONNECT_FAILED, "ROS未连接")
    ros_client = ROSClient()
    """
    前往取货点
    """
    ros_client.start_pose_printer(interval=1.0)
    msg = navigation_task_template()
    msg["type"] = "waypoint_name"
    # 确定取货点名称
    try:
        p = WayPoint.objects.filter(waypoint_type=WayPoint.PICKUP).first()
    except WayPoint.DoesNotExist:
        return failed_api_response(ErrorCode.NOT_FOUND_ERROR, "取货点不存在")
    name = p.waypoint_name
    msg['waypoint_name'] = name
    ros_client.nav_pub.publish(roslibpy.Message(msg))
    ros_client.mode = 2
    return success_api_response({"mode":"2"})

@require_GET
@response_wrapper
def task_info(request: HttpRequest):
    """将任务日志交给前端"""
    """
    GET /api/task/info
    可选参数：?status=1  过滤状态，默认返回所有任务
    返回任务列表，按更新时间倒序
    """
    status = request.GET.get('status')
    queryset = TaskRecord.objects.all().order_by('-update_time')
    if status is not None:
        queryset = queryset.filter(status=status)
    
    data = []
    for task in queryset:
        data.append({
            'task_index': task.task_index,
            'status': task.status,
            'status_display': task.get_status_display(),
            'message': task.message,
            'result_detail': task.result_detail,
            'create_time': task.create_time.isoformat(),
            'update_time': task.update_time.isoformat(),
        })
    return success_api_response(data)
    
"""==========================================  grabbing  ==============================================="""

@require_GET
@response_wrapper
@require_ros
def grabbing_start(request: HttpRequest):
    """启动抓取，发布模式切换消息"""
    if not check_connect():
        return failed_api_response(ErrorCode.ROS_CONNECT_FAILED, "ROS未连接")
    ros_client = ROSClient()

    info = info_msg_template()
    info['mode'] = 4
    info['scram'] = False
    info['header']['frame_id'] = 'grabbing_start'

    ros_client.info_pub.publish(roslibpy.Message(info))
    return success_api_response({"mode": "4"})

"""==========================================  util  ==============================================="""
@require_GET
@response_wrapper
@require_ros
def get_pose(request: HttpRequest):
    ros = ROSClient()

    if ros.current_pose is None:
        return success_api_response({"code": 1, "msg": "no pose yet"})

    pose = ros.current_pose['pose']['pose']

    return success_api_response({
        "x": pose['position']['x'],
        "y": pose['position']['y'],
    })

@require_GET
@response_wrapper
@require_ros
def get_mode(request: HttpRequest):
    ros = ROSClient()
    """
    uint8 INIT=0
    uint8 PENDING=1
    uint8 STARTING=2
    uint8 TASK_SCHEDULE=3
    """

    return success_api_response({"mode": ros.mode})

@require_GET
@response_wrapper
@require_ros
def emergency_stop(request: HttpRequest):
    ros = ROSClient()

    msg = info_msg_template()
    msg["scram"] = True
    msg["mode"] = 1
    ros.mode = 1
    ros.info_pub.publish(roslibpy.Message(msg))

    # 导航停止
    nav_msg = navigation_task_template()
    nav_msg["type"] = "relative"
    ros.nav_pub.publish(roslibpy.Message(nav_msg))

    return success_api_response({"code": 0, "msg": "scram sent"})

@require_GET
@response_wrapper
@require_ros
def renew(request: HttpRequest):

    target_dir = Path("~/ros_server").expanduser()
    shutil.rmtree(target_dir)

    try:
        call_command('flush', interactive=False, verbosity=0)
        return success_api_response({'message': 'All data cleared.'})
    except Exception as e:
        # 根据实际 response_wrapper 的约定，可返回错误字典或直接抛出
        return failed_api_response({'error': f'Reset failed: {str(e)}'})
