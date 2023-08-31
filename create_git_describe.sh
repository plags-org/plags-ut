#!/bin/bash

echo -e "Release on $(date -Isec)\n" > current_git_describe.txt
git show $(git rev-parse HEAD) --quiet --date=iso >> current_git_describe.txt
