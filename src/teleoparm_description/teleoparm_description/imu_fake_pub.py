import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Quaternion, Vector3
from std_msgs.msg import Header
# Action server imports
from rclpy.action import ActionServer
from imu_action_interfaces.action import ImuGoal
import time
# Dependencies to perform SLERP
import numpy as np
from scipy.spatial.transform import Rotation as R, Slerp
# Single threaded executor for async functions
from rclpy.executors import MultiThreadedExecutor

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

        # Create a ROS2 Action server
        self.action_server = ActionServer(
            self, 
            ImuGoal, # Type IMU Goal
            f'imu_goal_{self.imu_name}', 
            self.action_callback # Callback function for the action server
        )

    # Define the timer callback function
    def timer_callback(self):
        # Stamp the data with the current time and publish
        self.data.header.stamp = self.get_clock().now().to_msg()

        # Publish the message
        self.imu_pub.publish(self.data)

        # Log the publishing
        self.get_logger().info("Published NULL Fake IMU Data")

    # Define the action callback function 
    def action_callback(self, goal_handle):
        try:
            # Debug output
            self.get_logger().info('Executing goal...')
            # Init the feedback message
            feedback_msg = ImuGoal.Feedback()
            feedback_msg.progress = 0.0
            feedback_msg.current_orientation = self.data.orientation

            # Setup SLERP
            r_start = R.from_quat(self.quat_to_array(self.data.orientation))
            r_end = R.from_quat(self.quat_to_array(goal_handle.request.goal_orientation))
            # Key times and Rotations (Time range)
            key_times = [0.0, goal_handle.request.duration]
            key_rots = R.concatenate([r_start, r_end])
            # Perform slerp over these times
            slerp = Slerp(key_times, key_rots)

            # Start time and feedback publishing rate
            start_time = self.get_clock().now()

            # While node is not blocked
            while rclpy.ok():
                # Get the time that has elapsed
                elapsed = (self.get_clock().now() - start_time).nanoseconds/1e9
                # Clamp the time that has passed to duration
                elapsed = min(elapsed, goal_handle.request.duration)

                # Query the slerp function at this particular time
                r_current = slerp(elapsed)
                quat_current = r_current.as_quat()

                # Update the IMU Data for the publisher
                self.data.orientation = self.array_to_quat(quat_current)

                # Handle Action Cancellation
                # CHECK HERE - before or after updating orientation
                if goal_handle.is_cancel_requested:
                    # Handle cancellation
                    goal_handle.canceled()  # Mark as canceled
                    
                    result = ImuGoal.Result()
                    result.reached = False
                    result.message = "Goal was canceled by user"
                    result.final_orientation = self.data.orientation  # Current position
                    
                    return result  # Exit early


                # Calculate the progress to send to feedback
                progress = elapsed / goal_handle.request.duration

                # Send the feedback message
                feedback_msg.progress = progress
                feedback_msg.current_orientation = self.data.orientation
                goal_handle.publish_feedback(feedback_msg)
                # Break out of the loop if elapsed > duration
                if elapsed >= goal_handle.request.duration:
                    break
                # In loop to delay publishing 
                time.sleep(0.02)
            
            # Create result data and return it
            goal_handle.succeed()
            result = ImuGoal.Result()
            result.reached = True
            result.message = f"Goal {goal_handle.request.goal_orientation} for {self.imu_name} successfully reached..."
            result.final_orientation = self.data.orientation

            # Return the result
            return result
        
        # Catch the error
        except Exception as e:
            self.get_logger().error(f"Action failed with exception: {e}")
            import traceback
            self.get_logger().error(traceback.format_exc())
            
            goal_handle.abort()
            result = ImuGoal.Result()
            result.reached = False
            result.message = f"Error: {str(e)}"
            result.final_orientation = self.data.orientation
            return result


    # Function to convert from geometry_msgs/Quaternion to numpy array
    def quat_to_array(self, q):
        return np.array([q.x, q.y, q.z, q.w], dtype=float)
    
    # Fuction to convert np list to geometry_msgs/Quaternion
    def array_to_quat(self, arr):
        q = Quaternion()
        q.x, q.y, q.z, q.w = map(float, arr)
        return q

    

def main(args=None):
    # Init ROS2
    rclpy.init(args=args)
        
    # Make an object for the fake imu data publisher node
    imu_fake_publisher = IMUFakePublisher()
    
    # Create a SingleThreaded executor
    executor = MultiThreadedExecutor()
    executor.add_node(imu_fake_publisher)

    try:
        # Spin that node
        executor.spin()
    finally:
            executor.shutdown()
            imu_fake_publisher.destroy_node()
            rclpy.shutdown()
        
if __name__ == "__main__":
    main()