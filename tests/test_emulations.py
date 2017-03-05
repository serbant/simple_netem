import os
import sys

import pytest

# modules under test are one directory up, make sure python can find them
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import emulations


class TestEmulation(object):
    '''
    test class for :class:`<emulations._Emulation>`
    '''
    @pytest.mark.parametrize(
        'test_id,emulation,test_input,defaults,expected',
        [('integer, use defaults', 'test', '66', None, 'test 66.0'),
         ('integer, positive False', 'test', '-66',
          dict(positive=False), 'test -66.0'),
         ('integer, lt_100 False', 'test', '666',
          dict(lt_100=False), 'test 666.0'), ])
    def test_validate_and_add(
            self, test_id, emulation, test_input, defaults, expected):
        '''
        test the validate_and_arg() method on happy paths

        '''
        emulating = emulations._Emulation()
        emulating.emulation = emulation
        if defaults:
            emulating.validate_and_add(test_input, **defaults)
        else:
            emulating.validate_and_add(test_input)
        assert emulating.emulation == expected
