
import errno
import glob
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile


class DeodexException(Exception):
    ...


class RenamableTempFile(object):

    def __init__(self, *args, **kwargs):
        kwargs['delete'] = False
        self.file = tempfile.NamedTemporaryFile(*args, **kwargs)
        self.needs_unlink = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()
        if self.needs_unlink:
            os.unlink(self.file.name)

    def rename_and_disown(self, path):
        os.rename(self.file.name, path)
        self.needs_unlink = False


def is_deodexed(path):
    with zipfile.ZipFile(path) as z:
        try:
            z.getinfo('classes.dex')
            return True
        except KeyError:
            return False


def delete_file_and_empty_parents(path):
    os.unlink(path)
    for p in pathlib.Path(path).parents:
        try:
            os.rmdir(p)
        except OSError as e:
            if e.errno == errno.ENOTEMPTY or e.errno == errno.ENOENT:
                break
            raise


def find_optimized_files(path):
    file_path = pathlib.Path(path)
    files = glob.glob(str(file_path.parent / 'oat' / '*' / glob.escape(file_path.stem)) + '.*')
    if file_path.suffix == '.jar':
        files.extend(glob.glob(str(file_path.parent / '*' / ('boot-' + glob.escape(file_path.stem))) + '.*'))
        files.extend(glob.glob(str(file_path.parent / ('boot-' + glob.escape(file_path.stem))) + '.*'))
    known_extensions = ['.art', '.oat', '.odex', '.vdex']
    files_by_type = {}
    for f in files:
        extension = pathlib.Path(f).suffix
        if extension in known_extensions:
            files_by_type.setdefault(extension[1:], []).append(f)
    return files_by_type


def deodex_vdex(vdex, temp_dir):
    subprocess.run(['vdexExtractor', '-i', vdex, '-o', temp_dir, '-v', '2'], check=True)


def zipalign(path):
    if subprocess.run(['zipalign', '-c', '4', path]).returncode != 0:
        output_path = path + '.zipaligned'
        subprocess.run(['zipalign', '4', path, output_path], check=True)
        os.rename(output_path, path)


def add_dex_files_to_zip(zip_path, dex_dir, prefix):
    file_path = pathlib.Path(zip_path)
    with RenamableTempFile(dir=str(file_path.parent), prefix=str(file_path.name) + '.') as t:
        with open(zip_path, 'rb') as f:
            shutil.copyfileobj(f, t.file)
        t.file.seek(0)
        with zipfile.ZipFile(t.file, 'a', compression=zipfile.ZIP_DEFLATED) as z:
            for p in os.scandir(dex_dir):
                if not p.name.startswith(prefix):
                    raise DeodexException('Found unknown file in dex dir: ' + p.name)
                z.write(pathlib.Path(dex_dir) / p.name, arcname=p.name[len(prefix):])
        t.rename_and_disown(zip_path)
    zipalign(zip_path)


def deodex_file(path):
    optimized_files = find_optimized_files(path)
    if not is_deodexed(path):
        if optimized_files:
            if 'vdex' not in optimized_files:
                raise DeodexException('No vdex files found for: ' + path)
            with tempfile.TemporaryDirectory() as temp_dir:
                used_vdex = None
                fail_info = None
                for vdex in optimized_files['vdex']:
                    try:
                        deodex_vdex(vdex, temp_dir)
                        used_vdex = vdex
                        fail_info = None
                        break
                    except Exception as e:
                        fail_info = (vdex, e)
                if fail_info:
                    raise DeodexException('Failed to extract vdex: ' + fail_info[0]) from fail_info[1]
                prefix = pathlib.Path(used_vdex).stem + '.apk_'
                try:
                    add_dex_files_to_zip(path, temp_dir, prefix)
                except:
                    subprocess.run(['ls', temp_dir])
                    raise
    for t in optimized_files:
        for f in optimized_files[t]:
            delete_file_and_empty_parents(f)


def deodex(sysroot):
    failed = []
    for root, _, files in os.walk(sysroot):
        for f in files:
            full_path = str(pathlib.Path(root) / f)
            if f.endswith('.apk') or f.endswith('.jar'):
                print(f'Processing: {full_path}')
                try:
                    deodex_file(full_path)
                except DeodexException:
                    traceback.print_exc()
                    failed.append(full_path)
            elif f == 'boot.art' or f == 'boot.oat' or f == 'boot.vdex':
                delete_file_and_empty_parents(full_path)
    if failed:
        print('Failed to deodex:', file=sys.stderr)
        for f in failed:
            print(f'- {f}', file=sys.stderr)
        return False
    else:
        return True
