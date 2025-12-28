import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu, JointState
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
import numpy as np
from scipy.spatial.transform import Rotation as R

class ArmController(Node):
    # Init the node and create the subscriptions
    def __init__(self):
        super().__init__('arm_controller')
        # Create the 4 subscriptions
        # Chest IMU Data
        self.chest_sub = self.create_subscription(
            Imu, 
            '/chest_imu/imu/chestimu_1', 
            self.chest_callback, 
            10
        )
        self.chest_sub # Prevent the unused variable warning
        # Arm IMU Data
        self.arm_sub = self.create_subscription(
            Imu, 
            '/arm_imu/imu/armimu_1', 
            self.arm_callback, 
            10
        )
        self.arm_sub # Prevent the unused variable warning
        # Elbow IMU Data
        self.elbow_sub = self.create_subscription(
            Imu, 
            '/elbow_imu/imu/elbowimu_1', 
            self.elbow_callback, 
            10
        )
        self.elbow_sub # Prevent the unused variable warning
        # Wrist IMU Data
        self.wrist_sub = self.create_subscription(
            Imu, 
            '/wrist_imu/imu/wristimu_1', 
            self.wrist_callback, 
            10
        )
        self.wrist_sub # Prevent the unused variable warning

        # Initialize the transform broadcaster
        self.tf_broadcaster = TransformBroadcaster(self)

        # Create a publisher to publish the JointStates
        self.joint_pub = self.create_publisher(JointState, '/joint_states', 10)

        # Initialize joint data
        self.chest_quat = None
        self.arm_quat = None
        self.elbow_quat = None
        self.wrist_quat = None

    # Define the callback functions

    # Chest Callback
    def chest_callback(self, data):
        # Publish the odom -> base_link transform
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'world'
        t.child_frame_id = 'base_link'

        # Center the position at origin
        t.transform.translation.x = 0.0
        t.transform.translation.y = 0.0
        t.transform.translation.z = 0.0

        # Orient the whole thing based on the orientation of the chest imu
        t.transform.rotation = data.orientation

        # Publish the transform
        self.tf_broadcaster.sendTransform(t)
        
        # Store data to compute rotation for other imus
        self.chest_quat = data.orientation

        # Compute and publish the joint_states
        self.compute_and_publish_joints()

    # Arm Callback
    def arm_callback(self, data):
        self.arm_quat = data.orientation
        self.compute_and_publish_joints()
    
    # Elbow Callback
    def elbow_callback(self, data):
        self.elbow_quat = data.orientation
        self.compute_and_publish_joints()
    
    # Wrist Callback
    def wrist_callback(self, data):
        self.wrist_quat = data.orientation
        self.compute_and_publish_joints()

    # Function to compute and publish the joint states
    def compute_and_publish_joints(self):
        # Dont publish anything if even a single imu data has not been recieved
        if self.chest_quat is None or self.arm_quat is None or self.elbow_quat is None or self.wrist_quat is None:
            return
        else:
            # Convert the quaternions to scipy rotation objects
            chest_rot = R.from_quat([self.chest_quat.x, self.chest_quat.y, 
                                     self.chest_quat.z, self.chest_quat.w])
            arm_rot = R.from_quat([self.arm_quat.x, self.arm_quat.y, 
                                     self.arm_quat.z, self.arm_quat.w])
            elbow_rot = R.from_quat([self.elbow_quat.x, self.elbow_quat.y, 
                                     self.elbow_quat.z, self.elbow_quat.w])
            wrist_rot = R.from_quat([self.wrist_quat.x, self.wrist_quat.y, 
                                     self.wrist_quat.z, self.wrist_quat.w])
            
            # Compute their relative orientations to their parent links (Makes more sense honestly)
            shoulder_relative = chest_rot.inv() * arm_rot
            elbow_relative = arm_rot.inv() * elbow_rot 
            wrist_relative = elbow_rot.inv() * wrist_rot

            # Convert the quaternions to euler angles (x = roll, y = pitch, z = yaw)
            shoulder_roll, shoulder_pitch, shoulder_yaw = shoulder_relative.as_euler('xyz')
            elbow_roll, elbow_pitch, elbow_yaw = elbow_relative.as_euler('xyz')
            wrist_roll, wrist_pitch, wrist_yaw = wrist_relative.as_euler('xyz')

            # Create and publish the joint states
            joint_state = JointState()
            joint_state.header.stamp = self.get_clock().now().to_msg()
            joint_state.header.frame_id = ''  # Empty for joint states

            # Joint names from URDF 
            joint_state.name = [
                'shldrevolute_roll', 'shldrevolute_pitch', 'shldrevolute_yaw',
                'elbowrevolute_roll', 'elbowrevolute_pitch', 'elbowrevolute_yaw',
                'wristrevolute_roll', 'wristrevolute_pitch', 'wristrevolute_yaw'
            ]

            # Positions (9 joint angles in same order as names)
            joint_state.position = [
                shoulder_roll, shoulder_pitch, shoulder_yaw,
                elbow_roll, elbow_pitch, elbow_yaw,
                wrist_roll, wrist_pitch, wrist_yaw
            ]

            # Velocities and efforts can be empty lists
            joint_state.velocity = []
            joint_state.effort = []

            # Publish the Joint States
            self.joint_pub.publish(joint_state)
    
# Main function 
def main(args=None):
    rclpy.init(args=args)
    # Instantiate the controller node
    arm_controller = ArmController()
    # Spin the arm controller node
    rclpy.spin(arm_controller)

    # Cleanup
    arm_controller.destroy_node()
    rclpy.shutdown()

# Run if executed
if __name__ == '__main__':
    main()
