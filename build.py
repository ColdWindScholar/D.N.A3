#!/usr/bin/env python3
import os
import shutil
import zipfile
from platform import system
from pip._internal.cli.main import main as _main
with open('requirements.txt', 'r', encoding='utf-8') as l:
    for i in l.read().split("\n"):
        print(f"Installing {i}")
        _main(['install', i])
ostype = system()
if ostype == 'Linux':
    name = 'DNA3-linux.zip'
elif ostype == 'Darwin':
    name = 'DNA3-macos.zip'
else:
    name = 'DNA3-win.zip'


def zip_folder(folder_path):
    # 获取文件夹的绝对路径和文件夹名称
    abs_folder_path = os.path.abspath(folder_path)

    # 创建一个同名的zip文件
    zip_file_path = os.path.join(local, name)
    archive = zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED)

    # 遍历文件夹中的所有文件和子文件夹
    for root, dirs, files in os.walk(abs_folder_path):
        for file in files:
            if file == name:
                continue
            file_path = os.path.join(root, file)
            if ".git" in file_path:
                continue
            print(f"Adding: {file_path}")
            # 将文件添加到zip文件中
            archive.write(file_path, os.path.relpath(file_path, abs_folder_path))

    # 关闭zip文件
    archive.close()
    print(f"Done!")


local = os.getcwd()
print("Building...")
import PyInstaller.__main__
if ostype == 'Darwin':
    PyInstaller.__main__.run([
        'dna.py',
        '-F',
        '--exclude-module',
        'numpy',
        '--hidden-import',
        'tkinter',
        '--hidden-import',
        'PIL',
        '--hidden-import',
        'PIL._tkinter_finder'
    ])
elif os.name == 'posix':
    PyInstaller.__main__.run([
        'dna.py',
        '-F',
        '--exclude-module',
        'numpy',
        '--hidden-import',
        'tkinter',
        '--hidden-import',
        'PIL',
        '--hidden-import',
        'PIL._tkinter_finder',
    ])
elif os.name == 'nt':
    PyInstaller.__main__.run([
        'dna.py',
        '-F',
        '--exclude-module',
        'numpy',
    ])
if os.name == 'nt':
    if os.path.exists(local + os.sep + "dist" + os.sep + "dna.exe"):
        shutil.move(local + os.sep + "dist" + os.sep + "dna.exe", local)
else:
    if os.path.exists(local + os.sep + "dist" + os.sep + "dna"):
        shutil.move(local + os.sep + "dist" + os.sep + "dna", local)
pclist = ['bin', 'etc', 'set', 'usr', 'temp', 'extra_flash.zip', 'setting.ini', ostype]
for i in os.listdir(local + os.sep + "local"):
    if i in pclist:
        continue
    else:
        if os.path.isdir(local + os.sep + "local" + os.sep + i):
            shutil.rmtree(local + os.sep + "local" + os.sep + i)
        else:
            os.remove(local + os.sep + "local" + os.sep + i)
for i in os.listdir(local + os.sep + "local"+os.sep+"bin"):
    if i in pclist:
        continue
    else:
        if os.path.isdir(local + os.sep + "local"+os.sep+"bin" + os.sep + i):
            shutil.rmtree(local + os.sep + "local"+os.sep+"bin" + os.sep + i)
        else:
            os.remove(local + os.sep + "local"+os.sep+"bin" + os.sep + i)
for i in os.listdir(local):
    if i not in ['dna', 'dna.exe', 'local', 'LICENSE']:
        print(f"Removing {i}")
        if os.path.isdir(local + os.sep + i):
            try:
                shutil.rmtree(local + os.sep + i)
            except Exception or OSError as e:
                print(e)
        elif os.path.isfile(local + os.sep + i):
            try:
                os.remove(local + os.sep + i)
            except Exception or OSError as e:
                print(e)
    else:
        print(i)
if os.name == 'posix':
    for root, dirs, files in os.walk(local, topdown=True):
        for i in files:
            print(f"Chmod {os.path.join(root, i)}")
            os.system(f"chmod a+x {os.path.join(root, i)}")

zip_folder(".")
