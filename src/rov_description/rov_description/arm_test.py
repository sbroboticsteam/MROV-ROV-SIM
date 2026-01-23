#!/usr/bin/env python3
import sys
import select
import termios
import tty
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64


HELP = r"""
ROV Arm Keyboard Teleop (cmd_vel)

Controls:
  Shoulder:   q (+)   a (-)
  Elbow:      w (+)   s (-)
  Wrist:      e (+)   d (-)
  Claw:       r (+)   f (-)

  SPACE: stop all
  x: quit

Tip: hold key to keep moving (auto-stops if you stop pressing)
"""


def get_key_nonblocking():
    """Read 1 char from stdin if available, else return None."""
    dr, _, _ = select.select([sys.stdin], [], [], 0.0)
    if dr:
        return sys.stdin.read(1)
    return None


class ArmKeyboardTeleop(Node):
    def __init__(self):
        super().__init__("arm_keyboard_teleop")

        # Topics (match your ros2 topic list)
        self.shoulder_topic = self.declare_parameter("shoulder_topic", "/rov/shoulder").value
        self.elbow_topic    = self.declare_parameter("elbow_topic", "/rov/elbow").value
        self.wrist_topic    = self.declare_parameter("wrist_topic", "/rov/wrist").value
        self.claw_topic     = self.declare_parameter("claw_topic", "/rov/claw").value

        # Velocities (rad/s in sim, since plugin uses JointVelocityCmd)
        self.speed = float(self.declare_parameter("speed", 1.0).value)  # rad/s
        self.publish_hz = float(self.declare_parameter("publish_hz", 30.0).value)
        self.key_timeout = float(self.declare_parameter("key_timeout", 0.25).value)  # seconds

        # Publishers
        self.pub_shoulder = self.create_publisher(Float64, self.shoulder_topic, 10)
        self.pub_elbow    = self.create_publisher(Float64, self.elbow_topic, 10)
        self.pub_wrist    = self.create_publisher(Float64, self.wrist_topic, 10)
        self.pub_claw     = self.create_publisher(Float64, self.claw_topic, 10)

        # Current commanded velocities
        self.cmd = {
            "shoulder": 0.0,
            "elbow": 0.0,
            "wrist": 0.0,
            "claw": 0.0,
        }

        # Last time any key affected each joint
        now = time.time()
        self.last_update = {k: now for k in self.cmd.keys()}

        self.get_logger().info(HELP)

        # Timer for publish loop
        period = 1.0 / self.publish_hz
        self.timer = self.create_timer(period, self.on_timer)

    def stop_all(self):
        for k in self.cmd.keys():
            self.cmd[k] = 0.0
            self.last_update[k] = time.time()

    def apply_key(self, key: str):
        now = time.time()

        # STOP ALL
        if key == " ":
            self.stop_all()
            self.get_logger().info("STOP ALL")
            return

        # Quit
        if key == "x":
            raise KeyboardInterrupt

        # Shoulder
        if key == "q":
            self.cmd["shoulder"] = +self.speed
            self.last_update["shoulder"] = now
        elif key == "a":
            self.cmd["shoulder"] = -self.speed
            self.last_update["shoulder"] = now

        # Elbow
        elif key == "w":
            self.cmd["elbow"] = +self.speed
            self.last_update["elbow"] = now
        elif key == "s":
            self.cmd["elbow"] = -self.speed
            self.last_update["elbow"] = now

        # Wrist
        elif key == "e":
            self.cmd["wrist"] = +self.speed
            self.last_update["wrist"] = now
        elif key == "d":
            self.cmd["wrist"] = -self.speed
            self.last_update["wrist"] = now

        # Claw
        elif key == "r":
            self.cmd["claw"] = +self.speed
            self.last_update["claw"] = now
        elif key == "f":
            self.cmd["claw"] = -self.speed
            self.last_update["claw"] = now

    def on_timer(self):
        # Auto-stop joints if no key pressed recently
        now = time.time()
        for joint in self.cmd.keys():
            if now - self.last_update[joint] > self.key_timeout:
                self.cmd[joint] = 0.0

        # Publish all cmd_vel values continuously
        self.pub_shoulder.publish(Float64(data=float(self.cmd["shoulder"])))
        self.pub_elbow.publish(Float64(data=float(self.cmd["elbow"])))
        self.pub_wrist.publish(Float64(data=float(self.cmd["wrist"])))
        self.pub_claw.publish(Float64(data=float(self.cmd["claw"])))


def main():
    rclpy.init()

    # Put terminal in raw mode so we can read keys instantly
    old_attr = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    node = ArmKeyboardTeleop()

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.0)

            key = get_key_nonblocking()
            if key is not None:
                node.apply_key(key)

            time.sleep(0.005)

    except KeyboardInterrupt:
        pass
    finally:
        node.stop_all()
        # publish one more "stop"
        node.pub_shoulder.publish(Float64(data=0.0))
        node.pub_elbow.publish(Float64(data=0.0))
        node.pub_wrist.publish(Float64(data=0.0))
        node.pub_claw.publish(Float64(data=0.0))

        node.destroy_node()
        rclpy.shutdown()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attr)
        print("\nExiting arm teleop.")


if __name__ == "__main__":
    main()
