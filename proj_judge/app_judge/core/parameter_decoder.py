from typing import TypedDict


class ExerciseConcreteIdentity(TypedDict):
    agency_name: str
    agency_department_name: str
    exercise_concrete_name: str
    exercise_concrete_version: str
    exercise_concrete_directory_hash: str


def get_exercise_concrete_identity_from_request(
    request_param: dict,
) -> ExerciseConcreteIdentity:
    assert "agency_name" in request_param
    assert "agency_department_name" in request_param
    assert "exercise_concrete_name" in request_param
    assert "exercise_concrete_version" in request_param
    assert "exercise_concrete_directory_hash" in request_param

    agency_name = request_param["agency_name"]
    agency_department_name = request_param["agency_department_name"]
    exercise_concrete_name = request_param["exercise_concrete_name"]
    exercise_concrete_version = request_param["exercise_concrete_version"]
    exercise_concrete_directory_hash = request_param["exercise_concrete_directory_hash"]

    exercise_concrete_identity: ExerciseConcreteIdentity = {
        "agency_name": agency_name,
        "agency_department_name": agency_department_name,
        "exercise_concrete_name": exercise_concrete_name,
        "exercise_concrete_version": exercise_concrete_version,
        "exercise_concrete_directory_hash": exercise_concrete_directory_hash,
    }
    return exercise_concrete_identity
