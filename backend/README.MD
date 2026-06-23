在ubuntu24上进行测试，使用python版本为3.9.25
需要安装mysql-client
```
sudo mysql -u root

-- 创建用户（允许从任何主机连接，若只允许本地可将 '%' 改为 'localhost'）
CREATE USER IF NOT EXISTS 'akuouka'@'%' IDENTIFIED BY '';
-- 授予对 ros 数据库的所有权限
GRANT ALL PRIVILEGES ON ros.* TO 'akuouka'@'%';
-- 刷新权限
FLUSH PRIVILEGES;

EXIT;
```

再运行
```
mysql -h 127.0.0.1 -P 3306 -u akuouka -p
# 出现 Enter password: 时，直接按 Enter（密码为空）

CREATE DATABASE IF NOT EXISTS ros;

EXIT;
```

ros端需要做：
首次连接之前，在 ROS master所在环境用以下命令安装rosbridge suite:
```
sudo apt-get install -y ros-noetic-rosbridge-server
sudo apt-get install -y ros-noetic-tf2-web-republisher
```

在以后的每次连接之前，都要确保预先开启了以下服务:
```
roslaunch rosbridge_server rosbridge_websocket.launch
rosrun tf2_web_republisher tf2_web_republisher

```
