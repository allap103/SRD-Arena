# Rules Deviations

This document records intentional differences between SRD Arena mechanics and
the rules as written in SRD 5.2. These deviations reduce implementation
complexity or exclude situations outside the simulator's intended scope.

## Vampire Familiar Charmed Immunity

Rules as written, a Vampire Familiar is immune to the Charmed condition except
when Charmed by its vampire master.

SRD Arena treats the familiar as unconditionally immune to Charmed. The engine
does not model a Vampire Familiar fighting its own master, so representing the
exception would add source-sensitive immunity behavior without affecting an
intended encounter.

The normalized Vampire Familiar stat block therefore contains ordinary Charmed
immunity and omits the vampire-master exception.
