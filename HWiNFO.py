# usage:
#
# import HWiNFO
# hwinfo = HWiNFO.HwInfoRemote('127.0.0.1')
# data = hwinfo.get_data()
# hwinfo.close()


import socket
import struct
import datetime


HWINFO_VALUE_TYPES = {1: 'temperature', 2: 'voltage', 3: 'rpm', 5: 'power', 6: 'clock', 7: 'usage', 8: 'general'}


class HwInfoItem:
    def __init__(self, name, value, unit, value_type):
        self.name = name
        self.value = value
        self.unit = unit
        self.type = value_type

    def to_dict(self, group=None):
        ret = {'name': self.name, 'value': self.value, 'unit': self.unit, 'type': self.type}
        if group is not None:
            ret['group'] = group
        return ret

    def __eq__(self, other):
        return (self.name, self.type) == (other.name, other.type)


class HwInfoGroup:
    def __init__(self, name):
        self.name = name
        self.items = []

    def update(self, item):
        if item in self.items:
            self.items[self.items.index(item)] = item
        else:
            self.items.append(item)


class HwInfoData:
    def __init__(self):
        self.groups = []
        self.valid = False
        self.created = datetime.datetime.now()

    def parse(self, data):
        self.data = data
        if not self.parse_header() or not self.parse_groups() or not self.parse_values():
            return False
        self.data = None
        self.valid = True
        return True

    def parse_header(self):
        try:
            self.data_len, self.data_name, x1, x2, timestamp, x3, self.groups_offset, self.group_len, self.groups_count, self.values_offset, self.value_len, self.values_count = struct.unpack_from(
                'I4sIIIIIIIIII', self.data, 8)
            self.timestamp = datetime.datetime.fromtimestamp(timestamp)
        except Exception as e:
            print('Error parsing header: %s' % e)
            return False
        self.data = self.data[12:]
        return True

    def print_header_data(self):
        print('data_len: %s\ndata_name: %s\n%s\ngroups_count: %s\ngroup_len: %s\nvalues_offset: %s\nvalue_len: %s\nvalues_count: %s' % (
            self.data_len, self.data_name, self.timestamp, self.groups_count, self.group_len, self.values_offset, self.value_len, self.values_count))
        # print '%04X %04X %04X %04X %04X %04X' % (groups_count, group_len, l6, values_offset, value_len, values_count)

    def byte_array_to_str(self, byte_array):
        return ''.join(byte_array.decode('latin-1')).strip('\x00')

    def parse_groups(self):
        for group_nr in range(0, self.groups_count):
            group_offset = self.groups_offset + group_nr * self.group_len
            if not self.parse_group(group_offset):
                print('Error parsing groups')
                return False
        return True

    def parse_group(self, offset):
        try:
            b1, b2, b3, b4, l1, name, s2 = struct.unpack_from('BBBBI128s128s', self.data, offset)
        except Exception as e:
            print('Error parsing group: %s' % e)
            return False
        name = self.byte_array_to_str(name).rstrip(': ')
        group = HwInfoGroup(name)
        self.groups.append(group)
        return True

    def parse_values(self):
        for value_nr in range(0, self.values_count):
            value_offset = self.values_offset + value_nr * self.value_len
            if not self.parse_value(value_offset):
                print('Error parsing values')
                return False
        return True

    def parse_value(self, offset):
        try:
            l1, group_id, nr_in_group, b2, b3, value_type, name, s2, unit = struct.unpack_from(
                'IIBBBB128s128s16s', self.data, offset)
            value_cur, value_min, value_max, value_avg = struct.unpack_from('dddd', self.data, offset+284)
        except Exception as e:
            print('Error parsing value: %s' % e)
            return False
        name = self.byte_array_to_str(name)
        unit = self.byte_array_to_str(unit)
        # print '% 3s % 3s % 3s % 3s % 3s % 3s %s %s %s' % (value_type, group_id, nr_in_group, b2, b3, value_type, value_cur, unit, name)
        value_type = HWINFO_VALUE_TYPES.get(value_type, str(value_type))
        item = HwInfoItem(name, value_cur, unit, value_type)
        self.groups[group_id].update(item)
        return True

    def get_group_id(self, name):
        for gid, group in enumerate(self.groups):
            if group.name == name:
                return gid
        return None

    def hwinfo_update_value(self, key, value):
        if value is None:
            return False
        if not self.get_group_id(key):
            group = HwInfoGroup(key)
            self.groups.append(group)
        gid = self.get_group_id(key)
        item = HwInfoItem(key, value, key, 'general')
        self.groups[gid].update(item)
        return True


class HwInfoRemote:
    def __init__(self, ip, port=27007):
        self.ip = ip
        self.port = port
        self.sock = None
        self.socket_fail_count = 0

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(1)
            self.sock.connect((self.ip, self.port))

            self.sock.send(b'CRWH\x01' + b'\x00'*(128-5))
            data1 = self.sock.recv(132)
            data = self.sock.recv(72)
        except (socket.error, socket.timeout) as e:
            print('HwInfoRemote::connect() error: %s' % e)
            return False

        if data1[0:5] != b'RRWH\x01' or data1[12] != 0x48:  # H = 0x48
            print('Unknown CRWH1 response (1): %s %s' % (data1[0:5], data1[12]))
            return False
        if data[0:5] != b'PRWH\x01':
            print('Unknown CRWH1 response (2)')
            return False
        self.computer_name = b''.join(struct.unpack_from('32s', data, 0x08))
        self.hwinfo_ver = b''.join(struct.unpack_from('32s', data, 0x28))
        self.socket_fail_count = 0
        return True

    def close(self):
        if self.sock is not None:
            self.sock.close()

    def get_data(self):
        if self.sock is None:
            if not self.connect():
                self.sock = None
                return False
        try:
            self.sock.send(b'CRWH\x02' + b'\x00'*(128-5))
            data = self.sock.recv(132)
            if data[0:5] != b'RRWH\x02':
                print('Unknown RRWH2 response')
                return False
            data_len = struct.unpack_from('I', data, 12)[0]

            data = bytearray()
            while len(data) < data_len:
                packet = self.sock.recv(4096)
                if not packet:
                    print('Error receiving PRWH2')
                    return False
                data.extend(packet)
        except (socket.error, socket.timeout) as e:
            print('refresh() error: %s' % e)
            self.socket_fail_count += 1
            if self.socket_fail_count >= 3:
                self.sock = None
            return False
        if data[0:5] != b'PRWH\x02' or data_len != len(data):
            print('Unknown PRWH2 response')
            return False
        hwinfodata = HwInfoData()
        if not hwinfodata.parse(data):
            print('parse error')
            return False
        self.socket_fail_count = 0
        return hwinfodata
