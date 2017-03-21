""" unit tests for simple_netem.emulations """
import os
import sys

import pytest

# modules under test are one directory up, make sure python can find them
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import emulations   # pylint:disable=F0401,C0413


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
        emulating = emulations.Emulation()
        emulating.emulation = emulation
        if defaults:
            emulating.validate_and_add(test_input, **defaults)
        else:
            emulating.validate_and_add(test_input)
        assert emulating.emulation == expected

    @pytest.mark.parametrize(
        'test_id,test_input,expect_in_error',
        [('raise_no_number', 'aa aaa', 'a measurement')])
    def test_validate_and_args_raises(
            self, test_id, test_input, expect_in_error):
        '''
        test that validate_and_add() method raises the proper exceptions
        '''
        emulating = emulations.Emulation()
        emulating.emulation = 'bogus'
        with pytest.raises(emulations.EmulationTypeError) as error:
            emulating.validate_and_add(test_input)

        assert expect_in_error in error.value.args[0]
