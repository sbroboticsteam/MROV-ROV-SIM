import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():

    # Package directories
    pkg_rov_description = get_package_share_directory("rov_description")
    pkg_ros_gz_sim = get_package_share_directory("ros_gz_sim")

    # Paths
    xacro_file = os.path.join(pkg_rov_description, "urdf", "rov.xacro")
    rviz_config = os.path.join(pkg_rov_description, "config", "display.rviz")
    world_file = os.path.join(pkg_rov_description, "worlds", "CompetitionWorld2025.sdf")
    bridge_config = os.path.join(pkg_rov_description, "config", "ros_gz_bridge.yaml")

    # Launch arguments
    use_sim_time = LaunchConfiguration("use_sim_time")
    rviz = LaunchConfiguration("rviz")
    x = LaunchConfiguration("x")
    y = LaunchConfiguration("y")
    z = LaunchConfiguration("z")

    # -----------------------------
    # Reduce Gazebo rendering load (IMPORTANT)
    # -----------------------------
    gz_sim_flags = "-v2 -s -r --render-engine ogre2"

    # -----------------------------
    # Reduce GPU overdraw (safe env tuning)
    # -----------------------------
    force_vsync_off = SetEnvironmentVariable(
        name="OGRE_NEXT_SKIP_VSYNC",
        value="1"
    )

    # Keep plugin path unchanged
    force_plugin_path = SetEnvironmentVariable(
        name="GZ_SIM_SYSTEM_PLUGIN_PATH",
        value=pkg_rov_description
    )

    # Robot description from xacro
    robot_description_cmd = Command(["xacro", " ", xacro_file])
    robot_description = ParameterValue(robot_description_cmd, value_type=str)

    # Gazebo Sim Server
    gz_sim_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            f'{Path(pkg_ros_gz_sim) / "launch" / "gz_sim.launch.py"}'
        ),
        launch_arguments={
            "gz_args": f"{gz_sim_flags} {world_file}"
        }.items(),
    )

    # Gazebo Sim GUI (lighter startup)
    gz_sim_gui = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            f'{Path(pkg_ros_gz_sim) / "launch" / "gz_sim.launch.py"}'
        ),
        launch_arguments={
            "gz_args": "-v2 -g --render-engine ogre2"
        }.items(),
    )

    # Robot State Publisher
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="both",
        parameters=[{
            "robot_description": robot_description,
            "use_sim_time": use_sim_time,
            "frame_prefix": "",
        }],
    )

    # Spawn robot
    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-world", "",
            "-name", "rov",
            "-topic", "/robot_description",
            "-x", x,
            "-y", y,
            "-z", z,
        ],
        output="screen",
    )

    # Bridge
    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        parameters=[{
            "config_file": bridge_config,
            "qos_overrides./tf_static.publisher.durability": "transient_local",
            "use_sim_time": use_sim_time,
        }],
        output="screen",
    )

    # RViz
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        arguments=["-d", rviz_config],
        parameters=[{"use_sim_time": use_sim_time}],
        condition=IfCondition(rviz),
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("rviz", default_value="true"),
        DeclareLaunchArgument("x", default_value="2.0"),
        DeclareLaunchArgument("y", default_value="0"),
        DeclareLaunchArgument("z", default_value="0.4"),

        force_vsync_off,
        force_plugin_path,

        gz_sim_server,
        gz_sim_gui,
        robot_state_publisher,
        spawn_robot,
        bridge,
        rviz_node,
    ])