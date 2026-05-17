#include "librevolve/client.h"
#include "librevolve/protocol.h"

#include <simplecble/adapter.h>
#include <simplecble/peripheral.h>
#include <simplecble/simpleble.h>
#include <simplecble/types.h>

#include <ctype.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static pthread_mutex_t g_send_lock = PTHREAD_MUTEX_INITIALIZER;

static simpleble_uuid_t lv_service_uuid(void) {
    simpleble_uuid_t uuid = {0};
    snprintf(uuid.value, sizeof(uuid.value), "%s", LV_SERVICE_UUID);
    return uuid;
}

static simpleble_uuid_t lv_char_uuid(void) {
    simpleble_uuid_t uuid = {0};
    snprintf(uuid.value, sizeof(uuid.value), "%s", LV_CHAR_UUID);
    return uuid;
}

static simpleble_adapter_t get_default_adapter(void) {
    size_t count = simpleble_adapter_get_count();
    if (count == 0) {
        return NULL;
    }
    return simpleble_adapter_get_handle(0);
}

static void copy_upper(char *dest, size_t n, const char *src) {
    size_t i = 0;
    for (; src[i] && i + 1 < n; ++i) {
        dest[i] = (char)toupper((unsigned char)src[i]);
    }
    dest[i] = '\0';
}

static int name_matches_hints(const char *name) {
    if (!name) {
        return 0;
    }
    char upper[128];
    copy_upper(upper, sizeof(upper), name);
    static const char *hints[] = {"REVO_DUAL", "REVOPOINT", "DUAL_AXIS", "DUAL-AXIS", "DAT", "TURNTABLE", NULL};
    for (int i = 0; hints[i]; ++i) {
        if (strstr(upper, hints[i]) != NULL) {
            return 1;
        }
    }
    return 0;
}

static simpleble_peripheral_t find_peripheral_by_address(simpleble_adapter_t adapter, const char *address) {
    size_t count = simpleble_adapter_scan_get_results_count(adapter);
    for (size_t i = 0; i < count; ++i) {
        simpleble_peripheral_t peripheral = simpleble_adapter_scan_get_results_handle(adapter, i);
        char *addr = simpleble_peripheral_address(peripheral);
        if (addr && strcmp(addr, address) == 0) {
            simpleble_free(addr);
            return peripheral;
        }
        if (addr) {
            simpleble_free(addr);
        }
    }
    return NULL;
}

int lv_scan(const char *service_uuid, int timeout_ms, char addresses[][LV_ADDRESS_MAX],
            char names[][LV_ADDRESS_MAX], int max_devices) {
    int dat_names_only = (service_uuid != NULL && service_uuid[0] != '\0');
    simpleble_adapter_t adapter = get_default_adapter();
    if (!adapter) {
        return 0;
    }

    if (simpleble_adapter_scan_for(adapter, timeout_ms) != SIMPLEBLE_SUCCESS) {
        return 0;
    }

    size_t count = simpleble_adapter_scan_get_results_count(adapter);
    int found = 0;
    for (size_t i = 0; i < count && found < max_devices; ++i) {
        simpleble_peripheral_t peripheral = simpleble_adapter_scan_get_results_handle(adapter, i);
        char *addr = simpleble_peripheral_address(peripheral);
        char *name = simpleble_peripheral_identifier(peripheral);
        if (!addr) {
            if (name) {
                simpleble_free(name);
            }
            continue;
        }
        if (dat_names_only && !name_matches_hints(name)) {
            simpleble_free(addr);
            if (name) {
                simpleble_free(name);
            }
            continue;
        }
        snprintf(addresses[found], LV_ADDRESS_MAX, "%s", addr);
        snprintf(names[found], LV_ADDRESS_MAX, "%s", name ? name : "");
        ++found;
        simpleble_free(addr);
        if (name) {
            simpleble_free(name);
        }
    }
    return found;
}

int lv_connect(lv_client_t *client, const char *address, int timeout_ms) {
    if (!client || !address) {
        return -1;
    }
    if (client->connected) {
        lv_disconnect(client);
    }

    simpleble_adapter_t adapter = get_default_adapter();
    if (!adapter) {
        return -1;
    }

    if (simpleble_adapter_scan_for(adapter, timeout_ms) != SIMPLEBLE_SUCCESS) {
        return -1;
    }

    simpleble_peripheral_t peripheral = find_peripheral_by_address(adapter, address);
    if (!peripheral) {
        return -1;
    }

    if (simpleble_peripheral_connect(peripheral) != SIMPLEBLE_SUCCESS) {
        return -1;
    }

    client->peripheral = peripheral;
    snprintf(client->address, sizeof(client->address), "%s", address);
    client->connected = 1;

    char cmd[LV_CMD_MAX];
    char resp[LV_RESPONSE_MAX];
    lv_cmd_turn_speed(cmd, sizeof(cmd), LV_DEFAULT_ROTATION_SPEED);
    lv_send(client, cmd, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS);
    lv_cmd_tilt_speed(cmd, sizeof(cmd), LV_DEFAULT_TILT_SPEED);
    lv_send(client, cmd, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS);

    return 0;
}

int lv_disconnect(lv_client_t *client) {
    if (!client || !client->connected || !client->peripheral) {
        return 0;
    }

    lv_stop(client);
    simpleble_peripheral_disconnect((simpleble_peripheral_t)client->peripheral);
    simpleble_peripheral_release_handle((simpleble_peripheral_t)client->peripheral);
    client->peripheral = NULL;
    client->connected = 0;
    client->address[0] = '\0';
    return 0;
}

int lv_send(lv_client_t *client, const char *cmd, char *resp, size_t resp_size, int read_delay_ms) {
    if (!client || !client->connected || !client->peripheral || !cmd) {
        return -1;
    }

    if (resp && resp_size > 0) {
        resp[0] = '\0';
    }

    simpleble_uuid_t service = lv_service_uuid();
    simpleble_uuid_t characteristic = lv_char_uuid();

    pthread_mutex_lock(&g_send_lock);

    /* DAT ffe1 supports write-without-response only. */
    simpleble_err_t err = simpleble_peripheral_write_command(
        (simpleble_peripheral_t)client->peripheral, service, characteristic, (const uint8_t *)cmd, strlen(cmd));

    if (err != SIMPLEBLE_SUCCESS) {
        pthread_mutex_unlock(&g_send_lock);
        return -1;
    }

    usleep((useconds_t)read_delay_ms * 1000);

    uint8_t *data = NULL;
    size_t data_length = 0;
    err = simpleble_peripheral_read((simpleble_peripheral_t)client->peripheral, service, characteristic, &data,
                                  &data_length);

    if (err == SIMPLEBLE_SUCCESS && data && resp && resp_size > 0) {
        size_t n = data_length < resp_size - 1 ? data_length : resp_size - 1;
        memcpy(resp, data, n);
        resp[n] = '\0';
        simpleble_free(data);
    } else if (data) {
        simpleble_free(data);
    }

    pthread_mutex_unlock(&g_send_lock);
    return err == SIMPLEBLE_SUCCESS ? 0 : -1;
}

int lv_rotate(lv_client_t *client, double degrees) {
    char cmd[LV_CMD_MAX];
    char resp[LV_RESPONSE_MAX];
    if (lv_cmd_turn_angle(cmd, sizeof(cmd), degrees) != 0) {
        return -1;
    }
    return lv_send(client, cmd, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS);
}

int lv_tilt(lv_client_t *client, double degrees) {
    char cmd[LV_CMD_MAX];
    char resp[LV_RESPONSE_MAX];
    if (lv_cmd_tilt_value(cmd, sizeof(cmd), degrees) != 0) {
        return -1;
    }
    return lv_send(client, cmd, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS);
}

int lv_stop(lv_client_t *client) {
    char cmd[LV_CMD_MAX];
    char resp[LV_RESPONSE_MAX];
    lv_cmd_rotation_stop(cmd, sizeof(cmd));
    lv_send(client, cmd, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS);
    usleep(50000);
    lv_cmd_tilt_stop(cmd, sizeof(cmd));
    return lv_send(client, cmd, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS);
}

int lv_get_rotation_angle(lv_client_t *client, int *angle) {
    char cmd[LV_CMD_MAX];
    char resp[LV_RESPONSE_MAX];
    if (!angle) {
        return -1;
    }
    lv_cmd_query_rotation_angle(cmd, sizeof(cmd));
    if (lv_send(client, cmd, resp, sizeof(resp), LV_DEFAULT_READ_DELAY_MS) != 0) {
        return -1;
    }
    return lv_parse_data_int(resp, angle);
}

int lv_scan_dat(int timeout_ms, char addresses[][LV_ADDRESS_MAX], char names[][LV_ADDRESS_MAX], int max_devices) {
    return lv_scan(LV_SERVICE_UUID, timeout_ms, addresses, names, max_devices);
}
