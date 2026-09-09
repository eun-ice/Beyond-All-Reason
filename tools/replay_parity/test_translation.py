import struct
import unittest
from types import SimpleNamespace

from replay import queued_attack_chains


def attack(target, options=32, command=20):
    packet = bytes([11, 0, 0, 0]) + struct.pack('<iiBI', command, 0, options, 1)
    packet += struct.pack('<f', target)
    return packet[:1] + struct.pack('<H', len(packet)) + packet[3:]


class TranslationTests(unittest.TestCase):
    def demo(self, *packets):
        select = bytes([12, 6, 0, 0]) + struct.pack('<h', 42)
        return SimpleNamespace(packets=[(0, 0.0, select)] + [
            (index * 30, float(index), packet)
            for index, packet in enumerate(packets, 1)
        ])

    def test_later_shift_append_retains_original_frame_and_offset(self):
        groups = queued_attack_chains(self.demo(attack(100, 0), attack(101)))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['unit'], 42)
        self.assertEqual([e['frame'] for e in groups[0]['entries']], [30, 60])
        self.assertEqual([e['offset'] for e in groups[0]['entries']], [4, 4])
        self.assertEqual([e['options'] for e in groups[0]['entries']], [0, 32])

    def test_duplicates_and_replacement_do_not_form_chains(self):
        self.assertEqual(queued_attack_chains(self.demo(attack(100), attack(100))), [])
        self.assertEqual(queued_attack_chains(self.demo(attack(100), attack(101, 0))), [])

    def test_other_command_splits_chain(self):
        groups = queued_attack_chains(self.demo(
            attack(100), attack(101), attack(0, command=0), attack(102), attack(103)))
        self.assertEqual([[e['target'] for e in g['entries']] for g in groups],
                         [[100, 101], [102, 103]])


if __name__ == '__main__':
    unittest.main()
