#ifndef LIBREVOLVE_PROTOCOL_H
#define LIBREVOLVE_PROTOCOL_H

#include <stddef.h>

#define LV_SERVICE_UUID "0000ffe0-0000-1000-8000-00805f9b34fb"
#define LV_CHAR_UUID "0000ffe1-0000-1000-8000-00805f9b34fb"

#define LV_DEFAULT_READ_DELAY_MS 30
#define LV_DEFAULT_ROTATION_SPEED 50.0
#define LV_DEFAULT_TILT_SPEED 15.0

#define LV_TILT_MIN (-30.0)
#define LV_TILT_MAX 30.0

#define LV_CMD_MAX 64

int lv_cmd_turn_angle(char *buf, size_t n, double degrees);
int lv_cmd_turn_speed(char *buf, size_t n, double speed);
int lv_cmd_turn_continue(char *buf, size_t n, int direction);
int lv_cmd_rotation_stop(char *buf, size_t n);
int lv_cmd_rotation_zero(char *buf, size_t n);

int lv_cmd_tilt_value(char *buf, size_t n, double degrees);
int lv_cmd_tilt_speed(char *buf, size_t n, double speed);
int lv_cmd_tilt_stop(char *buf, size_t n);
int lv_cmd_tilt_zero(char *buf, size_t n);

int lv_cmd_query_rotation_angle(char *buf, size_t n);
int lv_cmd_query_rotation_speed(char *buf, size_t n);
int lv_cmd_query_tilt_angle(char *buf, size_t n);
int lv_cmd_query_tilt_speed(char *buf, size_t n);

int lv_parse_data_value(const char *response, double *out);
int lv_parse_data_int(const char *response, int *out);

#endif
