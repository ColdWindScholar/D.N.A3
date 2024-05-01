import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from glob import glob
from hashlib import sha1

import requests
from rich import print as echo
from rich.console import Console
from rich.progress import Progress

import devdex
import extract_payload
import fspatch
import img2sdat
import imgextractor
import sdat2img
import seekfd

if os.name == 'nt':
    import ctypes
    from tkinter.filedialog import askopenfilename

    ctypes.windll.kernel32.SetConsoleTitleW("DNA-3")
else:
    sys.stdout.write("\x1b]2;DNA-3\x07")
    sys.stdout.flush()
IS_ARM64 = False
PWD_DIR = os.getcwd() + os.sep
MOD_DIR = PWD_DIR + "local/sub/"
ROM_DIR = PWD_DIR
SETUP_JSON = PWD_DIR + "local/set/setup.json"
MAGISK_JSON = PWD_DIR + "local/set/magisk.json"
ostype = platform.system()
if os.getenv('PREFIX'):
    if "com.termux" in os.getenv('PREFIX'):
        ostype = 'Android'
if platform.machine() in ('aarch64', 'armv8l', 'arm64'):
    ostype = 'Android'
    if os.path.isdir("/sdcard/Download"):
        IS_ARM64 = True
        ROM_DIR = "/sdcard/Download/"
BIN_PATH = PWD_DIR + f"local/bin/{ostype}/{platform.machine()}/"

RED, WHITE, CYAN, YELLOW, MAGENTA, GREEN, BOLD, CLOSE = ['\x1b[91m',
                                                         '\x1b[97m', '\x1b[36m',
                                                         '\x1b[93m', '\x1b[1;35m',
                                                         '\x1b[1;32m',
                                                         '\x1b[1m', '\x1b[0m']


class GlobalValue(object):
    JM = False

    def __init__(self):
        self.programs = ["mv", "cpio", "brotli", "img2simg", "e2fsck", "resize2fs",
                         "mke2fs", "e2fsdroid", "mkfs.erofs", "lpmake", "lpunpack", "extract.erofs", "magiskboot"]
        if os.name == 'nt':
            self.programs = []

    def __getattr__(self, item):
        try:
            return getattr(self, item)
        except (Exception, BaseException):
            return "None"


V = GlobalValue()


def change_permissions_recursive(path, mode):
    for root, dirs, files in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), mode)
        for f in files:
            os.chmod(os.path.join(root, f), mode)
    os.chmod(path, mode)


if os.path.isdir(BIN_PATH):
    os.environ["PATH"] += os.pathsep + BIN_PATH
    if os.name == 'posix':
        change_permissions_recursive(BIN_PATH, 0o777)

    for prog in V.programs:
        if not shutil.which(prog):
            sys.exit(f"[x] Not found: {prog}\n[i] Please install {prog} \n   Or add <{prog}> to {BIN_PATH}")
else:
    print(f"Run err on: {platform.system()} {platform.machine()}")
    sys.exit()


def call(exe, kz='Y', out=0, shstate=False, sp=0):
    cmd = f'{BIN_PATH}{exe}' if kz == "Y" else exe
    if os.name != 'posix':
        conf = subprocess.CREATE_NO_WINDOW
    else:
        if sp == 0:
            cmd = cmd.split()
        conf = 0
    try:
        ret = subprocess.Popen(cmd, shell=shstate, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, creationflags=conf)
        for i in iter(ret.stdout.readline, b""):
            if out == 0:
                print(i.decode("utf-8", "ignore").strip())
    except subprocess.CalledProcessError as e:
        ret = None
        ret.wait = print
        ret.returncode = 1
        for i in iter(e.stdout.readline, b""):
            if out == 0:
                print(i.decode("utf-8", "ignore").strip())
    ret.wait()
    return ret.returncode


class CoastTime:

    def __init__(self):
        self.t = 0

    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"> Coast Time:{time.perf_counter() - self.t:.8f} s")


def display(message, flag=1, end='\n'):
    flags = {1: "3", 2: "6", 3: "4", 4: "1"}
    print(f"\x1b[1;3{flags[flag]}m [ {time.strftime('%H:%M:%S', time.localtime())} ]\t {message} \x1b[0m", end=end)


def get_dir_size(ddir, max_=1.06):
    size = 0
    for (root, dirs, files) in os.walk(ddir):
        for name in files:
            if not os.path.islink(name):
                try:
                    size += os.path.getsize(os.path.join(root, name))
                except:
                    ...
    return int(size * max_)


def ceil(x):
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        int_part = int(x)
        if x > 0 and x > int_part:
            return int_part + 1
        return int_part
    return int(x)


def load_image_json(dumpinfo, source_dir):
    with open(dumpinfo, "a+", encoding="utf-8") as f:
        f.seek(0)
        info = json.load(f)
    inodes = info["a"]
    block_size = info["b"]
    per_group = info["c"]
    mount_point = info["d"]
    if mount_point != "/":
        mount_point = "/" + mount_point
    fsize = info["s"]
    blocks = ceil(int(fsize) / int(block_size))
    dsize = get_dir_size(source_dir)
    if dsize > int(fsize):
        minsize = dsize - int(fsize)
        if int(minsize) < 20971520:
            isize = int(dsize * 1.08)
            dsize = str(isize)
    else:
        dsize = fsize
    return fsize, dsize, inodes, block_size, blocks, per_group, mount_point


def load_setup_json():
    with open(SETUP_JSON, "r", encoding="utf-8") as manifest_file:
        V.SETUP_MANIFEST = json.load(manifest_file)
    set_default_env_setup()
    validate_default_env_setup(V.SETUP_MANIFEST)
    with open(SETUP_JSON, "w", encoding="utf-8") as f:
        json.dump(V.SETUP_MANIFEST, f, indent=4)
    add_dir = f"{PWD_DIR}local/etc/devices/{V.SETUP_MANIFEST['DEVICE_CODE']}/{V.SETUP_MANIFEST['ANDROID_SDK']}"
    if not os.path.isdir(f"{add_dir}/addons"):
        os.makedirs(f"{add_dir}/addons")
    if not os.path.isfile(f"{add_dir}/ramdisk.cpio"):
        try:
            open(os.path.join(add_dir, "ramdisk.cpio.txt"), 'w').close()
        except Exception:
            ...
    if not os.path.isfile(f"{add_dir}/reduce.txt"):
        with open(f"{add_dir}/reduce.txt", "w", encoding='utf-8', newline='\n') as f:
            f.write(
                "product/app/PhotoTable\nsystem/system/app/BasicDreams\nsystem/system/data-app/Youpin\nsystem_ext/priv-app/EmergencyInfo\nvendor/app/MiGameService\n")
    if not os.path.isfile(MAGISK_JSON):
        default_magisk = {'CLASS': "alpha",
                          'KEEPVERITY': "true",
                          'KEEPFORCEENCRYPT': "true",
                          'PATCHVBMETAFLAG': "false",
                          'TARGET': "arm",
                          'IS_64BIT': "true"}
        with open(MAGISK_JSON, "w", encoding="utf-8") as g:
            json.dump(default_magisk, g, indent=4)


def set_default_env_setup():
    properties = {
        'IS_VAB': "1",
        'IS_DYNAMIC': "1",
        'ANDROID_SDK': "12",
        'DEVICE_CODE': "alioth",
        'REPACK_EROFS_IMG': "0",
        'REPACK_TO_RW': "0",
        'RESIZE_IMG': "0",
        'RESIZE_EROFSIMG': "0",
        'REPACK_SPARSE_IMG': "0",
        'REPACK_BR_LEVEL': "3",
        'SUPER_SIZE': "9126805504",
        'GROUP_NAME': "qti_dynamic_partitions",
        'SUPER_SECTOR': "2048",
        'SUPER_SPARSE': "1",
        'UTC': "LIVE",
        'UNPACK_SPLIT_DAT': "15"}
    with open(SETUP_JSON, 'w', encoding='utf-8') as ss:
        json.dump(properties, ss, ensure_ascii=False, indent=4)


def validate_default_env_setup(setup_manifest):
    for k in ('IS_VAB', 'IS_DYNAMIC', 'REPACK_EROFS_IMG', 'REPACK_SPARSE_IMG', 'REPACK_TO_RW',
              'SUPER_SPARSE', 'RESIZE_IMG'):
        if setup_manifest[k] not in ('1', '0'):
            sys.exit(f"Invalid [{k}] - must be one of <1/0>")

    if setup_manifest["RESIZE_EROFSIMG"] not in ('1', '2', '0'):
        sys.exit("Invalid [RESIZE_EROFSIMG] - must be one of <1/2/0>")
    if not re.match("\\d{1,2}", setup_manifest["ANDROID_SDK"]) or int(setup_manifest["ANDROID_SDK"]) < 5:
        sys.exit(f"Invalid [ANDROID_SDK : {setup_manifest['ANDROID_SDK']}] - must be one of <5+>")
    if not re.match("[0-9]", setup_manifest["REPACK_BR_LEVEL"]):
        sys.exit(f"Invalid [{setup_manifest['REPACK_BR_LEVEL']}] - must be one of <0-9>")
    if not re.match("\\d{1,3}", setup_manifest["UNPACK_SPLIT_DAT"]):
        sys.exit(
            f'Invalid ["UNPACK_SPLIT_DAT" : "{setup_manifest["UNPACK_SPLIT_DAT"]}"] - must be one of <1-999>')


def env_setup():
    question_list = {
        '安卓版本[12]': "ANDROID_SDK",
        '机型代号[alioth]': "DEVICE_CODE",
        '是否动态分区[1/0]': "IS_DYNAMIC",
        '是否虚拟AB分区[1/0]': "IS_VAB",
        '合成镜像类型[0:EXT4/1:EROFS]': "REPACK_EROFS_IMG",
        '合成镜像格式[0:RAW/1:SPARSE]': "REPACK_SPARSE_IMG",
        '合成SUPER镜像格式[1:SPARSE/0:RAW]': "SUPER_SPARSE",
        '合成EXT4动态分区状态[0:RO/1:RW]': "REPACK_TO_RW",
        '合成EXT4压缩分区空间[0/1]': "RESIZE_IMG",
        '合成EROFS压缩算法[0:NO/1:LZ4HC/2:LZ4]': "RESIZE_EROFSIMG",
        '压缩BROTLI等级[0-9|3]': "REPACK_BR_LEVEL",
        '动态分区簇名称[qti_dynamic_partitions]': "GROUP_NAME",
        '动态SUPER分区总大小[9126805504]': "SUPER_SIZE",
        '动态分区扇区大小[2048]': "SUPER_SECTOR",
        '自定义UTC时间戳[live]': "UTC",
        '分段DAT/IMG支持个数[15]': "UNPACK_SPLIT_DAT"}
    while True:
        os.system('cls' if os.name == 'nt' else "clear")
        print(f"\n> {GREEN}设置文件{CLOSE}: {SETUP_JSON.replace(PWD_DIR, '')}")
        i = 1
        data1 = {}
        with open(SETUP_JSON, 'r', encoding='utf-8') as ss:
            data = json.load(ss)
        for (name, value) in question_list.items():
            print(f"{YELLOW}[{'0' if i < 10 else ''}{i}]{CLOSE}\t{BOLD}{name}{CLOSE}: {GREEN}{data[value]}{CLOSE}")
            data1[str(i)] = name
            i += 1
        sum_ = input(f"\n请输入你要更改的序列，输入{YELLOW}00{CLOSE}为返回：")
        if sum_ in ["00", "0"]:
            return
        if sum_ not in data1.keys():
            continue
        data[question_list[data1[sum_]]] = input(data1[sum_] + "：")
        validate_default_env_setup(data)
        with open(SETUP_JSON, 'w', encoding='utf-8') as ss:
            json.dump(data, ss, ensure_ascii=False, indent=4)


def check_permissions():
    if not os.path.isfile(SETUP_JSON):
        if not os.path.isdir(os.path.dirname(SETUP_JSON)):
            os.makedirs(os.path.dirname(SETUP_JSON))
        set_default_env_setup()
    menu_once()


def find_file(path, rule):
    for (root, lists, files) in os.walk(path):
        for file in files:
            if re.search(rule, os.path.basename(file)):
                yield os.path.join(root, file)


def kill_avb():
    for tab in find_file(V.project, "^fstab.*?"):
        print(f"> 解除AVB加密: {tab}")
        with open(tab, "r") as sf:
            details = re.sub("avb.*?,", "", sf.read())
        details = re.sub(",avb,", ",", details)
        details = re.sub(",avb_keys=.*", "", details)
        with open(tab, "w") as tf:
            tf.write(details)


def kill_dm():
    for tab in find_file(V.project, "^fstab.*?"):
        print(f"> 解除DM加密: {tab}")
        with open(tab, "r") as sf:
            details = re.sub("forceencrypt=", "encryptable=", sf.read())
        details = re.sub(",fileencryption=.*metadata_encryption", "", details)
        with open(tab, "w") as tf:
            tf.write(details)


def patch_kernel(boot):
    for dt in ('dtb', 'kernel_dtb', 'extra'):
        if os.path.isfile(dt):
            print(f"- Patch fstab in {dt}")
            call(f"magiskboot dtb {dt} patch")
        call(
            "magiskboot hexpatch kernel 736B69705F696E697472616D667300 77616E745F696E697472616D667300")
        call("magiskboot hexpatch kernel 77616E745F696E697472616D6673 736B69705F696E697472616D6673")
        call("magiskboot hexpatch kernel 747269705F696E697472616D6673 736B69705F696E697472616D6673")
        print("- Repacking boot image")
        call(f"magiskboot repack {boot}")


def patch_twrp(BOOTIMG):
    if os.path.isfile(
            f"{PWD_DIR}local/etc/devices/{V.SETUP_MANIFEST['DEVICE_CODE']}/{V.SETUP_MANIFEST['ANDROID_SDK']}/ramdisk.cpio") and os.path.isfile(
        BOOTIMG):
        if os.path.isdir(f"{V.DNA_MAIN_DIR}bootimg"):
            rmdire(f"{V.DNA_MAIN_DIR}bootimg")
        os.makedirs(V.DNA_MAIN_DIR + "bootimg")
        print("- Unpacking boot image")
        os.chdir(V.DNA_MAIN_DIR + "bootimg")
        call(f"magiskboot unpack {BOOTIMG}")
        if os.path.isfile("kernel"):
            if os.path.isfile("ramdisk.cpio"):
                print(f"- Replace ramdisk twrp@{V.SETUP_MANIFEST['ANDROID_SDK']}")
                shutil.copy(
                    f"{PWD_DIR}local/etc/devices/{V.SETUP_MANIFEST['DEVICE_CODE']}/{V.SETUP_MANIFEST['ANDROID_SDK']}/ramdisk.cpio",
                    os.path.join(os.path.abspath("."), "ramdisk.cpio"))
                patch_kernel(BOOTIMG)

                if os.path.isfile("new-boot.img"):
                    print("+ Done")
                    if not os.path.isdir(V.DNA_DIST_DIR):
                        os.mkdir(V.DNA_DIST_DIR)
                    new_boot_img_name = f"{os.path.basename(BOOTIMG).split('.')[0]}{os.path.basename(V.DNA_DIST_DIR)}_twrp.img"
                    os.rename("new-boot.img", os.path.join(V.DNA_DIST_DIR, new_boot_img_name))
                    os.chdir(PWD_DIR)
                    add_magisk = input("> 是否继续添加Magisk [1/0]: ")
                    if add_magisk == "1":
                        patch_magisk(f"{V.DNA_DIST_DIR}{os.path.basename(BOOTIMG).split('.')[0]}_twrp.img")
        os.chdir(PWD_DIR)
        if os.path.isdir(f"{V.DNA_MAIN_DIR}bootimg"):
            rmdire(f"{V.DNA_MAIN_DIR}bootimg")
    else:
        input(
            f"> 未发现local/etc/devices/{V.SETUP_MANIFEST['DEVICE_CODE']}/{V.SETUP_MANIFEST['ANDROID_SDK']}/ramdisk.cpio文件")


def patch_magisk(bootimg):
    magisk_manifest = {}
    if os.path.isfile(MAGISK_JSON):
        with open(MAGISK_JSON, "r", encoding="utf-8") as manifest_file:
            magisk_manifest = json.load(manifest_file)
    default_manifest = {
        'CLASS': "alpha",
        'KEEPVERITY': "true",
        'KEEPFORCEENCRYPT': "true",
        'PATCHVBMETAFLAG': "false",
        'TARGET': "arm",
        'IS_64BIT': "true"}
    for property_, value in default_manifest.items():
        if property_ not in magisk_manifest:
            magisk_manifest[property_] = value

    for k in ('KEEPVERITY', 'KEEPFORCEENCRYPT', 'PATCHVBMETAFLAG', 'IS_64BIT'):
        if magisk_manifest[k] not in ('true', 'false'):
            sys.exit(f"Invalid [{k}] - must be one of <true/false>")

    if magisk_manifest["CLASS"].lower() not in ('stable', 'alpha', 'canary'):
        sys.exit("Invalid [CLASS] - must be one of <stable/alpha/canary>")
    if magisk_manifest["TARGET"] not in ('arm', 'arm64', 'armeabi-v7a', 'arm64-v8a',
                                         'x86', 'x86_64'):
        sys.exit("Invalid [TARGET] - must be one of <arm/x86>")
    magisk_files = glob(f"{PWD_DIR}local/etc/magisk/{magisk_manifest['CLASS']}/Magisk-*.apk")
    if not magisk_files:
        input(f"> 未发现local/etc/magisk/{magisk_manifest['CLASS']}/Magisk-*.apk文件")
        return
    if os.path.isfile(bootimg):
        if os.path.isdir(f"{V.DNA_MAIN_DIR}bootimg"):
            rmdire(f"{V.DNA_MAIN_DIR}bootimg")
        os.makedirs(V.DNA_MAIN_DIR + "bootimg")
        print("- Unpacking boot image")
        os.chdir(V.DNA_MAIN_DIR + "bootimg")
        call(f"magiskboot unpack {bootimg}")
        if os.path.isfile("kernel"):
            if os.path.isfile("ramdisk.cpio"):
                sha1_ = sha1()
                with open(bootimg, "rb") as f:
                    while True:
                        file_data = f.read(2048)
                        if not file_data:
                            break
                        else:
                            sha1_.update(file_data)
                SHA1 = sha1_.digest().hex()
                with open(bootimg, 'rb') as source_file, open('stock_boot.img', 'wb') as dest_file:
                    shutil.copyfileobj(source_file, dest_file)

                shutil.copy2('ramdisk.cpio', 'ramdisk.cpio.orig')
                print(F"- Patching ramdisk magisk@{magisk_manifest['CLASS']}")
                CONFIGS = f"KEEPVERITY={magisk_manifest['KEEPVERITY']}\nKEEPFORCEENCRYPT={magisk_manifest['KEEPFORCEENCRYPT']}\nPATCHVBMETAFLAG={magisk_manifest['PATCHVBMETAFLAG']}\n"
                CONFIGS += f"RECOVERYMODE={str(os.path.isfile('recovery_dtbo')).lower()}\n"
                if SHA1:
                    CONFIGS += f"SHA1={SHA1}"
                with open("config", "w", newline="\n") as cn:
                    cn.write(CONFIGS)
                is_64bit = magisk_manifest["IS_64BIT"] == "true"
                target = magisk_manifest["TARGET"]
                magisk_dict = {'magiskinit': "lib/armeabi-v7a/libmagiskinit.so",
                               'magisk32': "lib/armeabi-v7a/libmagisk32.so",
                               'magisk64': ""}
                if re.match("arm", target):
                    if is_64bit:
                        magisk_dict["magiskinit"] = "lib/arm64-v8a/libmagiskinit.so"
                        magisk_dict["magisk64"] = "lib/arm64-v8a/libmagisk64.so"
                elif re.match("x86", target):
                    magisk_dict["magiskinit"] = ('lib/x86/libmagiskinit.so',)
                    magisk_dict["magisk32"] = "lib/x86/libmagisk32.so"
                    if is_64bit:
                        magisk_dict["magiskinit"] = ('lib/x86_64/libmagiskinit.so',)
                        magisk_dict["magisk64"] = "lib/x86_64/libmagisk64.so"
                magisk_files = sorted(magisk_files, key=(lambda x: os.path.getmtime(x)), reverse=True)
                magisk_file = magisk_files[0]
                fantasy_zip = zipfile.ZipFile(magisk_file)
                zip_lists = fantasy_zip.namelist()
                for (k, v) in magisk_dict.items():
                    if v in zip_lists:
                        fantasy_zip.extract(v)
                        if os.path.isfile(v):
                            try:
                                os.renames(v, k)
                            except FileExistsError:
                                os.remove(k)
                                os.renames(v, k)
                fantasy_zip.close()
                call("magiskboot compress=xz magisk32 magisk32.xz")
                call("magiskboot compress=xz magisk64 magisk64.xz")
                patch_cmds = 'magiskboot cpio ramdisk.cpio "add 0750 init magiskinit" "mkdir 0750 overlay.d" "mkdir 0750 overlay.d/sbin" "add 0644 overlay.d/sbin/magisk32.xz magisk32.xz" '

                if is_64bit:
                    patch_cmds += '"add 0644 overlay.d/sbin/magisk64.xz magisk64.xz" '
                patch_cmds += '"patch" "backup ramdisk.cpio.orig" "mkdir 000 .backup" "add 000 .backup/.magisk config"'
                call(patch_cmds)
                for file_pattern in ['ramdisk.cpio.orig', 'config', 'magisk*.xz', 'magiskinit', 'magisk*']:
                    for file_to_delete in glob(file_pattern):
                        try:
                            os.remove(file_to_delete)
                            print(f"Clean: {file_to_delete}")
                        except Exception as e:
                            print(f"Error deleting {file_to_delete}: {e}")
                patch_kernel(bootimg)

                if os.path.isfile("new-boot.img"):
                    print("+ Done")
                    if not os.path.isdir(V.DNA_DIST_DIR):
                        os.mkdir(V.DNA_DIST_DIR)
                    new_boot_img_name = os.path.basename(bootimg).split(".")[0] + "_magisk.img"
                    destination_path = os.path.join(V.DNA_DIST_DIR, new_boot_img_name)
                    shutil.move("new-boot.img", destination_path)
                    if os.path.isdir(V.DNA_MAIN_DIR + "system" + os.sep + "system"):
                        try:
                            os.makedirs(
                                V.DNA_MAIN_DIR + "system" + os.sep + "system" + os.sep + "data-app" + os.sep + "Magisk")
                        except:
                            ...
                        else:
                            destination_path = os.path.join(V.DNA_MAIN_DIR, 'system', 'system', 'data-app',
                                                            'Magisk',
                                                            'Magisk.apk')
                            shutil.copy(magisk_file, destination_path)
                    elif os.path.isdir(V.DNA_MAIN_DIR + "vendor"):
                        os.makedirs(V.DNA_MAIN_DIR + "vendor" + os.sep + "data-app" + os.sep + "Magisk")
                        destination_path = os.path.join(V.DNA_MAIN_DIR, 'vendor', 'data-app', 'Magisk',
                                                        'Magisk.apk')
                        shutil.copy(magisk_file, destination_path)
            os.chdir(PWD_DIR)
            if os.path.isdir(f"{V.DNA_MAIN_DIR}bootimg"):
                rmdire(f"{V.DNA_MAIN_DIR}bootimg")


def patch_addons():
    if os.path.isdir(f"{PWD_DIR}local/etc/devices/default/{V.SETUP_MANIFEST['ANDROID_SDK']}/addons"):
        display(f"复制 default/{V.SETUP_MANIFEST['ANDROID_SDK']}/* ...")
        try:
            shutil.copytree(os.path.join(PWD_DIR, "local", "etc", "devices", "default", V.SETUP_MANIFEST["ANDROID_SDK"],
                                         "addons"), V.DNA_MAIN_DIR, dirs_exist_ok=True)
        except Exception as e:
            print("Error copying files:", e)
    if os.path.isdir(
            f"{PWD_DIR}local/etc/devices/{V.SETUP_MANIFEST['DEVICE_CODE']}/{V.SETUP_MANIFEST['ANDROID_SDK']}/addons"):
        display(f"复制 {V.SETUP_MANIFEST['DEVICE_CODE']}/{V.SETUP_MANIFEST['ANDROID_SDK']}/* ...")
        source_dir = os.path.join(PWD_DIR, "local", "etc", "devices", V.SETUP_MANIFEST["DEVICE_CODE"],
                                  V.SETUP_MANIFEST["ANDROID_SDK"], "addons")
        try:
            shutil.copytree(source_dir, V.DNA_MAIN_DIR, dirs_exist_ok=True)
        except Exception as e:
            print("Error copying files:", e)


def repack_super():
    parts_1 = [
        'system',
        'system_ext',
        'product',
        'vendor',
        'odm',
        "vendor_dlmk",
        "my_"
    ]
    parts = []
    for i in parts_1:
        for file in glob(V.DNA_DIST_DIR + i + '*' + '.img'):
            parts.append(os.path.basename(file).rsplit('.', 1)[0])
    argvs = f'lpmake --metadata-size 65536 --super-name super --device super:{V.SETUP_MANIFEST["SUPER_SIZE"]}:{int(V.SETUP_MANIFEST["SUPER_SECTOR"]) * 512} '
    if V.SETUP_MANIFEST['IS_VAB'] == '1':
        argvs += '--metadata-slots 3 --virtual-ab -F '
        for i in parts:
            if os.path.isfile(V.DNA_DIST_DIR + i + '.img'):
                img_a = V.DNA_DIST_DIR + i + '.img'
                file_type = seekfd.gettype(img_a)
                if file_type == 'sparse':
                    new_img_a = imgextractor.ULTRAMAN().APPLE(img_a)
                    if os.path.isfile(new_img_a):
                        os.remove(img_a)
                        img_a = new_img_a
                argvs += f'--partition {i}_a:readonly:{imgextractor.ULTRAMAN().LEMON(img_a)}:{V.SETUP_MANIFEST["GROUP_NAME"]}_a --image {i}_a={img_a} --partition {i}_b:readonly:0:{V.SETUP_MANIFEST["GROUP_NAME"]}_b '
    else:
        argvs += '--metadata-slots 2 '
        for i in parts:
            if os.path.isfile(V.DNA_DIST_DIR + i + '_b.img'):
                img_b = V.DNA_DIST_DIR + i + '_b.img'
                img_a = V.DNA_DIST_DIR + i + '.img'
                if os.path.isfile(V.DNA_DIST_DIR + i + '_a.img'):
                    img_a = V.DNA_DIST_DIR + i + '_a.img'
                file_type_a = seekfd.gettype(img_a)
                file_type_b = seekfd.gettype(img_b)
                if file_type_a == 'sparse':
                    new_img_a = imgextractor.ULTRAMAN().APPLE(img_a)
                    if os.path.isfile(new_img_a):
                        os.remove(img_a)
                        img_a = new_img_a
                if file_type_b == 'sparse':
                    new_img_b = imgextractor.ULTRAMAN().APPLE(img_b)
                    if os.path.isfile(new_img_b):
                        os.remove(img_b)
                        img_b = new_img_b
                image_size_a = imgextractor.ULTRAMAN().LEMON(img_a)
                image_size_b = imgextractor.ULTRAMAN().LEMON(img_b)
                argvs += f'--partition {i}_a:readonly:{image_size_a}:{V.SETUP_MANIFEST["GROUP_NAME"]}_a --image {i}_a={img_a} --partition {i}_b:readonly:{image_size_b}:{V.SETUP_MANIFEST["GROUP_NAME"]}_b --image {i}_b={img_b} '
    if not parts or "--image" not in argvs:
        input('> 未发现002_DNA文件夹下存在可用镜像文件')
        return
    if V.SETUP_MANIFEST['SUPER_SPARSE'] == '1':
        argvs += '--sparse '
    argvs += f'--group {V.SETUP_MANIFEST["GROUP_NAME"]}_a:{V.SETUP_MANIFEST["SUPER_SIZE"]} --group {V.SETUP_MANIFEST["GROUP_NAME"]}_b:{V.SETUP_MANIFEST["SUPER_SIZE"]} --output {V.DNA_DIST_DIR + "super.img"} '
    display(
        f'重新合成: super.img <Size:{V.SETUP_MANIFEST["SUPER_SIZE"]}|Vab:{V.SETUP_MANIFEST["IS_VAB"]}|Sparse:{V.SETUP_MANIFEST["SUPER_SPARSE"]}>')
    display(f"包含分区：{'|'.join(parts)}")
    with CoastTime():
        call(argvs)
    try:
        if os.path.isfile(os.path.join(V.DNA_DIST_DIR, 'super.img')):
            for i in parts:
                for slot in ('_a', '_b', ''):
                    if os.path.isfile(os.path.join(V.DNA_DIST_DIR, i + slot + '.img')):
                        os.remove(os.path.join(V.DNA_DIST_DIR, i + slot + '.img'))
    except (BaseException, Exception):
        ...


def walk_contexts(contexts):
    with open(contexts, "r", encoding="utf-8") as f3:
        text_list = list(set(f3.readlines()))
    if os.path.isfile(contexts):
        os.remove(contexts)
    with open(contexts, "a+", encoding="utf-8") as f:
        f.writelines(text_list)


def recompress(source, fsconfig, contexts, dumpinfo, flag=8):
    label = os.path.basename(source)
    if not os.path.isdir(V.DNA_DIST_DIR):
        os.makedirs(V.DNA_DIST_DIR)
    distance = V.DNA_DIST_DIR + label + ".img"
    if os.path.isfile(distance):
        os.remove(distance)
    fspatch.main(source, fsconfig)
    walk_contexts(fsconfig)
    walk_contexts(contexts)
    if os.name == 'nt':
        source = source.replace("\\", '/')
    timestamp = int(time.time()) if V.SETUP_MANIFEST["UTC"].lower() == "live" else V.SETUP_MANIFEST["UTC"]
    read = "ro"
    resize2_rw = False
    fsize = None
    if dumpinfo:
        (fsize, dsize, inodes, block_size, blocks, per_group, mount_point) = load_image_json(dumpinfo, source)
        size = dsize
    else:
        size = get_dir_size(source, 1.3)
        if int(size) <= 1048576:
            size = 1048576
        mount_point = "/" + label
        if os.path.isfile(source + os.sep + "system" + os.sep + "build.prop"):
            mount_point = "/"
    if V.SETUP_MANIFEST["REPACK_EROFS_IMG"] == "0":
        fs_variant = "ext4"
        if (V.SETUP_MANIFEST["REPACK_TO_RW"] == "1" and V.SETUP_MANIFEST["IS_DYNAMIC"] == "1") or not fsize:
            resize2_rw = True
            read = "rw"
            block_size = 4096
            blocks = ceil(int(size) / int(block_size))
            mkimage_cmd = f"make_ext4fs -J -T {timestamp} -S {contexts} -C {fsconfig} -l {size} -L {label} -a /{label} {distance} {source}"
            mke2fs_a_cmd = f"mke2fs -O ^has_journal,^metadata_csum,extent,huge_file,^flex_bg,^64bit,uninit_bg,dir_nlink,extra_isize -t {fs_variant} -b {block_size} -L {label} -I 256 -M {mount_point} -m 0 -q -F {distance} {blocks}"
            e2fsdroid_a_cmd = f"e2fsdroid -T {timestamp} -C {fsconfig} -S {contexts} -f {source} -a /{label} -e {distance}"
        else:
            size = fsize
            if int(V.SETUP_MANIFEST["ANDROID_SDK"]) <= 9:
                read = "rw"
                mkimage_cmd = f"make_ext4fs -J -T {timestamp} -S {contexts} -C {fsconfig} -l {size} -L {label} -a /{label} {distance} {source}"
            else:
                mkimage_cmd = f"make_ext4fs -T {timestamp} -S {contexts} -C {fsconfig} -l {size} -L {label} -a /{label} {distance} {source}"
            mke2fs_a_cmd = f"mke2fs -O ^has_journal,^metadata_csum,extent,huge_file,^flex_bg,^64bit,uninit_bg,dir_nlink,extra_isize -t {fs_variant} -b {block_size} -L {label} -I 256 -N {inodes} -M {mount_point} -m 0 -g {per_group} -q -F {distance} {blocks}"
            e2fsdroid_a_cmd = f"e2fsdroid -T {timestamp} -C {fsconfig} -S {contexts} -f {source} -a /{label} -e -s {distance}"
    else:
        fs_variant = "erofs"
        mkerofs_cmd = "mkfs.erofs "
        if not re.match("5.3", platform.uname().release):
            mkerofs_cmd += "-E legacy-compress "
        if V.SETUP_MANIFEST["RESIZE_EROFSIMG"] == "1":
            mkerofs_cmd += "-zlz4hc "
        elif V.SETUP_MANIFEST["RESIZE_EROFSIMG"] == "2":
            mkerofs_cmd += "-zlz4 "
        mkerofs_cmd += f"-T{timestamp} --mount-point=/{label} --fs-config-file={fsconfig} --file-contexts={contexts} {distance} {source}"
    printinform = f"Size:{size}|FsT:{fs_variant}|FsR:{read}|Sparse:{V.SETUP_MANIFEST['REPACK_SPARSE_IMG']}"
    if V.SETUP_MANIFEST["REPACK_EROFS_IMG"] == "0":
        if V.SETUP_MANIFEST["RESIZE_IMG"] == "1" and V.SETUP_MANIFEST["REPACK_TO_RW"] == "1":
            printinform += "|Resize:1"
        else:
            printinform += "|Resize:0"
    elif V.SETUP_MANIFEST["RESIZE_EROFSIMG"] == "1":
        printinform += "|lz4hc"
    elif V.SETUP_MANIFEST["RESIZE_EROFSIMG"] == "2":
        printinform += "|lz4"
    display(printinform)
    display(f"重新合成: {label}.img ...", 4)

    if V.SETUP_MANIFEST["REPACK_EROFS_IMG"] == "1":
        if call(mkerofs_cmd) != 0:
            try:
                os.remove(distance)
            except:
                ...
    elif int(V.SETUP_MANIFEST["ANDROID_SDK"]) <= 9:
        call(mkimage_cmd)
    else:
        call(mke2fs_a_cmd)
        if os.path.isfile(distance):
            if call(e2fsdroid_a_cmd) != 0:
                try:
                    os.remove(distance)
                except:
                    ...
    if os.path.isfile(distance):
        print(" Done")
        if resize2_rw and os.name == 'posix':
            os.system(f"e2fsck -E unshare_blocks {distance}")
            if dumpinfo:
                if int(os.path.getsize(distance)) > int(fsize):
                    os.system(f"resize2fs -M {distance}")
                if V.SETUP_MANIFEST["RESIZE_IMG"] == "1":
                    if V.SETUP_MANIFEST["REPACK_EROFS_IMG"] == "0":
                        if V.SETUP_MANIFEST["REPACK_TO_RW"] == "1":
                            os.system(f"resize2fs -M {distance}")
        op_list = V.DNA_TEMP_DIR + "dynamic_partitions_op_list"
        new_op_list = V.DNA_DIST_DIR + "dynamic_partitions_op_list"
        if os.path.isfile(op_list) or os.path.isfile(new_op_list):
            if not os.path.isfile(new_op_list):
                shutil.copyfile(op_list, new_op_list)
        else:
            CONTENT = "remove_all_groups\n"
            for slot in ('_a', '_b'):
                CONTENT += f"add_group qti_dynamic_partitions{slot} {V.SETUP_MANIFEST['SUPER_SIZE']}\n"

            for partition in ('system', 'system_ext', 'product', 'vendor', 'odm'):
                for slot in ('_a', '_b'):
                    CONTENT += f"add {partition}{slot} qti_dynamic_partitions{slot}\n"

            if V.SETUP_MANIFEST["IS_VAB"] == "1":
                for partition in ('system_a', 'system_ext_a', 'product_a', 'vendor_a',
                                  'odm_a'):
                    CONTENT += f"resize {partition} 4294967296\n"

            else:
                for partition in ('system', 'system_ext', 'product', 'vendor', 'odm'):
                    for slot in ('_a', '_b'):
                        CONTENT += f"resize {partition}{slot} 4294967296\n"

            with open(new_op_list, "w", encoding="UTF-8", newline="\n") as ST:
                ST.write(CONTENT)
        renew_size = os.path.getsize(distance)
        with open(new_op_list, "r", encoding="UTF-8") as f_r:
            with open(new_op_list, "w", encoding="UTF-8") as f_w:
                for line in f_r.readlines():
                    if f"resize {label} " in line:
                        line = f"resize {label} {renew_size}\n"
                    elif f"resize {label}_a " in line:
                        line = f"resize {label}_a {renew_size}\n"
                    f_w.write(line)

        if flag > 8 or (V.SETUP_MANIFEST["REPACK_SPARSE_IMG"] == "1"):
            display("开始转换: sparse format ...")
            call(f"img2simg {distance} {distance.rsplit('.', 1)[0] + '_sparse.img'}")
            if os.path.exists(distance):
                try:
                    os.remove(distance)
                except:
                    ...
            if os.path.isfile(distance.rsplit(".", 1)[0] + "_sparse.img"):
                source_file = distance.rsplit(".", 1)[0] + "_sparse.img"
                try:
                    os.rename(source_file, distance)
                except Exception as e:
                    print("Error moving file:", e)
                if flag > 8:
                    display(f"重新生成: {label}.new.dat ...", 3)
                    img2sdat.main(distance, V.DNA_DIST_DIR, 4, label)
                    newdat = V.DNA_DIST_DIR + label + ".new.dat"
                    if os.path.isfile(newdat):
                        print(" Done")
                        os.remove(distance)
                        if flag == 10:
                            level = V.SETUP_MANIFEST["REPACK_BR_LEVEL"]
                            display(f"重新生成: {label}.new.dat.br | Level={level} ...", 3)
                            newdat_brotli = newdat + ".br"
                            call(f"brotli -{level}jfo {newdat_brotli} {newdat}")
                            print(f" {GREEN}打包成功{CLOSE}" if os.path.isfile(
                                newdat_brotli) else f" {RED}打包失败{CLOSE}")
                    else:
                        print(f" {RED}打包失败{CLOSE}")
    else:
        print(f" {RED}打包失败{CLOSE}")


def rmdire(path):
    if os.path.exists(path):
        if os.name == 'nt':
            for r, d, f in os.walk(path):
                for i in d:
                    if i.endswith('.'):
                        call('mv {} {}'.format(os.path.join(r, i), os.path.join(r, i[:1])))
                for i in f:
                    if i.endswith('.'):
                        call('mv {} {}'.format(os.path.join(r, i), os.path.join(r, i[:1])))

        try:
            shutil.rmtree(path)
        except PermissionError:
            print("无法删除文件夹，权限不足")
        else:
            print("删除成功！")


def unpackboot(file, distance):
    or_dir = os.getcwd()
    rmdire(distance)
    os.makedirs(distance)
    os.chdir(distance)
    shutil.copy(file, os.path.join(distance, "boot_o.img"))
    if call("magiskboot unpack -h %s" % file) != 0:
        print("Unpack %s Fail..." % file)
        os.chdir(or_dir)
        shutil.rmtree(distance)
        return
    if os.path.isfile(distance + os.sep + "ramdisk.cpio"):
        comp = seekfd.gettype(distance + os.sep + "ramdisk.cpio")
        print("Ramdisk is %s" % comp)
        with open(distance + os.sep + "comp", "w") as f:
            f.write(comp)
        if comp != "unknow":
            os.rename(distance + os.sep + "ramdisk.cpio",
                      distance + os.sep + "ramdisk.cpio.comp")
            if call("magiskboot decompress %s %s" % (
                    distance + os.sep + "ramdisk.cpio.comp",
                    distance + os.sep + "ramdisk.cpio")) != 0:
                print("Decompress Ramdisk Fail...")
                return
        if not os.path.exists(distance + os.sep + "ramdisk"):
            os.mkdir(distance + os.sep + "ramdisk")
        os.chdir(distance)
        print("Unpacking Ramdisk...")
        call('cpio -i -d -F ramdisk.cpio -D ramdisk')
        os.chdir(or_dir)
    else:
        print("Unpack Done!")
    os.chdir(or_dir)


def dboot(infile, dist):
    or_dir = os.getcwd()
    flag = ''
    if not os.path.exists(infile):
        print(f"Cannot Find {infile}...")
        return
    if os.path.isdir(infile + os.sep + "ramdisk"):
        try:
            os.chdir(infile + os.sep + "ramdisk")
        except Exception as e:
            print("Ramdisk Not Found.. %s" % e)
            return
        cpio = seekfd.findfile("cpio.exe" if os.name != 'posix' else 'cpio',
                               BIN_PATH).replace(
            '\\', "/")
        call(exe="busybox ash -c \"find | sed 1d | %s -H newc -R 0:0 -o -F ../ramdisk-new.cpio\"" % cpio, sp=1,
             shstate=True)
        os.chdir(infile)
        with open("comp", "r", encoding='utf-8') as compf:
            comp = compf.read()
        print("Compressing:%s" % comp)
        if comp != "unknow":
            if call("magiskboot compress=%s ramdisk-new.cpio" % comp) != 0:
                print("Pack Ramdisk Fail...")
                os.remove("ramdisk-new.cpio")
                return
            else:
                print("Pack Ramdisk Successful..")
                try:
                    os.remove("ramdisk.cpio")
                except (Exception, BaseException):
                    ...
                os.rename("ramdisk-new.cpio.%s" % comp.split('_')[0], "ramdisk.cpio")
        else:
            print("Pack Ramdisk Successful..")
            os.remove("ramdisk.cpio")
            os.rename("ramdisk-new.cpio", "ramdisk.cpio")
        if comp == "cpio":
            flag = "-n"
    else:
        os.chdir(infile)
    if call("magiskboot repack %s %s" % (flag, os.path.join(infile, "boot_o.img"))) != 0:
        print("Pack boot Fail...")
        return
    else:
        if os.path.exists(os.path.join(dist, os.path.basename(infile) + ".img")):
            os.remove(os.path.join(dist, os.path.basename(infile) + ".img"))
        os.rename(infile + os.sep + "new-boot.img", os.path.join(dist, os.path.basename(infile) + ".img"))
        os.chdir(or_dir)
        print("Pack Successful...")


def boot_utils(source, distance, flag=1):
    if not os.path.isdir(distance):
        os.makedirs(distance)
    if flag == 1:
        display(f"正在分解: {os.path.basename(source)}")
        unpackboot(source, distance)
    elif flag == 2:
        display(f"重新合成: {os.path.basename(source)}.img")
        dboot(source, distance)


def decompress_img(source, distance, keep=1):
    if os.path.basename(source) in ('dsp.img', 'exaid.img', 'cust.img'):
        return
    s_time = time.time()
    file_type = seekfd.gettype(source)
    if file_type == 'boot' or file_type == 'vendor_boot':
        if os.path.isdir(distance):
            shutil.rmtree(distance)
        os.makedirs(distance)
        boot_utils(source, distance)
        if not os.path.isdir(V.DNA_CONF_DIR):
            os.makedirs(V.DNA_CONF_DIR)
        boot_info = V.DNA_CONF_DIR + os.path.basename(distance) + '_kernel.txt'
        open(boot_info, 'w', encoding='utf-8').close()
    elif file_type == 'sparse':
        display(f'正在转换: Unsparse Format [{os.path.basename(source)}] ...')
        new_source = imgextractor.ULTRAMAN().APPLE(source)
        if os.path.isfile(new_source):
            if keep == 0:
                os.remove(source)
            decompress_img(new_source, distance)
    if file_type in ['ext', 'erofs', 'super']:
        if file_type != 'ext':
            display(f'正在分解: {os.path.basename(source)} <{file_type}>', 3)
        if not os.path.isdir(V.DNA_CONF_DIR):
            os.makedirs(V.DNA_CONF_DIR)
        if file_type == 'ext':
            with Console().status(f"[yellow]正在提取{os.path.basename(source)}[/]"):
                try:
                    imgextractor.ULTRAMAN().MONSTER(source, distance)
                except:
                    shutil.rmtree(distance)
                    os.unlink(source)
        else:
            if file_type == 'erofs':
                with open(V.DNA_CONF_DIR + os.path.basename(distance) + '_size.txt', 'w') as sf:
                    sf.write(str(os.path.getsize(source)))
                if 'unsparse' in os.path.basename(source):
                    try:
                        os.rename(source, source.replace('.unsparse', ''))
                    except Exception as e:
                        print("Error moving file:", e)
                    source = source.replace('.unsparse', '')
                call(f'extract.erofs -i {source.replace(os.sep, "/")} -o {V.DNA_MAIN_DIR} -x')
            elif file_type == 'super':
                call(f'lpunpack {source} {V.DNA_TEMP_DIR}')
                for img in glob(V.DNA_TEMP_DIR + '*_b.img'):
                    if not V.SETUP_MANIFEST['IS_VAB'] == '1' or os.path.getsize(img) == 0:
                        os.remove(img)
                    else:
                        decompress_img(img, V.DNA_MAIN_DIR + os.path.basename(img).rsplit('.', 1)[0], keep=0)
                else:
                    for img in glob(V.DNA_TEMP_DIR + '*_a.img'):
                        new_source = img.rsplit('_', 1)[0] + '.img'
                        try:
                            os.rename(img, new_source)
                        except:
                            ...
                        decompress_img(new_source, V.DNA_MAIN_DIR + os.path.basename(new_source).rsplit('.', 1)[0],
                                       keep=0)
            else:
                print(F'> ..., not support fs_type [{file_type}]')
            distance = V.DNA_MAIN_DIR + os.path.basename(source).replace('.unsparse.img', '').replace('.img', '')
            if os.path.isdir(distance):
                if os.path.isdir(V.DNA_MAIN_DIR + 'config'):
                    contexts = V.DNA_MAIN_DIR + 'config' + os.sep + os.path.basename(source).replace(
                        '.unsparse.img',
                        '').replace('.img',
                                    '') + '_file_contexts'
                    fsconfig = V.DNA_MAIN_DIR + 'config' + os.sep + os.path.basename(source).replace(
                        '.unsparse.img',
                        '').replace('.img',
                                    '') + '_fs_config'
                    if os.path.isfile(contexts) and os.path.isfile(fsconfig):
                        new_contexts = V.DNA_CONF_DIR + os.path.basename(source).replace('.unsparse.img',
                                                                                         '').replace(
                            '.img', '') + '_contexts.txt'
                        new_fsconfig = V.DNA_CONF_DIR + os.path.basename(source).replace('.unsparse.img',
                                                                                         '').replace(
                            '.img', '') + '_fsconfig.txt'
                        shutil.copy(contexts, new_contexts)
                        shutil.copy(fsconfig, new_fsconfig)
                        shutil.rmtree(V.DNA_MAIN_DIR + 'config')
                    else:
                        if os.path.isdir(V.DNA_MAIN_DIR + 'config'):
                            shutil.rmtree(V.DNA_MAIN_DIR + 'config')

        if os.path.isdir(distance):
            print('\x1b[1;32m %ds Done\x1b[0m' % (time.time() - s_time))
            if keep == 0:
                if os.path.isfile(source):
                    os.remove(source)
                if os.path.isfile(source.rsplit('.', 1)[0] + '.unsparse.img'):
                    os.remove(source.rsplit('.', 1)[0] + '.unsparse.img')
        else:
            if file_type != 'super':
                echo('[red][Failed][/]')


def decompress_dat(transfer, source, distance, keep=0):
    sTime = time.time()
    if os.path.isfile(source + ".1"):
        max__ = V.SETUP_MANIFEST["UNPACK_SPLIT_DAT"]
        display(f"合并: {os.path.basename(source)}.1~{max__} ...")
        with open(source, "ab") as f:
            for i in range(1, int(max__)):
                if os.path.exists("{}.{}".format(source, i)):
                    with open("{}.{}".format(source, i), "rb") as f2:
                        f.write(f2.read())
                    try:
                        os.remove("{}.{}".format(source, i))
                    except:
                        ...

    display(f"正在分解: {os.path.basename(source)} ...", 3)
    sdat2img.main(transfer, source, distance)
    if os.path.isfile(distance):
        tTime = time.time() - sTime
        print("\x1b[1;32m [%ds]\x1b[0m" % tTime)
        if keep == 0:
            os.remove(source)
            os.remove(transfer)
            if os.path.isfile(source.rsplit(".", 2)[0] + ".patch.dat"):
                os.remove(source.rsplit(".", 2)[0] + ".patch.dat")
        elif keep == 2:
            os.remove(source)
        decompress_img(distance, V.DNA_MAIN_DIR + os.path.basename(distance).split(".")[0], 0)
    else:
        print("\x1b[1;31m [Failed]\x1b[0m")


def decompress_bro(transfer, source, distance, keep=0):
    s_time = time.time()
    display(f"正在分解: {os.path.basename(source)} ...", 3)
    call(f"brotli -df {source} -o {distance}")
    if os.path.isfile(distance):
        print("\x1b[1;32m [%ds]\x1b[0m" % (time.time() - s_time))
        if keep == 0:
            os.remove(source)
        elif keep == 1:
            keep = 2
        if transfer:
            decompress_dat(transfer, distance, distance.rsplit(".", 2)[0] + ".img", keep)
    else:
        print("\x1b[1;31m [Failed]\x1b[0m")


def decompress_bin(infile, outdir, flag='1'):
    os.system("cls" if os.name == "nt" else "clear")
    if flag == "1":
        payload_partitions = extract_payload.info(infile)
        print(f"> {YELLOW}包含的所有镜像文件: {CLOSE}\n{extract_payload.info(infile)}")
        partitions = input(
            f"> {RED}根据以上信息输入一个或多个镜像，以空格分开{CLOSE}\n> {MAGENTA}").split()
        print("\n")
        for part in partitions:
            if not part.endswith(".img"):
                part = part + ".img"
            if part in payload_partitions:
                extract_payload.main(infile, outdir, part)
    else:
        print(f"> {YELLOW}提取【{os.path.basename(infile)}】所有镜像文件:{CLOSE}\n")
        extract_payload.main(infile, outdir)
        infile = glob(outdir + "*.img")
        if infile:
            decompress(infile)


def appendf(msg, log):
    if not os.path.isfile(log) and not os.path.exists(log):
        open(log, 'tw', encoding='utf-8').close()
    with open(log, 'w', newline='\n') as file:
        print(msg, file=file)


def decompress_win(infile_list):
    parts = []
    for i in infile_list:
        if i.endswith(".win"):
            parts.append(i)
        main = os.path.join(os.path.dirname(i), os.path.basename(i).split(".")[0] + ".win")
        if i == main:
            continue
        with open(main, "ab" if os.path.exists(main) else "wb") as f:
            with open(i, "rb") as f2:
                print(f'合并{i}到{main}')
                f.write(f2.read())
            try:
                os.remove(i)
            except:
                ...
    parts = list(set(parts))
    for i in parts:
        if not os.path.isdir(V.DNA_MAIN_DIR + os.path.basename(i).rsplit('.', 1)[0]):
            os.makedirs(V.DNA_MAIN_DIR + os.path.basename(i).rsplit('.', 1)[0])
        if not os.path.exists(i):
            continue
        if seekfd.gettype(i) in ['erofs', 'ext', 'super', 'boot', 'vendor_boot']:
            decompress_img(i, V.DNA_MAIN_DIR + os.path.basename(i).rsplit('.', 1)[0])
        elif tarfile.is_tarfile(i):
            with tarfile.open(i, 'r') as tar:
                for n in tar.getmembers():
                    print(f"正在提取:{n.name}")
                    tar.extract(n, path=(V.DNA_MAIN_DIR + os.path.basename(i).rsplit('.', 1)[0]), filter='tar')
            i = os.path.basename(i).rsplit('.', 1)[0]
            fsconfig_0 = []
            contexts_0 = []
            symlinks_0 = []
            if fsconfig_0:
                fsconfig_0.sort()
                if "vendor" in i or "odm" in i:
                    fsconfig_0.insert(0, "/ 0 2000 0755")
                    fsconfig_0.insert(1, i + " 0 2000 0755")
                else:
                    fsconfig_0.insert(0, "/ 0 0 0755")
                    fsconfig_0.insert(1, i + " 0 0 0755")
                appendf("\n".join((str(k) for k in fsconfig_0)), "%s_fsconfig.txt" % i)
            if contexts_0:
                contexts_0.sort()
                sar = False
                for c in contexts_0:
                    if re.search(f"{i}/system/build\\.prop ", c):
                        sar = True
                        break
                if sar:
                    contexts_0.insert(0, "/ u:object_r:rootfs:s0")
                    contexts_0.insert(1, "/{}(/.*)? u:object_r:rootfs:s0".format(i))
                    contexts_0.insert(2, "/{} u:object_r:rootfs:s0".format(i))
                    contexts_0.insert(3, "/{}/system(/.*)? u:object_r:system_file:s0".format(i))
                else:
                    contexts_0.insert(0, "/ u:object_r:system_file:s0")
                    contexts_0.insert(1, "/{}(/.*)? u:object_r:system_file:s0".format(i))
                    contexts_0.insert(2, "/{} u:object_r:system_file:s0".format(i))
                appendf("\n".join((str(j) for j in contexts_0)), "%s_contexts.txt" % i)
            if not symlinks_0 != -1:
                symlinks_0.sort()
                appendf("\n".join((str(h) for h in symlinks_0)), "%s_symlinks.txt" % i)
        else:
            input("未知格式")


def decompress(infile, flag=4):
    for part in infile:
        if os.path.isfile(part) and flag < 4:
            transfer = os.path.join(os.path.dirname(part), os.path.basename(part).split('.')[0] + '.transfer.list')
            if not os.path.isfile(transfer):
                if flag == 3:
                    continue
                else:
                    transfer = None
            if not V.JM:
                display(f'是否分解: {os.path.basename(part)} [1/0]: ', 2, '')
                if input() != '1':
                    continue
            if flag == 2:
                decompress_bro(transfer, part, part.rsplit('.', 1)[0])
            elif flag == 3:
                decompress_dat(transfer, part, part.rsplit('.', 2)[0] + '.img')
            continue
        if flag == 4 and os.path.basename(part) in ('dsp.img', 'cust.img'):
            continue
        if seekfd.gettype(part) not in ('ext', 'sparse', 'erofs', 'super', 'boot', 'vendor_boot'):
            continue
        if not V.JM:
            display(f'是否分解: {os.path.basename(part)} [1/0]: ', 2, '')
            if input() != '1':
                continue
        decompress_img(part, V.DNA_MAIN_DIR + os.path.basename(part).rsplit('.', 1)[0])


def envelop_project():
    V.DNA_MAIN_DIR = PWD_DIR + V.project + os.sep
    V.DNA_TEMP_DIR = V.DNA_MAIN_DIR + "001_DNA" + os.sep
    V.DNA_CONF_DIR = V.DNA_MAIN_DIR + "000_DNA" + os.sep
    V.DNA_DIST_DIR = V.DNA_MAIN_DIR + "002_DNA" + os.sep
    if IS_ARM64:
        V.DNA_TEMP_DIR = ROM_DIR + "D.N.A" + os.sep + V.project + os.sep + "001_DNA" + os.sep
        V.DNA_DIST_DIR = ROM_DIR + "D.N.A" + os.sep + V.project + os.sep + "002_DNA" + os.sep
    if not os.path.isdir(V.DNA_TEMP_DIR):
        os.makedirs(V.DNA_TEMP_DIR)
    if not os.path.isdir(V.DNA_TEMP_DIR):
        os.makedirs(V.DNA_MAIN_DIR)
    if not os.path.isdir(V.DNA_MAIN_DIR):
        os.makedirs(V.DNA_MAIN_DIR)


def extract_zrom(rom):
    if zipfile.is_zipfile(rom):
        V.project = 'DNA_' + os.path.basename(rom).rsplit('.', 1)[0]
        fantasy_zip = zipfile.ZipFile(rom)
        zip_lists = fantasy_zip.namelist()
    else:
        input('> 破损的zip或不支持的zip类型')
        return
    if 'payload.bin' in zip_lists:
        print(f'> 解压缩: {os.path.basename(rom)}')
        envelop_project()
        fantasy_zip.close()
        if os.path.isfile(V.DNA_TEMP_DIR + 'payload.bin'):
            decompress_bin(fantasy_zip.extract('payload.bin', V.DNA_TEMP_DIR), V.DNA_TEMP_DIR,
                           input(f'> {RED}选择提取方式:  [0]全盘提取  [1]指定镜像{CLOSE} >> '))
            menu_main()
    elif 'run.sh' in zip_lists:
        if not os.path.isdir(MOD_DIR):
            os.makedirs(MOD_DIR)
        mod_name = os.path.basename(rom).rsplit('.', 1)[0].replace(' ', '_')
        sub_dir = MOD_DIR + 'DNA_' + mod_name
        if not os.path.isdir(sub_dir):
            display(f'是否安装插件: {mod_name} ? [1/0]: ', 2, '')
        else:
            display(f'已安装插件: {mod_name}，是否删除原插件后安装 ? [0/1]: ', 2, '')
        if input() == '1':
            rmdire(sub_dir)
            fantasy_zip.extractall(sub_dir)
            fantasy_zip.close()
            if os.path.isfile(sub_dir + os.sep + 'run.sh'):
                if os.name != 'nt':
                    change_permissions_recursive(sub_dir, 0o777)
                print('\x1b[1;31m\n 安装完成 !!!\x1b[0m')
            else:
                rmdire(sub_dir)
                print('\x1b[1;31m\n 安装失败 !!!\x1b[0m')
    else:
        able = 5
        infile = []
        print(f'> 解压缩: {os.path.basename(rom)}')
        envelop_project()
        fantasy_zip.extractall(V.DNA_TEMP_DIR)
        fantasy_zip.close()
        if [part_name for part_name in sorted(zip_lists) if part_name.endswith(".new.dat.br")]:
            infile = glob(V.DNA_TEMP_DIR + '*.br')
            able = 2
        elif [part_name for part_name in zip_lists if part_name.endswith(".new.dat")]:
            infile = glob(V.DNA_TEMP_DIR + '*.dat')
            able = 3
        elif [part_name for part_name in zip_lists if part_name.endswith(".img")]:
            infile = glob(V.DNA_TEMP_DIR + '*.img')
            able = 4
        if not infile:
            input('> 仅支持含有payload.bin/*.new.dat/*.new.dat.br/*.img的zip固件')
        else:
            quiet()
            decompress(infile, able)
        menu_main()


def lists_project(dTitle, sPath, flag):
    i = 0
    V.dict0 = {i: dTitle}
    if flag == 0:
        for obj in glob(sPath):
            if os.path.isdir(obj):
                i += 1
                V.dict0[i] = obj

    elif flag == 1:
        for obj in glob(sPath):
            if os.path.isfile(obj):
                i += 1
                V.dict0[i] = obj

    elif flag == 2:
        for obj in glob(sPath):
            if os.path.isdir(obj):
                if os.path.isfile(obj + os.sep + "run.sh"):
                    i += 1
                    V.dict0[i] = obj

    e = 1
    print("-------------------------------------------------------\n")
    for (key, value) in V.dict0.items():
        print(f"  \x1b[0;3{e}m[{key}]\x1b[0m - \x1b[0;3{e + 4}m{os.path.basename(value)}\x1b[0m")
        e = 2

    print("\n-------------------------------------------------------")
    if flag == 0:
        print("\x1b[0;35m  [33] - 解压      [44] - 删除\n  [77] - 设置      [66] - 下载\n  [88] - 退出  \x1b[0m\n")

    if flag == 2:
        print("\x1b[0;35m  [33] - 安装         [44] - 删除         [88] - 退出  \x1b[0m\n")


def choose_zrom(flag=0):
    os.system('cls' if os.name == 'nt' else 'clear')
    if flag == 1:
        print('\x1b[0;33m> 选择固件:\x1b[0m')
        s_file_path = askopenfilename(title='选择一个固件', filetypes=(("zip", "*.zip"),))
        if s_file_path:
            extract_zrom(s_file_path)
    else:
        print('\x1b[0;33m> 固件列表\x1b[0m')
        print(f"固件放置路径: {ROM_DIR}")
        lists_project('返回上级', ROM_DIR + '*.zip', 1)
        choice = input('> 选择: ')
        if choice:
            if int(choice) == 66:
                download_zrom()
            elif int(choice) == 0:
                return
            elif 0 < int(choice) < len(V.dict0):
                extract_zrom(V.dict0[int(choice)])
            else:
                input(f'> Number \x1b[0;33m{choice}\x1b[0m enter error !')


def download_rom(rom, url):
    os.system("cls" if os.name == "nt" else "clear")
    res = requests.get(url, stream=True)
    file_size = int(res.headers.get("Content-Length"))
    file_size_in_mb = int(file_size / 1048576)
    com = 0
    print(f"> {GREEN}D.N.A DOWNLOADER:{CLOSE}\n")
    print(f"Link: {url}")
    print(f"Size: {file_size_in_mb}Mb")
    print(f"Path: {rom}")
    if not os.path.isfile(rom):
        with Progress() as progress:
            task = progress.add_task("[yellow]Downloading...", total=file_size)
            with open(rom, "wb") as f:
                for chunk in res.iter_content(2097152):
                    f.write(chunk)
                    com += len(chunk)
                    progress.update(task, completed=com)

        if os.path.exists(rom):
            print(f"{RED}Successed !{CLOSE}")
            choose_zrom()
        else:
            if os.path.exists(rom):
                os.remove(rom)
            input(f"> {GREEN}Failed !{CLOSE}")
    else:
        input("> 发现 " + os.path.basename(rom))


def download_zrom():
    url = input("> 输入直链: ")
    if url:
        s_file_path = ROM_DIR + url.split("/")[-1]
        if not os.path.isfile(s_file_path):
            download_rom(s_file_path, url)


def creat_project():
    os.system("cls" if os.name == "nt" else "clear")
    print("\x1b[1;31m> 新建工程:\x1b[0m\n")
    creat_name = input("  输入名称【不能有空格、特殊符号】: DNA_").strip().rstrip("\\").replace(" ", "_")
    if creat_name:
        V.project = "DNA_" + creat_name
        if not os.path.isdir(V.project):
            os.mkdir(V.project)
            menu_main()
        else:
            input(f"\x1b[0;31m\n 工程目录< \x1b[0;32m{V.project} \x1b[0;31m>已存在, 回车返回 ...\x1b[0m\n")
            del V.project
            creat_project()
    else:
        menu_once()


def menu_once():
    load_setup_json()
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("\x1b[0;33m> 工程列表\x1b[0m")
        lists_project("新建工程", "DNA_*", 0)
        choice = input("> 选择: ")
        if not choice or not choice.isdigit():
            continue
        if int(choice) == 88:
            sys.exit()
        elif int(choice) == 33:
            choose_zrom(int(os.name == "nt"))
        elif int(choice) == 44:
            if V.dict0:
                which = input("> 输入序号进行删除: ")
                if not which.isdigit():
                    continue
                elif int(which) > 0:
                    if int(which) < len(V.dict0):
                        if input(
                                f"\x1b[0;31m> 是否删除 \x1b[0;34mNo.{which} \x1b[0;31m工程: \x1b[0;32m{os.path.basename(V.dict0[int(which)])}\x1b[0;31m [0/1]:\x1b[0m ") == "1":
                            if os.path.isdir(V.dict0[int(which)]):
                                rmdire(V.dict0[int(which)])
                                if IS_ARM64:
                                    if os.path.isdir(ROM_DIR + "D.N.A" + os.sep + V.dict0[int(which)]):
                                        input(
                                            f"> 请自主判断删除内置存储 {ROM_DIR + 'D.N.A' + os.sep + V.dict0[int(which)]}")
                                menu_once()
                    input(f"> Number {which} Error !")
        elif int(choice) == 66:
            download_zrom()
        elif int(choice) == 77:
            env_setup()
            load_setup_json()
        elif int(choice) == 0:
            creat_project()
            break
        elif 0 < int(choice) < len(V.dict0):
            V.project = V.dict0[int(choice)]
            menu_main()
            break
        else:
            input(f"> Number \x1b[0;33m{choice}\x1b[0m enter error !")


def menu_more():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print(f"\x1b[1;36m> 当前工程: \x1b[0m{V.project}")
        print("-------------------------------------------------------\n")
        print("\x1b[0;31m  0> 返回上级    \x1b[0m")
        print("\x1b[0;32m  1> 去除AVB    \x1b[0m")
        print("\x1b[0;34m  2> 去除DM     \x1b[0m")
        print("\x1b[0;31m  3> [A11+]全局合并dev    \x1b[0m")
        print("\x1b[0;35m  4> 标准精简    \x1b[0m")
        print("\x1b[0;32m  5> 添加文件    \x1b[0m")
        print("\x1b[0;34m  6> 修补boot.img @twrp    \x1b[0m")
        print("\x1b[0;36m  7> 修补boot.img @magisk    \x1b[0m")
        print("\x1b[0;33m  8> 合成super.img    \x1b[0m\n")
        print("-------------------------------------------------------")
        option = input(f"> {RED}输入序号{CLOSE} >> ")
        if not option.isdigit():
            input("> 输入序号数字")
            continue
        if int(option) == 0:
            break
        elif int(option) == 1:
            with CoastTime():
                kill_avb()
        elif int(option) == 2:
            with CoastTime():
                kill_dm()
        elif int(option) == 3:
            with CoastTime():
                devdex.deodex(V.project)
        elif int(option) == 4:
            add_dir = f"{PWD_DIR}local/etc/devices/{V.SETUP_MANIFEST['DEVICE_CODE']}/{V.SETUP_MANIFEST['ANDROID_SDK']}"
            if os.path.isfile(f"{add_dir}/reduce.txt"):
                reduce_conf = f"{add_dir}/reduce.txt"
            elif os.path.isfile(
                    f"{PWD_DIR}local/etc/devices/default/{V.SETUP_MANIFEST['ANDROID_SDK']}/reduce.txt"):
                reduce_conf = f"{PWD_DIR}local/etc/devices/default/{V.SETUP_MANIFEST['ANDROID_SDK']}/reduce.txt"
            else:
                input("精简列表<reduce.txt>丢失！")
                continue
            with CoastTime():
                for line in open(reduce_conf):
                    line = line.replace("/", os.sep).strip()
                    if not line.startswith("#") and line:
                        if os.path.exists(V.DNA_MAIN_DIR + line):
                            print(line)
                            try:
                                shutil.rmtree(V.DNA_MAIN_DIR + line)
                            except NotADirectoryError:
                                os.remove(V.DNA_MAIN_DIR + line)
        elif int(option) == 5:
            with CoastTime():
                patch_addons()
        elif int(option) in [6, 7]:
            currentbootimg = None
            if os.path.isfile(V.DNA_DIST_DIR + "boot.img"):
                currentbootimg = V.DNA_DIST_DIR + "boot.img"
            elif os.path.isfile(V.DNA_TEMP_DIR + "boot.img"):
                currentbootimg = V.DNA_TEMP_DIR + "boot.img"
            if not currentbootimg:
                continue
            if os.path.isfile(currentbootimg):
                with CoastTime():
                    patch_twrp(currentbootimg) if int(option) == 6 else patch_magisk(currentbootimg)
        elif int(option) == 8:
            repack_super()
        else:
            input(f"> Number \x1b[0;33m{option}\x1b[0m enter error !")
        input('> 任意键继续')


def menu_modules():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("\x1b[0;33m> 插件列表\x1b[0m")
        lists_project("返回上级", MOD_DIR + "DNA_*", 2)
        choice = input("> 选择: ")
        if not choice.isdigit():
            continue
        if int(choice) == 88:
            sys.exit()
        elif int(choice) == 33:
            extract_zrom(input("请输入插件路径："))
        elif int(choice) == 44:
            if V.dict0:
                which = input("> 输入序号进行删除: ")
                if int(which) == 0 or not which.isdigit():
                    continue
                if int(which) <= len(V.dict0):
                    if input(
                            f"\x1b[0;31m> 是否删除 \x1b[0;34mNo.{which} \x1b[0;31m插件: \x1b[0;32m{os.path.basename(V.dict0[int(which)])}\x1b[0;31m [0/1]:\x1b[0m ") == "1":
                        if os.path.isdir(V.dict0[int(which)]):
                            rmdire(V.dict0[int(which)])
                            continue
                        else:
                            input(f"> Number {which} Error !")
        elif int(choice) == 0:
            return
        if 0 < int(choice) < len(V.dict0):
            os.system("cls" if os.name == "nt" else "clear")
            print(f"\x1b[1;31m> 执行插件:\x1b[0m {os.path.basename(V.dict0[int(choice)])}\n")
            if os.path.isfile(shell_sub := (V.dict0[int(choice)] + os.sep + "run.sh")):
                call(f"busybox bash {shell_sub} {V.DNA_MAIN_DIR.replace(os.sep, '/')}")
            input('> 任意键继续')
        else:
            print(f"> Number \x1b[0;33m{choice}\x1b[0m enter error !")


def quiet():
    V.JM = input('> 是否开启静默 [0/1]: ') == '1'


menu_actions = {
    55: lambda: input(
        "Github: https://github.com/ColdWindScholar/D.N.A3/\nWrote By ColdWindScholar (3590361911@qq.com)"),
    88: sys.exit,
    0: menu_once,
    7: menu_modules,
    6: menu_more
}


def menu_main():
    envelop_project()
    V.JM = True
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f'\x1b[1;36m> 当前工程: \x1b[0m{V.project}')
    print('-------------------------------------------------------\n')
    print('\x1b[0;31m\t  0> 选择[etc]          1> 分解[bin]\x1b[0m\n')
    print('\x1b[0;32m\t  2> 分解[bro]          3> 分解[dat]\x1b[0m\n')
    print('\x1b[0;36m\t  4> 分解[img]          5> 分解[win]\x1b[0m\n')
    print('\x1b[0;33m\t  6> 更多[dev]          7> 插件[sub]\x1b[0m\n')
    print('\x1b[0;35m\t  8> 合成[img]          9> 合成[dat]\x1b[0m\n')
    print('\x1b[0;34m\t  10> 合成[bro]         88> 退出[bye]\x1b[0m\n')
    print('-------------------------------------------------------')
    option = input(f'> {RED}输入序号{CLOSE} >> ')
    if not option.isdigit():
        input('> 输入序号数字')
    else:
        if int(option) in menu_actions.keys():
            menu_actions[int(option)]()
        elif int(option) == 1:
            infile = V.DNA_TEMP_DIR + 'payload.bin'
            if not os.path.exists(infile):
                input("未发现Payload.Bin")
            else:
                decompress_bin(infile, V.DNA_TEMP_DIR,
                               input(f'> {RED}选择提取方式:  [0]全盘提取  [1]指定镜像{CLOSE} >> '))
        elif int(option) in [2, 3, 4]:
            quiet()
            decompress(glob(V.DNA_TEMP_DIR + {2: "*.br", 3: "*.new.dat", 4: "*.img"}[int(option)]), int(option))
        elif int(option) == 5:
            infile = glob(V.DNA_TEMP_DIR + '*.win*')
            for i in glob(V.DNA_TEMP_DIR + '*.win'):
                infile.append(i)
            quiet()
            decompress_win(list(set(sorted(infile))))
        elif int(option) in [8, 9, 10]:
            quiet()
            if int(option) == 8:
                for file in glob(V.DNA_CONF_DIR + '*_kernel.txt'):
                    f_basename = os.path.basename(file).rsplit('_', 1)[0]
                    source = V.DNA_MAIN_DIR + f_basename
                    if os.path.isdir(source):
                        if not V.JM:
                            display(f'是否合成: {f_basename}.img [1/0]: ', end='')
                            if input() != '1':
                                continue
                        boot_utils(source, V.DNA_DIST_DIR, 2)
            for file in glob(V.DNA_CONF_DIR + '*_contexts.txt'):
                f_basename = os.path.basename(file).rsplit('_', 1)[0]
                source = V.DNA_MAIN_DIR + f_basename
                if os.path.isdir(source):
                    fsconfig = V.DNA_CONF_DIR + f_basename + '_fsconfig.txt'
                    contexts = V.DNA_CONF_DIR + f_basename + '_contexts.txt'
                    infojson = V.DNA_CONF_DIR + f_basename + '_info.txt'
                    if not os.path.isfile(infojson):
                        infojson = None
                    if V.SETUP_MANIFEST['REPACK_EROFS_IMG'] == '0' and V.SETUP_MANIFEST['REPACK_TO_RW'] == '1':
                        if V.SETUP_MANIFEST['REPACK_EROFS_IMG'] == '1':
                            V.SETUP_MANIFEST['REPACK_EROFS_IMG'] = '0'
                            V.SETUP_MANIFEST['REPACK_TO_RW'] = '1'
                    elif V.SETUP_MANIFEST['REPACK_EROFS_IMG'] == '0' and V.SETUP_MANIFEST['REPACK_TO_RW'] == '0':
                        if V.SETUP_MANIFEST['REPACK_EROFS_IMG'] == '1':
                            V.SETUP_MANIFEST['REPACK_EROFS_IMG'] = '1'
                            V.SETUP_MANIFEST['REPACK_TO_RW'] = '0'
                    if os.path.isfile(contexts) and os.path.isfile(fsconfig):
                        if not V.JM:
                            txts = {8: "img", 9: "new.dat", 10: "new.dat.br"}
                            display(f'是否合成: {f_basename}.{txts.get(int(option), ".new.dat.br")} [1/0]: ', end='')
                            if input() != '1':
                                continue
                        recompress(source, fsconfig, contexts, infojson, int(option))
        else:
            input(f'\x1b[0;33m{option}\x1b[0m enter error !')
        input('> 任意键继续')
    menu_main()
