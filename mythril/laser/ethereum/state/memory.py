"""This module contains a representation of a smart contract's memory."""
from copy import copy
from typing import cast, List, Union, overload
from z3 import Z3Exception

from mythril.laser.ethereum import util
from mythril.laser.smt import (
    BitVec,
    Bool,
    Concat,
    Extract,
    If,
    simplify,
    symbol_factory,
)


def convert_bv(val: Union[int, BitVec]) -> BitVec:
    if isinstance(val, BitVec):
        return val
    return symbol_factory.BitVecVal(val, 256)


class Memory:
    """A class representing contract memory with random access."""

    def __init__(self):
        """"""
        self._msize = 0
        self._memory = {}

    def __len__(self):
        """

        :return:
        """
        return self._msize

    def __copy__(self):
        new_memory = Memory()
        new_memory._memory = copy(self._memory)
        new_memory._msize = self._msize
        return new_memory

    def extend(self, size: int):
        """

        :param size:
        """
        self._msize += size

    def get_word_at(self, index: int) -> Union[int, BitVec]:
        """Access a word from a specified memory index.

        :param index: integer representing the index to access
        :return: 32 byte word at the specified index
        """
        try:
            return symbol_factory.BitVecVal(
                util.concrete_int_from_bytes(
                    bytes([util.get_concrete_int(b) for b in self[index : index + 32]]),
                    0,
                ),
                256,
            )
        except TypeError:
            result = simplify(
                Concat(
                    [
                        b if isinstance(b, BitVec) else symbol_factory.BitVecVal(b, 8)
                        for b in cast(
                            List[Union[int, BitVec]], self[index : index + 32]
                        )
                    ]
                )
            )
            assert result.size() == 256
            return result

    def write_word_at(self, index: int, value: Union[int, BitVec, bool, Bool]) -> None:
        """Writes a 32 byte word to memory at the specified index`

        :param index: index to write to
        :param value: the value to write to memory
        """
        try:
            # Attempt to concretize value
            if isinstance(value, bool):
                _bytes = (
                    int(1).to_bytes(32, byteorder="big")
                    if value
                    else int(0).to_bytes(32, byteorder="big")
                )
            else:
                _bytes = util.concrete_int_to_bytes(value)
            assert len(_bytes) == 32
            self[index : index + 32] = list(bytearray(_bytes))
        except (Z3Exception, AttributeError):  # BitVector or BoolRef
            value = cast(Union[BitVec, Bool], value)
            if isinstance(value, Bool):
                value_to_write = If(
                    value,
                    symbol_factory.BitVecVal(1, 256),
                    symbol_factory.BitVecVal(0, 256),
                )
            else:
                value_to_write = value
            assert value_to_write.size() == 256

            for i in range(0, value_to_write.size(), 8):
                self[index + 31 - (i // 8)] = Extract(i + 7, i, value_to_write)

    @overload
    def __getitem__(self, item: int) -> Union[int, BitVec]:
        ...

    @overload
    def __getitem__(self, item: slice) -> List[Union[int, BitVec]]:
        ...

    def __getitem__(
        self, item: Union[int, slice]
    ) -> Union[BitVec, int, List[Union[int, BitVec]]]:
        """

        :param item:
        :return:
        """
        if isinstance(item, slice):
            start, step, stop = item.start, item.step, item.stop
            if start is None:
                start = 0
            if stop is None:  # 2**256 is just a bit too big
                raise IndexError("Invalid Memory Slice")
            if step is None:
                step = 1
            start, stop, step = convert_bv(start), convert_bv(stop), convert_bv(step)
            ret_lis = []
            itr = symbol_factory.BitVecVal(0, 256)
            while simplify(start + itr != stop) and itr <= 10000000:
                ret_lis.append(self[start + step * itr])
                itr += 1

            return ret_lis

        item = simplify(convert_bv(item))
        return self._memory.get(item, 0)

    def __setitem__(
        self,
        key: Union[int, slice],
        value: Union[BitVec, int, List[Union[int, BitVec]]],
    ):
        """

        :param key:
        :param value:
        """
        if isinstance(key, slice):
            start, step, stop = key.start, key.step, key.stop

            if start is None:
                start = 0
            if stop is None:
                raise IndexError("Invalid Memory Slice")
            if step is None:
                step = 1
            else:
                assert False, "Currently mentioning step size is not supported"
            assert type(value) == list
            start, stop, step = convert_bv(start), convert_bv(stop), convert_bv(step)
            itr = symbol_factory.BitVecVal(0, 256)
            while simplify(start + itr != stop) and itr <= 10000000:
                self[start + itr] = value[itr.value]
                itr += 1

        else:
            key = simplify(convert_bv(key))
            if key >= len(self):
                return
            if isinstance(value, int):
                assert 0 <= value <= 0xFF
            if isinstance(value, BitVec):
                assert value.size() == 8
            self._memory[key] = cast(Union[int, BitVec], value)
