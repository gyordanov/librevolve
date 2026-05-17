#include "librevolve/protocol.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int write_cmd(char *buf, size_t n, const char *cmd) {
    int len = snprintf(buf, n, "%s", cmd);
    if (len < 0 || (size_t)len >= n) {
        return -1;
    }
    return 0;
}

static int format_value(char *out, size_t n, double value) {
    int len = snprintf(out, n, "%g", value);
    if (len < 0 || (size_t)len >= n) {
        return -1;
    }
    for (char *p = out; *p; ++p) {
        *p = (char)toupper((unsigned char)*p);
    }
    return 0;
}

int lv_cmd_turn_angle(char *buf, size_t n, double degrees) {
    char val[32];
    if (format_value(val, sizeof(val), degrees) != 0) {
        return -1;
    }
    char cmd[LV_CMD_MAX];
    if (snprintf(cmd, sizeof(cmd), "+CT,TURNANGLE=%s;", val) >= (int)sizeof(cmd)) {
        return -1;
    }
    return write_cmd(buf, n, cmd);
}

int lv_cmd_turn_speed(char *buf, size_t n, double speed) {
    char val[32];
    if (format_value(val, sizeof(val), speed) != 0) {
        return -1;
    }
    char cmd[LV_CMD_MAX];
    if (snprintf(cmd, sizeof(cmd), "+CT,TURNSPEED=%s;", val) >= (int)sizeof(cmd)) {
        return -1;
    }
    return write_cmd(buf, n, cmd);
}

int lv_cmd_turn_continue(char *buf, size_t n, int direction) {
    if (direction < -1 || direction > 1) {
        return -1;
    }
    char cmd[LV_CMD_MAX];
    snprintf(cmd, sizeof(cmd), "+CT,TURNCONTINUE=%d;", direction);
    return write_cmd(buf, n, cmd);
}

int lv_cmd_rotation_stop(char *buf, size_t n) {
    return write_cmd(buf, n, "+CT,STOP;");
}

int lv_cmd_rotation_zero(char *buf, size_t n) {
    return write_cmd(buf, n, "+CT,TOZERO;");
}

int lv_cmd_tilt_value(char *buf, size_t n, double degrees) {
    if (degrees < LV_TILT_MIN) {
        degrees = LV_TILT_MIN;
    }
    if (degrees > LV_TILT_MAX) {
        degrees = LV_TILT_MAX;
    }
    char val[32];
    if (format_value(val, sizeof(val), degrees) != 0) {
        return -1;
    }
    char cmd[LV_CMD_MAX];
    if (snprintf(cmd, sizeof(cmd), "+CR,TILTVALUE=%s;", val) >= (int)sizeof(cmd)) {
        return -1;
    }
    return write_cmd(buf, n, cmd);
}

int lv_cmd_tilt_speed(char *buf, size_t n, double speed) {
    char val[32];
    if (format_value(val, sizeof(val), speed) != 0) {
        return -1;
    }
    char cmd[LV_CMD_MAX];
    if (snprintf(cmd, sizeof(cmd), "+CR,TILTSPEED=%s;", val) >= (int)sizeof(cmd)) {
        return -1;
    }
    return write_cmd(buf, n, cmd);
}

int lv_cmd_tilt_stop(char *buf, size_t n) {
    return write_cmd(buf, n, "+CR,STOP;");
}

int lv_cmd_tilt_zero(char *buf, size_t n) {
    return write_cmd(buf, n, "+CR,TOZERO;");
}

int lv_cmd_query_rotation_angle(char *buf, size_t n) {
    return write_cmd(buf, n, "+QT,CHANGEANGLE;");
}

int lv_cmd_query_rotation_speed(char *buf, size_t n) {
    return write_cmd(buf, n, "+QT,TURNSPEED;");
}

int lv_cmd_query_tilt_angle(char *buf, size_t n) {
    return write_cmd(buf, n, "+QR,TILTANGLE;");
}

int lv_cmd_query_tilt_speed(char *buf, size_t n) {
    return write_cmd(buf, n, "+QR,TILTSPEED;");
}

int lv_parse_data_value(const char *response, double *out) {
    if (!response || !out) {
        return -1;
    }
    while (*response == ' ' || *response == '\t') {
        ++response;
    }
    if (strncasecmp(response, "+DATA=", 6) != 0) {
        return -1;
    }
    response += 6;
    char *end = NULL;
    double value = strtod(response, &end);
    if (end == response) {
        return -1;
    }
    *out = value;
    return 0;
}

int lv_parse_data_int(const char *response, int *out) {
    double value = 0;
    if (lv_parse_data_value(response, &value) != 0 || !out) {
        return -1;
    }
    *out = (int)lround(value);
    return 0;
}
