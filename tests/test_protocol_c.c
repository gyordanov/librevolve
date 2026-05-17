#include "librevolve/protocol.h"

#include <stdio.h>
#include <string.h>

static int expect_cmd(int (*builder)(char *, size_t, double), double arg, const char *expected) {
    char buf[LV_CMD_MAX];
    if (builder(buf, sizeof(buf), arg) != 0) {
        fprintf(stderr, "builder failed\n");
        return 1;
    }
    if (strcmp(buf, expected) != 0) {
        fprintf(stderr, "expected '%s', got '%s'\n", expected, buf);
        return 1;
    }
    return 0;
}

static int expect_str(int (*builder)(char *, size_t), const char *expected) {
    char buf[LV_CMD_MAX];
    if (builder(buf, sizeof(buf)) != 0) {
        return 1;
    }
    if (strcmp(buf, expected) != 0) {
        fprintf(stderr, "expected '%s', got '%s'\n", expected, buf);
        return 1;
    }
    return 0;
}

int main(void) {
    int failures = 0;
    failures += expect_cmd(lv_cmd_turn_angle, 45, "+CT,TURNANGLE=45;");
    failures += expect_cmd(lv_cmd_tilt_value, 10, "+CR,TILTVALUE=10;");
    failures += expect_cmd(lv_cmd_tilt_value, 50, "+CR,TILTVALUE=30;");
    failures += expect_str(lv_cmd_rotation_stop, "+CT,STOP;");
    failures += expect_str(lv_cmd_query_rotation_angle, "+QT,CHANGEANGLE;");

    int angle = 0;
    if (lv_parse_data_int("+DATA=120;", &angle) != 0 || angle != 120) {
        fprintf(stderr, "parse_data_int failed\n");
        failures += 1;
    }

    return failures == 0 ? 0 : 1;
}
