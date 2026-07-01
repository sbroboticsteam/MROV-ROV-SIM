cmake_minimum_required(VERSION 3.8)
project(encoder_plugins)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ----------------------------
# Dependencies
# ----------------------------
find_package(ament_cmake REQUIRED)

# Gazebo Harmonic stack
find_package(gz-sim8 REQUIRED)
find_package(gz-plugin2 REQUIRED)
find_package(gz-transport13 REQUIRED)
find_package(gz-msgs10 REQUIRED)

# ----------------------------
# Library target
# ----------------------------
add_library(BRT27 SHARED
  src/BRT27.cpp
)

target_compile_features(BRT27 PUBLIC cxx_std_17)

# ----------------------------
# Link Gazebo libraries
# ----------------------------
target_link_libraries(BRT27
  gz-sim8::gz-sim8
  gz-plugin2::gz-plugin2
  gz-transport13::gz-transport13
  gz-msgs10::gz-msgs10
)

# ----------------------------
# Install plugin library
# ----------------------------
install(TARGETS BRT27
  LIBRARY DESTINATION lib/${PROJECT_NAME}
)

# ----------------------------
# Make plugin discoverable
# ----------------------------
ament_export_libraries(BRT27)

ament_package()