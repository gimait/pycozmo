"""

AudioKinetic WWise SoundBank representation and reading.

References:
    - http://wiki.xentax.com/index.php/Wwise_SoundBank_(*.bnk)
    - https://github.com/rickvg/Wwise-BNKExtract

"""

from typing import BinaryIO, Iterable
import struct
from chunk import Chunk

from . import exception


class File:
    """ AudioKinetic WWise WEM File. """

    __slots__ = [
        "soundbank_id",
        "id",
        "offset",
        "length",
    ]

    def __init__(self, soundbank_id: int, file_id: int, offset: int, length: int) -> None:
        # SoundBank ID.
        self.soundbank_id = int(soundbank_id)
        # File ID.
        self.id = int(file_id)
        # Offset from start of DATA chunk.
        self.offset = int(offset)
        # Length in bytes.
        self.length = int(length)


class SFX:
    """ AudioKinetic WWise sound effect/voice. """

    __slots__ = [
        "soundbank_id",
        "id",
        "location",
        "file_id",
        "length",
        "type",
    ]

    def __init__(self, soundbank_id: int, sfx_id: int, location: int, file_id: int, length: int, sfx_type: int) -> None:
        # SoundBank ID.
        self.soundbank_id = int(soundbank_id)
        # SFX ID.
        self.id = int(sfx_id)
        # Location.
        #   - 0: "embedded"
        #       - the file is in the SoundBank
        #       - length is the same as in DIDX
        #   - 1: "streamed"
        #       - the file is in the SoundBank
        #       - length is the same as in DIDX
        #   - 2: "streamed, zero latency"
        #       - the file is in the file-system as .wem
        #       - length does not match file size?
        self.location = int(location)
        # File ID.
        self.file_id = int(file_id)
        # Length in bytes.
        self.length = int(length)
        # Type:
        #   - 0: SFX
        #   - 1: voice
        self.type = int(sfx_type)


class EventAction:
    """ AudioKinetic WWise Event Action. """

    __slots__ = [
        "soundbank_id",
        "id",
        "scope",
        "type",
        "reference_id"
    ]

    def __init__(self, soundbank_id: int, ea_id: int, scope: int, ea_type: int, reference_id: int) -> None:
        # SoundBank ID.
        self.soundbank_id = int(soundbank_id)
        # Event action ID.
        self.id = int(ea_id)
        # Scope.
        self.scope = int(scope)
        # Event action ID.
        self.type = int(ea_type)
        # Event action ID.
        self.reference_id = int(reference_id)


class Event:
    """ AudioKinetic WWise Event. """

    __slots__ = [
        "soundbank_id",
        "id",
        "action_ids"
    ]

    def __init__(self, soundbank_id: int, event_id: int, action_ids: Iterable[int]) -> None:
        # SoundBank ID.
        self.soundbank_id = int(soundbank_id)
        # Event ID.
        self.id = int(event_id)
        # Action IDs.
        self.action_ids = action_ids


class SoundBank:
    """ AudioKinetic WWise SoundBank (.bnk) file representation class. """

    __slots__ = [
        "fspec",
        "id",
        "version",
        "data_offset",
        "objs",
    ]

    def __init__(self) -> None:
        # File specification.
        self.fspec = ""
        # SoundBank ID.
        self.id = -1
        # SoundBank version.
        self.version = -1
        # DATA chunk start offset for loading WEM files.
        self.data_offset = -1
        # Object dictionary (ID -> File/SFX/EventAction/Event).
        self.objs = {}


class SoundBankReader:

    def __init__(self):
        self.soundbank = None

    @staticmethod
    def _read_uint8(chunk: Chunk) -> int:
        """ Read uint8 value from chunk. """
        return struct.unpack('B', chunk.read(1))[0]

    @staticmethod
    def _read_uint32(chunk: Chunk) -> int:
        """ Read uint32 value from chunk. """
        return struct.unpack('<L', chunk.read(4))[0]

    def _read_header(self, f: BinaryIO) -> None:
        """ Read Bank Header (BKHD) chunk. """
        chunk = Chunk(f, bigendian=False, align=False)
        if chunk.getname() != b"BKHD":
            raise exception.AudioKineticFormatError("Not an AudioKinetic WWise SoundBank file.")
        self.soundbank.version = self._read_uint32(chunk)
        self.soundbank.id = self._read_uint32(chunk)
        # There are additional 6 unknown uint32 values.
        chunk.skip()

    def _read_data_index(self, chunk: Chunk) -> None:
        """ Read Data Index (DIDX) chunk."""
        num_objects = chunk.getsize() // 12
        for i in range(num_objects):
            file_id, offset, length = struct.unpack("<LLL", chunk.read(12))
            assert file_id
            assert length
            assert file_id not in self.soundbank.objs
            self.soundbank.objs[file_id] = File(self.soundbank.id, file_id, offset, length)

    def _read_hirc(self, chunk: Chunk) -> None:
        """ Read HIRC chunk. """
        num_objects = self._read_uint32(chunk)
        for i in range(num_objects):
            object_type, object_len, object_id = struct.unpack("<BLL", chunk.read(9))
            assert object_id
            assert object_type
            assert object_len
            object_len -= 4
            obj_data = chunk.read(object_len)
            if object_type == 2:
                # Sound effect/voice
                _, location, file_id, length, sfx_type = struct.unpack_from('<LBLLL', obj_data)
                assert location in (0, 1, 2)
                assert file_id
                assert sfx_type in (0, 1)
                assert object_id not in self.soundbank.objs
                self.soundbank.objs[object_id] = SFX(
                    self.soundbank.id, object_id, location, file_id, length, sfx_type)
            elif object_type == 3:
                # Event Action
                act_scope, act_type, reference_id, zero = struct.unpack_from('<BBLB', obj_data)
                assert act_scope in (1, 2, 3, 4, 8)
                assert act_type in (1, 2, 3, 4, 18, 19, 25, 30, 33)
                assert zero == 0
                assert object_id not in self.soundbank.objs
                self.soundbank.objs[object_id] = EventAction(
                    self.soundbank.id, object_id, act_scope, act_type, reference_id)
            elif object_type == 4:
                # Event
                action_ids = []
                num_act_ids = struct.unpack_from('<L', obj_data)[0]
                for j in range(num_act_ids):
                    action_id = struct.unpack_from('<L', obj_data, 4 + j * 4)[0]
                    assert action_id
                    action_ids.append(action_id)
                assert object_id not in self.soundbank.objs
                self.soundbank.objs[object_id] = Event(
                    self.soundbank.id, object_id, action_ids)
            else:
                # Skip unknown objects.
                pass

    def load_file(self, f: BinaryIO, fspec: str) -> SoundBank:
        """ Load a SoundBank .bnk file object and return a SoundBank object. """

        self.soundbank = SoundBank()
        self.soundbank.fspec = fspec

        # Read header.
        try:
            self._read_header(f)
        except (EOFError, OSError, ValueError, RuntimeError) as e:
            raise exception.AudioKineticIOError("Failed to read SoundBank file header.") from e

        # Read subsequent chunks.
        while True:
            try:
                chunk = Chunk(f, bigendian=False, align=False)
                chunkname = chunk.getname()
                if chunkname == b"DIDX":
                    self._read_data_index(chunk)
                elif chunkname == b"DATA":
                    self.soundbank.data_offset = f.tell()
                elif chunkname == b"HIRC":
                    self._read_hirc(chunk)
                else:
                    # Skip other unknown chunks (e.g. INIT, STMG, ENVS, PLAT).
                    pass
                chunk.skip()
            except EOFError:
                # Reached end of file.
                break
            except (OSError, ValueError, RuntimeError) as e:
                raise exception.AudioKineticIOError("Failed reading SoundBank file.") from e

        return self.soundbank

    def load(self, fspec: str) -> SoundBank:
        """ Load a SoundBank .bnk file and return a SoundBank object. """
        with open(fspec, "rb") as f:
            return self.load_file(f, fspec)
