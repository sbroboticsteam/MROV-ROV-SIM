#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

def main(args=None):
    rclpy.init(args=args)
    node = Node('arm_calibrator')
    
    # Create service client
    client = node.create_client(Trigger, 'calibrate_arm')
    
    node.get_logger().info('Waiting for calibration service...')
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info('Service not available, waiting...')
    
    # Call the service
    request = Trigger.Request()
    node.get_logger().info('Calling calibration service...')
    future = client.call_async(request)
    rclpy.spin_until_future_complete(node, future)
    
    if future.result() is not None:
        response = future.result()
        if response.success:
            node.get_logger().info(f'SUCCESS: {response.message}')
        else:
            node.get_logger().error(f'FAILED: {response.message}')
    else:
        node.get_logger().error('Service call failed')
    
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
