from django.urls import path
from app0.views import test
from app0.api import file as file_api, map as map_api, note as note_api
from app0.api.ros import (ros_connect, get_ros_connect_status, ros_free,
    mapping_start, mapping_end, mapping_save,
    navigation_to, navigation_stop,
    navigation_map_list, navigation_point_list,
    task_start, task_info, grabbing_start,
    get_mode, emergency_stop, get_pose,
    waypoints_start, waypoints_save,
    renew)

urlpatterns = [
    # test
    path("test", test),

    # map_upload
    path('file/upload/', file_api.upload_file, name='upload_file'),

    # ros connect
    path("ros/connect", ros_connect),
    path("ros/connect_status", get_ros_connect_status),
    path("ros/free", ros_free),

    # mapping
    path("mapping/start", mapping_start),
    path("mapping/end", mapping_end),
    path("mapping/save", mapping_save),

    path("waypoints/start",waypoints_start),
    path("waypoints/save",waypoints_save),

    # navigating
    path("navigation/to/<int:query_id>", navigation_to),
    path("navigation/stop", navigation_stop),
    path("navigation/map_list", navigation_map_list),
    path("navigation/point_list/<int:query_id>", navigation_point_list),
    path("navigation/point/<int:waypoint_id>", note_api.update_waypoint),

    # task
    path("task/start", task_start),
    path("task/info", task_info),

    # grabbing
    path("grabbing/start", grabbing_start),
    path("pose", get_pose),

    # map management
    path("map/image/<int:map_id>", map_api.map_image),
    path("map/<int:map_id>", map_api.map_rename),
    path("map/delete/<int:map_id>", map_api.map_delete),

    # util
    path("util/get_mode", get_mode),
    path("util/emergency_stop", emergency_stop),
    path("util/renew", renew),
]
