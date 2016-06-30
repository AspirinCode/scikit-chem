#! /usr/bin/env python
#
# Copyright (C) 2016 Rich Lewis <rl403@cam.ac.uk>
# License: 3-clause BSD

"""
## skchem.standardizers.chemaxon

Module wrapping ChemAxon Standardizer.  Must have standardizer installed and
license activated.
"""

import os
import re
from tempfile import NamedTemporaryFile
import subprocess
import logging

logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd

from .. import core
from .. import io

# ideally we will programatically build this file, but for now just use it.
DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), 'default_config.xml')

class ChemAxonStandardizer(object):

    """ Object wrapping the ChemAxon Standardizer, for standardizing molecules.

    Args:
        config_path (str):
            The path of the config_file. If None, use the default one.

    Note:
        ChemAxon Standardizer must be installed and accessible as `standardize`
        from the shell launching the program.

    Warn:
        When using standardizer on smiles, it is currently unsupported if any
        of the compounds fail to subsequently parse.
    """
    def __init__(self, config_path=None, warn_on_fail=True, error_on_fail=False,
                    keep_failed=False):

        if not config_path:
            config_path = DEFAULT_CONFIG
        self.config_path = config_path
        self.keep_failed = keep_failed
        self.error_on_fail = error_on_fail
        self.warn_on_fail = warn_on_fail

    def transform(self, obj):

        """ Standardize compounds.

        Args:
            obj (str, skchem.Mol, pd.Series or pd.DataFrame):
                The object to standardize as either smiles as a string, Mol, or
                a series or dataframe of these. The object to standardize.

        Returns:
            skchem.Mol or pd.Series or pd.DataFrame:
                The standardized molecule, or molecules as a series or
                dataframe.
        """

        if isinstance(obj, core.Mol):
            return self._transform_mol(obj)
        elif isinstance(obj, pd.Series):
            return self._transform_ser(obj)
        elif isinstance(obj, pd.DataFrame):
            res = self._transform_ser(obj.structure)
            return res.to_frame(name='structure').join(obj.drop('structure', axis=1))

        else:
            raise NotImplementedError

    def _transform_mol(self, mol):
        mol = pd.DataFrame([mol], index=[mol.name], columns=['structure'])
        return self.transform(mol).structure.iloc[0]

    def _transform_mols(self, X, by='sdf'):

        with NamedTemporaryFile() as f_in, NamedTemporaryFile() as f_out:
            getattr(io, 'write_' + by)(X, f_in.name)
            errs = self._transform_file(f_in.name, f_out.name)
            out = io.read_sdf(f_out.name).structure
        return out, errs

    def _transform_smis(self, X):
        with NamedTemporaryFile() as f_in, NamedTemporaryFile() as f_out:
            X.to_csv(f_in.name, header=None, index=None)
            logger.debug('Input file length: %s', len(X))
            errs = self._transform_file(f_in.name, f_out.name)
            out = io.read_sdf(f_out.name).structure
            logger.debug('Output file length: %s', len(out))
        return out, errs

    def _transform_file(self, f_in, f_out):
        args = ['standardize', f_in,
                         '-c', self.config_path,
                         '-f', 'sdf',
                         '-o', f_out,
                         '--ignore-error']
        logger.debug('Running %s', ' '.join(args))
        sub = subprocess.Popen(args, stderr=subprocess.PIPE)
        errs = sub.stderr.read().decode('ascii')
        if len(errs):
            logger.debug('stderr from Standardizer: \n%s', errs)
            errs = errs.strip().split('\n')
            errs = [re.findall('No. ([0-9]+):', err) for err in errs]
            errs = [int(err[0]) - 1 for err in errs if len(err)]
        return errs

    def _transform_ser(self, X, y=None):

        # TODO: try using different serializations
        if isinstance(X.iloc[0], core.Mol):
            out, errs = self._transform_mols(X)
        elif isinstance(X.iloc[0], str):
            out, errs = self._transform_smis(X)
        if errs:
            out.index = X.index.delete(errs)
            for err in errs:
                err = X.index[err]
                if self.error_on_fail:
                    raise ValueError('{} failed to standardize'.format(err))
                if self.warn_on_fail:
                    logger.warn('%s failed to standardize', err)
        else:
            out.index = X.index
        if self.keep_failed:
            out_c = X.copy()
            out_c.loc[out.index] = out
            return out_c
        else:
            return out
