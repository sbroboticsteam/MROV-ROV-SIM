# EER Thruster Plugin (Gazebo Sim)

This directory contains the `EER_Thruster` Gazebo Sim system plugin, including support for the custom `ESCCmd` mode (ESC input 0–255 mapped to thrust and angular velocity using BlueRobotics T200 behavior CSV files).

---

## ✅ Requirements

- Gazebo Sim (Ignition / Gazebo Garden / Fortress depending on your environment)
- `gz` CLI installed and working
- CMake + a C++ compiler (gcc/clang)

---

## ✅ Build + Install (Recommended)

From the **root of your workspace** (the folder containing `src/`):

```bash
rm -rf build/ plugins/
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build . -j$(nproc)