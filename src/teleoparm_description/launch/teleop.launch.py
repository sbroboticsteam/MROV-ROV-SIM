from launch_ros.actions import Node
from launch import LaunchDescription
import xacro
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    share_dir = get_package_share_directory('teleoparm_description')

    # Process URDF
    xacro_file = os.path.join(share_dir, 'urdf', 'teleoparm.urdf')
    robot_description_config = xacro.process_file(xacro_file)
    robot_urdf = robot_description_config.toxml()

    # RViz config
    rviz_config_file = os.path.join(share_dir, 'config', 'display.rviz')

    # Robot state publisher - listens to /joint_states and publishes TF tree
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[
            {'robot_description': robot_urdf}
        ]
    )

    # Fake IMU publishers (4 nodes)
    chest_imu_node = Node(
        package='teleoparm_description',
        namespace='chest_imu',
        executable='imufakepub',
        name='fakeimudata', 
        parameters=[{'imu_name':'chestimu_1'}]
    )

    arm_imu_node = Node(
        package='teleoparm_description',
        namespace='arm_imu',
        executable='imufakepub',
        name='fakeimudata',
        parameters=[{'imu_name':'armimu_1'}]
    )

    elbow_imu_node = Node(
        package='teleoparm_description',
        namespace='elbow_imu',
        executable='imufakepub',
        name='fakeimudata',
        parameters=[{'imu_name':'elbowimu_1'}]
    )

    wrist_imu_node = Node(
        package='teleoparm_description',
        namespace='wrist_imu',
        executable='imufakepub',
        name='fakeimudata',
        parameters=[{'imu_name':'wristimu_1'}]
    )

    # Arm controller - subscribes to IMUs, publishes /joint_states and world->base_link TF
    arm_controller_node = Node(
        package='teleoparm_description',
        executable='armcontroller',
        name='arm_controller',
        output='screen'
    )

    # RViz for visualization
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config_file],
        output='screen'
    )

    return LaunchDescription([
        robot_state_publisher_node,
        chest_imu_node,
        arm_imu_node,
        elbow_imu_node,
        wrist_imu_node,
        arm_controller_node,
        rviz_node
    ])
