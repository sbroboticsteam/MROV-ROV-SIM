#include "BNO08x_rvc.h"

#include <string.h>   // memcpy, memmove
#include <math.h>

#include "esp_timer.h"

// ---------- helpers ----------

static inline int16_t le_i16(uint8_t lsb, uint8_t msb)
{
    return (int16_t)((uint16_t)lsb | ((uint16_t)msb << 8));
}

// Datasheet: checksum is sum of bytes Index..Reserved (bytes 2..17), mod 256
static uint8_t rvc_checksum(const uint8_t *pkt)
{
    uint32_t sum = 0;
    for (int i = 2; i <= 17; i++) sum += pkt[i];
    return (uint8_t)(sum & 0xFF);
}

static inline float deg2rad(float deg)
{
    return deg * (float)M_PI / 180.0f;
}

static inline bno08x_quat_t quat_normalize(bno08x_quat_t q)
{
    float n = sqrtf(q.w*q.w + q.x*q.x + q.y*q.y + q.z*q.z);
    if (n > 0.0f) {
        q.w /= n; q.x /= n; q.y /= n; q.z /= n;
    }
    return q;
}

// ---------- public API ----------

esp_err_t bno08x_rvc_uart_init(uart_port_t uart_num,
                              int rx_pin,
                              int rx_buf_size,
                              int evt_queue_len,
                              QueueHandle_t *out_evt_queue)
{
    const uart_config_t cfg = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    // Install driver + (optional) event queue
    esp_err_t err = uart_driver_install(uart_num,
                                        rx_buf_size,
                                        0,                 // no TX buffer
                                        evt_queue_len,
                                        out_evt_queue,
                                        0);
    if (err != ESP_OK) return err;

    err = uart_param_config(uart_num, &cfg);
    if (err != ESP_OK) return err;

    // RX only: TX pin unchanged
    err = uart_set_pin(uart_num,
                       UART_PIN_NO_CHANGE,
                       rx_pin,
                       UART_PIN_NO_CHANGE,
                       UART_PIN_NO_CHANGE);
    return err;
}

bool bno08x_rvc_read_packet(uart_port_t uart_num,
                            bno08x_rvc_sync_t *st,
                            uint8_t out_pkt[BNO08X_RVC_PKT_LEN],
                            TickType_t wait_ticks)
{
    while (1) {
        // Ensure we have enough data to possibly contain a packet
        if (st->stash_len < BNO08X_RVC_PKT_LEN) {
            int n = uart_read_bytes(uart_num,
                                    st->stash + st->stash_len,
                                    (int)sizeof(st->stash) - st->stash_len,
                                    wait_ticks);
            if (n <= 0) return false;
            st->stash_len += n;
        }

        // Scan for header 0xAA 0xAA
        int i = 0;
        while (i + 1 < st->stash_len) {
            if (st->stash[i] == 0xAA && st->stash[i + 1] == 0xAA) {
                // Do we have a full packet from here?
                if (i + BNO08X_RVC_PKT_LEN <= st->stash_len) {
                    uint8_t *cand = &st->stash[i];

                    // Verify checksum before returning
                    if (rvc_checksum(cand) == cand[18]) {
                        memcpy(out_pkt, cand, BNO08X_RVC_PKT_LEN);

                        // Remove consumed bytes from stash
                        int remaining = st->stash_len - (i + BNO08X_RVC_PKT_LEN);
                        memmove(st->stash, cand + BNO08X_RVC_PKT_LEN, remaining);
                        st->stash_len = remaining;
                        return true;
                    }

                    // Bad checksum: shift by one and keep searching
                    i += 1;
                    continue;
                }

                // Header found but not enough bytes yet
                break;
            }
            i++;
        }

        // No valid packet found yet. Keep last byte so a trailing 0xAA can match next byte.
        if (st->stash_len > 1) {
            st->stash[0] = st->stash[st->stash_len - 1];
            st->stash_len = 1;
        }
    }
}

bool bno08x_rvc_parse_sample(const uint8_t pkt[BNO08X_RVC_PKT_LEN],
                             bno08x_rvc_sample_t *out)
{
    if (pkt[0] != 0xAA || pkt[1] != 0xAA) return false;
    if (rvc_checksum(pkt) != pkt[18]) return false;

    out->index = pkt[2];

    int16_t yaw   = le_i16(pkt[3],  pkt[4]);
    int16_t pitch = le_i16(pkt[5],  pkt[6]);
    int16_t roll  = le_i16(pkt[7],  pkt[8]);

    int16_t ax_mg = le_i16(pkt[9],  pkt[10]);
    int16_t ay_mg = le_i16(pkt[11], pkt[12]);
    int16_t az_mg = le_i16(pkt[13], pkt[14]);

    out->yaw_deg   = yaw   * 0.01f;
    out->pitch_deg = pitch * 0.01f;
    out->roll_deg  = roll  * 0.01f;

    // mg -> m/s^2
    const float MG_TO_MS2 = 0.00980665f;
    out->ax_ms2 = ax_mg * MG_TO_MS2;
    out->ay_ms2 = ay_mg * MG_TO_MS2;
    out->az_ms2 = az_mg * MG_TO_MS2;

    // esp_timer_get_time() is microseconds
    out->stamp_ns = (int64_t)esp_timer_get_time() * 1000;

    return true;
}

bno08x_quat_t bno08x_rvc_ypr_to_quat(float yaw_deg, float pitch_deg, float roll_deg)
{
    // Datasheet order: yaw then pitch then roll => Rz(yaw) * Ry(pitch) * Rx(roll)
    float hy = 0.5f * deg2rad(yaw_deg);
    float hp = 0.5f * deg2rad(pitch_deg);
    float hr = 0.5f * deg2rad(roll_deg);

    float cy = cosf(hy), sy = sinf(hy);
    float cp = cosf(hp), sp = sinf(hp);
    float cr = cosf(hr), sr = sinf(hr);

    bno08x_quat_t q;
    q.w = cy*cp*cr + sy*sp*sr;
    q.x = cy*cp*sr - sy*sp*cr;
    q.y = cy*sp*cr + sy*cp*sr;
    q.z = sy*cp*cr - cy*sp*sr;

    return quat_normalize(q);
}
