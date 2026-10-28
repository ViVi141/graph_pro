import bisect
import numpy as np
import pefile

EXE = r"<ARMA3>\Arma3_x64.exe"

class Bin:
    def __init__(self, path=EXE):
        self.pe = pefile.PE(path, fast_load=True)
        self.pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.sections = [(s.Name.rstrip(b'\0').decode(), s.VirtualAddress, s.Misc_VirtualSize,
                          s.PointerToRawData, s.SizeOfRawData) for s in self.pe.sections]
        self.text = self.section('.text')
        self.rdata = self.section('.rdata')
        self.funcs = self._pdata()

    def section(self, name):
        for n, va, vs, pr, sr in self.sections:
            if n == name:
                return self.pe.get_data(va, vs)
        raise KeyError(name)

    def _pdata(self):
        out = []
        for s in self.pe.DIRECTORY_ENTRY_EXCEPTION:
            b, e = s.struct.BeginAddress, s.struct.EndAddress
            if e > b:
                out.append((b, e))
        out.sort()
        return out
    def func_at(self, rva):
        i = bisect.bisect_right(self.funcs, (rva, 1 << 32)) - 1
        if i >= 0 and self.funcs[i][0] <= rva < self.funcs[i][1]:
            return self.funcs[i]
        return None

    def data(self, rva, size):
        for n, va, vs, pr, sr in self.sections:
            if va <= rva < va + max(vs, sr):
                off = pr + (rva - va)
                return self.pe.__data__[off:off+size]
        return b''

    def cstr(self, rva, maxlen=240):
        b = self.data(rva, maxlen)
        z = b.find(b'\0')
        return b[:z if z >= 0 else len(b)].decode('latin1', 'replace')

    def xrefs(self, target):
        t = np.frombuffer(self.text, dtype=np.uint8).astype(np.int64)
        n = len(t)
        va = self.sections[0][1]
        addrs = np.arange(n, dtype=np.int64) + va
        want = (target - (addrs[:n-3] + 4))
        got = (t[:n-3] | (t[1:n-2] << 8) | (t[2:n-1] << 16) | (t[3:] << 24)) & 0xFFFFFFFF
        got = np.where(got >= 0x80000000, got - 0x100000000, got)
        idx = np.nonzero(got == want)[0]
        out = []
        for p in idx:
            prev = t[max(0, p-4):p]
            if len(prev) >= 3 and prev[-2] in (0x8D, 0x8B, 0x89, 0x8F) and (prev[-1] & 0xC7) == 0x05:
                out.append(va + p - 3)
        return out

    def strings(self, minlen=8, maxlen=200, sections=('.rdata', '.data')):
        import re
        pat = re.compile(rb'[\x20-\x7e]{%d,%d}' % (minlen, maxlen))
        out = []
        for n, va, vs, pr, sr in self.sections:
            if n not in sections:
                continue
            blob = self.pe.__data__[pr:pr+sr]
            for m in pat.finditer(blob):
                out.append((va + m.start(), m.group().decode('latin1')))
        return out
# CHUNK3
