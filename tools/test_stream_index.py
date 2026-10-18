# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4"]
# ///
import copy
import struct
import unittest
from types import SimpleNamespace as NS
import stream_index as si

PATH='data\\test\\phone.vintdoc_pc'
LUA='data\\test\\phone.lua'


def fixture():
    entries=[NS(path='data\\test\\icon.cvbm_pc',name='icon.cvbm_pc',off=0,size=20,stored=10),
             NS(path='data\\test\\icon.gvbm_pc',name='icon.gvbm_pc',off=10,size=60,stored=30),
             NS(path=LUA,name='phone.lua',off=40,size=100,stored=50)]
    arc=NS(entries=entries,data_start=128,file_size=218)
    data=bytearray(struct.pack('<II',si.MAGIC,si.VERSION))
    p=PATH.encode();data+=struct.pack('<H',len(p))+p+b'\x28'+b'\0'*20
    data+=struct.pack('<IBII',128,10,90,2)
    data+=struct.pack('<QII',1,10,30)+struct.pack('<QII',2,50,0)
    p=LUA.encode();data+=struct.pack('<H',len(p))+p+b'\x2b'+struct.pack('<Q',2)+b'\0'*17+struct.pack('<Q',100)
    return bytes(data),arc


class StreamIndexTests(unittest.TestCase):
    def test_identity_and_gpu_group(self):
        data,a=fixture();bundle=si.bind_bundle(data,PATH+'.str2_pc',a)
        self.assertEqual(len(bundle.rows),2)
        self.assertEqual(si.update_containers(data,[(PATH,a,a)]),data)

    def test_changed_compressed_and_source_sizes(self):
        data,a=fixture();new=copy.deepcopy(a)
        new.entries[2].stored=70;new.entries[2].size=150;new.file_size+=20
        out=si.update_containers(data,[(PATH,a,new)])
        bundle=si.bind_bundle(out,PATH,new)
        self.assertEqual(bundle.payload_size,110)
        self.assertEqual(bundle.rows[-1].cpu_stored,70)
        self.assertEqual(si.update_lua_resource_size(out,LUA,150,150),out)

    def test_append_only_layout_rejected(self):
        data,a=fixture();new=copy.deepcopy(a);new.entries[2].off=90;new.file_size+=50
        with self.assertRaisesRegex(ValueError,'not compact'):
            si.update_containers(data,[(PATH,a,new)])

    def test_stale_sizes_rejected(self):
        data,a=fixture();a.entries[-1].stored+=1
        with self.assertRaises(ValueError):si.bind_bundle(data,PATH,a)

    def test_shared_copy_conflict_rejected(self):
        data,a=fixture();new=copy.deepcopy(a);new.entries[-1].size=150
        other=copy.deepcopy(a);other.entries[-1].size=160
        with self.assertRaisesRegex(ValueError,'disagree'):
            si.update_containers(data,[(PATH,a,new),(PATH,a,other)])


if __name__=='__main__':unittest.main()

