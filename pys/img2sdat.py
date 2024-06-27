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
from pys import blockimgdiff
from pys import sparse_img


def main(INPUT_IMAGE, OUTDIR='.', VERSION=None, PREFIX='system'):
    __version__ = '1.7'
    print('img2sdat binary - version: %s\n' % __version__)

    if not os.path.isdir(OUTDIR):
        os.makedirs(OUTDIR)

    OUTDIR = OUTDIR + '/' + PREFIX

    blockimgdiff.BlockImageDiff(sparse_img.SparseImage(INPUT_IMAGE, tempfile.mkstemp()[1], '0'), None, VERSION).Compute(
        OUTDIR)

    print('Done! Output files: %s' % os.path.dirname(OUTDIR))
