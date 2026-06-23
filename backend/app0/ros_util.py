import math
import time

import cv2
import numpy as np
import roslibpy
from django.http import HttpRequest
from roslibpy import ServiceRequest

from app0.util import ErrorCode, failed_api_response
import json
from app0.models.WayPoint import WayPoint
from app0.models.TaskRecord import TaskRecord
from backend.settings import ROS_PORT, ROS_HOST

import threading


def info_msg_template():
    """返回一个带有默认值的 Info 消息模板（字典）"""
    """
    uint8 INIT=0
    uint8 PENDING=1
    uint8 NAVIGATION=2
    uint8 TASK_SCHEDULE=3
    uint8 GRUB=4
    """
    return {
        "header": {
            "seq": 0,
            "stamp": roslibpy.Time.now().to_sec(),  # 当前时间
            "frame_id": "base_link"
        },
        "mode": 0,
        "scram": False
    }

def motion_PoseStamped_template():
    return {
        "header": {
            "seq": 0,
            "stamp": roslibpy.Time.now().to_sec(),  # 当前时间
            "frame_id": "base_link"
        },
        "pose": {
            "position" : {'x' : 0.66, 'y': 0.66, 'z':0.66} ,
            "orientation" : {'w': 1.0}
        }
    }

def task_status_template():
    """
        msg 匹配以下结构：
        int32 task_index
        bool is_finish
    """
    return {
        "task_index": 0,                         # 当前任务编号
        "is_finish": False                       # 是否终止
    }

def navigation_task_template():
    """
    生成导航任务消息的模板字典，匹配以下结构：
        string type
        geometry_msgs/PoseStamped pose
        string waypoint_name
        float32 dx
        float32 dy
        float32 dtheta_deg
    """
    return {
        "type": "pose",  # 可选值: "pose", "waypoint", "relative"
        "pose": {
            "header": {
                "seq": 0,
                "stamp": roslibpy.Time.now().to_sec(),  # 当前时间戳（秒）
                "frame_id": "map"                       # 可根据需要修改
            },
            "pose": {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
            }
        },
        "waypoint_name": "",    # 航点名称，如 "wp1"
        "dx": 0.0,              # 前后移动（米）
        "dy": 0.0,              # 左右移动（米）
        "dtheta_deg": 0.0       # 旋转角度（度）
    }

class ROSClient(object):
    _instance = None
    _flag = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not ROSClient._flag:
            ROSClient._flag = True
            self.counter = 0
            self.node_count = 0
            self.failed_count = 0
            self.map_id = 0
            self.last_op_time = time.time()
            self.client = None
            self.mode = 0  # init
            # Publishers
            self.info_pub = None
            self.motion_pub = None

            # Subscribers
            self.ctrl_listener = None
            self.nav_listener = None
            self.task_listener = None
            self.motion_listener = None
            self.pose_thread = None
            self.pose_running = False

    def reset(self, host, port):
        self.counter = 0
        self.failed_count = 0
        self.map_id = 0
        self.node_count = 0
        self.client = roslibpy.Ros(host=host, port=port)
        self.mode = 1 # pending
        self.info_pub = roslibpy.Topic(self.client, "/ctrl/info", 'robot_core/Info')
        self.motion_pub = roslibpy.Topic(self.client, "/motion_control/place_pose", 'geometry_msgs/PoseStamped' )
        self.nav_pub = roslibpy.Topic(self.client,'/nav_task', "robot_navigation/NavTask" )
        self.nav_listener = roslibpy.Topic(self.client, "/navigation_state", 'std_msgs/String')
        self.nav_listener.subscribe(self.nav_listen_callback)
        self.task_listener = roslibpy.Topic(self.client, "/ctrl/taskfeedback", 'robot_core/Taskfeedback')   # 现在订阅抓取模块
        self.task_listener.subscribe(self.task_listen_callback)
        self.motion_listener = roslibpy.Topic(self.client, "/motion_control/sub_task_result", 'motion_control/SubTaskResult')
        self.motion_listener.subscribe(self.grub_listen_callback)
        self.map_service = roslibpy.Service(self.client, '/save_map', 'robot_core/SaveMap')

        self.current_pose = None
        self.subscriber = roslibpy.Topic(
            self.client,
            '/amcl_pose',
            'geometry_msgs/PoseWithCovarianceStamped'
        )
        self.subscriber.subscribe(self.pose_callback)
        self.client.run()

    def exit(self):
        self.client.terminate()
        self.counter = 0
        self.failed_count = 0
        self.map_id = 0
        self.last_op_time = time.time()
        self.client = None


    def nav_listen_callback(self, msg):
        try:
            data = json.loads(msg.data)
            status = data.get("status", "UNKNOWN")
            status_text = data.get("status_text", "")
            x = data.get("current_x", 0.0)
            y = data.get("current_y", 0.0)
            
            print(f"Navigation Status: {status} ({status_text}) at ({x:.2f}, {y:.2f})")
            
            if status == "SUCCEEDED":
                print("Goal reached! Performing action...")
                if self.mode == 3:
                    # 发布放置消息 
                    motion_msg = motion_PoseStamped_template() # 导航到后仅提醒放置，不指定位置
                    self.motion_pub.publish(motion_msg)
                elif self.mode == 2 or self.mode == 1:
                    self.mode = 3
                    info = info_msg_template()
                    info['mode'] = 3
                    info['scram'] = False
                    info['header']['frame_id'] = 'task_start'
                    self.info_pub.publish(roslibpy.Message(info))
                    self.mode = 3
                    
            elif status == "ABORTED":
                print("Navigation failed, retrying...")
                
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")

    def task_listen_callback(self, msg):
        task_index = msg.get('task_index')
        is_finish = msg.get('is_finish', False)
            
        # 判断状态
        if is_finish:
            status = TaskRecord.Status.SUCCESS
            self.mode = 1
            # 构建简要 message
            brief = "任务成功"
        else:
            status = TaskRecord.Status.RUNNING
            # 应回到取货点
            msg = navigation_task_template()
            msg["type"] = "waypoint_name"
            waypoint = WayPoint.objects.filter(waypoint_type=WayPoint.PICKUP).first()
            if waypoint is None:
                return record, created
            msg['waypoint_name'] = waypoint.waypoint_name
            self.nav_pub.publish(roslibpy.Message(msg))


        # 更新或创建记录
        record, created = TaskRecord.objects.update_or_create(
            task_index=task_index,
            defaults={
                'status': TaskRecord.Status.SUCCESS,
                'message': brief,
                # update_time 会自动更新（auto_now=True）
            }
        )
        # 回到取货点
        
        return record, created

    def grub_listen_callback(self, msg):
        """
        msg: 
        int32 RUNNING=0
        int32 SUCCESS=1
        int32 FAILED=2

        int32 task_index
        int32 result
        string message
        string class_id

        """
        # 提取字段
        task_index = msg['task_index']   # int
        result = msg['result']           # int
        message = msg['message']         # str
        class_id = msg['class_id']

        if result == 1:
            print(f"Task {task_index} succeeded: {message}")
            if message == "GRUB_DONE" :
                # 发送消息告知底盘去放置点，根据颜色选择
                nav_msg = navigation_task_template()
                nav_msg["type"] = "waypoint_name"
                #  添加选择功能
                
                if class_id ==  0:
                    # 查询放货点中货物类型为 0 的航点
                    points = WayPoint.objects.filter(waypoint_type=WayPoint.DROPOFF, cargo_type=0)
                    target = points.first()
                    nav_msg['waypoint_name'] = target.waypoint_name
                elif class_id == 1:
                    # 查询放货点中货物类型为 1 的航点
                    points = WayPoint.objects.filter(waypoint_type=WayPoint.DROPOFF, cargo_type=1)
                    target = points.first()
                    nav_msg['waypoint_name'] = target.waypoint_name
                elif class_id == 2:
                    # 查询放货点中货物类型为 2 的航点
                    points = WayPoint.objects.filter(waypoint_type=WayPoint.DROPOFF, cargo_type=2)
                    target = points.first()
                    nav_msg['waypoint_name'] = target.waypoint_name
                elif class_id == 3:
                    # 查询放货点中货物类型为 3 的航点
                    points = WayPoint.objects.filter(waypoint_type=WayPoint.DROPOFF, cargo_type=3)
                    target = points.first()
                    nav_msg['waypoint_name'] = target.waypoint_name
                else :
                    points = WayPoint.objects.filter(waypoint_type=WayPoint.DROPOFF, cargo_type=0)
                    target = points.first()
                    nav_msg['waypoint_name'] = target.waypoint_name

                self.nav_pub.publish(nav_msg)

        elif result == 2:
            print(f"Task {task_index} failed: {message}")
        else:
            print(f"Task {task_index} is running: {message}")

    def pose_callback(self, message):
        self.current_pose = message

    def print_pose_once(self):
        if self.current_pose is None:
            print("No pose yet")
            return

        pose = self.current_pose['pose']['pose']
        x = pose['position']['x']
        y = pose['position']['y']

        print(f"[ROS POSE] x={x:.3f}, y={y:.3f}")

    def start_pose_printer(self, interval=2.0):
        if self.pose_running:
            return

        self.pose_running = True

        def loop():
            while self.pose_running and self.client and self.client.is_connected:
                self.print_pose_once()
                time.sleep(interval)

        self.pose_thread = threading.Thread(target=loop, daemon=True)
        self.pose_thread.start()

    def stop_pose_printer(self):
        self.pose_running = False

    @property
    def is_connect(self):
        if self.client is None:
            return False
        return self.client.is_connected
    
    def save_map_local(self, name):
        response = self.map_service.call(ServiceRequest({}))
        width = response["map"]["info"]["height"]
        height = response["map"]["info"]["width"]
        m = response["map"]["data"]
        m = np.array(m).reshape((width, height))
        tem = np.zeros((width, height))
        for i in range(width):
            for j in range(height):
                if m[i, j] == -1:
                    tem[width - 1 - i, j] = 127
                else:
                    tem[width - 1 - i, j] = 255 - (m[i, j] * 2)
        cv2.imwrite("./{}.png".format(name), tem)

    def trigger_save_map(self, map_name):
        if not self.client.is_connected:
            raise Exception("ROS not connected")
        
        # 等待服务可用
        service = self.map_service
        request = roslibpy.ServiceRequest({'map_name': map_name})
        
        # 同步调用（会阻塞，可设置超时）
        response = service.call(request)
        return response
    
    def get_map_list(self):
        """
        通过 ROS 服务 /get_map_list 获取服务器上已保存的地图名称列表。
        :return: list of map names (strings)
        :raises: 连接异常或服务调用失败
        """
        if not self.is_connect:
            raise RuntimeError("ROS client not connected")

        service = roslibpy.Service(self.client, '/get_map_list', 'robot_core/GetMapList')
        request = roslibpy.ServiceRequest({})  # 无参数
        response = service.call(request)
        # 响应应为 {'map_names': ['map1', 'map2', ...]}
        return response.get('map_names', [])


def ctrl_template() -> dict:
    return {
        "type": 0,
        "keyboard_ctrl_msg": {
            "direction": 0,
            "speed": 0,
        },
        "navigation_ctrl_msg": {
            "loop": 0,
            "pose_list": [],
            "name_list": [],
        },
        "command": "",
    }

def require_ros(func):
    """
    由用户请求一台机器人
    """
    def wrapper(request: HttpRequest, *args, **kwargs):
        ros_client = ROSClient()
        if ros_client.client is None:
            ros_client.reset(host=ROS_HOST, port=ROS_PORT)
        return func(request, *args, **kwargs)

    return wrapper

def ros_wrap_point(x, y, theta):
    return {
        "position": {
            "x": x,
            "y": y,
            "z": 0.0,
        },
        "orientation": theta,
    }