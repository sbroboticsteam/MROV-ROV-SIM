import rclpy
import sys
from rclpy.node import Node
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Quaternion, Vector3
from std_msgs.msg import Header

# Quaternion Structure
# Roll (Y) -> (90, -90), Pitch (X) (-90, 90), Yaw:(+90, -90), W (0)

class IMUFakePublisher(Node):
    def __init__(self):
        # Initialize the ROS2 node
        super().__init__(f"fake_imudata_publisher")

        # Declare node parameters
        self.declare_parameter('imu_name', 'imu')

        # Get the parameter and store it in the class for later use
        self.imu_name = self.get_parameter('imu_name').get_parameter_value().string_value

        # Create the IMU data publisher with the correct imu name
        self.imu_pub = self.create_publisher(Imu, f"imu/{self.imu_name}", 10)

        # Create a period of 0.01s = 100 hz
        timer_period = 0.01
        # Create a ROS2 Timer with a callback function
        self.timer = self.create_timer(timer_period, self.timer_callback)

        # Create a default IMU Message
        self.data = Imu()
        # Initialize the header
        self.data.header = Header()
        self.data.header.frame_id = self.imu_name # Ensure this is the same link name as the tf tree imu
        # Scalar Quaternion as initialization
        self.data.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)  # Identity quaternion (no rotation)
        # Set angular velocity (rad/s)
        self.data.angular_velocity = Vector3(x=0.0, y=0.0, z=0.0)
        # Set linear acceleration (m/s^2)
        self.data.linear_acceleration = Vector3(x=0.0, y=0.0, z=0.0) 
        # Initialize the covariances to -1 (Assume that we dont have this data)
        self.data.orientation_covariance = [-1.0] * 9  # 3x3 matrix flattened to 9 elements
        self.data.angular_velocity_covariance = [-1.0] * 9
        self.data.linear_acceleration_covariance = [-1.0] * 9

    def timer_callback(self):
        # Stamp the data with the current time and publish
        self.data.header.stamp = self.get_clock().now().to_msg()

        # Publish the message
        self.imu_pub.publish(self.data)

        # Log the publishing
        self.get_logger().info("Published NULL Fake IMU Data")

def main(args=None):
    # Init ROS2
    rclpy.init(args=args)
        
    # Make an object for the fake imu data publisher node
    imu_fake_publisher = IMUFakePublisher()
    # Spin that node
    rclpy.spin(imu_fake_publisher)

    # Cleanup
    imu_fake_publisher.destroy_node()
    rclpy.shutdown()
        
if __name__ == "__main__":
    main()