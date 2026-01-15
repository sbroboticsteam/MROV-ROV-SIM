# Modeled from main repo for fake IMU data

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Quaternion, Vector3
from std_msgs.msg import Header, Float32, Float64, String

# Action server imports
from rclpy.action import ActionServer
# from imu_action_interfaces.action import ImuGoal
import time
# Dependencies to perform SLERP
import numpy as np
# Single threaded executor for async functions
from rclpy.executors import MultiThreadedExecutor


class FakeThrusterPublisher(Node):
    def __init__(self):
        super().__init__('fake_thruster_publisher')

        # Enable simulation time
        self.set_parameters([
            rclpy.parameter.Parameter(
                'use_sim_time',
                rclpy.Parameter.Type.BOOL,
                True
            )
        ])

        #vertical thrusters
        self.propvertbackleft_pub = self.create_publisher(
            Float64,
            'propvert/backleft/ang_vel',
            10
        )
        self.propvertbackright_pub = self.create_publisher(
            Float64,
            'propvert/backright/ang_vel',
            10
        )
        self.propvertfrontleft_pub = self.create_publisher(
            Float64,
            'propvert/frontleft/ang_vel',
            10
        )
        self.propvertfrontright_pub = self.create_publisher(
            Float64,
            'propvert/frontright/ang_vel',
            10
        )
        
        #translational thrusters
        self.proptransbackleft_pub = self.create_publisher(
            Float64,
            'proptrans/backleft/ang_vel',
            10
        )
        self.proptransbackright_pub = self.create_publisher(
            Float64,
            'proptrans/backright/ang_vel',
            10
        )
        self.proptransfrontleft_pub = self.create_publisher(
            Float64,
            'proptrans/frontleft/ang_vel',
            10
        )
        self.proptransfrontright_pub = self.create_publisher(
            Float64,
            'proptrans/frontright/ang_vel',
            10
        )
        
        self.timer = self.create_timer(0.5, self.timer_callback)
        self.i = 0
        
        self.base_force = 100 * 25
        # msg = Float64()
        # msg.data = float(float_force)
        # self.propbackleft_pub.publish(msg)
        # self.propbackright_pub.publish(msg)
        # self.propfrontleft_pub.publish(msg)
        # self.propfrontright_pub.publish(msg)

    # Define the timer callback function
    def timer_callback(self):
        msg = Float64()
        msg.data = float(10 * self.i  + self.base_force)
        self.publish_force_vert(msg)
        self.get_logger().info('Publishing: "%s"' % msg.data)
        self.i += 1

    def publish_force_vert(self, msg):
        self.propvertbackleft_pub.publish(msg)
        self.propvertbackright_pub.publish(msg)
        self.propvertfrontleft_pub.publish(msg)
        self.propvertfrontright_pub.publish(msg)
        
    def publish_force_trans(self, msg):
        self.proptransbackleft_pub.publish(msg)
        self.proptransbackright_pub.publish(msg)
        self.proptransfrontleft_pub.publish(msg)
        self.proptransfrontright_pub.publish(msg)

def main(args=None):
    # Init ROS2
    rclpy.init(args=args)
        
    # Make an object for the fake imu data publisher node
    fake_thruster_pub = FakeThrusterPublisher()
    
    rclpy.spin(fake_thruster_pub)
    fake_thruster_pub.destroy_node()
    rclpy.shutdown()
    
if __name__ == "__main__":
    main()
    
'''
/clock
/gazebo/resource_paths
/gui/camera/pose
/gui/currently_tracked
/gui/track
/proptrans/backleft/ang_vel
/proptrans/backright/ang_vel
/proptrans/frontleft/ang_vel
/proptrans/frontright/ang_vel
/propvert/backleft/ang_vel
/propvert/backright/ang_vel
/propvert/frontleft/ang_vel
/propvert/frontright/ang_vel
/stats
/world/ROVWorld/clock
/world/ROVWorld/dynamic_pose/info
/world/ROVWorld/pose/info
/world/ROVWorld/scene/deletion
/world/ROVWorld/scene/info
/world/ROVWorld/state
/world/ROVWorld/stats
/ocean_current
/proptrans/backleft
/proptrans/backleft/enable_deadband
/proptrans/backright
/proptrans/backright/enable_deadband
/proptrans/frontleft
/proptrans/frontleft/enable_deadband
/proptrans/frontright
/proptrans/frontright/enable_deadband
/propvert/backleft
/propvert/backleft/enable_deadband
/propvert/backright
/propvert/backright/enable_deadband
/propvert/frontleft
/propvert/frontleft/enable_deadband
/propvert/frontright
/propvert/frontright/enable_deadband
/rov/propbackleft/force
/world/ROVWorld/light_config
/world/ROVWorld/material_color'''