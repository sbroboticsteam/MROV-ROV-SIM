#pragma once

#include <stdint.h>
#include <stdbool.h>

#include "esp_err.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

// The BNO08x UART-RVC packet length is always 19 bytes
#define BNO08X_RVC_PKT_LEN 19

// Parsed IMU sample (engineering units)
typedef struct {
    uint8_t index;
    float yaw_deg;
    float pitch_deg;
    float roll_deg;
    float ax_ms2;
    float ay_ms2;
    float az_ms2;
    int64_t stamp_ns;   // timestamp in nanoseconds (derived from esp_timer_get_time)
} bno08x_rvc_sample_t;

// Quaternion type
typedef struct {
    float w, x, y, z;
} bno08x_quat_t;

// Per-UART resync stash/state (must be one per UART stream)
typedef struct {
    uint8_t stash[64];
    int stash_len;
} bno08x_rvc_sync_t;

/**
 * Initialize a UART port for BNO08x UART-RVC RX-only operation.
 *
 * - Installs the UART driver with an event queue (optional but recommended).
 * - Configures 115200-8N1, RX pin, no flow control.
 *
 * @param uart_num UART port (UART_NUM_1, UART_NUM_2, etc.)
 * @param rx_pin   GPIO number used as RX
 * @param rx_buf_size RX ring buffer size in bytes (e.g. 1024 or 4096)
 * @param evt_queue_len UART event queue length (e.g. 20)
 * @param out_evt_queue If non-NULL, receives the created event queue handle
 */
esp_err_t bno08x_rvc_uart_init(uart_port_t uart_num,
                              int rx_pin,
                              int rx_buf_size,
                              int evt_queue_len,
                              QueueHandle_t *out_evt_queue);

/**
 * Try to extract one VERIFIED raw 19-byte packet from a UART stream.
 *
 * This function:
 * - reads from the UART RX ring buffer into st->stash
 * - searches for header 0xAA 0xAA
 * - verifies checksum
 * - on success copies the packet into out_pkt and returns true
 *
 * @param wait_ticks How long uart_read_bytes is allowed to block when more data is needed.
 *                   Use 0 for "don't block" (useful when called after UART_DATA event).
 */
bool bno08x_rvc_read_packet(uart_port_t uart_num,
                            bno08x_rvc_sync_t *st,
                            uint8_t out_pkt[BNO08X_RVC_PKT_LEN],
                            TickType_t wait_ticks);

/**
 * Parse a verified packet into a sample.
 * Returns false if header/checksum fail.
 */
bool bno08x_rvc_parse_sample(const uint8_t pkt[BNO08X_RVC_PKT_LEN],
                             bno08x_rvc_sample_t *out);

/**
 * Convert yaw/pitch/roll (degrees) to quaternion using datasheet order:
 * apply rotations in order yaw (Z), pitch (Y), roll (X) => Rz * Ry * Rx.
 */
bno08x_quat_t bno08x_rvc_ypr_to_quat(float yaw_deg, float pitch_deg, float roll_deg);
