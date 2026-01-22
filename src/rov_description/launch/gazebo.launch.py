import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
)
from launch.conditions import IfCondition

from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch.conditions import IfCondition, UnlessCondition
from launch.actions import SetEnvironmentVariable


def generate_launch_description():
    
    # Package directories
    pkg_rov_description = get_package_share_directory("rov_description")
    pkg_ros_gz_sim = get_package_share_directory("ros_gz_sim")
    
    # Paths
    xacro_file = os.path.join(pkg_rov_description, "urdf", "rov.xacro")
    rviz_config = os.path.join(pkg_rov_description, "config", "display.rviz")
    world_file = os.path.join(pkg_rov_description, "worlds", "CompetitionWorld2025.sdf")
    
    # Launch arguments
    use_sim_time = LaunchConfiguration("use_sim_time")
    rviz = LaunchConfiguration("rviz")
    x = LaunchConfiguration("x")
    y = LaunchConfiguration("y")
    z = LaunchConfiguration("z")
    
    # Ensure SDF_PATH is populated for sdformat_urdf
    if "GZ_SIM_RESOURCE_PATH" in os.environ:
        gz_sim_resource_path = os.environ["GZ_SIM_RESOURCE_PATH"]
        if "SDF_PATH" in os.environ:
            sdf_path = os.environ["SDF_PATH"]
            os.environ["SDF_PATH"] = sdf_path + ":" + gz_sim_resource_path
        else:
            os.environ["SDF_PATH"] = gz_sim_resource_path
    
    # Robot description from xacro
    robot_description = Command(
        [
            "xacro ",
            xacro_file,
        ]
    )
    force_plugin_path = SetEnvironmentVariable(
        name="GZ_SIM_SYSTEM_PLUGIN_PATH",
        value=pkg_rov_description
    )
    
    # Gazebo Sim Server
    gz_sim_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            f'{Path(pkg_ros_gz_sim) / "launch" / "gz_sim.launch.py"}'
        ),
        launch_arguments={
            "gz_args": f"-v4 -s -r {world_file}"
        }.items(),
    )
    
    # Gazebo Sim GUI
    gz_sim_gui = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            f'{Path(pkg_ros_gz_sim) / "launch" / "gz_sim.launch.py"}'
        ),
        launch_arguments={"gz_args": "-v4 -g"}.items(),
    )
    
    # Robot State Publisher
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="both",
        parameters=[
            {
                "robot_description": robot_description,
                "use_sim_time": use_sim_time,
                "frame_prefix": "",
            }
        ],
    )
    
    # Spawn robot in Gazebo
    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-world",
            "",
            "-name",
            "rov",
            "-topic",
            "/robot_description",
            "-x",
            x,
            "-y",
            y,
            "-z",
            z,
        ],
        output="screen",
    )
    
    # RViz2
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        arguments=["-d", rviz_config],
        parameters=[{"use_sim_time": use_sim_time}],
        condition=IfCondition(rviz),
        output="screen",
    )

    gui_arg = DeclareLaunchArgument(
        name='gui',
        default_value='True'
    )

    show_gui = LaunchConfiguration('gui')

    joint_state_publisher_node = Node(
        condition=UnlessCondition(show_gui),
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher'
    )

    joint_state_publisher_gui_node = Node(
        condition=IfCondition(show_gui),
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui'
    )
    
    return LaunchDescription(
        [
            # Launch arguments
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="true",
                description="Use simulation clock",
            ),
            DeclareLaunchArgument(
                "rviz",
                default_value="true",
                description="Open RViz",
            ),
            DeclareLaunchArgument(
                "x",
                default_value="2.0",
                description="Initial x position (m)",
            ),
            DeclareLaunchArgument(
                "y",
                default_value="0",
                description="Initial y position (m)",
            ),
            DeclareLaunchArgument(
                "z",
                default_value="0.4",
                description="Initial z position (m)",
            ),
            # Start Gazebo and support nodes first
            force_plugin_path,
            gz_sim_server,
            gz_sim_gui,
            robot_state_publisher,
            spawn_robot,
            rviz_node,
            gui_arg,
            joint_state_publisher_node,
            joint_state_publisher_gui_node,
        ]
    )