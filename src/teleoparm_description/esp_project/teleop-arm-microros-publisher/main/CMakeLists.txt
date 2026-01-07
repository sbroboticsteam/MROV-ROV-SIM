idf_component_register(
                    SRCS "BNO08x_rvc.c" "main.c"
                    INCLUDE_DIRS "."
                    REQUIRES driver esp_timer micro_ros_espidf_component
                    )
