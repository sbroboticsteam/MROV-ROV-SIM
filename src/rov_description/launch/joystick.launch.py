from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='joy',
            executable='joy_node',
            name='joy_node',
            parameters=[{
                'autorepeat_rate': 10.0,
            }]
        ),
        Node(
            package='rov_description',          
            executable='controller_node',    
            name='rov_joy_teleop',
            output='screen',
            parameters=[{
                'arm_speed': 1.0,
                'deadzone': 0.06,
                'gain_surge': 1.0,
                'gain_sway': 1.0,
                'gain_yaw': 1.0,
                'gain_heave': 1.0,
                'gain_pitch': 0.7,
                'invert_pitch': True,
                'invert_sway': True,
                'joy_timeout_sec': 0.5,
            }]
        ),
    ])