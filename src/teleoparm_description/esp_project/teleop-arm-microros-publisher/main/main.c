#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#include "esp_err.h"
#include "esp_wifi.h"

#include <uros_network_interfaces.h>

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>

#ifdef CONFIG_MICRO_ROS_ESP_XRCE_DDS_MIDDLEWARE
#include <rmw_microros/rmw_microros.h>
#endif

#include <sensor_msgs/msg/imu.h>
#include <rosidl_runtime_c/string_functions.h>

#include "driver/uart.h"
#include "BNO08x_rvc.h"

// ------------------------- User config -------------------------

#define IMU1_UART        UART_NUM_1
#define IMU2_UART        UART_NUM_2
#define IMU1_RX_PIN      8
#define IMU2_RX_PIN      14

#define UART_RX_BUF_SIZE (4096)
#define UART_EVT_Q_LEN   (20)

// 100 Hz => 10 ms period
#define PUB_PERIOD_MS    (10)

// Core/pin/priorities (ESP32-S3: keep app on core 1; Wi-Fi runs mainly on core 0)
#define APP_CORE         (1)
#define UROS_TASK_PRIO   (5)
#define UROS_TASK_STACK  (8192)

#define UART_TASK_PRIO   (6)
#define UART_TASK_STACK  (4096)

// ------------------------- Fast “latest sample” queues -------------------------

static QueueHandle_t q_imu1_latest = NULL;
static QueueHandle_t q_imu2_latest = NULL;

// ------------------------- UART RX tasks -------------------------

typedef struct {
  uart_port_t uart_num;
  QueueHandle_t evt_q;
  QueueHandle_t out_latest_q;
} imu_uart_task_args_t;

static void imu_uart_task(void *arg)
{
  imu_uart_task_args_t *a = (imu_uart_task_args_t *)arg;

  bno08x_rvc_sync_t sync = {0};
  uint8_t pkt[BNO08X_RVC_PKT_LEN];
  bno08x_rvc_sample_t s;

  uart_event_t ev;

  for (;;) {
    if (xQueueReceive(a->evt_q, &ev, portMAX_DELAY) != pdTRUE) {
      continue;
    }

    if (ev.type == UART_DATA) {
      // Drain packets without blocking
      while (bno08x_rvc_read_packet(a->uart_num, &sync, pkt, 0)) {
        if (bno08x_rvc_parse_sample(pkt, &s)) {
          // Keep only the newest sample
          xQueueOverwrite(a->out_latest_q, &s);
        }
      }
    } else if (ev.type == UART_FIFO_OVF || ev.type == UART_BUFFER_FULL) {
      uart_flush_input(a->uart_num);
      xQueueReset(a->evt_q);
      sync.stash_len = 0;
    }
  }
}

// ------------------------- micro-ROS helpers -------------------------

#define RCCHECK(fn) do {                     \
  rcl_ret_t _rc = (fn);                      \
  if (_rc != RCL_RET_OK) {                   \
    /* fail-fast: nothing else to do */      \
    vTaskDelete(NULL);                       \
  }                                          \
} while (0)

#define RCSOFTCHECK(fn) do {                 \
  rcl_ret_t _rc = (fn);                      \
  (void)_rc;                                 \
} while (0)

static inline void stamp_from_ns(int64_t ns, builtin_interfaces__msg__Time *t)
{
  if (ns < 0) ns = 0;
  t->sec = (int32_t)(ns / 1000000000LL);
  t->nanosec = (uint32_t)(ns % 1000000000LL);
}

static inline void fill_imu_msg(sensor_msgs__msg__Imu *msg,
                                const bno08x_rvc_sample_t *s)
{
  // Stamp
  stamp_from_ns(s->stamp_ns, &msg->header.stamp);

  // Orientation from yaw/pitch/roll
  bno08x_quat_t q = bno08x_rvc_ypr_to_quat(s->yaw_deg, s->pitch_deg, s->roll_deg);
  msg->orientation.x = q.x;
  msg->orientation.y = q.y;
  msg->orientation.z = q.z;
  msg->orientation.w = q.w;

  // Linear acceleration
  msg->linear_acceleration.x = s->ax_ms2;
  msg->linear_acceleration.y = s->ay_ms2;
  msg->linear_acceleration.z = s->az_ms2;
}

// ------------------------- micro-ROS main task -------------------------

static void micro_ros_task(void *arg)
{
  (void)arg;

  // For sustained 100 Hz over UDP, disable Wi-Fi power save.
  (void)esp_wifi_set_ps(WIFI_PS_NONE);

  // Create single-slot “latest sample” queues (no backlog)
  q_imu1_latest = xQueueCreate(1, sizeof(bno08x_rvc_sample_t));
  q_imu2_latest = xQueueCreate(1, sizeof(bno08x_rvc_sample_t));
  if (!q_imu1_latest || !q_imu2_latest) {
    vTaskDelete(NULL);
  }

  // Init UARTs with event queues
  QueueHandle_t imu1_evt_q = NULL;
  QueueHandle_t imu2_evt_q = NULL;

  ESP_ERROR_CHECK(bno08x_rvc_uart_init(IMU1_UART, IMU1_RX_PIN, UART_RX_BUF_SIZE, UART_EVT_Q_LEN, &imu1_evt_q));
  ESP_ERROR_CHECK(bno08x_rvc_uart_init(IMU2_UART, IMU2_RX_PIN, UART_RX_BUF_SIZE, UART_EVT_Q_LEN, &imu2_evt_q));

  // Start UART RX tasks
  static imu_uart_task_args_t imu1_args;
  static imu_uart_task_args_t imu2_args;

  imu1_args.uart_num = IMU1_UART;
  imu1_args.evt_q = imu1_evt_q;
  imu1_args.out_latest_q = q_imu1_latest;

  imu2_args.uart_num = IMU2_UART;
  imu2_args.evt_q = imu2_evt_q;
  imu2_args.out_latest_q = q_imu2_latest;

  xTaskCreatePinnedToCore(imu_uart_task, "imu1_uart", UART_TASK_STACK, &imu1_args, UART_TASK_PRIO, NULL, APP_CORE);
  xTaskCreatePinnedToCore(imu_uart_task, "imu2_uart", UART_TASK_STACK, &imu2_args, UART_TASK_PRIO, NULL, APP_CORE);

  // ---- micro-ROS init (retry until agent is up) ----
  for (;;) {
    rcl_allocator_t allocator = rcl_get_default_allocator();
    rclc_support_t support;

    rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
    rcl_node_t node = rcl_get_zero_initialized_node();

    rcl_publisher_t pub1 = rcl_get_zero_initialized_publisher();
    rcl_publisher_t pub2 = rcl_get_zero_initialized_publisher();

    // Init options
    if (rcl_init_options_init(&init_options, allocator) != RCL_RET_OK) {
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }

#ifdef CONFIG_MICRO_ROS_ESP_XRCE_DDS_MIDDLEWARE
    rmw_init_options_t *rmw_options = rcl_init_options_get_rmw_init_options(&init_options);
    if (rmw_uros_options_set_udp_address(CONFIG_MICRO_ROS_AGENT_IP,
                                         CONFIG_MICRO_ROS_AGENT_PORT,
                                         rmw_options) != RCL_RET_OK) {
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }
#endif

    // Context/support (fails if agent not reachable yet)
    if (rclc_support_init_with_options(&support, 0, NULL, &init_options, &allocator) != RCL_RET_OK) {
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }

    // Node
    if (rclc_node_init_default(&node, "bno08x_rvc_node", "", &support) != RCL_RET_OK) {
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }

    // Publishers: try Best Effort first (better for high-rate sensor streaming),
    // fallback to Reliable if BE is not supported in your build.
    rcl_ret_t rc1 = rclc_publisher_init_best_effort(
        &pub1, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu),
        "/chest_imu/imu/chestimu_1");

    if (rc1 != RCL_RET_OK) {
      rc1 = rclc_publisher_init_default(
          &pub1, &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu),
          "/chest_imu/imu/chestimu_1");
    }

    rcl_ret_t rc2 = rclc_publisher_init_best_effort(
        &pub2, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu),
        "/arm_imu/imu/armimu_1");

    if (rc2 != RCL_RET_OK) {
      rc2 = rclc_publisher_init_default(
          &pub2, &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu),
          "/arm_imu/imu/armimu_1");
    }

    if (rc1 != RCL_RET_OK || rc2 != RCL_RET_OK) {
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }

    // Pre-init messages once (no per-loop allocation)
    sensor_msgs__msg__Imu msg1;
    sensor_msgs__msg__Imu msg2;
    sensor_msgs__msg__Imu__init(&msg1);
    sensor_msgs__msg__Imu__init(&msg2);

    // Set frame_id once (do NOT assign every publish)
    (void)rosidl_runtime_c__String__assign(&msg1.header.frame_id, "chestimu_1");
    (void)rosidl_runtime_c__String__assign(&msg2.header.frame_id, "armimu_1");

    // Covariances unknown: set once
    for (int i = 0; i < 9; i++) {
      msg1.orientation_covariance[i] = -1.0;
      msg1.angular_velocity_covariance[i] = -1.0;
      msg1.linear_acceleration_covariance[i] = -1.0;

      msg2.orientation_covariance[i] = -1.0;
      msg2.angular_velocity_covariance[i] = -1.0;
      msg2.linear_acceleration_covariance[i] = -1.0;
    }

    // Last-known samples (publish only after first data arrives)
    bno08x_rvc_sample_t s1 = {0};
    bno08x_rvc_sample_t s2 = {0};
    bool have1 = false;
    bool have2 = false;

    // ---- Tight 100 Hz publish loop (no executor) ----
    TickType_t last_wake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(PUB_PERIOD_MS);

    while (1) {
      // Grab newest samples (non-blocking)
      if (xQueueReceive(q_imu1_latest, &s1, 0) == pdTRUE) have1 = true;
      if (xQueueReceive(q_imu2_latest, &s2, 0) == pdTRUE) have2 = true;

      if (have1) {
        fill_imu_msg(&msg1, &s1);
        RCSOFTCHECK(rcl_publish(&pub1, &msg1, NULL));
      }

      if (have2) {
        fill_imu_msg(&msg2, &s2);
        RCSOFTCHECK(rcl_publish(&pub2, &msg2, NULL));
      }

      vTaskDelayUntil(&last_wake, period);
    }
  }
}

void app_main(void)
{
#if defined(CONFIG_MICRO_ROS_ESP_NETIF_WLAN) || defined(CONFIG_MICRO_ROS_ESP_NETIF_ENET)
  ESP_ERROR_CHECK(uros_network_interface_initialize());
#endif

  xTaskCreatePinnedToCore(micro_ros_task, "uros_task",
                          UROS_TASK_STACK, NULL, UROS_TASK_PRIO,
                          NULL, APP_CORE);
}
