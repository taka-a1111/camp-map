#!/usr/bin/env bash
# 自動処理で作ったデータをコミットして main に push する（GitHub Actions 用）。
#
# 使い方: bash scripts/commit_push.sh "コミットメッセージ" ファイル1 ファイル2 ...
#
# 複数の自動処理が同じ時間帯に動くと、push の前に main が先に進んでいて
# 取り込み（rebase）で衝突することがある。ここで扱うファイルはどれも自動生成の
# データなので、衝突したファイルは「この処理で作った版」を丸ごと採用して先に進める。
# （他方の更新内容は、次にその処理が動いたときに作り直される）
set -u

msg="$1"
shift

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

# 存在するファイルだけを対象にする（1つでも無いと git add 全体が失敗するため）
for f in "$@"; do
  if [ -e "$f" ]; then git add -- "$f"; fi
done
if git diff --cached --quiet; then
  echo "変更なし"
  exit 0
fi
git commit -q -m "$msg"

for i in 1 2 3 4 5; do
  git fetch -q origin main
  if ! git rebase origin/main; then
    conflicted=$(git diff --name-only --diff-filter=U)
    echo "::warning::main と衝突したため、この処理で作った版を採用します: ${conflicted}"
    for f in $conflicted; do
      # rebase 中の --theirs は「いま載せ直しているこの処理のコミット側」
      git checkout --theirs -- "$f"
      git add -- "$f"
    done
    if ! GIT_EDITOR=true git rebase --continue; then
      # 採用した結果が main と同じになった（載せる変更が無い）場合
      git rebase --skip || { git rebase --abort; echo "::error::取り込みに失敗しました"; exit 1; }
    fi
  fi
  if git push origin HEAD:main; then
    echo "push 完了"
    exit 0
  fi
  echo "push に失敗（${i}回目）。少し待って取り込み直します"
  sleep $((i * 15))
done

echo "::error::5回試しても push できませんでした"
exit 1
