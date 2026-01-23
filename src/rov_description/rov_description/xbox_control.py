#!/usr/bin/env python3
import time
from typing import Dict

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Joy
from std_msgs.msg import Int32, Float64


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def apply_deadzone(x: float, dz: float) -> float:
    if abs(x) < dz:
        return 0.0
    return x


def normalize_mix(vals: Dict[str, float], max_mag: float = 1.0) -> Dict[str, float]:
    """If any output magnitude exceeds max_mag, scale them all down uniformly."""
    peak = max(abs(v) for v in vals.values()) if vals else 0.0
    if peak <= max_mag or peak < 1e-9:
        return vals
    scale = max_mag / peak
    return {k: v * scale for k, v in vals.items()}


def axis_to_trigger01(x: float) -> float:
    """
    Convert a trigger axis that ranges 1 (free) to -1 (pressed)
    into 0..1 (0 free, 1 fully pressed).
    """
    return clamp((1.0 - x) * 0.5, 0.0, 1.0)


def thruster_float_to_esc(v: float) -> int:
    """
    Map [-1, 1] to [0, 255].
    Neutral is near 127/128.
    """
    v = clamp(v, -1.0, 1.0)
    esc = int(round((v + 1.0) * 0.5 * 255.0))
    return int(clamp(esc, 0, 255))


class ROVJoyTeleop(Node):
    def __init__(self):
        super().__init__("rov_joy_teleop")

        # -------- Parameters --------
        self.deadzone = float(self.declare_parameter("deadzone", 0.06).value)

        # Thruster gains (feel free to tweak)
        self.g_surge = float(self.declare_parameter("gain_surge", 1.0).value)
        self.g_sway  = float(self.declare_parameter("gain_sway", 1.0).value)
        self.g_yaw   = float(self.declare_parameter("gain_yaw", 1.0).value)
        self.g_heave = float(self.declare_parameter("gain_heave", 1.0).value)
        self.g_pitch = float(self.declare_parameter("gain_pitch", 0.7).value)

        # If any axis feels inverted, flip these
        self.inv_surge = bool(self.declare_parameter("invert_surge", False).value)
        self.inv_sway  = bool(self.declare_parameter("invert_sway", False).value)
        self.inv_yaw   = bool(self.declare_parameter("invert_yaw", False).value)
        self.inv_pitch = bool(self.declare_parameter("invert_pitch", False).value)

        # Arm speed in rad/s for servo plugin (velocity command)
        self.arm_speed = float(self.declare_parameter("arm_speed", 1.0).value)

        # Safety timeout if /joy stops
        self.joy_timeout_sec = float(self.declare_parameter("joy_timeout_sec", 0.5).value)

        # Publish rate
        self.publish_hz = float(self.declare_parameter("publish_hz", 30.0).value)

        # -------- Publishers --------
        # Thrusters
        self.pub_thr = {
            "backleft":      self.create_publisher(Int32, "/rov/backleft", 10),
            "backright":     self.create_publisher(Int32, "/rov/backright", 10),
            "frontleft":     self.create_publisher(Int32, "/rov/frontleft", 10),
            "frontright":    self.create_publisher(Int32, "/rov/frontright", 10),
            "topbackleft":   self.create_publisher(Int32, "/rov/topbackleft", 10),
            "topbackright":  self.create_publisher(Int32, "/rov/topbackright", 10),
            "topfrontleft":  self.create_publisher(Int32, "/rov/topfrontleft", 10),
            "topfrontright": self.create_publisher(Int32, "/rov/topfrontright", 10),
        }

        # Arm (servo cmd_vel)
        self.pub_arm = {
            "shoulder": self.create_publisher(Float64, "/rov/shoulder", 10),
            "elbow":    self.create_publisher(Float64, "/rov/elbow", 10),
            "wrist":    self.create_publisher(Float64, "/rov/wrist", 10),
            "claw":     self.create_publisher(Float64, "/rov/claw", 10),
        }

        # -------- Subscriber --------
        self.sub = self.create_subscription(Joy, "/joy", self.on_joy, 10)

        # Internal state
        self.last_joy_time = 0.0
        self.last_thruster_cmd = {k: 0.0 for k in self.pub_thr.keys()}
        self.last_arm_cmd = {k: 0.0 for k in self.pub_arm.keys()}

        # Timer loop
        self.timer = self.create_timer(1.0 / self.publish_hz, self.on_timer)

        self.get_logger().info("ROVJoyTeleop running: /joy -> thrusters + arm")

    def stop_all(self):
        for k in self.last_thruster_cmd.keys():
            self.last_thruster_cmd[k] = 0.0
        for k in self.last_arm_cmd.keys():
            self.last_arm_cmd[k] = 0.0

    def on_joy(self, msg: Joy):
        self.last_joy_time = time.time()

        axes = msg.axes
        buttons = msg.buttons

        # ---- Axis mapping from your description ----
        # axes[2] trigger: 1 -> -1 : go DOWN
        # axes[5] trigger: 1 -> -1 : go UP
        # axes[1] surge forward/back: -1..1
        # axes[0] strafe left/right: -1..1
        # axes[3] yaw left/right: -1..1
        # axes[4] pitch up/down: -1..1
        #
        # axes[6] dpad: wrist (-1..1)
        # axes[7] dpad: claw  (-1..1)

        def get_axis(i: int, default: float = 0.0) -> float:
            return axes[i] if i < len(axes) else default

        def get_btn(i: int) -> int:
            return buttons[i] if i < len(buttons) else 0

        surge = apply_deadzone(get_axis(1), self.deadzone) * self.g_surge
        sway  = apply_deadzone(get_axis(0), self.deadzone) * self.g_sway
        yaw   = apply_deadzone(get_axis(3), self.deadzone) * self.g_yaw
        pitch = apply_deadzone(get_axis(4), self.deadzone) * self.g_pitch

        if self.inv_surge: surge *= -1.0
        if self.inv_sway:  sway  *= -1.0
        if self.inv_yaw:   yaw   *= -1.0
        if self.inv_pitch: pitch *= -1.0

        down_trig = axis_to_trigger01(get_axis(5, 1.0))  # 0..1
        up_trig   = axis_to_trigger01(get_axis(2, 1.0))  # 0..1

        # Heave (+up, -down)
        heave = (up_trig - down_trig) * self.g_heave

        # ---- Thruster mixing ----
        #
        # Horizontal (surge/sway/yaw):
        #  FL = surge + sway - yaw
        #  FR = surge - sway + yaw
        #  BL = surge - sway - yaw
        #  BR = surge + sway + yaw
        #
        # Vertical (heave + pitch):
        #  Front vertical = heave - pitch
        #  Back  vertical = heave + pitch
        #
        # This gives pitch control using vertical thrusters.
        #

        horiz = {
            "frontleft":  -1 * (surge + sway - yaw),
            "frontright": -1 * (surge - sway + yaw),
            "backleft":   surge - sway - yaw,
            "backright":  surge + sway + yaw,
        }
        horiz = normalize_mix(horiz, 1.0)

        vert = {
            "topfrontleft":  heave - pitch,
            "topfrontright": heave - pitch,
            "topbackleft":   heave + pitch,
            "topbackright":  heave + pitch,
        }
        vert = normalize_mix(vert, 1.0)

        # Store latest commands
        for k, v in horiz.items():
            self.last_thruster_cmd[k] = clamp(v, -1.0, 1.0)
        for k, v in vert.items():
            self.last_thruster_cmd[k] = clamp(v, -1.0, 1.0)

        # ---- Arm mapping ----
        # Buttons:
        # 0 -> +shoulder
        # 3 -> -shoulder
        # 1 -> +elbow
        # 2 -> -elbow
        #
        # axes[6] dpad -> wrist
        # axes[7] dpad -> claw

        shoulder_pos = get_btn(0)
        shoulder_neg = get_btn(3)
        elbow_pos    = get_btn(1)
        elbow_neg    = get_btn(2)

        shoulder_cmd = (shoulder_pos - shoulder_neg) * self.arm_speed
        elbow_cmd    = (elbow_pos - elbow_neg) * self.arm_speed

        wrist_axis = apply_deadzone(get_axis(6), self.deadzone)
        claw_axis  = apply_deadzone(get_axis(7), self.deadzone)

        wrist_cmd = wrist_axis * self.arm_speed
        claw_cmd  = claw_axis * self.arm_speed

        self.last_arm_cmd["shoulder"] = float(shoulder_cmd)
        self.last_arm_cmd["elbow"]    = float(elbow_cmd)
        self.last_arm_cmd["wrist"]    = float(wrist_cmd)
        self.last_arm_cmd["claw"]     = float(claw_cmd)

    def on_timer(self):
        now = time.time()

        # If joystick stopped publishing: stop everything
        if self.last_joy_time > 0.0 and (now - self.last_joy_time) > self.joy_timeout_sec:
            self.stop_all()

        # Publish thrusters as ESC 0..255 Int32
        for name, pub in self.pub_thr.items():
            v = self.last_thruster_cmd[name]
            esc = thruster_float_to_esc(v)
            pub.publish(Int32(data=int(esc)))

        # Publish arm cmd_vel as Float64 (rad/s)
        for name, pub in self.pub_arm.items():
            pub.publish(Float64(data=float(self.last_arm_cmd[name])))


def main():
    rclpy.init()
    node = ROVJoyTeleop()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_all()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
