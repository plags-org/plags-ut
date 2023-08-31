"""PLAGS の自動評価設定のスキーマ定義

# CHANGE LOG

- v1.0
  - initial release
"""
from typing import Dict, Final, Iterable, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel
from typing_extensions import TypeAlias

from judge_core.exercise_concrete.common.schema_type import (
    CustomStateName,
    String64,
    StringUrl64,
)

SCHEMA_VERSION: Final[str] = "v1.0"


class _SchemaBaseModel(BaseModel):
    # class Config:
    #     extra = "forbid"
    pass


################################################################################
# COMMON
################################################################################


################################################################################
# METADATA
################################################################################


class SettingExercise(_SchemaBaseModel):
    # 課題のシステム上での識別子
    name: StringUrl64
    # 課題のバージョン
    # - システム内部では、課題の各versionの最新版が、独立して保持される
    # 更新時の振る舞い:
    # - 既存の登録にないバージョン -> 新規にバージョンを登録し、最新版とする
    # - 既存の最新版のバージョン   -> 設定を上書きする
    # - 既存の非最新版のバージョン -> 更新（上書き）を拒絶する
    # NOTE 最後の振る舞いを実現するため、システムは内部的に、時系列とともに
    #      (name, version) のペアに対して登録された全ての版を内部で保持します。
    #      これは、複数の担当者が非同期的に更新作業を行った際に、
    #      意図しない設定のロールバックの発生を抑止するためです。
    #      もし過去のバージョンに巻き戻したくなったら、
    #      不要な改行を追加するなどして内容を少し改変してください。
    version: String64


################################################################################
# JUDGE
################################################################################


class SettingJudgePreprocess(_SchemaBaseModel):
    # 提出ファイル名の統一: judge 側でこれにrenameすることで、自動評価側でファイル名を固定できる
    rename: Optional[String64]


class SettingJudgeEnvironment(_SchemaBaseModel):
    # 環境名
    # - 環境はユーザーの要請に応じてシステム管理者が準備する
    name: String64
    # 環境のバージョン
    version: String64


class SettingJudgeSandboxFirejailOptions(_SchemaBaseModel):
    # CPU数制限
    cpu_limit: int  # e.g. 1
    # メモリ制限
    # - str: integer string with suffix (available: GiB, MiB, KiB, GB, MB, KB)
    # - int: bytes
    memory_limit: Union[str, int]  # e.g. '256MiB'
    # ネットワーク制限
    network_limit: str  # e.g. 'disable'
    # NOTE 今後増える可能性がある


class SettingJudgeSandboxNsJailOptions(_SchemaBaseModel):
    # CPU数制限
    cpu_limit: int  # e.g. 1
    # メモリ制限
    # - str: integer string with suffix (available: GiB, MiB, KiB, GB, MB, KB)
    # - int: bytes
    memory_limit: Union[str, int]  # e.g. '256MiB'
    # ネットワーク制限
    network_limit: str  # e.g. 'disable'
    # NOTE 今後増える可能性がある


class SettingJudgeSandbox(_SchemaBaseModel):
    # サンドボックス名
    # - サンドボックスはユーザーの要請に応じてシステム管理者が準備する
    # ATTENTION NsJail: CloudRun に移行前は Firejail 扱い、移行後は NsJail 扱いする
    name: Literal["Firejail", "NsJail"]  # 64文字以内
    # サンドボックスの種類別のオプション
    options: Union[SettingJudgeSandboxFirejailOptions, SettingJudgeSandboxNsJailOptions]


# CO や CS は単項述語と見做す
# NOTE これ以外にも必要に応じて追加
Status: TypeAlias = Literal["CS", "CO"]
Disjunction: TypeAlias = Iterable[Status]
# - forall: 旧 "only" に相当
# - exists: 現状使わない
Quantifier: TypeAlias = Literal["$forall", "$exists"]
# NOTE Disjunctionに限定する必要はないが今はこれで十分
QuantifiedPredicate: TypeAlias = Tuple[Quantifier, Disjunction]
TransitionCondition: TypeAlias = Union[Literal[True], QuantifiedPredicate]


class SettingJudgeEvaluationStateRunnerPythonUnittestExample(_SchemaBaseModel):
    # 評価時の振る舞い
    # - 'separate': 何も前処理をせずに「{{ 状態名}} .py」を呼び出す
    #   - ユーザーの記述したテストコードと同じディレクトリに提出物が配置されるため、 import が可能になる
    #   - ヒント: judge.preprocess.rename とともに利用せよ
    # - 'append': 「{{ 状態名}} .py」の先頭に提出されたソースコードを挿入してから呼び出す
    # 注意: いずれの設定でも、「{{ 状態名}} .py」の末尾には以下が挿入されて呼び出される:
    # ```python
    # import unittest
    # result = unittest.main(verbosity=2, exit=False, catchbreak=True, buffer=True).result
    # ```
    evaluation_style: Literal["separate", "append"]


class SettingJudgeEvaluationStateRunner(_SchemaBaseModel):
    # ランナー名
    name: String64  # e.g. 'test_runner_py37_unittest.py'
    # ランナーのバージョン
    version: String64  # e.g. ''
    # ランナー種類別のオプション
    options: SettingJudgeEvaluationStateRunnerPythonUnittestExample


class SettingJudgeEvaluationState(_SchemaBaseModel):
    # 評価を実行するスクリプト名
    runner: SettingJudgeEvaluationStateRunner
    # 実行時間制限
    # - str: integer string with suffix (available: m, s, ms, us)
    # - int: seconds
    time_limit: Union[str, int]  # e.g. 500ms
    # 評価に必要なファイルの設定
    required_files: Iterable[str]  # e.g. ('.judge/judge_util.py', )


Grade: TypeAlias = int

# e.g.
# [
#     [["precheck", ["pass"]], ["given", null]],
#     [["precheck", "otherwise"], ["$", 0]],
#     [["given", ["pass"]], ["hidden", null]],
#     [["given", "otherwise"], ["$", 0]],
#     [["hidden", ["pass"]], ["$", 2]],
#     [["hidden", "otherwise"], ["$", 1]],
# ]
StateOutcome: TypeAlias = Literal["pass"]
SettingJudgeEvaluationTransitionFunction: TypeAlias = List[
    Tuple[
        Tuple[CustomStateName, Union[List[StateOutcome], Literal["otherwise"]]],
        Tuple[Union[CustomStateName, Literal["$"]], Optional[Grade]],
    ]
]


class SettingJudgeEvaluation(_SchemaBaseModel):
    # 初期状態名
    initial_state: CustomStateName  # 64文字以内
    # 各状態の定義
    # - キー: 状態名
    # - 値: 状態の設定
    states: Dict[CustomStateName, SettingJudgeEvaluationState]
    # 評価指標の集約方法の設定
    transition_function: SettingJudgeEvaluationTransitionFunction


class SettingJudge(_SchemaBaseModel):
    # 提出物への前処理の設定
    preprocess: SettingJudgePreprocess
    # 自動評価を行う環境の設定
    environment: SettingJudgeEnvironment
    # 自動評価を行う際のサンドボックスの設定
    sandbox: SettingJudgeSandbox
    # 自動評価の状態遷移の設定
    evaluation: SettingJudgeEvaluation


################################################################################
# WHOLE
################################################################################


class Setting(_SchemaBaseModel):
    # 設定ファイルの形式バージョン (SCHEMA_VERSION)
    schema_version: Literal["v1.0"]
    # 課題全般の設定
    exercise: SettingExercise
    # 自動評価側で必要な設定
    judge: SettingJudge
