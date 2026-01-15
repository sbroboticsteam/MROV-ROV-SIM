from launch import LaunchDescription
from launch.actions import ExecuteProcess, IncludeLaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

from launch_ros.actions import Node
# from launch.launch_description_sources import PythonLaunchDescriptionSource
# import xacro
# import os
# from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    world_file = "./worlds/rov_world.sdf" # jank but whatever
    
    fake_thrusters = Node(
        package='rov_description',
        executable='fake_thrusters',
        parameters=[{'use_sim_time': True}],
        output='screen'
    )
    
    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'
        ],
        output='screen'
    )

    # experimental force bridge
    trans_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/proptrans/backleft/ang_vel@std_msgs/msg/Float64[gz.msgs.Double',
            '/proptrans/frontleft/ang_vel@std_msgs/msg/Float64[gz.msgs.Double',
            '/proptrans/backright/ang_vel@std_msgs/msg/Float64[gz.msgs.Double',
            '/proptrans/frontright/ang_vel@std_msgs/msg/Float64[gz.msgs.Double'
        ],
        output='screen'
    )
    
    vert_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[

            '/propvert/backleft/ang_vel@std_msgs/msg/Float64[gz.msgs.Double',
            '/propvert/frontleft/ang_vel@std_msgs/msg/Float64[gz.msgs.Double',
            '/propvert/backright/ang_vel@std_msgs/msg/Float64[gz.msgs.Double',
            '/propvert/frontright/ang_vel@std_msgs/msg/Float64[gz.msgs.Double'
        ],
        output='screen'
    )

    return LaunchDescription([
        fake_thrusters,
        clock_bridge,
        trans_bridge,
        vert_bridge,
        ExecuteProcess(
            cmd=[
                'gz', 'sim', '-v', '4',
                world_file
            ],
            output='screen'
        )
    ])


