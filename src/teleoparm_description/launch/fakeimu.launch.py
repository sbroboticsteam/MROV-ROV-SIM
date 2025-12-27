from launch import LaunchDescription
from launch_ros.actions import Node

# Generate the launch description
def generate_launch_description():
    return LaunchDescription([
        Node(
            package='teleoparm_description',
            namespace='chest_imu',
            executable='imufakepub',
            name='fakeimudata', 
            parameters=[{'imu_name':'chestimu_1'}]
        ),
        Node(
            package='teleoparm_description',
            namespace='arm_imu',
            executable='imufakepub',
            name='fakeimudata',
            parameters=[{'imu_name':'armimu_1'}]
        ),
        Node(
            package='teleoparm_description',
            namespace='elbow_imu',
            executable='imufakepub',
            name='fakeimudata',
            parameters=[{'imu_name':'elbowimu_1'}]
        ),
        Node(
            package='teleoparm_description',
            namespace='wrist_imu',
            executable='imufakepub',
            name='fakeimudata',
            parameters=[{'imu_name':'wristimu_1'}]
        )
    ])