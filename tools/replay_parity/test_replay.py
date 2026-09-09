import gzip,struct,tempfile,unittest,zlib
from pathlib import Path
from replay import Demo,commands,attack_runs
from compare import compare

class ReplayTests(unittest.TestCase):
 def test_runs_preserve_boundaries_and_reject_duplicate_cancellation(self):
  c=lambda i,o=32:(20,o,(float(i),),0)
  self.assertEqual(attack_runs([(0,0,(),0),c(1),c(2),(10,0,(1,2,3),0),c(3),c(4)]),[[1,2],[4,5]])
  self.assertEqual(attack_runs([c(1),c(1)]),[])
  self.assertEqual(attack_runs([c(1,0),c(2,0)]),[])
 def test_shared_command_packet(self):
  packet=bytes([15])+b'\0\0'+struct.pack('<BBBIBHh',0,255,0,20,32,1,2)+struct.pack('<hhhff',11,12,2,100,101)
  packet=packet[:1]+struct.pack('<H',len(packet))+packet[3:]
  cs,units=commands(packet)
  self.assertEqual(units,(11,12));self.assertEqual(attack_runs(cs),[[0,1]])
  self.assertEqual([c[3] for c in cs],[6,6])
 def test_demo_roundtrip_keeps_packets_and_suffix(self):
  header=bytearray(352);header[:16]=b'spring demofile\0'
  struct.pack_into('<II',header,16,5,352);script=b'[game]{}'
  packet=bytes([1])+struct.pack('<i',123);stream=struct.pack('<fI',1.25,len(packet))+packet
  struct.pack_into('<II',header,304,len(script),len(stream));raw=header+script+stream+b'stats'
  with tempfile.TemporaryDirectory() as tmp:
   a=Path(tmp)/'a.sdfz';b=Path(tmp)/'b.sdfz';a.write_bytes(gzip.compress(raw));d=Demo(a);d.write(b)
   self.assertEqual(gzip.decompress(b.read_bytes()),raw)
 def test_comparator_rejects_incomplete_trace_and_locates_difference(self):
  def trace(path,value,complete=True):
   data=zlib.compress(('hp\t1\t'+value+'\n').encode())
   path.write_bytes(f'FRAME\t1\t{len(data)}\n'.encode()+data+(b'COMPLETE\t1\n' if complete else b''))
  with tempfile.TemporaryDirectory() as tmp:
   a,b=Path(tmp)/'a',Path(tmp)/'b';trace(a,'100');trace(b,'99')
   self.assertEqual(compare(a,b)['first_difference']['frame'],1)
   trace(b,'100');self.assertTrue(compare(a,b)['equal'])
   trace(b,'100',False)
   with self.assertRaises(ValueError):compare(a,b)
if __name__=='__main__':unittest.main()
