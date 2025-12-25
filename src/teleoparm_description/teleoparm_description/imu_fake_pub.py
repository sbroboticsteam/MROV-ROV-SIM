import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Quaternion

# Quaternion Structure
# Roll (Y) -> (90, -90), Pitch (X) (-90, 90), Yaw:(+90, -90), W (0)

class IMUFakePublisher(Node):
    def __init__(self):
        # Initialize the ROS2 node
        super().__init__("fake_imu_publisher")
        # Create the IMU data publishers
        self.imu_chest = self.create_publisher(Quaternion, 'chest_imu', 10)
        self.imu_arm = self.create_publisher(Quaternion, 'arm_imu', 10)
        self.imu_elbow = self.create_publisher(Quaternion, 'elbow_imu', 10)
        self.imu_wrist = self.create_publisher(Quaternion, 'wrist_imu', 10)
        # Create a period of 0.01s = 100 hz
        timer_period = 0.01
        # Create a ROS2 Timer with a callback function
        self.timer = self.create_timer(timer_period, self.timer_callback)
    
    def timer_callback(self):
        # Publish all zeroes for now
        data = [0.0, 0.0, 0.0, 1.0]
        # Convert to the proper type using the library
        data_quat = Quaternion(x = data[0], y=data[1], z=data[2], w=data[3])
        # Publish the fake IMU data
        self.imu_chest.publish(data_quat)
        self.imu_arm.publish(data_quat)
        self.imu_elbow.publish(data_quat)
        self.imu_wrist.publish(data_quat)
        # Print to logger
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