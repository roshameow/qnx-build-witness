/*
 * Minimal QNX 8.0 target-side test used by the QNX Build Witness codelab.
 *
 * It exercises QNX native message passing: create a channel, attach to it,
 * send a pulse, receive the pulse, and verify its code/value. This is a real
 * QNX-specific API sequence; it is not a portable POSIX-only hello-world.
 */

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/neutrino.h>

#define QBW_TEST_PULSE_CODE 42
#define QBW_TEST_PULSE_VALUE 7

int main(void) {
    int chid = ChannelCreate(0);
    if (chid == -1) {
        fprintf(stderr, "ChannelCreate failed: %s\n", strerror(errno));
        return 1;
    }

    int coid = ConnectAttach(0, 0, chid, 0, 0);
    if (coid == -1) {
        fprintf(stderr, "ConnectAttach failed: %s\n", strerror(errno));
        ChannelDestroy(chid);
        return 1;
    }

    if (MsgSendPulse(coid, -1, QBW_TEST_PULSE_CODE, QBW_TEST_PULSE_VALUE) == -1) {
        fprintf(stderr, "MsgSendPulse failed: %s\n", strerror(errno));
        ConnectDetach(coid);
        ChannelDestroy(chid);
        return 1;
    }

    struct _pulse pulse;
    memset(&pulse, 0, sizeof(pulse));
    if (MsgReceive(chid, &pulse, sizeof(pulse), NULL) <= 0) {
        fprintf(stderr, "MsgReceive failed: %s\n", strerror(errno));
        ConnectDetach(coid);
        ChannelDestroy(chid);
        return 1;
    }

    int ok = (pulse.type == _PULSE_TYPE &&
              pulse.code == QBW_TEST_PULSE_CODE &&
              pulse.value.sival_int == QBW_TEST_PULSE_VALUE);

    ConnectDetach(coid);
    ChannelDestroy(chid);

    if (!ok) {
        fprintf(stderr, "unexpected pulse: type=%d code=%d value=%d\n",
                pulse.type, pulse.code, pulse.value.sival_int);
        return 1;
    }

    puts("QBW_QNX_TARGET_TEST_PASS");
    return 0;
}
