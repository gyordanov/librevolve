#include "librevolve/client.h"
#include "librevolve/protocol.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void usage(const char *prog) {
    fprintf(stderr,
            "Usage: %s <command> [args]\n"
            "Commands:\n"
            "  scan\n"
            "  rotate <degrees> <address>\n"
            "  tilt <degrees> <address>\n"
            "  angle <address>\n"
            "  stop <address>\n"
            "  send \"<command>\" <address>\n",
            prog);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        usage(argv[0]);
        return 1;
    }

    const char *cmd = argv[1];

    if (strcmp(cmd, "scan") == 0) {
        char addresses[32][LV_ADDRESS_MAX];
        char names[32][LV_ADDRESS_MAX];
        int n = lv_scan(LV_SERVICE_UUID, 10000, addresses, names, 32);
        if (n == 0) {
            fprintf(stderr, "No devices found\n");
            return 1;
        }
        for (int i = 0; i < n; ++i) {
            printf("%s\t%s\n", addresses[i], names[i]);
        }
        return 0;
    }

    if (argc < 3) {
        usage(argv[0]);
        return 1;
    }

    lv_client_t client = {0};
    const char *address = NULL;

    if (strcmp(cmd, "send") == 0) {
        if (argc < 4) {
            usage(argv[0]);
            return 1;
        }
        const char *raw = argv[2];
        address = argv[3];
        if (lv_connect(&client, address, 30000) != 0) {
            fprintf(stderr, "Connect failed\n");
            return 1;
        }
        char resp[LV_RESPONSE_MAX];
        int rc = lv_send(&client, raw, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS);
        if (rc == 0 && resp[0]) {
            printf("%s\n", resp);
        }
        lv_disconnect(&client);
        return rc;
    }

    if (strcmp(cmd, "rotate") == 0 || strcmp(cmd, "tilt") == 0 || strcmp(cmd, "angle") == 0 ||
        strcmp(cmd, "stop") == 0) {
        if (strcmp(cmd, "rotate") == 0 || strcmp(cmd, "tilt") == 0) {
            if (argc < 4) {
                usage(argv[0]);
                return 1;
            }
            address = argv[3];
        } else {
            address = argv[2];
        }
    } else {
        usage(argv[0]);
        return 1;
    }

    if (lv_connect(&client, address, 30000) != 0) {
        fprintf(stderr, "Connect failed\n");
        return 1;
    }

    int rc = 0;
    if (strcmp(cmd, "rotate") == 0) {
        rc = lv_rotate(&client, atof(argv[2]));
    } else if (strcmp(cmd, "tilt") == 0) {
        rc = lv_tilt(&client, atof(argv[2]));
    } else if (strcmp(cmd, "angle") == 0) {
        int angle = 0;
        rc = lv_get_rotation_angle(&client, &angle);
        if (rc == 0) {
            printf("%d\n", angle);
        }
    } else if (strcmp(cmd, "stop") == 0) {
        rc = lv_stop(&client);
    }

    lv_disconnect(&client);
    return rc == 0 ? 0 : 1;
}
