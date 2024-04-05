import codecs
import json
import mmap
import os
import re
import struct

if os.name == 'nt':
    from ctypes import windll
    from ctypes.wintypes import LPCSTR, DWORD
    from stat import FILE_ATTRIBUTE_SYSTEM

import ext4

SPARSE_HEADER_MAGIC = 0xED26FF3A
EXT4_RAW_HEADER_MAGIC = 0xED26FF3A
EXT4_SPARSE_HEADER_LEN = 28
EXT4_CHUNK_HEADER_SIZE = 12
LP_METADATA_HEADER_MAGIC = 1095520304
EROFS_HEADER_MAGIC = 0xE0F5E1E2


class EXT4_IMAGE_HEADER(object):

    def __init__(self, buf):
        (self.magic, self.major, self.minor, self.file_header_size, self.chunk_header_size, self.block_size,
         self.total_blocks, self.total_chunks, self.crc32) = struct.unpack('<I4H4I', buf)


class EXT4_CHUNK_HEADER(object):

    def __init__(self, buf):
        (self.type, self.reserved, self.chunk_size, self.total_size) = struct.unpack('<2H2I', buf)


class ULTRAMAN(object):

    def __init__(self):
        self.FileName = ''
        self.BASE_DIR = ''
        self.OUTPUT_IMAGE_FILE = ''
        self.EXTRACT_DIR = ''
        self.contexts = []
        self.fsconfig = []
        self.space = []

    def __file_name(self, file_path):
        name = os.path.basename(file_path).split('.img')[0]
        name = name.split('.unsparse')[0]
        name = name.replace('/', '\\')
        return name

    @staticmethod
    def __appendf(msg, log):
        if not os.path.isfile(log) and not os.path.exists(log):
            open(log, 'tw', encoding='utf-8').close()
        with open(log, 'w', newline='\n') as file:
            print(msg, file=file)

    def __getperm(self, arg):
        if len(arg) < 9 or len(arg) > 10:
            return
        if len(arg) > 8:
            arg = arg[1:]
        oor, ow, ox, gr, gw, gx, wr, ww, wx = list(arg)
        o, g, w, s = 0, 0, 0, 0
        if oor == 'r': o += 4
        if ow == 'w': o += 2
        if ox == 'x': o += 1
        if ox == 'S': s += 4
        if ox == 's': s += 4; o += 1
        if gr == 'r': g += 4
        if gw == 'w': g += 2
        if gx == 'x': g += 1
        if gx == 'S': s += 2
        if gx == 's': s += 2; g += 1
        if wr == 'r': w += 4
        if ww == 'w': w += 2
        if wx == 'x': w += 1
        if wx == 'T': s += 1
        if wx == 't': s += 1; w += 1
        return str(s) + str(o) + str(g) + str(w)

    def checkSignOffset(self, file):
        size = os.stat(file.name).st_size
        if size <= 52428800:
            mm = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        else:
            mm = mmap.mmap(file.fileno(), 52428800, access=mmap.ACCESS_READ)  # 52428800=50Mb
        offset = mm.find(struct.pack('<L', EXT4_RAW_HEADER_MAGIC))
        return offset

    def __ImgSizeFromSparseFile(self, target):
        img_file = open(target, 'rb')

        if self.sign_offset > 0:
            img_file.seek(self.sign_offset, 0)

        header = EXT4_IMAGE_HEADER(img_file.read(28))
        imgsize = header.block_size * header.total_blocks
        img_file.close()

        return imgsize

    @staticmethod
    def __ImgSizeFromRawFile(target):
        with open(target, 'rb') as img_file:
            m = ''
            see = 1028

            for i in reversed(range(4)):
                img_file.seek(see + i)
                m += img_file.read(1).hex()

            imgsize = int('0x' + m, 16) * 4096

        return imgsize

    def GetImageType(self, target):
        filename, file_extension = os.path.splitext(target)
        if file_extension == '.img':
            with open(target, "rb") as img_file:
                setattr(self, 'sign_offset', self.checkSignOffset(img_file))
                if self.sign_offset > 0:
                    img_file.seek(self.sign_offset, 0)
                header = EXT4_IMAGE_HEADER(img_file.read(28))
                if header.magic != EXT4_RAW_HEADER_MAGIC:
                    return 'img'
                else:
                    return 'simg'

    def FIX_MOTO(self, input_file):
        if not os.path.exists(input_file):
            return
        output_file = input_file + "_"
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except:
                pass
        with open(input_file, 'rb') as f:
            data = f.read(500000)
        moto = re.search(b'\x4d\x4f\x54\x4f', data)
        if not moto:
            return
        result = []
        for i in re.finditer(b'\x53\xEF', data):
            result.append(i.start() - 1080)
        offset = 0
        for i in result:
            if data[i] == 0:
                offset = i
                break
        if offset > 0:
            with open(output_file, 'wb') as o, open(input_file, 'rb') as f:
                data = f.seek(offset)
                data = f.read(15360)
                if data:
                    devnull = o.write(data)
        try:
            os.remove(input_file)
            os.rename(output_file, input_file)
        except:
            pass

    def MONSTER(self, target, output_dir):
        self.BASE_DIR = os.path.realpath(os.path.dirname(target)) + os.sep
        self.EXTRACT_DIR = os.path.realpath(os.path.dirname(output_dir)) + os.sep + self.__file_name(
            os.path.basename(output_dir))
        self.OUTPUT_IMAGE_FILE = self.BASE_DIR + os.path.basename(target)
        self.FileName = self.__file_name(os.path.basename(target))
        IMAGE_TYPE = self.GetImageType(target)
        if IMAGE_TYPE == 'simg':
            self.OUTPUT_IMAGE_FILE = self.Simg2Rimg(target)
            with open(os.path.abspath(self.OUTPUT_IMAGE_FILE), 'rb') as f:
                data = f.read(500000)
            moto = re.search(b'MOTO', data)
            if moto:
                self.FIX_MOTO(os.path.abspath(self.OUTPUT_IMAGE_FILE))
            self.EXT4_EXTRACTOR()
        if IMAGE_TYPE == 'img':
            with open(os.path.abspath(self.OUTPUT_IMAGE_FILE), 'rb') as f:
                data = f.read(500000)
            moto = re.search(b'MOTO', data)
            if moto:
                self.FIX_MOTO(os.path.abspath(self.OUTPUT_IMAGE_FILE))
            self.EXT4_EXTRACTOR()

    def LEMON(self, target):
        from seekfd import gettype
        if not os.path.exists(target):
            return 0
        target_type = gettype(target)
        if target_type == 'sparse':
            return self.__ImgSizeFromSparseFile(target)
        else:
            return os.path.getsize(target)

    def APPLE(self, target):
        target_type = self.GetImageType(target)
        if target_type == 'simg':
            return self.Simg2Rimg(target)

    def Simg2Rimg(self, target):
        with open(target, 'rb') as img_file:
            if self.sign_offset > 0:
                img_file.seek(self.sign_offset, 0)
            header = EXT4_IMAGE_HEADER(img_file.read(28))
            total_chunks = header.total_chunks
            if header.file_header_size > EXT4_SPARSE_HEADER_LEN:
                img_file.seek(header.file_header_size - EXT4_SPARSE_HEADER_LEN, 1)
            unsparse_file = target.replace('.img', '.unsparse.img')
            with open(unsparse_file, 'wb') as raw_img_file:
                sector_base = 82528
                output_len = 0
                while True:
                    if total_chunks > 0:
                        chunk_header = EXT4_CHUNK_HEADER(img_file.read(EXT4_CHUNK_HEADER_SIZE))
                        sector_size = chunk_header.chunk_size * header.block_size >> 9
                        chunk_data_size = chunk_header.total_size - header.chunk_header_size
                        if chunk_header.type == 51905:
                            if header.chunk_header_size > EXT4_CHUNK_HEADER_SIZE:
                                img_file.seek(header.chunk_header_size - EXT4_CHUNK_HEADER_SIZE, 1)
                            data = img_file.read(chunk_data_size)
                            len_data = len(data)
                            if len_data == sector_size << 9:
                                raw_img_file.write(data)
                                output_len += len_data
                                sector_base += sector_size
                        else:
                            if chunk_header.type == 51906:
                                if header.chunk_header_size > EXT4_CHUNK_HEADER_SIZE:
                                    img_file.seek(header.chunk_header_size - EXT4_CHUNK_HEADER_SIZE, 1)
                                data = img_file.read(chunk_data_size)
                                len_data = sector_size << 9
                                raw_img_file.write(struct.pack('B', 0) * len_data)
                                output_len += len(data)
                                sector_base += sector_size
                            else:
                                if chunk_header.type == 51907:
                                    if header.chunk_header_size > EXT4_CHUNK_HEADER_SIZE:
                                        img_file.seek(header.chunk_header_size - EXT4_CHUNK_HEADER_SIZE, 1)
                                    data = img_file.read(chunk_data_size)
                                    len_data = sector_size << 9
                                    raw_img_file.write(struct.pack('B', 0) * len_data)
                                    output_len += len(data)
                                    sector_base += sector_size
                                else:
                                    len_data = sector_size << 9
                                    raw_img_file.write(struct.pack('B', 0) * len_data)
                                    sector_base += sector_size
                        total_chunks -= 1
            return unsparse_file

    def EXT4_EXTRACTOR(self):
        CONFIGS_DIR = os.path.dirname(self.EXTRACT_DIR) + os.sep + '000_DNA' + os.sep
        if not os.path.isdir(CONFIGS_DIR):
            os.mkdir(CONFIGS_DIR)
        dna_contexts = CONFIGS_DIR + self.FileName + '_contexts.txt'
        dna_fsconfig = CONFIGS_DIR + self.FileName + '_fsconfig.txt'
        dna_info = CONFIGS_DIR + self.FileName + '_info.txt'
        partition_size = os.path.getsize(self.OUTPUT_IMAGE_FILE)

        BLOCKSIZE = 1024
        LE32 = '<L'
        with open(self.OUTPUT_IMAGE_FILE, 'rb') as filesystem:
            filesystem.seek(BLOCKSIZE)
            superblock = filesystem.read(BLOCKSIZE)
        inode_count = struct.unpack_from(LE32, superblock, 0)[0]
        inode_count = inode_count
        block_size = 1024 << struct.unpack_from(LE32, superblock, 24)[0]
        block_size = block_size
        per_group = struct.unpack_from(LE32, superblock, 32)[0]
        per_group = per_group
        label_raw = superblock[120:136]
        label = ''.join((chr(c) for c in label_raw))
        manifest = {'a': inode_count,
                    'b': block_size,
                    'c': per_group,
                    'd': label.strip(b'\x00'.decode()),
                    'e': 'ext4',
                    's': partition_size}

        with codecs.open(dna_info, 'w', 'utf-8') as f:
            json.dump(manifest, f, indent=4)

        def scan_dir(root_inode, root_path=""):
            for entry_name, entry_inode_idx, entry_type in root_inode.open_dir():
                if entry_name in ['.', '..'] or entry_name.endswith(' (2)'):
                    continue
                entry_inode = root_inode.volume.get_inode(entry_inode_idx, entry_type)
                entry_inode_path = root_path + '/' + entry_name
                if entry_inode_path[-1:] == '/' and not entry_inode.is_dir:
                    continue
                mode = self.__getperm(entry_inode.mode_str)
                uid = entry_inode.inode.i_uid
                gid = entry_inode.inode.i_gid
                cap = ''
                link_target = ''
                tmp_path = self.FileName + entry_inode_path
                for f, e in entry_inode.xattrs():
                    if f == 'security.selinux':
                        t_p_mkc = tmp_path
                        for fuk_ in '\\^$.|?*+(){}[]':
                            t_p_mkc = t_p_mkc.replace(fuk_, '\\' + fuk_)
                        self.contexts.append(f"/{t_p_mkc} {e.decode('utf8')[:-1]}")
                    elif f == 'security.capability':
                        r = struct.unpack('<5I', e)
                        if r[1] > 65535:
                            cap = hex(int(f'{r[3]:04x}{r[1]:04x}', 16))
                        else:
                            cap = hex(int(f'{r[3]:04x}{r[2]:04x}{r[1]:04x}', 16))
                        cap = f" capabilities={cap}"
                if entry_inode.is_symlink:
                    try:
                        link_target = entry_inode.open_read().read().decode("utf8")
                    except Exception and BaseException:
                        link_target_block = int.from_bytes(entry_inode.open_read().read(), "little")
                        link_target = root_inode.volume.read(link_target_block * root_inode.volume.block_size,
                                                             entry_inode.inode.i_size).decode("utf8")
                if tmp_path.find(' ', 1, len(tmp_path)) > 0:
                    self.space.append(tmp_path)
                    self.fsconfig.append(
                        f"{tmp_path.replace(' ', '_')} {uid} {gid} {mode}{cap} {link_target}")
                else:
                    self.fsconfig.append(
                        f'{tmp_path} {uid} {gid} {mode}{cap} {link_target}')
                if entry_inode.is_dir:
                    dir_target = self.EXTRACT_DIR + entry_inode_path.replace(' ', '_').replace('"', '')
                    if dir_target.endswith('.') and os.name == 'nt':
                        dir_target = dir_target[:-1]
                    if not os.path.isdir(dir_target):
                        os.makedirs(dir_target)

                    if os.name == 'posix' and os.geteuid() == 0:
                        os.chmod(dir_target, int(mode, 8))
                        os.chown(dir_target, uid, gid)
                    scan_dir(entry_inode, entry_inode_path)
                elif entry_inode.is_file:
                    file_target = self.EXTRACT_DIR + entry_inode_path.replace(' ', '_').replace('"', '')
                    try:
                        with open(file_target, 'wb') as out:
                            out.write(entry_inode.open_read().read())
                    except Exception and BaseException as e:
                        print(f'[E] Cannot Write to {file_target}, Reason: {e}')
                    if os.name == 'posix' and os.geteuid() == 0:
                        os.chmod(file_target, int(mode, 8))
                        os.chown(file_target, uid, gid)
                elif entry_inode.is_symlink:
                    target = self.EXTRACT_DIR + entry_inode_path.replace(' ', '_')
                    try:
                        if os.path.islink(target) or os.path.isfile(target):
                            try:
                                os.remove(target)
                            finally:
                                ...
                        if os.name == 'posix':
                            os.symlink(link_target, target)
                        elif os.name == 'nt':
                            with open(target.replace('/', os.sep), 'wb') as out:
                                out.write(b'!<symlink>' + link_target.encode('utf-16') + b'\x00\x00')
                                try:
                                    windll.kernel32.SetFileAttributesA(LPCSTR(target.encode()),
                                                                       DWORD(FILE_ATTRIBUTE_SYSTEM))
                                except Exception as e:
                                    print(e.__str__())
                    except BaseException and Exception:
                        try:
                            if link_target and link_target.isprintable():
                                if os.name == 'posix':
                                    os.symlink(link_target, target)
                                elif os.name == 'nt':
                                    with open(target.replace('/', os.sep), 'wb') as out:
                                        out.write(b'!<symlink>' + link_target.encode('utf-16') + b'\x00\x00')
                                    try:
                                        windll.kernel32.SetFileAttributesA(LPCSTR(target.encode()),
                                                                           DWORD(FILE_ATTRIBUTE_SYSTEM))
                                    except Exception as e:
                                        print(e.__str__())
                        finally:
                            ...

        if not os.path.isdir(CONFIGS_DIR):
            os.makedirs(CONFIGS_DIR)

        with open(self.OUTPUT_IMAGE_FILE, 'rb') as file:
            dir_r = self.FileName
            scan_dir(ext4.Volume(file).root)
            self.fsconfig.insert(0, '/ 0 2000 0755' if dir_r == 'vendor' else '/ 0 0 0755')
            self.fsconfig.insert(1, f'{dir_r} 0 2000 0755' if dir_r == 'vendor' else '/lost+found 0 0 0700')
            self.fsconfig.insert(2 if dir_r == 'system' else 1, f'{dir_r} 0 0 0755')
            self.__appendf('\n'.join(self.fsconfig), dna_fsconfig)
            self.__appendf('\n'.join(self.space), os.path.join(CONFIGS_DIR, self.FileName + '_space.txt'))
            p1 = p2 = 0
            if self.contexts:
                self.contexts.sort()
                for c in self.contexts:
                    if re.search('/system/system/build..prop ', c) and p1 == 0:
                        self.contexts.insert(3, '/lost+\\found u:object_r:rootfs:s0')
                        self.contexts.insert(4, f'/{dir_r}/{dir_r}/(/.*)? ' + c.split()[1])
                        p1 = 1
                    if re.search('lost..found', c) and p2 == 0:
                        self.contexts.insert(0, '/ ' + c.split()[1])
                        self.contexts.insert(1, f'/{dir_r}(/.*)? ' + c.split()[1])
                        self.contexts.insert(2, f'/{dir_r} {c.split()[1]}')
                        self.contexts.insert(3, f'/{dir_r}/lost+\\found ' + c.split()[1])
                        p2 = 1
                    if p1 == p2 == 1:
                        break
                self.__appendf('\n'.join(self.contexts), dna_contexts)
