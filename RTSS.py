# https://github.com/Kaldaien/BMF/blob/master/BMF/RTSSSharedMemory.h

import mmap
import struct
from collections import defaultdict

last_dwTime0s = defaultdict(int)


def get_fps():
    global last_dwTime0
    mmap_size = 4485160  # 65536 for older versions ??
    mm = mmap.mmap(0, mmap_size, 'RTSSSharedMemoryV2')
    dwSignature, dwVersion, dwAppEntrySize, dwAppArrOffset, dwAppArrSize, dwOSDEntrySize, dwOSDArrOffset, dwOSDArrSize, dwOSDFrame = struct.unpack(
        '4sLLLLLLLL', mm[0:36])
    calc_mmap_size = dwAppArrOffset + dwAppArrSize * dwAppEntrySize
    if mmap_size < calc_mmap_size:
        #print('Adjusting RTSS mm size: %s -> %s' % (mmap_size, calc_mmap_size))
        mm = mmap.mmap(0, calc_mmap_size, 'RTSSSharedMemoryV2')
    # print '%s %08x' % (dwSignature, dwVersion)
    if dwSignature[::-1] not in [b'RTSS', b'SSTR'] or dwVersion < 0x00020000:
        print('RTSS signature/version fail: %s %08x' % (dwSignature, dwVersion))
        return None
    fps = None
    for dwEntry in range(0, dwAppEntrySize):
        entry = dwAppArrOffset + dwEntry * dwAppEntrySize
        stump = mm[entry:entry+6*4+260]
        if len(stump) == 0:
            continue
        dwProcessID, szName, dwFlags, dwTime0, dwTime1, dwFrames, dwFrameTime = struct.unpack('L260sLLLLL', stump)
        #print('%d %s\n%08x %d..%d %d %d' % (dwProcessID, szName[0:60], dwFlags, dwTime0, dwTime1, dwFrames, dwFrameTime))
        if dwTime0 > 0 and dwTime1 > 0 and dwFrames > 0:
            # 1000.0f * dwFrames / (dwTime1 - dwTime0) for framerate calculated once per second
            if dwTime0 != last_dwTime0s.get(dwProcessID):  # check for change: if same, process maybe dead
                fps = 1000 * dwFrames / (dwTime1 - dwTime0)
                #print('%d %08x %d..%d %d %d %.1f %s' % (dwProcessID, dwFlags, dwTime0, dwTime1, dwFrames, dwFrameTime, fps, szName[0:60].decode('utf-8')))
                last_dwTime0s[dwProcessID] = dwTime0
                # return fps
    return fps
