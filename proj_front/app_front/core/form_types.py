import dataclasses


@dataclasses.dataclass
class ExerciseConcreteIdentity:
    name: str
    version: str
    concrete_hash: str
