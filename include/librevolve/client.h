#ifndef LIBREVOLVE_CLIENT_H
#define LIBREVOLVE_CLIENT_H

#include <stddef.h>

#define LV_RESPONSE_MAX 128
#define LV_ADDRESS_MAX 64

typedef struct lv_client lv_client_t;

struct lv_client {
    void *peripheral; /* opaque SimpleBLE peripheral handle */
    char address[LV_ADDRESS_MAX];
    int connected;
};

/* Scan timeout in milliseconds; writes up to max_devices (address, name) pairs. Returns count. */
int lv_scan(const char *service_uuid, int timeout_ms, char addresses[][LV_ADDRESS_MAX], char names[][LV_ADDRESS_MAX], int max_devices);

/* Scan and return only devices with DAT-like advertised names. */
int lv_scan_dat(int timeout_ms, char addresses[][LV_ADDRESS_MAX], char names[][LV_ADDRESS_MAX], int max_devices);

int lv_connect(lv_client_t *client, const char *address, int timeout_ms);
int lv_disconnect(lv_client_t *client);

/* Send command; response written to resp (may be empty). Returns 0 on success. */
int lv_send(lv_client_t *client, const char *cmd, char *resp, size_t resp_size, int read_delay_ms);

int lv_rotate(lv_client_t *client, double degrees);
int lv_tilt(lv_client_t *client, double degrees);
int lv_stop(lv_client_t *client);
int lv_get_rotation_angle(lv_client_t *client, int *angle);

#endif
