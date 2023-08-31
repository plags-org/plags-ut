import asyncio
import asyncio.subprocess
from typing import AsyncGenerator

import strawberry
from asgiref.sync import sync_to_async

from app_front.utils.parameter_decoder import get_organization_course_submission
from app_front.utils.time_util import get_current_datetime


@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "world"


@strawberry.type
class SubmissionEvaluation:
    # 0 := 課題が存在しない, 10 := 待機中, [11:90]: 実行中, 100 := 完了
    progress_percent: int


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def count(self, target: int = 100) -> AsyncGenerator[int, None]:
        for i in range(target):
            yield i
            await asyncio.sleep(0.5)

    @strawberry.subscription
    async def submissionEvaluation(
        self, organization_name: str, course_name: str, submission_eb64: str
    ) -> AsyncGenerator[SubmissionEvaluation, None]:
        # from asgiref.sync import async_to_sync, sync_to_async
        # from django.contrib.auth.decorators import login_required

        _organization, _course, submission = await sync_to_async(
            get_organization_course_submission
        )(
            **{
                "o_name": organization_name,
                "c_name": course_name,
                "s_eb64": submission_eb64,
            }
        )

        # 「進捗」の計算式
        # if not judge へ評価要求済み:
        #     return 1
        # if not judge から評価開始応答済み:
        #     return 10
        # if judge から評価完了応答済み:
        #     return 100
        # return 10 + min({judge への要求からの経過秒数} , 40) * 2

        while True:
            yield SubmissionEvaluation(progress_percent=1)
            # 評価が始まるまで待機
            await sync_to_async(submission.refresh_from_db)()
            if submission.evaluation_queued_at is not None:
                break
            await asyncio.sleep(1)

        # 評価が完了するまで待機（最大 40 秒）
        max_subscription_tick = 80
        respond_tick = 0.5
        for _ in range(max_subscription_tick):
            # 評価が完了したら離脱
            await sync_to_async(submission.refresh_from_db)()
            if submission.evaluated_at is not None:
                yield SubmissionEvaluation(progress_percent=100)
                break

            elapsed_second = (
                get_current_datetime() - submission.evaluation_queued_at
            ).seconds
            progress_percent = max(10, min(90, 10 + int(elapsed_second * 2)))
            yield SubmissionEvaluation(progress_percent=progress_percent)
            await asyncio.sleep(respond_tick)


schema = strawberry.Schema(query=Query, subscription=Subscription)
