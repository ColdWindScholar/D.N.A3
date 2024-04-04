#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ====================================================
#          FILE: img2sdat.py
#       AUTHORS: xpirt - luxi78 - howellzhu
#          DATE: 2018-05-25 12:19:12 CEST
# ====================================================

from __future__ import print_function

import os
import tempfile

import blockimgdiff
import sparse_img


def main(INPUT_IMAGE, OUTDIR='.', VERSION=None, PREFIX='system'):
    global input

    __version__ = '1.7'

    print('img2sdat binary - version: %s\n' % __version__)

    if not os.path.isdir(OUTDIR):
        os.makedirs(OUTDIR)

    OUTDIR = OUTDIR + '/' + PREFIX

    if not VERSION:
        VERSION = 4
        while True:
            print('''            1. Android Lollipop 5.0
            2. Android Lollipop 5.1
            3. Android Marshmallow 6.0
            4. Android Nougat 7.0/7.1/8.0/8.1
            ''')
            item = input('Choose system version: ')
            if item == '1':
                VERSION = 1
                break
            elif item == '2':
                VERSION = 2
                break
            elif item == '3':
                VERSION = 3
                break
            elif item == '4':
                VERSION = 4
                break
            else:
                return

    # Get sparse image
    image = sparse_img.SparseImage(INPUT_IMAGE, tempfile.mkstemp()[1], '0')

    # Generate output files
    b = blockimgdiff.BlockImageDiff(image, None, VERSION)
    b.Compute(OUTDIR)

    print('Done! Output files: %s' % os.path.dirname(OUTDIR))
